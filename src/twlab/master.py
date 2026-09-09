"""Maestro histórico de valores (SCD tipo 2, sólo anexado).

La identidad no es el símbolo: un símbolo puede reutilizarse (UNI-03), un
emisor puede cambiar de mercado sin cambiar de identidad (UNI-02) y una
retirada no borra al emisor de la historia (UNI-01).

Modelo: cada fila describe un *segmento de vigencia* ``[valid_from, valid_to)``
de un ``security_id``. Una fila posterior con el mismo ``(security_id,
valid_from)`` y mayor ``recorded_at`` sustituye a la anterior para quien
consulte con ``known_at`` posterior; la anterior nunca se borra.

Correcciones rondas 1 y 2 (Astra): los segmentos solapados se rechazan al
insertar, tanto en la vista actual como en la vista conocida en el
``recorded_at`` de la fila nueva (R01-06, R02-03); ``change_segment`` valida
todo antes de anexar nada (R02-12); los eventos terminales se versionan
(R01-07); la elegibilidad exige mercado e instrumento en alcance (R01-08).
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, datetime
from typing import Iterable, Optional

from .timeutil import ensure_aware, to_utc

ORDINARY_EQUITY = "ordinary_equity"
SIMULATION_MARKETS = ("TWSE", "TPEX")


class UnknownSymbol(KeyError):
    pass


class AmbiguousSymbol(ValueError):
    pass


class OverlappingSegment(ValueError):
    pass


@dataclass(frozen=True)
class SecurityVersion:
    security_id: str
    issuer_id: str
    symbol: str
    name_zh: str
    market: str            # TWSE | TPEX | ESB
    board: str             # main | innovation | emerging | ...
    instrument_type: str   # ordinary_equity | etf | etn | dr | warrant | ...
    valid_from: date
    valid_to: Optional[date]
    recorded_at: datetime
    source_id: str
    currency: str = "TWD"
    name_en: Optional[str] = None

    def covers(self, d: date) -> bool:
        return self.valid_from <= d and (self.valid_to is None or d < self.valid_to)

    def overlaps(self, other: "SecurityVersion") -> bool:
        a_end = self.valid_to or date.max
        b_end = other.valid_to or date.max
        return self.valid_from < b_end and other.valid_from < a_end


@dataclass(frozen=True)
class TerminalEvent:
    security_id: str
    kind: str              # delisting | merger | conversion | ...
    effective: date
    recorded_at: datetime
    source_id: str
    detail: str = ""


class SecurityMaster:
    def __init__(self) -> None:
        self._versions: list[SecurityVersion] = []
        self._terminal: list[TerminalEvent] = []

    # -- validación -------------------------------------------------------
    @staticmethod
    def _validate_row(v: SecurityVersion) -> None:
        ensure_aware(v.recorded_at, "recorded_at")
        if v.valid_to is not None and v.valid_to <= v.valid_from:
            raise ValueError("valid_to must be after valid_from")

    def _check_no_overlap(self, v: SecurityVersion, *, extra_rows: Iterable[SecurityVersion] = (),
                          ignore_segment_from: Optional[date] = None) -> None:
        """Rechaza solapes en la vista actual y en la vista conocida en ``v.recorded_at``."""
        rows = self._versions + list(extra_rows)
        # toda vista histórica en la que la fila nueva sea visible: cada instante de registro de este emisor
        # desde v.recorded_at en adelante, y la vista actual (R03-07). Antes de v.recorded_at la fila no existe.
        new_at = to_utc(v.recorded_at)
        instants = sorted({to_utc(r.recorded_at) for r in rows if r.security_id == v.security_id and to_utc(r.recorded_at) >= new_at} | {new_at})
        for known_at in [*instants, None]:
            for seg in self._effective_from(rows, known_at):
                if seg.security_id != v.security_id:
                    continue
                if seg.valid_from == v.valid_from:
                    if to_utc(v.recorded_at) < to_utc(seg.recorded_at):
                        raise ValueError("a superseding row must not be recorded before the row it supersedes")
                    if to_utc(v.recorded_at) == to_utc(seg.recorded_at) and seg != v:
                        raise ValueError(
                            f"{v.security_id}@{v.valid_from}: a different row already exists with recorded_at "
                            f"{seg.recorded_at.isoformat()}; a revision needs a later recorded_at (R04-12)"
                        )
                    continue  # sustitución legítima del mismo segmento
                if ignore_segment_from is not None and seg.valid_from == ignore_segment_from:
                    continue
                if seg.overlaps(v):
                    raise OverlappingSegment(
                        f"{v.security_id}: new segment [{v.valid_from}, {v.valid_to}) overlaps "
                        f"[{seg.valid_from}, {seg.valid_to}) as known at {known_at or 'now'}; close the current segment first"
                    )

    # -- escritura (sólo anexado) ------------------------------------------
    def add(self, v: SecurityVersion) -> None:
        self._validate_row(v)
        self._check_no_overlap(v)
        self._versions.append(v)

    def extend(self, versions: Iterable[SecurityVersion]) -> None:
        for v in versions:
            self.add(v)

    def close_version(
        self,
        security_id: str,
        *,
        valid_to: date,
        recorded_at: datetime,
        source_id: str,
        terminal: Optional[TerminalEvent] = None,
    ) -> SecurityVersion:
        """Cierra el segmento vigente añadiendo una fila nueva; la anterior se conserva."""
        current = self.current_segment(security_id)
        if current is None:
            raise UnknownSymbol(security_id)
        closed = replace(current, valid_to=valid_to, recorded_at=ensure_aware(recorded_at), source_id=source_id)
        if terminal is not None:
            ensure_aware(terminal.recorded_at, "terminal.recorded_at")
        self.add(closed)
        if terminal is not None:
            self._terminal.append(terminal)
        return closed

    def change_segment(self, security_id: str, *, new: SecurityVersion, recorded_at: datetime, source_id: str) -> None:
        """Cambio de mercado/símbolo/clase: cierra el segmento vigente en ``new.valid_from`` y añade el nuevo.

        Atómico: se valida todo antes de anexar nada (R02-12).
        """
        if new.security_id != security_id:
            raise ValueError("change_segment keeps the identity; security_id must match")
        self._validate_row(new)
        current = self.current_segment(security_id)
        if current is None:
            raise UnknownSymbol(security_id)
        if new.valid_from <= current.valid_from:
            raise ValueError("the new segment must start after the current segment starts")
        if current.valid_to is not None and current.valid_to != new.valid_from:
            raise ValueError(
                f"current segment is already closed at {current.valid_to}; a new segment must start exactly there, "
                "or be added with add() after the gap (R03-16)"
            )
        closed = replace(current, valid_to=new.valid_from, recorded_at=ensure_aware(recorded_at), source_id=source_id)
        self._validate_row(closed)
        self._check_no_overlap(closed)
        self._check_no_overlap(new, extra_rows=[closed])
        self._versions.append(closed)
        self._versions.append(new)

    # -- lectura ----------------------------------------------------------
    def _known(self, known_at: Optional[datetime]) -> list[SecurityVersion]:
        return self._known_from(self._versions, known_at)

    @staticmethod
    def _known_from(rows: list[SecurityVersion], known_at: Optional[datetime]) -> list[SecurityVersion]:
        if known_at is None:
            return list(rows)
        ka = to_utc(known_at, "known_at")
        return [v for v in rows if to_utc(v.recorded_at) <= ka]

    def _effective(self, known_at: Optional[datetime]) -> list[SecurityVersion]:
        return self._effective_from(self._versions, known_at)

    @classmethod
    def _effective_from(cls, rows: list[SecurityVersion], known_at: Optional[datetime]) -> list[SecurityVersion]:
        """Última fila registrada por segmento ``(security_id, valid_from)``."""
        latest: dict[tuple[str, date], SecurityVersion] = {}
        for v in cls._known_from(rows, known_at):
            key = (v.security_id, v.valid_from)
            cur = latest.get(key)
            if cur is None or to_utc(v.recorded_at) >= to_utc(cur.recorded_at):
                latest[key] = v
        return list(latest.values())

    def versions_of(self, security_id: str, *, known_at: Optional[datetime] = None) -> list[SecurityVersion]:
        """Todas las filas registradas (incluidas las sustituidas): nada se borra."""
        return sorted(
            (v for v in self._known(known_at) if v.security_id == security_id),
            key=lambda v: (to_utc(v.recorded_at), v.valid_from),
        )

    def current_segment(self, security_id: str, *, known_at: Optional[datetime] = None) -> Optional[SecurityVersion]:
        segs = [v for v in self._effective(known_at) if v.security_id == security_id]
        return max(segs, key=lambda v: v.valid_from) if segs else None

    def resolve_symbol(self, symbol: str, *, as_of: date, known_at: Optional[datetime] = None) -> SecurityVersion:
        """Símbolo + fecha → segmento vigente, según lo conocido en ``known_at``."""
        covering = [v for v in self._effective(known_at) if v.symbol == symbol and v.covers(as_of)]
        if not covering:
            raise UnknownSymbol(f"{symbol} as of {as_of.isoformat()}")
        ids = {v.security_id for v in covering}
        if len(ids) > 1:
            raise AmbiguousSymbol(f"{symbol} maps to {sorted(ids)} as of {as_of.isoformat()}")
        return max(covering, key=lambda v: v.valid_from)

    def universe(
        self,
        *,
        as_of: date,
        known_at: Optional[datetime] = None,
        instrument_types: tuple[str, ...] = (ORDINARY_EQUITY,),
        markets: tuple[str, ...] = SIMULATION_MARKETS,
    ) -> list[SecurityVersion]:
        best: dict[str, SecurityVersion] = {}
        for v in self._effective(known_at):
            if not v.covers(as_of):
                continue
            cur = best.get(v.security_id)
            if cur is None or v.valid_from > cur.valid_from:
                best[v.security_id] = v
        out = [v for v in best.values() if v.instrument_type in instrument_types and v.market in markets]
        return sorted(out, key=lambda v: (v.market, v.symbol))

    def terminal_events(self, security_id: str, *, known_at: Optional[datetime] = None) -> list[TerminalEvent]:
        evs = [e for e in self._terminal if e.security_id == security_id]
        if known_at is not None:
            ka = to_utc(known_at, "known_at")
            evs = [e for e in evs if to_utc(e.recorded_at) <= ka]
        return sorted(evs, key=lambda e: to_utc(e.recorded_at))

    def terminal_event(self, security_id: str, *, known_at: Optional[datetime] = None) -> Optional[TerminalEvent]:
        """Último evento terminal conocido en ``known_at``; las revisiones no borran las anteriores."""
        evs = self.terminal_events(security_id, known_at=known_at)
        return evs[-1] if evs else None


@dataclass(frozen=True)
class CoverageStatus:
    security_id: str
    in_catalog: bool
    numerically_scorable: bool
    simulation_eligible: bool
    reasons: tuple[str, ...]


def classify_coverage(
    v: SecurityVersion,
    *,
    price_history_sessions: int,
    min_history_sessions: int,
    trading_status: str = "normal",
    liquidity_ok: Optional[bool] = None,
) -> CoverageStatus:
    """Separa censo, puntuación numérica y elegibilidad de simulación (UNI-05, UNI-06, UNI-07).

    ``liquidity_ok=None`` significa que la regla de capacidad aún no está
    congelada (bloqueante del protocolo): la elegibilidad queda en False con
    motivo explícito, nunca se adivina. ESB y cualquier instrumento distinto
    de acción ordinaria nunca son elegibles sin adaptador propio (R01-08).
    """
    reasons: list[str] = []
    scorable = price_history_sessions >= min_history_sessions
    if not scorable:
        reasons.append(f"insufficient_history:{price_history_sessions}<{min_history_sessions}")
    eligible = scorable
    if v.market not in SIMULATION_MARKETS:
        eligible = False
        reasons.append(f"market_out_of_simulation_scope:{v.market}")
    if v.instrument_type != ORDINARY_EQUITY:
        eligible = False
        reasons.append(f"instrument_out_of_simulation_scope:{v.instrument_type}")
    if trading_status != "normal":
        eligible = False
        reasons.append(f"trading_status:{trading_status}")
    if liquidity_ok is None:
        eligible = False
        reasons.append("liquidity_rule_not_frozen")
    elif not liquidity_ok:
        eligible = False
        reasons.append("liquidity_below_capacity_threshold")
    return CoverageStatus(v.security_id, True, scorable, eligible, tuple(reasons))
