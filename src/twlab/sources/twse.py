"""Adaptadores de las capturas de TWSE OpenAPI a estructuras del laboratorio.

Sólo transforman bytes archivados (``RawStore``) en registros tipados; no
descargan nada. Cada función recibe las filas ya decodificadas y devuelve
objetos con procedencia (``source_id``, ``capture_id``).
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime
from typing import Iterable, Optional

from ..master import ORDINARY_EQUITY, SecurityVersion, TerminalEvent
from ..store import CaptureRecord, RawStore
from ..timeutil import DateParseError, parse_date


@dataclass(frozen=True)
class CensusRow:
    symbol: str
    name_zh: str
    industry_code: str
    listing_date: Optional[date]
    registration: str          # 外國企業註冊地國; «－» para emisores locales
    issued_shares: Optional[int]
    report_date: date          # 出表日期 (fecha de la instantánea, no de publicación por empresa)


def _int_or_none(v: str) -> Optional[int]:
    try:
        return int(str(v).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def census_rows_twse(rows: Iterable[dict]) -> list[CensusRow]:
    """``opendata/t187ap03_L``: sociedades cotizadas en TWSE (sin ETF)."""
    out: list[CensusRow] = []
    for r in rows:
        try:
            listing = parse_date(r.get("上市日期", ""))
        except DateParseError:
            listing = None
        out.append(CensusRow(
            symbol=str(r["公司代號"]).strip(), name_zh=str(r.get("公司簡稱", "")).strip(),
            industry_code=str(r.get("產業別", "")).strip(), listing_date=listing,
            registration=str(r.get("外國企業註冊地國", "")).strip(),
            issued_shares=_int_or_none(r.get("已發行普通股數或TDR原股發行股數", "")),
            report_date=parse_date(r["出表日期"]),
        ))
    return out


def census_rows_tpex(rows: Iterable[dict]) -> list[CensusRow]:
    """``mopsfin_t187ap03_O`` (TPEx) y ``mopsfin_t187ap03_R`` (ESB): claves en inglés."""
    out: list[CensusRow] = []
    for r in rows:
        try:
            listing = parse_date(r.get("DateOfListing", ""))
        except DateParseError:
            listing = None
        out.append(CensusRow(
            symbol=str(r["SecuritiesCompanyCode"]).strip(), name_zh=str(r.get("CompanyAbbreviation", "")).strip(),
            industry_code=str(r.get("SecuritiesIndustryCode", "")).strip(), listing_date=listing,
            registration=str(r.get("Registration", "")).strip(),
            issued_shares=_int_or_none(r.get("IssueShares", "")),
            report_date=parse_date(r["Date"]),
        ))
    return out


@dataclass(frozen=True)
class DelistingRow:
    symbol: str
    name_zh: str
    delisting_date: date


def delisting_rows_twse(rows: Iterable[dict]) -> list[DelistingRow]:
    """``company/suspendListingCsvAndHtml``: retiradas de TWSE (fecha ROC con barras)."""
    return [DelistingRow(str(r["Code"]).strip(), str(r.get("Company", "")).strip(), parse_date(r["DelistingDate"])) for r in rows]


def load_rows(store: RawStore, rec: CaptureRecord) -> list[dict]:
    return json.loads(store.read(rec).decode("utf-8"))


def latest_capture(store: RawStore, source_id: str, dataset: str) -> CaptureRecord:
    recs = store.captures(source_id=source_id, dataset=dataset)
    if not recs:
        raise KeyError(f"no capture for {source_id}/{dataset}")
    return recs[-1]


def security_versions_from_census(
    rows: Iterable[CensusRow], *, market: str, instrument_types: dict[str, str], boards: dict[str, str],
    recorded_at: datetime, source_id: str,
) -> list[SecurityVersion]:
    """Convierte filas de censo en segmentos abiertos del maestro.

    ``instrument_types``/``boards`` vienen del clasificador (FinMind ``TaiwanStockInfo``);
    un símbolo sin clasificación queda como ``unclassified`` y fuera del universo simulable.
    """
    out: list[SecurityVersion] = []
    for r in rows:
        if r.listing_date is None:
            continue
        out.append(SecurityVersion(
            security_id=f"{market}:{r.symbol}", issuer_id=r.symbol, symbol=r.symbol, name_zh=r.name_zh,
            market=market, board=boards.get(r.symbol, "main"),
            instrument_type=instrument_types.get(r.symbol, "unclassified"),
            valid_from=r.listing_date, valid_to=None, recorded_at=recorded_at, source_id=source_id,
        ))
    return out


def terminal_events_from_delistings(rows: Iterable[DelistingRow], *, market: str, recorded_at: datetime, source_id: str) -> list[TerminalEvent]:
    return [TerminalEvent(f"{market}:{r.symbol}", "delisting", r.delisting_date, recorded_at, source_id, r.name_zh) for r in rows]


__all__ = ["ORDINARY_EQUITY"]
