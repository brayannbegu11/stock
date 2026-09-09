"""Fechas, horas y política de disponibilidad.

Formatos reales observados en la auditoría del 9-09-2026:
- ROC compacto        ``1150908``   (TWSE/TPEx OpenAPI, la mayoría de tablas)
- ROC con barras      ``115/09/01`` (TWSE ``company/suspendListingCsvAndHtml``)
- ROC en chino        ``民國115年06月11日`` (cuerpo de anuncios materiales)
- Gregoriano compacto ``20260901``  (TPEx ``tpex_index``)
- ISO                 ``2026-09-01`` (FinMind)
- Hora HHMMSS sin ceros a la izquierda: ``3220`` = 00:32:20, ``70004`` = 07:00:04

Reglas:
- Nunca se inventa una hora. Si sólo hay fecha, se aplica la política
  conservadora del protocolo (``admit_next_session_unless_earlier_time_verified``)
  y la inferencia queda marcada en ``AvailabilityQuality``.
- Toda comparación temporal se hace sobre instantes UTC (``to_utc``). Comparar
  dos ``datetime`` con la misma ``ZoneInfo`` ordena por hora local e ignora
  ``fold`` en cambios de horario (hallazgo R01-03 de Astra).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, time
from enum import Enum
from typing import TYPE_CHECKING, Optional
from zoneinfo import ZoneInfo

if TYPE_CHECKING:  # pragma: no cover
    from .calendar import TradingCalendar

TAIPEI = ZoneInfo("Asia/Taipei")
UTC = ZoneInfo("UTC")


class AvailabilityQuality(str, Enum):
    VERIFIED_ORIGINAL = "verified_original"
    VERIFIED_VERSION = "verified_version"
    CONSERVATIVE_INFERENCE = "conservative_inference"
    UNKNOWN = "unknown"


class DateParseError(ValueError):
    pass


_ISO = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")
_GREG_COMPACT = re.compile(r"^(\d{4})(\d{2})(\d{2})$")
_ROC_COMPACT = re.compile(r"^(\d{2,3})(\d{2})(\d{2})$")
_SLASH = re.compile(r"^(\d{2,4})/(\d{1,2})/(\d{1,2})$")
_ROC_CJK = re.compile(r"^(?:民國)?(\d{2,3})年(\d{1,2})月(\d{1,2})日$")


def roc_year_to_gregorian(year: int) -> int:
    if year <= 0:
        raise DateParseError(f"ROC year must be positive, got {year}")
    return year + 1911


def parse_date(value: str) -> date:
    """Convierte cualquiera de los formatos observados a ``date``.

    Falla en vez de adivinar: cadenas vacías, formatos desconocidos o
    fechas imposibles levantan ``DateParseError``.
    """
    s = (value or "").strip()
    if not s:
        raise DateParseError("empty date")
    try:
        m = _ISO.match(s)
        if m:
            return date(int(m[1]), int(m[2]), int(m[3]))
        m = _GREG_COMPACT.match(s)
        if m:
            return date(int(m[1]), int(m[2]), int(m[3]))
        m = _ROC_COMPACT.match(s)
        if m:
            return date(roc_year_to_gregorian(int(m[1])), int(m[2]), int(m[3]))
        m = _SLASH.match(s)
        if m:
            y = int(m[1])
            y = y if len(m[1]) == 4 else roc_year_to_gregorian(y)
            return date(y, int(m[2]), int(m[3]))
        m = _ROC_CJK.match(s)
        if m:
            return date(roc_year_to_gregorian(int(m[1])), int(m[2]), int(m[3]))
    except ValueError as exc:  # fecha imposible (mes 13, día 32...)
        raise DateParseError(f"invalid date {value!r}: {exc}") from exc
    raise DateParseError(f"unrecognised date format: {value!r}")


def parse_hhmmss(value: str) -> time:
    """Hora ``HHMMSS`` con o sin ceros a la izquierda (``3220`` → 00:32:20)."""
    s = (value or "").strip()
    if not s or not s.isdigit() or len(s) > 6:
        raise DateParseError(f"invalid HHMMSS time: {value!r}")
    s = s.zfill(6)
    try:
        return time(int(s[0:2]), int(s[2:4]), int(s[4:6]))
    except ValueError as exc:
        raise DateParseError(f"invalid HHMMSS time {value!r}: {exc}") from exc


def taipei(d: date, t: Optional[time] = None) -> datetime:
    return datetime.combine(d, t or time(0, 0), tzinfo=TAIPEI)


def ensure_aware(dt: datetime, label: str = "datetime") -> datetime:
    if not isinstance(dt, datetime) or dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None:
        raise ValueError(f"{label} must be a timezone-aware datetime; naive values are forbidden")
    return dt


def to_utc(dt: datetime, label: str = "datetime") -> datetime:
    """Instante normalizado a UTC. Respeta ``fold`` (PEP 495)."""
    return ensure_aware(dt, label).astimezone(UTC)


def is_after(a: datetime, b: datetime) -> bool:
    """``a`` es estrictamente posterior a ``b`` como instantes."""
    return to_utc(a).timestamp() > to_utc(b).timestamp()


def is_not_after(a: datetime, b: datetime) -> bool:
    return not is_after(a, b)


@dataclass(frozen=True)
class Availability:
    available_at: datetime
    quality: AvailabilityQuality
    basis: str


def derive_available_at(
    published_date: date,
    published_time: Optional[time] = None,
    *,
    calendar: "TradingCalendar",
    time_is_verified: bool = False,
) -> Availability:
    """Política ``admit_next_session_unless_earlier_time_verified``.

    - Hora verificada → disponible en ese instante (``verified_original``).
    - Sólo fecha (o hora no verificada) → disponible en la apertura de la
      primera sesión *posterior* a esa fecha (``conservative_inference``).
      Nunca se convierte una fecha en las 00:00 del mismo día.

    Esta política sólo es admisible cuando la fecha de publicación es un
    hecho verificado. Un plazo legal (p. ej. «ingresos hasta el día 10») no
    es evidencia de publicación: esos registros se clasifican ``unknown``
    (hallazgo R01-24) hasta disponer de evidencia por versión.
    """
    if published_time is not None and time_is_verified:
        return Availability(
            taipei(published_date, published_time),
            AvailabilityQuality.VERIFIED_ORIGINAL,
            "verified publication timestamp",
        )
    nxt = calendar.next_session(after=published_date)
    return Availability(
        calendar.session_open(nxt),
        AvailabilityQuality.CONSERVATIVE_INFERENCE,
        f"date-only publication {published_date.isoformat()}; admitted from next session open {nxt.isoformat()}",
    )
