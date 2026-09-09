"""Adaptador de FinMind (nivel gratuito, sin token): descarga a ``RawStore`` y lectura tipada.

- ``TaiwanStockInfo``: catálogo con tipo (twse/tpex/emerging) e industria; sirve
  para clasificar instrumentos (ETF, ETN, DR, índice) que el censo oficial no marca.
- ``TaiwanStockPrice``: barras diarias **nominales** (el laboratorio no usa ajustadas).
- ``TaiwanStockDividend``: dividendos con fecha de anuncio y hora, fecha ex y fecha de pago.

Todo lo descargado se archiva tal cual con ``ingested_at`` real; la
disponibilidad histórica de estos datos es ``conservative_inference`` o
``unknown`` según el campo (ver informe 02).
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
    "存託憑證": "dr", "受益證券": "beneficiary_certificate", "Index": "index", "所有證券": "aggregate",
}
BOARD_CATEGORIES = {"創新板股票": "innovation", "創新版股票": "innovation"}


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
    """symbol → instrument_type, symbol → board, symbol → market (twse/tpex/emerging)."""
    instrument: dict[str, str] = {}
    board: dict[str, str] = {}
    market: dict[str, str] = {}
    for r in info_rows:
        sid = str(r["stock_id"]).strip()
        cat = str(r.get("industry_category", "")).strip()
        market[sid] = str(r.get("type", "")).strip()
        if cat in NON_EQUITY_CATEGORIES:
            instrument[sid] = NON_EQUITY_CATEGORIES[cat]
        elif cat in BOARD_CATEGORIES:
            instrument.setdefault(sid, "ordinary_equity")
            board[sid] = BOARD_CATEGORIES[cat]
        else:
            instrument.setdefault(sid, "ordinary_equity")
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


def bars_from_rows(price_rows: Iterable[dict]) -> list[Bar]:
    out: list[Bar] = []
    for r in price_rows:
        d = date.fromisoformat(r["date"])
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
    announced_at: Optional[datetime]      # AnnouncementDate + AnnouncementTime (Taipei)
    cash_per_share: Decimal               # CashEarningsDistribution + CashStatutorySurplus
    stock_per_share: Decimal              # StockEarningsDistribution + StockStatutorySurplus (acciones por acción)
    cash_ex_date: Optional[date]
    cash_pay_date: Optional[date]
    stock_ex_date: Optional[date]
    period: str


def dividends_from_rows(div_rows: Iterable[dict]) -> list[DividendRow]:
    out: list[DividendRow] = []
    for r in div_rows:
        ann = None
        if r.get("AnnouncementDate"):
            try:
                hh, mm, ss = (r.get("AnnouncementTime") or "00:00:00").split(":")
                ann = datetime.combine(date.fromisoformat(r["AnnouncementDate"]), datetime.min.time(), tzinfo=TAIPEI)
                ann = ann.replace(hour=int(hh), minute=int(mm), second=int(ss))
            except ValueError:
                ann = None

        def _d(key: str) -> Optional[date]:
            v = r.get(key)
            return date.fromisoformat(v) if v else None

        out.append(DividendRow(
            stock_id=str(r["stock_id"]), announced_at=ann,
            cash_per_share=Decimal(str(r.get("CashEarningsDistribution") or 0)) + Decimal(str(r.get("CashStatutorySurplus") or 0)),
            stock_per_share=Decimal(str(r.get("StockEarningsDistribution") or 0)) + Decimal(str(r.get("StockStatutorySurplus") or 0)),
            cash_ex_date=_d("CashExDividendTradingDate"), cash_pay_date=_d("CashDividendPaymentDate"),
            stock_ex_date=_d("StockExDividendTradingDate"), period=str(r.get("year", "")),
        ))
    return out
