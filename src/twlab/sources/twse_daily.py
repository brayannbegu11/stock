"""Cotizaciones diarias oficiales por fecha (todas las acciones): TWSE ``MI_INDEX`` y TPEx ``dailyQuotes``.

Fuente oficial e histórica (una petición por sesión y mercado), alternativa al nivel gratuito de
FinMind para el universo completo. Se archiva la respuesta íntegra en ``RawStore``; la lectura tipada
produce ``Bar`` por símbolo con la misma política de disponibilidad (cierre 13:30 Taipei + 24 h).
**Sin derechos**: esta fuente sólo trae precios y volúmenes; el mercado construido con ella no tiene
dividendos y así debe declararse.

Formatos observados el 9-09-2026 (sesiones desde 2021 hasta hoy):
- TWSE ``rwd/zh/afterTrading/MI_INDEX?date=YYYYMMDD&type=ALLBUT0999&response=json`` → ``stat`` («OK» o texto
  de «sin datos» en cierres) y ``tables`` con una tabla «每日收盤行情» (campos 證券代號, 成交股數, 成交筆數,
  成交金額, 開盤價, 最高價, 最低價, 收盤價, …; números con comas; «--» sin precio).
- TPEx ``www/zh-tw/afterTrading/dailyQuotes?date=YYYY/MM/DD&response=json`` → ``tables`` con «上櫃股票行情»
  (campos 代號, 名稱, 收盤, 漲跌, 開盤, 最高, 最低, 均價, 成交股數, 成交金額(元), 成交筆數, …); filas más largas que
  la lista de campos (se toman las primeras columnas).
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
_PLACEHOLDERS = {"--", "---", "-", "X", "除權", "除息", "除權息", ""}


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


def twse_rows(store: RawStore, rec: CaptureRecord) -> Optional[list[dict]]:
    """Filas de «每日收盤行情» como diccionarios; ``None`` si la fecha no tuvo datos (cierre)."""
    body = json.loads(store.read(rec).decode("utf-8"))
    if body.get("stat") != "OK":
        return None
    for t in body.get("tables", []):
        if "每日收盤行情" in str(t.get("title", "")) and t.get("data"):
            fields = t["fields"]
            return [dict(zip(fields, row)) for row in t["data"]]
    return None


def tpex_rows(store: RawStore, rec: CaptureRecord) -> Optional[list[dict]]:
    body = json.loads(store.read(rec).decode("utf-8"))
    for t in body.get("tables", []):
        if str(t.get("title", "")).startswith("上櫃股票行情"):
            if not t.get("data"):
                return None
            fields = t["fields"]
            return [dict(zip(fields, row[: len(fields)])) for row in t["data"]]
    return None


def _bar(session: date, o, h, l, c, vol, val, n) -> Bar:
    close_at = taipei(session).replace(hour=13, minute=30)
    return Bar(session=session, open=o if o is not None else Decimal(0), high=h if h is not None else Decimal(0),
               low=l if l is not None else Decimal(0), close=c if c is not None else Decimal(0),
               volume_shares=int(vol or 0), value_twd=val if val is not None else Decimal(0), transactions=int(n or 0),
               available_at=close_at + PRICE_AVAILABILITY_LAG)


def bars_twse(session: date, rows: Iterable[dict]) -> dict[str, Bar]:
    out: dict[str, Bar] = {}
    for r in rows:
        sid = str(r.get("證券代號", "")).strip()
        if not sid:
            continue
        out[sid] = _bar(session, _num(r.get("開盤價")), _num(r.get("最高價")), _num(r.get("最低價")), _num(r.get("收盤價")),
                        _num(r.get("成交股數")), _num(r.get("成交金額")), _num(r.get("成交筆數")))
    return out


def bars_tpex(session: date, rows: Iterable[dict]) -> dict[str, Bar]:
    out: dict[str, Bar] = {}
    for r in rows:
        sid = str(r.get("代號", "")).strip()
        if not sid:
            continue
        out[sid] = _bar(session, _num(r.get("開盤")), _num(r.get("最高")), _num(r.get("最低")), _num(r.get("收盤")),
                        _num(r.get("成交股數")), _num(r.get("成交金額(元)")), _num(r.get("成交筆數")))
    return out


def captured_sessions(store: RawStore, source_id: str, dataset: str) -> dict[date, CaptureRecord]:
    """Última captura con HTTP 200 por sesión para un conjunto de datos por fecha."""
    out: dict[date, CaptureRecord] = {}
    for rec in store.captures(source_id=source_id):
        if rec.dataset.startswith(dataset + "/") and rec.http_status == 200:
            out[date.fromisoformat(rec.dataset.split("/", 1)[1])] = rec
    return out
