"""Cotizaciones diarias oficiales por fecha (todas las acciones): TWSE ``MI_INDEX`` y TPEx ``dailyQuotes``.

Fuente oficial e histórica (una petición por sesión y mercado), alternativa al nivel gratuito de
FinMind para el universo completo. Se archiva la respuesta íntegra en ``RawStore``; la lectura tipada
produce ``Bar`` por símbolo con la misma política de disponibilidad (cierre 13:30 Taipei + 24 h).
**Sin derechos**: esta fuente sólo trae precios y volúmenes; el mercado construido con ella no tiene
dividendos y así debe declararse.

Lectura estricta (ronda 16): la fecha declarada en el cuerpo debe ser la sesión archivada (R16-01); un
símbolo repetido en la misma sesión es un error, no una sobrescritura (R16-04); una fila sin alguna de las
columnas obligatorias rompe el esquema y se rechaza en vez de convertirse en ceros (R16-05).

Formatos observados el 9-09-2026 (sesiones desde 2021 hasta hoy):
- TWSE ``rwd/zh/afterTrading/MI_INDEX?date=YYYYMMDD&type=ALLBUT0999&response=json`` → ``stat`` («OK» o texto
  de «sin datos» en cierres), ``date`` (YYYYMMDD) y ``tables`` con una tabla «每日收盤行情» (campos 證券代號,
  成交股數, 成交筆數, 成交金額, 開盤價, 最高價, 最低價, 收盤價, …; números con comas; «--» sin precio).
- TPEx ``www/zh-tw/afterTrading/dailyQuotes?date=YYYY/MM/DD&response=json`` → ``date`` (YYYYMMDD) y ``tables``
  con «上櫃股票行情» (campos 代號, 名稱, 收盤, 漲跌, 開盤, 最高, 最低, 均價, 成交股數, 成交金額(元), 成交筆數, …);
  filas más largas que la lista de campos (se toman las primeras columnas).
"""
from __future__ import annotations

import json
import time
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Iterable, Optional

import requests

from ..store import CaptureRecord, RawStore
from ..timeutil import taipei
from .finmind import PRICE_AVAILABILITY_LAG, Bar

TWSE_URL = "https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX"
TPEX_URL = "https://www.tpex.org.tw/www/zh-tw/afterTrading/dailyQuotes"
HEADERS = {"User-Agent": "Mozilla/5.0 taiwan-ia-lab/0.1 (private research)", "Accept": "application/json"}
TWSE_DATASET = "MI_INDEX_ALLBUT0999"
TPEX_DATASET = "dailyQuotes"
TWSE_DERIVATION = "twse_mi_index_daily_v1"
TPEX_DERIVATION = "tpex_daily_quotes_v1"
TWSE_FIELDS = ("證券代號", "成交股數", "成交筆數", "成交金額", "開盤價", "最高價", "最低價", "收盤價")
TPEX_FIELDS = ("代號", "收盤", "開盤", "最高", "最低", "成交股數", "成交金額(元)", "成交筆數")
_PLACEHOLDERS = {"--", "---", "-", "X", "除權", "除息", "除權息", ""}


class DailyQuoteSchemaError(ValueError):
    """La captura no tiene la forma esperada (fecha, columnas o filas repetidas)."""


def _num(v) -> Optional[Decimal]:
    s = str(v).replace(",", "").strip()
    if s in _PLACEHOLDERS:
        return None
    try:
        d = Decimal(s)
    except InvalidOperation:
        return None
    return d if d.is_finite() else None


def fetch_twse(store: RawStore, d: date, *, pause_s: float = 3.0) -> CaptureRecord:
    r = requests.get(TWSE_URL, params={"date": d.strftime("%Y%m%d"), "type": "ALLBUT0999", "response": "json"}, headers=HEADERS, timeout=90)
    rec = store.put(source_id="twse", dataset=f"{TWSE_DATASET}/{d.isoformat()}", payload=r.content, url=r.url, http_status=r.status_code,
                    content_type=r.headers.get("Content-Type"), extra={"session": d.isoformat()})
    time.sleep(pause_s)
    return rec


def fetch_tpex(store: RawStore, d: date, *, pause_s: float = 3.0) -> CaptureRecord:
    r = requests.get(TPEX_URL, params={"date": d.strftime("%Y/%m/%d"), "response": "json"}, headers=HEADERS, timeout=90)
    rec = store.put(source_id="tpex", dataset=f"{TPEX_DATASET}/{d.isoformat()}", payload=r.content, url=r.url, http_status=r.status_code,
                    content_type=r.headers.get("Content-Type"), extra={"session": d.isoformat()})
    time.sleep(pause_s)
    return rec


def _session_of(rec: CaptureRecord) -> date:
    return date.fromisoformat(rec.dataset.split("/", 1)[1])


def _check_body_date(body: dict, rec: CaptureRecord) -> None:
    declared = str(body.get("date", "")).strip()
    if declared and declared != _session_of(rec).strftime("%Y%m%d"):
        raise DailyQuoteSchemaError(f"{rec.capture_id}: body date {declared} does not match archived session {_session_of(rec).isoformat()} (R16-01)")


def twse_rows(store: RawStore, rec: CaptureRecord) -> Optional[list[dict]]:
    """Filas de «每日收盤行情» como diccionarios; ``None`` si la fecha no tuvo datos (cierre)."""
    body = json.loads(store.read(rec).decode("utf-8"))
    if body.get("stat") != "OK":
        return None
    _check_body_date(body, rec)
    for t in body.get("tables", []):
        if "每日收盤行情" in str(t.get("title", "")) and t.get("data"):
            fields = t["fields"]
            missing = [f for f in TWSE_FIELDS if f not in fields]
            if missing:
                raise DailyQuoteSchemaError(f"{rec.capture_id}: missing columns {missing} (R16-05)")
            return [dict(zip(fields, row)) for row in t["data"]]
    return None


def tpex_rows(store: RawStore, rec: CaptureRecord) -> Optional[list[dict]]:
    body = json.loads(store.read(rec).decode("utf-8"))
    _check_body_date(body, rec)
    for t in body.get("tables", []):
        if str(t.get("title", "")).startswith("上櫃股票行情"):
            if not t.get("data"):
                return None
            fields = t["fields"]
            missing = [f for f in TPEX_FIELDS if f not in fields]
            if missing:
                raise DailyQuoteSchemaError(f"{rec.capture_id}: missing columns {missing} (R16-05)")
            return [dict(zip(fields, row[: len(fields)])) for row in t["data"]]
    return None


def _bar(session: date, o, h, l, c, vol, val, n) -> Bar:
    close_at = taipei(session).replace(hour=13, minute=30)
    return Bar(session=session, open=o if o is not None else Decimal(0), high=h if h is not None else Decimal(0),
               low=l if l is not None else Decimal(0), close=c if c is not None else Decimal(0),
               volume_shares=int(vol or 0), value_twd=val if val is not None else Decimal(0), transactions=int(n or 0),
               available_at=close_at + PRICE_AVAILABILITY_LAG)


def _bars(session: date, rows: Iterable[dict], *, key_sid: str, keys: tuple[str, ...], required: tuple[str, ...]) -> dict[str, Bar]:
    out: dict[str, Bar] = {}
    for r in rows:
        missing = [k for k in required if k not in r]
        if missing:
            raise DailyQuoteSchemaError(f"row {r.get(key_sid)!r} lacks columns {missing} (R16-05)")
        sid = str(r.get(key_sid, "")).strip()
        if not sid:
            continue
        if sid in out:
            raise DailyQuoteSchemaError(f"{sid}: repeated row in session {session.isoformat()} (R16-04)")
        o, h, l, c, vol, val, n = (r.get(k) for k in keys)
        out[sid] = _bar(session, _num(o), _num(h), _num(l), _num(c), _num(vol), _num(val), _num(n))
    return out


def bars_twse(session: date, rows: Iterable[dict]) -> dict[str, Bar]:
    return _bars(session, rows, key_sid="證券代號", keys=("開盤價", "最高價", "最低價", "收盤價", "成交股數", "成交金額", "成交筆數"), required=TWSE_FIELDS)


def bars_tpex(session: date, rows: Iterable[dict]) -> dict[str, Bar]:
    return _bars(session, rows, key_sid="代號", keys=("開盤", "最高", "最低", "收盤", "成交股數", "成交金額(元)", "成交筆數"), required=TPEX_FIELDS)


def captured_sessions(store: RawStore, source_id: str, dataset: str) -> dict[date, CaptureRecord]:
    """Última captura con HTTP 200 por sesión para un conjunto de datos por fecha."""
    out: dict[date, CaptureRecord] = {}
    for rec in store.captures(source_id=source_id):
        if rec.dataset.startswith(dataset + "/") and rec.http_status == 200:
            out[date.fromisoformat(rec.dataset.split("/", 1)[1])] = rec
    return out
