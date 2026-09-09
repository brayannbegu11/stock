"""Comparaciones emparejadas e incertidumbre por bloques de semanas.

Correcciones rondas 1-5 (R01-21, R02-07/08, R03-14, R04-01, R05-02/03/10):
una comparación sólo es emparejada si comparte extremos temporales, tipo de
precio, exposición, moneda y tratamiento de costes. La unidad estadística es
la semana ISO (STA-01). Para la clase prospectiva cada corrida **válida**
debe apuntar a una captura del archivo cuyo sello de producción se
recalcula, cuyos bytes son la predicción canónica archivada
(``forecast_id`` y semana derivada del corte deben coincidir con la
observación), acreditada y archivada antes del plazo de registro del
paquete; una captura no puede acreditar dos semanas. Las corridas inválidas
sin predicción se cuentan como excluidas sin exigirles sello (STA-04, R05-10).
"""
from __future__ import annotations

import json
import math
import random
import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Optional, Sequence

from .store import RawStore
from .timeutil import TAIPEI, to_utc

_WEEK = re.compile(r"^(\d{4})-W(0[1-9]|[1-4]\d|5[0-3])$")
EVIDENCE_PROSPECTIVE = "prospective_registered"


class IntervalMismatch(ValueError):
    pass


class ObservationError(ValueError):
    pass


@dataclass(frozen=True)
class IntervalReturn:
    label: str
    start_at: datetime
    end_at: datetime
    start_price_kind: str   # open | close
    end_price_kind: str     # open | close
    value: Decimal
    exposure: Decimal       # fracción del patrimonio invertida en el intervalo (0..1)
    currency: str = "TWD"
    net_of_costs: bool = True
    week_id: Optional[str] = None

    def pairing_key(self) -> tuple:
        return (to_utc(self.start_at), to_utc(self.end_at), self.start_price_kind, self.end_price_kind,
                self.exposure, self.currency, self.net_of_costs, self.week_id)


def paired_excess(a: IntervalReturn, b: IntervalReturn) -> Decimal:
    """SIM-12 / R01-21: sólo se restan rentabilidades estrictamente comparables."""
    if a.pairing_key() != b.pairing_key():
        raise IntervalMismatch(f"{a.label} {a.pairing_key()} vs {b.label} {b.pairing_key()}")
    return a.value - b.value


def week_monday(week_id: str) -> date:
    m = _WEEK.match(week_id)
    if not m:
        raise ObservationError(f"week_id must be ISO 'YYYY-Www', got {week_id!r}")
    try:
        return date.fromisocalendar(int(m[1]), int(m[2]), 1)
    except ValueError as exc:
        raise ObservationError(f"invalid ISO week {week_id!r}: {exc}") from exc


@dataclass(frozen=True)
class WeeklyObservation:
    week_id: str            # semana ISO del lunes de entrada, p. ej. 2026-W37
    forecast_id: str
    evidence_class: str
    seal_capture_id: Optional[str]   # captura del archivo cuyo sello acredita la predicción (clase prospectiva)
    valid_run: bool         # False → corrida inválida/tardía; se cuenta pero no se usa
    value: Optional[float]  # exceso neto emparejado; None si la corrida no es válida


@dataclass(frozen=True)
class BootstrapResult:
    mean: float
    ci_low: float
    ci_high: float
    n_used: int
    n_invalid_excluded: int
    block_length: int
    seed: int
    evidence_class: str


def _archived_forecast(store: RawStore, capture_id: str, *, allow_test_authorities: bool) -> Optional[dict]:
    """Lee la predicción canónica archivada, la valida contra el contrato y recalcula su sello.

    El plazo de registro no se toma del archivo: se deriva del protocolo a
    partir del corte (que debe ser el corte semanal) y del plazo de emisión,
    que debe ser un 08:30 Taipei dentro de la semana objetivo o, para una
    semana sin sesiones, igual al corte (R06-02, R06-03). ``None`` si algo no cuadra.
    """
    from datetime import time as _time, timedelta as _td
    from .schemas import prediction_validator
    from .weekly import WEEKLY_DEADLINE_TIME, is_weekly_cutoff, target_monday_for, taipei as _taipei
    try:
        rec = store.get(capture_id)
        body = json.loads(store.read(rec).decode("utf-8"))
        forecast = body["forecast"]
        if not isinstance(forecast, dict) or not isinstance(body.get("packet_hash"), str):
            return None
        # el recibo se asigna después de archivar: el sobre sellado no lo contiene por diseño
        candidate = {**forecast, "independent_timestamp_receipt_id": forecast.get("independent_timestamp_receipt_id") or "assigned-after-seal"}
        if any(True for _ in prediction_validator().iter_errors(candidate)):
            return None                                   # el archivo no es una predicción completa del contrato
        cutoff = datetime.fromisoformat(forecast["cutoff_at"])
        deadline = datetime.fromisoformat(forecast["deadline_at"])
    except Exception:
        return None
    if cutoff.tzinfo is None or deadline.tzinfo is None or not is_weekly_cutoff(cutoff):
        return None
    monday = target_monday_for(cutoff)
    week_end = _taipei(monday + _td(days=7), _time(0, 0))
    if to_utc(deadline) == to_utc(cutoff):
        not_after = week_end                                # semana sin sesiones: registro dentro de la semana objetivo
    else:
        local = to_utc(deadline).astimezone(TAIPEI)
        if local.time() != WEEKLY_DEADLINE_TIME or not (monday <= local.date() < monday + _td(days=7)):
            return None                                     # plazo archivado incompatible con el protocolo
        not_after = deadline
    info = store.seal_info(rec, not_after=not_after)
    if info is None or (not info.production and not allow_test_authorities):
        return None
    iso = monday.isocalendar()
    return {"forecast_id": forecast.get("forecast_id"), "week_id": f"{iso[0]}-W{iso[1]:02d}",
            "evidence_class": forecast.get("evidence_class"), "status": forecast.get("status"), "digest": info.digest}


def block_bootstrap_mean(
    observations: Sequence[WeeklyObservation],
    *,
    block_length: int,
    n_boot: int,
    seed: int,
    store: Optional[RawStore] = None,
    require_sealed: bool = False,
    allow_test_authorities: bool = False,
) -> BootstrapResult:
    """Media y percentiles 2,5/97,5 con bootstrap por bloques móviles sobre semanas.

    ``block_length`` no tiene valor por defecto: es un bloqueante del protocolo
    (``statistics.bootstrap_block_length``) y debe fijarse antes de mirar la reserva.
    """
    if not observations:
        raise ObservationError("no observations")
    mondays = [week_monday(o.week_id) for o in observations]
    if len(set(mondays)) != len(mondays):
        raise ObservationError("duplicate week_id: the statistical unit is the week (STA-01)")
    if mondays != sorted(mondays):
        raise ObservationError("observations must be in chronological order for block bootstrap")
    classes = {o.evidence_class for o in observations}
    if len(classes) != 1:
        raise ObservationError(f"mixed evidence classes are not one sample: {sorted(classes)}")
    evidence_class = classes.pop()
    need_seal = require_sealed or evidence_class == EVIDENCE_PROSPECTIVE
    if need_seal:
        if not isinstance(store, RawStore):
            raise ObservationError("prospective evaluation requires the RawStore to recompute seals (R04-01)")
        used: set[str] = set()
        for o in observations:
            if not o.valid_run:
                continue                                  # corrida inválida sin predicción: se cuenta, no se sella (R05-10)
            if not o.seal_capture_id or o.seal_capture_id in used:
                raise ObservationError(f"{o.week_id}: missing or reused seal capture (R05-02)")
            used.add(o.seal_capture_id)
            archived = _archived_forecast(store, o.seal_capture_id, allow_test_authorities=allow_test_authorities)
            if archived is None:
                raise ObservationError(f"{o.week_id}: unsealed, late or unreadable archived forecast (R05-02/03)")
            if archived["forecast_id"] != o.forecast_id or archived["week_id"] != o.week_id or archived["evidence_class"] != evidence_class:
                raise ObservationError(f"{o.week_id}: archived forecast does not match the observation (R05-02)")
            if archived["status"] != "selected":
                raise ObservationError(f"{o.week_id}: archived run status is {archived['status']!r}; it cannot be a valid observation (R06-04)")
    valid = [(m, o) for m, o in zip(mondays, observations) if o.valid_run and o.value is not None]
    for _, o in valid:
        if isinstance(o.value, bool) or not isinstance(o.value, (int, float)) or not math.isfinite(float(o.value)):
            raise ObservationError(f"{o.week_id}: value must be a finite number, got {o.value!r} (R03-14)")
    n_invalid = len(observations) - len(valid)
    n = len(valid)
    if n == 0:
        raise ObservationError("no valid runs")
    if block_length < 1 or block_length > n:
        raise ObservationError("block_length must be within 1..n_valid")
    if block_length > 1:
        for (m1, _), (m2, _) in zip(valid, valid[1:]):
            if (m2 - m1).days != 7:
                raise ObservationError(
                    f"valid weeks are not consecutive between {m1.isoformat()} and {m2.isoformat()}; "
                    "blocks of length > 1 cannot bridge invalid or missing weeks"
                )
    values = [float(o.value) for _, o in valid]  # type: ignore[arg-type]
    rng = random.Random(seed)
    starts = n - block_length + 1
    means: list[float] = []
    for _ in range(n_boot):
        sample: list[float] = []
        while len(sample) < n:
            s = rng.randrange(starts)
            sample.extend(values[s:s + block_length])
        sample = sample[:n]
        means.append(sum(sample) / n)
    means.sort()
    lo = means[int(0.025 * (n_boot - 1))]
    hi = means[int(0.975 * (n_boot - 1))]
    return BootstrapResult(sum(values) / n, lo, hi, n, n_invalid, block_length, seed, evidence_class)
