"""Calendario de sesiones construido desde la lista oficial, versionada.

Corrección tras la ronda 1 de Astra (R01-01): el endpoint
``holidaySchedule`` de TWSE mezcla dos clases de filas. Las de cierre
(«依規定放假», «補假», «市場無交易，僅辦理結算交割作業») y las **informativas
de negociación** («國曆新年開始交易日», «農曆春節前最後交易日»,
«農曆春節後開始交易日»), que son sesiones. Cada fila se clasifica y una fila
no reconocida, contradictoria o con negación detiene la carga en vez de
adivinarse (R02-19).

El calendario es inmutable tras construirse (R02-18) y se versiona:
``CalendarStore`` conserva cada versión con su ``recorded_at`` para poder
consultar «el calendario conocido al corte».
"""
from __future__ import annotations

import json
from datetime import date, datetime, time, timedelta
from pathlib import Path
from types import MappingProxyType
from typing import Iterable, Mapping, Optional, Sequence

from .timeutil import TAIPEI, ensure_aware, parse_date, taipei, to_utc

REPO_ROOT = Path(__file__).resolve().parents[2]
REFERENCE_DIR = REPO_ROOT / "data" / "reference"

ROW_SESSION_MARKER = "session_marker"
ROW_CLOSURE = "closure"
ROW_UNKNOWN = "unknown"

_SESSION_MARKERS = ("開始交易", "最後交易", "正常交易")
_CLOSURE_MARKERS = ("放假", "補假", "市場無交易", "休市")
_NEGATION_PREFIXES = ("不", "未", "取消", "非", "無")   # cualquier marcador precedido de negación → revisión (R03-12)


class CalendarRangeError(ValueError):
    pass


class UnclassifiedCalendarRow(ValueError):
    pass


def classify_holiday_row(row: Mapping[str, str]) -> str:
    """Clasifica una fila del endpoint oficial; ante ambigüedad o negación devuelve ``unknown``."""
    name = str(row.get("Name", ""))
    desc = str(row.get("Description", ""))
    text = name + " " + desc
    for marker in _CLOSURE_MARKERS + _SESSION_MARKERS:
        if any(prefix + marker in text for prefix in _NEGATION_PREFIXES):
            return ROW_UNKNOWN
    if "取消" in text:
        return ROW_UNKNOWN
    is_session = any(m in text for m in _SESSION_MARKERS)
    is_closure = any(m in text for m in _CLOSURE_MARKERS)
    if is_session and is_closure:
        return ROW_UNKNOWN
    if is_session:
        return ROW_SESSION_MARKER
    if is_closure:
        return ROW_CLOSURE
    return ROW_UNKNOWN


class TradingCalendar:
    OPEN = time(9, 0)
    CLOSE = time(13, 30)

    def __init__(
        self,
        *,
        start: date,
        end: date,
        closures: Iterable[date],
        extra_sessions: Iterable[date] = (),
        session_overrides: Optional[Mapping[date, tuple[time, time]]] = None,
        source_id: str,
        recorded_at: datetime,
        version: str = "1",
    ) -> None:
        if end < start:
            raise CalendarRangeError("end before start")
        self.start = start
        self.end = end
        self.source_id = source_id
        self.recorded_at = ensure_aware(recorded_at, "recorded_at")
        self.version = version
        self._closures = frozenset(closures)
        self._extra = frozenset(extra_sessions)
        overrides: dict[date, tuple[time, time]] = {}
        for od, hours in (session_overrides or {}).items():
            hours = tuple(hours)
            if len(hours) != 2 or not all(isinstance(h, time) for h in hours) or hours[0] >= hours[1]:
                raise CalendarRangeError(f"session override for {od} must be (open, close) times with open < close")
            overrides[od] = hours
        self._overrides: Mapping[date, tuple[time, time]] = MappingProxyType(overrides)   # R03-11: sin alias mutables
        sessions: list[date] = []
        d = start
        while d <= end:
            weekday_open = d.weekday() < 5 and d not in self._closures
            if weekday_open or d in self._extra:
                sessions.append(d)
            d += timedelta(days=1)
        self._sessions: Sequence[date] = tuple(sessions)
        self._set = frozenset(sessions)
        for od in self._overrides:
            if od not in self._set:
                raise CalendarRangeError(f"session override for non-session {od}")
        self._frozen = True

    def __setattr__(self, name: str, value) -> None:
        if getattr(self, "_frozen", False):
            raise AttributeError(f"TradingCalendar is immutable; cannot set {name}. Add a new version to CalendarStore instead")
        object.__setattr__(self, name, value)

    def __delattr__(self, name: str) -> None:
        raise AttributeError("TradingCalendar is immutable")

    # -- consultas básicas -------------------------------------------------
    def _check_range(self, d: date) -> None:
        if d < self.start or d > self.end:
            raise CalendarRangeError(
                f"{d.isoformat()} outside calendar coverage {self.start}..{self.end} (source {self.source_id})"
            )

    def is_session(self, d: date) -> bool:
        self._check_range(d)
        return d in self._set

    @property
    def sessions(self) -> Sequence[date]:
        return self._sessions

    @property
    def closures(self) -> frozenset[date]:
        return self._closures

    def sessions_between(self, a: date, b: date) -> list[date]:
        self._check_range(a)
        self._check_range(b)
        return [s for s in self._sessions if a <= s <= b]

    def next_session(self, *, after: date) -> date:
        self._check_range(after)
        for s in self._sessions:
            if s > after:
                return s
        raise CalendarRangeError(f"no session after {after.isoformat()} within {self.end}")

    def prev_session(self, *, before: date) -> date:
        self._check_range(before)
        for s in reversed(self._sessions):
            if s < before:
                return s
        raise CalendarRangeError(f"no session before {before.isoformat()} within {self.start}")

    def session_hours(self, d: date) -> tuple[time, time]:
        if not self.is_session(d):
            raise CalendarRangeError(f"{d.isoformat()} is not a session")
        return self._overrides.get(d, (self.OPEN, self.CLOSE))

    def session_open(self, d: date) -> datetime:
        return taipei(d, self.session_hours(d)[0])

    def session_close(self, d: date) -> datetime:
        return taipei(d, self.session_hours(d)[1])

    # -- semanas ----------------------------------------------------------
    @staticmethod
    def monday_of(any_day: date) -> date:
        return any_day - timedelta(days=any_day.weekday())

    def week_sessions(self, any_day: date) -> list[date]:
        """Sesiones reales de la semana natural (lunes..domingo) de ``any_day``."""
        mon = self.monday_of(any_day)
        return self.sessions_between(mon, mon + timedelta(days=6))

    def first_session_of_week(self, any_day: date) -> Optional[date]:
        s = self.week_sessions(any_day)
        return s[0] if s else None

    def last_session_of_week(self, any_day: date) -> Optional[date]:
        s = self.week_sessions(any_day)
        return s[-1] if s else None

    # -- constructores ----------------------------------------------------
    @classmethod
    def from_twse_holiday_rows(
        cls,
        rows: Iterable[dict],
        *,
        year: int,
        source_id: str,
        recorded_at: datetime,
        version: str = "1",
    ) -> "TradingCalendar":
        closures: set[date] = set()
        unknown: list[str] = []
        for r in rows:
            kind = classify_holiday_row(r)
            if kind == ROW_CLOSURE:
                closures.add(parse_date(r["Date"]))
            elif kind == ROW_UNKNOWN:
                unknown.append(f"{r.get('Date')} {r.get('Name')}")
        if unknown:
            raise UnclassifiedCalendarRow("unclassified or contradictory rows; refusing to guess: " + "; ".join(unknown))
        return cls(
            start=date(year, 1, 1),
            end=date(year, 12, 31),
            closures=closures,
            source_id=source_id,
            recorded_at=recorded_at,
            version=version,
        )


class CalendarStore:
    """Versiones inmutables del calendario con ``recorded_at``: conocido vs. efectivo."""

    def __init__(self) -> None:
        self._versions: list[TradingCalendar] = []

    def add(self, cal: TradingCalendar) -> None:
        if not isinstance(cal, TradingCalendar):
            raise TypeError("CalendarStore only accepts TradingCalendar versions")
        self._versions.append(cal)

    def as_known_at(self, known_at: datetime) -> TradingCalendar:
        ka = to_utc(known_at, "known_at")
        candidates = [c for c in self._versions if to_utc(c.recorded_at) <= ka]
        if not candidates:
            raise CalendarRangeError(f"no calendar version recorded at or before {known_at.isoformat()}")
        return max(candidates, key=lambda c: to_utc(c.recorded_at))

    def latest(self) -> TradingCalendar:
        if not self._versions:
            raise CalendarRangeError("no calendar versions")
        return max(self._versions, key=lambda c: to_utc(c.recorded_at))


def load_twse_reference_calendar_2026() -> TradingCalendar:
    """Calendario 2026 desde la captura oficial guardada en ``data/reference``.

    ``recorded_at`` es la hora real de esa captura (18:04 UTC del 9-09-2026
    según el manifiesto de la primera corrida de captura); no tiene recibo de
    sello temporal independiente.
    """
    path = REFERENCE_DIR / "twse_holidaySchedule_2026__captured_2026-09-09.json"
    rows = json.loads(path.read_text(encoding="utf-8"))
    return TradingCalendar.from_twse_holiday_rows(
        rows,
        year=2026,
        source_id="S06:openapi.twse.com.tw/v1/holidaySchedule/holidaySchedule",
        recorded_at=datetime(2026, 9, 10, 2, 4, 32, tzinfo=TAIPEI),
        version="captured_2026-09-09",
    )
