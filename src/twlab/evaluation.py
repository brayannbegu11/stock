"""Comparaciones emparejadas e incertidumbre por bloques de semanas.

Correcciones rondas 1-7. Una comparación sólo es emparejada si comparte
extremos temporales, tipo de precio, exposición, moneda y tratamiento de
costes. La unidad estadística es la semana ISO (STA-01).

Para la clase prospectiva cada corrida **válida** debe apuntar a una
captura del archivo cuyos bytes son la predicción canónica archivada; el
evaluador (R07-01/02/03/04):

- recalcula el sello (autoridades de producción; las de prueba sólo con la
  bandera explícita);
- **recupera el paquete acreditado** por su hash desde el registro de
  paquetes archivados y ejecuta la misma validación completa que el
  registro de predicciones (``validate_prediction`` con paquete, archivo y
  calendario): esquema, orden temporal, experimento, ranking, calibradores,
  plan semanal re-derivado del calendario, referencias documentales y sello;
- exige que ``forecast_id``, semana y clase de evidencia coincidan con la
  observación, que la corrida archivada sea ``selected`` y que una captura
  no acredite dos semanas.

Las corridas inválidas sin predicción se cuentan como excluidas sin exigirles
sello (STA-04).
"""
from __future__ import annotations

import json
import math
import random
import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Mapping, Optional, Sequence

from .packet import Packet
from .store import RawStore
from .timeutil import to_utc

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


def paired_excess(a: IntervalReturn, b: IntervalReturn, *, exposure_tolerance: Decimal = Decimal(0)) -> Decimal:
    """SIM-12 / R01-21: sólo se restan rentabilidades estrictamente comparables.

    ``exposure_tolerance`` (por defecto 0: igualdad exacta) admite la diferencia de
    exposición que produce el redondeo a lotes enteros entre dos carteras del mismo
    tamaño. Es un valor del protocolo: se declara antes de mirar los datos, nunca se
    elige para que una semana «cuadre».
    """
    tol = Decimal(exposure_tolerance)
    if not tol.is_finite() or tol < 0 or tol >= 1:
        raise ValueError("exposure_tolerance must be a finite Decimal in [0, 1)")
    ka, kb = a.pairing_key(), b.pairing_key()
    same_frame = ka[:4] == kb[:4] and ka[5:] == kb[5:]
    if not same_frame or abs(Decimal(a.exposure) - Decimal(b.exposure)) > tol:
        raise IntervalMismatch(f"{a.label} {ka} vs {b.label} {kb} (exposure_tolerance={tol})")
    return a.value - b.value


def _segments(mondays: Sequence[date]) -> list[tuple[int, int]]:
    """Tramos ``(inicio, longitud)`` de lunes consecutivos (siete días exactos entre vecinos)."""
    if not mondays:
        return []
    segments: list[tuple[int, int]] = []
    start = 0
    for i in range(1, len(mondays) + 1):
        if i == len(mondays) or (mondays[i] - mondays[i - 1]).days != 7:
            segments.append((start, i - start))
            start = i
    return segments


def _block_starts(mondays: Sequence[date], block_length: int) -> list[tuple[int, int]]:
    """Bloques móviles que nunca cruzan un hueco (R02-08).

    Devuelve ``(inicio, longitud)`` dentro de cada tramo de semanas consecutivas.
    Un tramo más corto que el bloque forma un bloque propio: no se pierde la
    observación y ningún bloque une dos semanas que no fueron consecutivas.
    """
    out: list[tuple[int, int]] = []
    for s0, ln in _segments(mondays):
        if ln <= block_length:
            out.append((s0, ln))
        else:
            out.extend((s0 + k, block_length) for k in range(ln - block_length + 1))
    return out


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
    n_segments: int = 1     # tramos de semanas consecutivas entre los que los bloques no cruzan (R02-08)
    resample_mean: float = float("nan")   # media de las medias remuestreadas: diagnóstico de sesgo del remuestreo (R08-11)


def _archived_forecast(
    store: RawStore, capture_id: str, *, packets: Mapping[str, Packet], calendar, known_calibrators,
    allow_test_authorities: bool,
) -> tuple[Optional[dict], str]:
    """Lee la predicción canónica archivada, recupera su paquete y la valida por completo.

    Devuelve ``(resumen, motivo)``; ``resumen`` es ``None`` si algo no cuadra.
    """
    from .schemas import RECEIPT_FIELD, validate_prediction
    from .weekly import target_monday_for
    try:
        rec = store.get(capture_id)
        body = json.loads(store.read(rec).decode("utf-8"))
        forecast = body["forecast"]
        packet_hash = body.get("packet_hash")
    except Exception as exc:
        return None, f"unreadable archive: {exc}"
    if not isinstance(forecast, dict) or not isinstance(packet_hash, str):
        return None, "archive is not a sealed forecast envelope"
    packet = packets.get(packet_hash)
    if packet is None or packet.packet_hash() != packet_hash or packet.packet_id != forecast.get("packet_id"):
        return None, "accredited packet not found in the packet registry (R07-03)"
    # El registro no es de confianza: un paquete recuperado vuelve a pasar el filtro de admisión (R08-01).
    from .packet import readmission_problems
    readmit = readmission_problems(packet, store=store)
    if readmit:
        return None, "recovered packet fails readmission: " + "; ".join(readmit[:5])
    receipt = rec.receipt_obj
    candidate = {**forecast, RECEIPT_FIELD: receipt.receipt_id if receipt else "missing"}
    problems = validate_prediction(candidate, packet, store=store, calendar=calendar, known_calibrators=known_calibrators,
                                   allow_test_authorities=allow_test_authorities)
    if problems:
        return None, "; ".join(problems[:5])
    monday = target_monday_for(packet.cutoff_at)
    iso = monday.isocalendar()
    return {"forecast_id": forecast.get("forecast_id"), "week_id": f"{iso[0]}-W{iso[1]:02d}",
            "evidence_class": forecast.get("evidence_class"), "status": forecast.get("status")}, "ok"


def block_bootstrap_mean(
    observations: Sequence[WeeklyObservation],
    *,
    block_length: int,
    n_boot: int,
    seed: int,
    store: Optional[RawStore] = None,
    packets: Optional[Mapping[str, Packet]] = None,
    calendar=None,
    known_calibrators=None,
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
        if not isinstance(packets, Mapping) or calendar is None:
            raise ObservationError("prospective evaluation requires the packet registry and the calendar (R07-03/04)")
        used: set[str] = set()
        for o in observations:
            if not o.valid_run:
                continue                                  # corrida inválida sin predicción: se cuenta, no se sella (R05-10)
            if not o.seal_capture_id or o.seal_capture_id in used:
                raise ObservationError(f"{o.week_id}: missing or reused seal capture (R05-02)")
            used.add(o.seal_capture_id)
            archived, why = _archived_forecast(store, o.seal_capture_id, packets=packets, calendar=calendar,
                                               known_calibrators=known_calibrators,
                                               allow_test_authorities=allow_test_authorities)
            if archived is None:
                raise ObservationError(f"{o.week_id}: archived forecast rejected: {why}")
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
    # Las semanas inválidas o ausentes parten la serie en tramos; los bloques se muestrean dentro de cada
    # tramo y nunca unen dos semanas que no fueron consecutivas (R02-08). Con un solo tramo sin huecos el
    # muestreo es el bootstrap por bloques móviles clásico.
    values = [float(o.value) for _, o in valid]  # type: ignore[arg-type]
    valid_mondays = [m for m, _ in valid]
    starts = _block_starts(valid_mondays, block_length)
    n_segments = len(_segments(valid_mondays))
    # Ponderación (R08-11): el tramo se elige con probabilidad proporcional a su longitud y el bloque
    # uniformemente dentro del tramo; así cada tramo pesa lo que pesa en la muestra, no según cuántos
    # bloques caben en él. Con un solo tramo equivale al bootstrap por bloques móviles clásico.
    segments = _segments(valid_mondays)
    blocks_by_segment = [[(s0, ln) for s0, ln in starts if seg0 <= s0 < seg0 + seg_len] for seg0, seg_len in segments]
    cumulative: list[int] = []
    acc = 0
    for _, seg_len in segments:
        acc += seg_len
        cumulative.append(acc)
    rng = random.Random(seed)
    means: list[float] = []
    for _ in range(n_boot):
        sample: list[float] = []
        while len(sample) < n:
            u = rng.randrange(n)
            seg_idx = next(i for i, c in enumerate(cumulative) if u < c)
            blocks = blocks_by_segment[seg_idx]
            s0, ln = blocks[rng.randrange(len(blocks))]
            sample.extend(values[s0:s0 + ln])
        sample = sample[:n]
        means.append(sum(sample) / n)
    resample_mean = sum(means) / len(means)
    means.sort()
    lo = means[int(0.025 * (n_boot - 1))]
    hi = means[int(0.975 * (n_boot - 1))]
    return BootstrapResult(sum(values) / n, lo, hi, n, n_invalid, block_length, seed, evidence_class, n_segments, resample_mean)
