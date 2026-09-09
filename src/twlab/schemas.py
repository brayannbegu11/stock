"""Validación de predicciones contra el contrato adjunto, el paquete y el protocolo.

Correcciones rondas 1-4 (R01-18/19/22, R02-06/07/09/20, R03-02/04/13/17, R04-01..04, R04-13):

- Orden temporal estricto ``cutoff < issued_at <= deadline_at`` para ``selected``.
- El plazo lo fija el paquete (derivado del calendario y del protocolo); una
  predicción ``selected`` sin paquete no puede validarse.
- Igualdad de ``packet_id`` y ``cutoff_at`` con el paquete; unicidad de valores
  y rangos; experimento registrado; tipos comprobados antes de usarse.
- TXT-07: calibrador registrado con ventana cerrada antes del corte y
  evaluación fuera de muestra, tipos validados.
- Evidencia ``prospective_registered``: el validador **no acepta sellos
  suministrados por el llamante**. Recibe el ``RawStore`` y recalcula el sello
  de la captura cuyo digest debe ser exactamente ``sealed_forecast_digest``:
  el sha256 de la serialización canónica de la predicción (sin el campo del
  recibo) más el ``packet_hash``. Así ranking, identificadores, corte y
  paquete quedan dentro de lo acreditado (R04-01/02/03). El sello se recalcula
  con ``not_after = deadline`` (R04-04) y sólo cuentan autoridades de
  producción (P2).
- Semana ``invalid:no_sessions``: la corrida se registra como ``invalid`` con
  ``deadline_at == cutoff_at`` (ventana nula), sin inventar un plazo futuro (R04-13).
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, FrozenSet, Mapping, Optional

from jsonschema import Draft202012Validator, FormatChecker

from .packet import EVIDENCE_PROSPECTIVE, MODE_PROSPECTIVE, Packet, canonical_bytes, validate_document_references
from .store import RawStore
from .timeutil import TAIPEI, ensure_aware, is_after, to_utc
from datetime import time, timedelta

from .timeutil import taipei
from .weekly import (  # noqa: F401  (weekly_deadline re-exportado)
    STATUS_NO_SESSIONS, STATUS_VALID, WEEKLY_DEADLINE_TIME, is_weekly_cutoff, plan_week, target_monday_for,
    weekly_deadline,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
PREDICTION_SCHEMA_PATH = REPO_ROOT / "docs" / "spec" / "v2" / "PREDICCION.schema.json"
EXPERIMENTS_PATH = REPO_ROOT / "docs" / "spec" / "v2" / "EXPERIMENTOS.json"
RECEIPT_FIELD = "independent_timestamp_receipt_id"


@dataclass(frozen=True)
class CalibratorRecord:
    calibrator_id: str
    trained_until: datetime          # fin de la ventana de ajuste (aware)
    evaluated_out_of_sample: bool

    def __post_init__(self) -> None:
        if not isinstance(self.calibrator_id, str) or not self.calibrator_id:
            raise ValueError("calibrator_id must be a non-empty string")
        ensure_aware(self.trained_until, "trained_until")
        if not isinstance(self.evaluated_out_of_sample, bool):
            raise TypeError("evaluated_out_of_sample must be a bool")


def load_prediction_schema() -> dict:
    return json.loads(PREDICTION_SCHEMA_PATH.read_text(encoding="utf-8"))


def registered_experiment_ids() -> FrozenSet[str]:
    return frozenset(e["experiment_id"] for e in json.loads(EXPERIMENTS_PATH.read_text(encoding="utf-8")))


def sealed_forecast_bytes(obj: Mapping[str, Any], packet: Packet) -> bytes:
    """Bytes que se archivan y sellan: predicción completa (sin el recibo, que se asigna después) + hash del paquete."""
    body = {k: v for k, v in obj.items() if k != RECEIPT_FIELD}
    return canonical_bytes({"forecast": body, "packet_hash": packet.packet_hash()})


def sealed_forecast_digest(obj: Mapping[str, Any], packet: Packet) -> str:
    return hashlib.sha256(sealed_forecast_bytes(obj, packet)).hexdigest()


_validator: Optional[Draft202012Validator] = None


def prediction_validator() -> Draft202012Validator:
    global _validator
    if _validator is None:
        schema = load_prediction_schema()
        Draft202012Validator.check_schema(schema)
        _validator = Draft202012Validator(schema, format_checker=FormatChecker())
    return _validator


def _parse(obj: dict[str, Any], key: str, problems: list[str]) -> Optional[datetime]:
    v = obj.get(key)
    if not isinstance(v, str):
        return None
    try:
        dt = datetime.fromisoformat(v)
    except ValueError:
        problems.append(f"{key}:not_iso8601:{v}")
        return None
    if dt.tzinfo is None:
        problems.append(f"{key}:naive_datetime:{v}")
        return None
    return dt


def _packet_plan_problems(packet: Packet, calendar) -> list[str]:
    """El paquete lo construye el llamante: se comprueba que su plan sea el del protocolo (R05-11)."""
    out: list[str] = []
    if packet.week_status is None:
        return ["packet_without_protocol_week_plan"]
    if packet.week_status not in (STATUS_VALID, STATUS_NO_SESSIONS):
        out.append(f"packet_week_status_unknown:{packet.week_status}")
    if not is_weekly_cutoff(packet.cutoff_at):
        out.append("packet_cutoff_is_not_the_weekly_protocol_cutoff")
    # sin calendario también se comprueba lo que el protocolo determina por sí solo (R06-05)
    monday = target_monday_for(packet.cutoff_at)
    iso = monday.isocalendar()
    week_end = taipei(monday + timedelta(days=7), time(0, 0))
    if packet.week_id != f"{iso[0]}-W{iso[1]:02d}":
        out.append("packet_week_id_does_not_match_cutoff")
    if packet.week_status == STATUS_VALID:
        if packet.deadline_at is None or packet.entry_at is None or packet.exit_at is None:
            out.append("packet_valid_week_without_deadline_entry_or_exit")
        else:
            local = to_utc(packet.deadline_at).astimezone(TAIPEI)
            in_week = all(monday <= to_utc(x).astimezone(TAIPEI).date() < monday + timedelta(days=7)
                          for x in (packet.deadline_at, packet.entry_at, packet.exit_at))
            if (local.time() != WEEKLY_DEADLINE_TIME or not in_week or not is_after(packet.entry_at, packet.deadline_at)
                    or not is_after(packet.exit_at, packet.entry_at)):
                out.append("packet_plan_inconsistent_with_protocol")
            if packet.registration_deadline_at is None or to_utc(packet.registration_deadline_at) != to_utc(packet.deadline_at):
                out.append("packet_registration_deadline_must_equal_forecast_deadline")
    elif packet.week_status == STATUS_NO_SESSIONS:
        if packet.entry_at is not None or packet.exit_at is not None:
            out.append("packet_no_sessions_week_cannot_have_entry_or_exit")
        if packet.registration_deadline_at is None or to_utc(packet.registration_deadline_at) != to_utc(week_end):
            out.append("packet_registration_deadline_must_be_end_of_target_week")
    if calendar is not None:
        try:
            plan = plan_week(packet.cutoff_at, calendar)
        except Exception as exc:
            return out + [f"packet_plan_not_reproducible:{exc}"]
        expected = (plan.week_id, plan.status, plan.deadline_at, plan.entry_at, plan.exit_at, plan.registration_deadline_at)
        got = (packet.week_id, packet.week_status, packet.deadline_at, packet.entry_at, packet.exit_at, packet.registration_deadline_at)
        if [to_utc(x) if isinstance(x, datetime) else x for x in expected] != [to_utc(x) if isinstance(x, datetime) else x for x in got]:
            out.append("packet_plan_does_not_match_calendar")
    return out


def validate_prediction(
    obj: dict[str, Any],
    packet: Optional[Packet] = None,
    *,
    known_calibrators: Optional[Mapping[str, CalibratorRecord]] = None,
    store: Optional[RawStore] = None,
    calendar=None,
    experiment_ids: Optional[FrozenSet[str]] = None,
    allow_test_authorities: bool = False,
) -> list[str]:
    """Devuelve la lista de problemas; vacía si la predicción es válida.

    ``allow_test_authorities`` sólo debe usarse en pruebas: permite sellos de
    autoridades de prueba registradas en el ``RawStore``. Las autoridades de
    producción se resuelven únicamente en ``twlab.seals`` (R05-01).
    """
    if not isinstance(obj, dict):
        return ["not_an_object"]
    problems = [
        f"schema:{'/'.join(str(p) for p in e.path) or '$'}:{e.message}"
        for e in prediction_validator().iter_errors(obj)
    ]
    cutoff = _parse(obj, "cutoff_at", problems)
    issued = _parse(obj, "issued_at", problems)
    deadline = _parse(obj, "deadline_at", problems)
    status = obj.get("status") if isinstance(obj.get("status"), str) else None
    evidence = obj.get("evidence_class") if isinstance(obj.get("evidence_class"), str) else None
    if packet is not None:
        problems.extend(_packet_plan_problems(packet, calendar))
    week_invalid = packet is not None and packet.week_status == STATUS_NO_SESSIONS
    if cutoff and deadline and not is_after(deadline, cutoff) and not (week_invalid and to_utc(deadline) == to_utc(cutoff)):
        problems.append("temporal:deadline_not_after_cutoff")
    if cutoff and issued and not is_after(issued, cutoff):
        problems.append("temporal:issued_not_after_cutoff")
    if issued and deadline and is_after(issued, deadline) and status == "selected":
        problems.append("temporal:late_forecast_cannot_be_selected (late_forecast_policy: no_new_positions)")
    exp_ids = experiment_ids if experiment_ids is not None else registered_experiment_ids()
    exp = obj.get("experiment_id")
    if not isinstance(exp, str) or exp not in exp_ids:
        problems.append(f"experiment_id_not_registered:{exp!r}")
    if packet is None:
        if status == "selected":
            problems.append("packet_required_for_selected_forecast")
    else:
        if obj.get("packet_id") != packet.packet_id:
            problems.append(f"packet_id_mismatch:{obj.get('packet_id')}!={packet.packet_id}")
        if cutoff and to_utc(cutoff) != to_utc(packet.cutoff_at):
            problems.append(f"cutoff_mismatch:{to_utc(cutoff).isoformat()}!={to_utc(packet.cutoff_at).isoformat()}")
        if packet.week_status is None:
            pass  # ya informado por _packet_plan_problems
        elif week_invalid:
            if status != "invalid":
                problems.append(f"week_{packet.week_status}:only_invalid_runs_allowed")
            if deadline and cutoff and to_utc(deadline) != to_utc(cutoff):
                problems.append("week_invalid:deadline_must_equal_cutoff (null window; no fictitious deadline)")
        elif packet.week_status == STATUS_VALID:
            if packet.deadline_at is None:
                problems.append("packet_without_protocol_deadline")
            elif deadline and to_utc(deadline) != to_utc(packet.deadline_at):
                problems.append(f"deadline_mismatch:{to_utc(deadline).isoformat()}!=protocol {to_utc(packet.deadline_at).isoformat()}")
        if evidence == EVIDENCE_PROSPECTIVE and packet.mode != MODE_PROSPECTIVE:
            problems.append(f"evidence_class_incompatible_with_packet_mode:{packet.mode}")
    if evidence == EVIDENCE_PROSPECTIVE:
        rid = obj.get(RECEIPT_FIELD)
        if packet is None:
            problems.append("prospective_requires_packet")
        elif not isinstance(store, RawStore):
            problems.append("prospective_requires_raw_store_to_recompute_seal")
        elif not isinstance(rid, str):
            problems.append(f"prospective_receipt_not_sealed:{rid!r}")
        else:
            expected = sealed_forecast_digest(obj, packet)
            not_after = packet.registration_deadline_at or packet.deadline_at or packet.cutoff_at
            seals = store.seals(not_after=not_after, allow_test_authorities=allow_test_authorities)
            seal = next((s for s in seals.values() if s.receipt_id == rid), None)
            if seal is None:
                problems.append(f"prospective_receipt_not_sealed:{rid!r} (no production seal attested and archived by {to_utc(not_after).isoformat()})")
            elif seal.digest != expected:
                problems.append("prospective_seal_digest_does_not_cover_this_forecast_and_packet")
    ranking = obj.get("ranking", []) or []
    if not isinstance(ranking, list):
        ranking = []
    seen_sec: set[str] = set()
    seen_rank: set[int] = set()
    for i, item in enumerate(ranking):
        if not isinstance(item, dict):
            problems.append(f"ranking[{i}]:not_an_object")
            continue
        sid, rank = item.get("security_id"), item.get("rank")
        if not isinstance(sid, str):
            problems.append(f"ranking[{i}]:security_id_not_string")
        elif sid in seen_sec:
            problems.append(f"duplicate_security_id:{sid}")
        else:
            seen_sec.add(sid)
        if not isinstance(rank, int) or isinstance(rank, bool):
            problems.append(f"ranking[{i}]:rank_not_int")
        elif rank in seen_rank:
            problems.append(f"duplicate_rank:{rank}")
        else:
            seen_rank.add(rank)
        if packet is not None:
            refs = item.get("document_ids", []) or []
            refs = [r for r in refs if isinstance(r, str)] if isinstance(refs, list) else []
            missing = validate_document_references(refs, packet)
            if missing:
                problems.append(f"TXT-05:rank{rank}:unknown_documents:{missing}")
        prob = item.get("calibrated_probability")
        cal_id = item.get("calibration_model_id")
        if prob is not None:
            if not isinstance(known_calibrators, Mapping):
                problems.append(f"TXT-07:rank{rank}:calibrator_registry_missing_or_invalid")
            elif not isinstance(cal_id, str) or cal_id not in known_calibrators:
                problems.append(f"TXT-07:rank{rank}:calibrator_not_registered:{cal_id!r}")
            else:
                rec = known_calibrators[cal_id]
                if not isinstance(rec, CalibratorRecord):
                    problems.append(f"TXT-07:rank{rank}:calibrator_record_invalid:{cal_id}")
                else:
                    if rec.evaluated_out_of_sample is not True:
                        problems.append(f"TXT-07:rank{rank}:calibrator_not_evaluated_out_of_sample:{cal_id}")
                    if cutoff and is_after(rec.trained_until, cutoff):
                        problems.append(f"TXT-07:rank{rank}:calibrator_trained_after_cutoff:{cal_id}")
    if ranking and sorted(seen_rank) != list(range(1, len(ranking) + 1)):
        problems.append("ranks_not_contiguous_from_1")
    return problems
