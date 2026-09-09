"""Adaptador de FinMind (nivel gratuito, sin token): descarga a ``RawStore`` y lectura tipada.

- ``TaiwanStockInfo``: catálogo con tipo (twse/tpex/emerging) e industria; sirve
  para clasificar instrumentos (ETF, ETN, DR, índice) que el censo oficial no marca.
- ``TaiwanStockPrice``: barras diarias **nominales** (el laboratorio no usa ajustadas).
- ``TaiwanStockDividend``: dividendos con fecha de anuncio y hora, fecha ex y fecha de pago.

Todo lo descargado se archiva tal cual con ``ingested_at`` real; la
disponibilidad histórica de estos datos es ``conservative_inference`` o
``unknown`` según el campo (ver informe 02). La lectura tipada exige el
``stock_id`` esperado (R08-06) y rechaza fechas repetidas (R08-07): una
revisión de FinMind no es una sesión nueva.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Iterable, Optional

import requests

from ..store import CaptureRecord, RawStore
from ..timeutil import TAIPEI, taipei

BASE = "https://api.finmindtrade.com/api/v4/data"
HEADERS = {"User-Agent": "taiwan-ia-lab/0.1 (private research)", "Accept": "application/json"}
PRICE_AVAILABILITY_LAG = timedelta(hours=24)   # política declarada: barra de la sesión D disponible en cierre(D) + 24 h

# categorías de FinMind que NO son acciones ordinarias (se excluyen del universo simulable)
NON_EQUITY_CATEGORIES = {
    "ETF": "etf", "上櫃ETF": "etf", "上櫃指數股票型基金(ETF)": "etf", "ETN": "etn", "指數投資證券(ETN)": "etn",
    "存託憑證": "dr", "受益證券": "beneficiary_certificate", "Index": "index", "所有證券": "aggregate", "大盤": "aggregate",
}
BOARD_CATEGORIES = {"創新板股票": "innovation", "創新版股票": "innovation"}
# industrias observadas en el catálogo capturado el 9-09-2026 para acciones ordinarias. Una categoría que no esté aquí
# ni en las tablas anteriores NO se supone acción ordinaria: queda ``unclassified`` y fuera del universo (R08-04).
EQUITY_INDUSTRY_CATEGORIES = frozenset({
    "光電業", "其他", "其他電子業", "其他電子類", "化學工業", "化學生技醫療", "半導體業", "塑膠工業", "居家生活", "居家生活類",
    "建材營造", "數位雲端", "數位雲端類", "文化創意業", "橡膠工業", "水泥工業", "汽車工業", "油電燃氣業", "玻璃陶瓷", "生技醫療業",
    "紡織纖維", "綠能環保", "綠能環保類", "航運業", "觀光事業", "觀光餐旅", "貿易百貨", "資訊服務業", "農業科技", "農業科技業",
    "通信網路業", "造紙工業", "運動休閒", "運動休閒類", "金融保險", "金融業", "鋼鐵工業", "電器電纜", "電子商務業", "電子工業",
    "電子通路業", "電子零組件業", "電機機械", "電腦及週邊設備業", "食品工業",
})
# precedencia al clasificar un símbolo con varias filas: un tipo concreto no accionarial gana siempre (exclusión
# conservadora); «aggregate» e «index» son agrupaciones, no instrumentos, y sólo se usan si no hay nada más.
_INSTRUMENT_PRECEDENCE = ("etf", "etn", "dr", "beneficiary_certificate", "ordinary_equity", "index", "aggregate", "unclassified")


class SourceIdentityMismatch(ValueError):
    pass


class DuplicateSession(ValueError):
    pass


def fetch(store: RawStore, dataset: str, *, data_id: Optional[str] = None, start_date: Optional[str] = None,
          end_date: Optional[str] = None, pause_s: float = 1.0) -> CaptureRecord:
    params = {"dataset": dataset}
    if data_id:
        params["data_id"] = data_id
    if start_date:
        params["start_date"] = start_date
    if end_date:
        params["end_date"] = end_date
    r = requests.get(BASE, params=params, headers=HEADERS, timeout=90)
    rec = store.put(source_id="finmind", dataset=f"{dataset}/{data_id}" if data_id else dataset, payload=r.content,
                    url=r.url, http_status=r.status_code, content_type=r.headers.get("Content-Type"),
                    extra={"start_date": start_date, "end_date": end_date})
    time.sleep(pause_s)
    return rec


def rows(store: RawStore, rec: CaptureRecord) -> list[dict]:
    body = json.loads(store.read(rec).decode("utf-8"))
    if body.get("status") != 200 or body.get("msg") != "success":
        raise ValueError(f"FinMind capture {rec.capture_id} is not a success payload: {body.get('msg')}")
    return body.get("data", [])


def classify_info(info_rows: Iterable[dict]) -> tuple[dict[str, str], dict[str, str], dict[str, str]]:
    """symbol → instrument_type, symbol → board, symbol → market (twse/tpex/emerging).

    FinMind repite un símbolo en varias categorías (industria principal, secundarias,
    ``所有證券``). El resultado no depende del orden de las filas: se reúnen todas las
    categorías y se aplica ``_INSTRUMENT_PRECEDENCE``. Una categoría vacía o desconocida
    nunca se supone acción ordinaria (R08-04).
    """
    cats: dict[str, set[str]] = {}
    market: dict[str, str] = {}
    for r in info_rows:
        sid = str(r["stock_id"]).strip()
        cats.setdefault(sid, set()).add(str(r.get("industry_category", "")).strip())
        market.setdefault(sid, str(r.get("type", "")).strip())
    instrument: dict[str, str] = {}
    board: dict[str, str] = {}
    for sid, cs in cats.items():
        kinds: set[str] = set()
        for c in cs:
            if c in NON_EQUITY_CATEGORIES:
                kinds.add(NON_EQUITY_CATEGORIES[c])
            elif c in EQUITY_INDUSTRY_CATEGORIES or c in BOARD_CATEGORIES:
                kinds.add("ordinary_equity")
            else:
                kinds.add("unclassified")
        instrument[sid] = next(k for k in _INSTRUMENT_PRECEDENCE if k in kinds)
        if any(c in BOARD_CATEGORIES for c in cs):
            board[sid] = "innovation"
    return instrument, board, market


@dataclass(frozen=True)
class Bar:
    session: date
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume_shares: int
    value_twd: Decimal
    transactions: int
    available_at: datetime     # política PRICE_AVAILABILITY_LAG sobre el cierre 13:30 Taipei

    @property
    def has_regular_price(self) -> bool:
        """FinMind publica OHLC a cero cuando no hubo precio de sesión regular; puede haber importe y volumen
        (negociación de lotes menores u otras). Sin precio regular no hay ejecución ni valoración (R08-12)."""
        return self.open > 0 and self.close > 0


def bars_from_rows(price_rows: Iterable[dict], *, stock_id: str) -> list[Bar]:
    """Barras de una captura ``TaiwanStockPrice/<stock_id>``; toda fila debe pertenecer a ese ``stock_id``."""
    out: list[Bar] = []
    seen: set[date] = set()
    for r in price_rows:
        sid = str(r.get("stock_id", "")).strip()
        if sid != stock_id:
            raise SourceIdentityMismatch(f"row stock_id={sid!r} does not belong to {stock_id!r}")
        d = date.fromisoformat(r["date"])
        if d in seen:
            raise DuplicateSession(f"{stock_id}: repeated session {d.isoformat()}; revisions must be resolved upstream, not counted twice")
        seen.add(d)
        close_at = taipei(d).replace(hour=13, minute=30)
        out.append(Bar(
            session=d, open=Decimal(str(r["open"])), high=Decimal(str(r["max"])), low=Decimal(str(r["min"])),
            close=Decimal(str(r["close"])), volume_shares=int(r["Trading_Volume"]), value_twd=Decimal(str(r["Trading_money"])),
            transactions=int(r["Trading_turnover"]), available_at=close_at + PRICE_AVAILABILITY_LAG,
        ))
    out.sort(key=lambda b: b.session)
    return out


@dataclass(frozen=True)
class DividendRow:
    stock_id: str
    announced_date: Optional[date]        # AnnouncementDate; sin hora no es un instante (R08-03)
    announced_at: Optional[datetime]      # AnnouncementDate + AnnouncementTime (Taipei) sólo cuando la hora existe
    cash_per_share: Decimal               # CashEarningsDistribution + CashStatutorySurplus
    stock_per_share: Decimal              # StockEarningsDistribution + StockStatutorySurplus (TWD de valor nominal por acción)
    cash_ex_date: Optional[date]
    cash_pay_date: Optional[date]
    stock_ex_date: Optional[date]
    period: str


def dividends_from_rows(div_rows: Iterable[dict], *, stock_id: str) -> list[DividendRow]:
    out: list[DividendRow] = []
    for r in div_rows:
        sid = str(r.get("stock_id", "")).strip()
        if sid != stock_id:
            raise SourceIdentityMismatch(f"row stock_id={sid!r} does not belong to {stock_id!r}")
        ann_date: Optional[date] = None
        ann_at: Optional[datetime] = None
        if r.get("AnnouncementDate"):
            try:
                ann_date = date.fromisoformat(str(r["AnnouncementDate"]))
            except ValueError:
                ann_date = None
            t = str(r.get("AnnouncementTime") or "").strip()
            if ann_date is not None and t:
                try:
                    hh, mm, ss = t.split(":")
                    ann_at = datetime.combine(ann_date, datetime.min.time(), tzinfo=TAIPEI).replace(hour=int(hh), minute=int(mm), second=int(ss))
                except ValueError:
                    ann_at = None          # hora ilegible: se conserva la fecha, no se inventa el instante

        def _d(key: str) -> Optional[date]:
            v = r.get(key)
            return date.fromisoformat(v) if v else None

        out.append(DividendRow(
            stock_id=sid, announced_date=ann_date, announced_at=ann_at,
            cash_per_share=Decimal(str(r.get("CashEarningsDistribution") or 0)) + Decimal(str(r.get("CashStatutorySurplus") or 0)),
            stock_per_share=Decimal(str(r.get("StockEarningsDistribution") or 0)) + Decimal(str(r.get("StockStatutorySurplus") or 0)),
            cash_ex_date=_d("CashExDividendTradingDate"), cash_pay_date=_d("CashDividendPaymentDate"),
            stock_ex_date=_d("StockExDividendTradingDate"), period=str(r.get("year", "")),
        ))
    return out
