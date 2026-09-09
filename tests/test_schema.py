import hashlib
from copy import deepcopy
from dataclasses import replace
from datetime import date, datetime, time, timedelta

import pytest

from twlab.calendar import TradingCalendar, load_twse_reference_calendar_2026
from twlab.packet import Document, Rejection, build_packet, packet_from_json, packet_to_json
from twlab.schemas import (
    CalibratorRecord, registered_experiment_ids, sealed_forecast_bytes, sealed_forecast_digest, semantic_problems,
    validate_prediction,
)
from twlab.store import RawStore, SealInfo
from twlab.timeutil import TAIPEI, AvailabilityQuality as Q, taipei
from twlab.weekly import NoSessionsInWeek, weekly_deadline

CAL = load_twse_reference_calendar_2026()
CUTOFF = taipei(date(2026, 9, 6), time(18, 0))
DEADLINE = taipei(date(2026, 9, 7), time(8, 30))
CALS = {"cal-2025": CalibratorRecord("cal-2025", datetime(2025, 12, 31, tzinfo=TAIPEI), True)}
# Calendario sintético lejano para escenarios prospectivos con reloj real: plazos en el futuro.
# La semana del 14-20 de enero de 2030 está cerrada para probar corridas sin sesiones.
CAL_2030 = TradingCalendar(start=date(2030, 1, 1), end=date(2030, 12, 31),
                           closures=[date(2030, 1, d) for d in range(14, 19)], source_id="synthetic-2030",
                           recorded_at=datetime(2026, 1, 1, tzinfo=TAIPEI))
CUTOFF_2030 = taipei(date(2030, 1, 6), time(18, 0))      # domingo → semana 2030-W02 válida
CUTOFF_2030_EMPTY = taipei(date(2030, 1, 13), time(18, 0))   # domingo → semana 2030-W03 sin sesiones


def calendar_for(pkt):
    if pkt is None or pkt.calendar_version is None:
        return None
    return CAL_2030 if pkt.calendar_version.startswith("synthetic-2030") else CAL


def vp(obj, pkt=None, **kw):
    """validate_prediction con el calendario que corresponde al paquete (obligatorio desde R07-04)."""
    kw.setdefault("calendar", calendar_for(pkt))
    return validate_prediction(obj, pkt, **kw)


def packet(**kw):
    d = Document(doc_id="doc-1", kind="news", source_id="t", security_ids=("SEC-1",),
                 available_at=taipei(date(2026, 9, 1), time(9, 0)), availability_quality=Q.VERIFIED_ORIGINAL)
    args = dict(packet_id="pkt-1", cutoff_at=CUTOFF, documents=[d], mode="historical",
                evidence_class="historical_current_llm_exploratory", calendar=CAL)
    args.update(kw)
    return build_packet(**args)


def prospective_packet(cutoff=CUTOFF_2030, **kw):
    args = dict(packet_id="pkt-p", cutoff_at=cutoff, documents=[], mode="prospective", evidence_class="prospective_registered",
                calendar=CAL_2030, captures={}, read_bytes=lambda r: b"", extractors={})
    args.update(kw)
    return build_packet(**args)


def base(**over):
    obj = {
        "schema_version": "2.0", "forecast_id": "f-1", "experiment_id": "L1", "protocol_version": "2.0-draft",
        "packet_id": "pkt-1", "cutoff_at": "2026-09-06T18:00:00+08:00", "issued_at": "2026-09-07T07:00:00+08:00",
        "deadline_at": "2026-09-07T08:30:00+08:00", "timezone": "Asia/Taipei",
        "evidence_class": "historical_current_llm_exploratory",
        "model": {"requested_id": "claude-fable-5-1", "returned_id": "claude-fable-5-1", "revision_id": None,
                  "prompt_or_feature_version": "p1", "training_manifest_id": None},
        "coverage": {"catalog_count": 1984, "scored_count": 1700, "deep_review_count": 50, "eligible_count": 1500,
                     "missing_critical_sources": []},
        "status": "selected",
        "ranking": [{"security_id": "SEC-1", "ticker_as_of": "2330", "market": "TWSE", "rank": 1, "score": 0.7,
                     "score_definition": "relative_weekly_return_score", "document_ids": ["doc-1"], "feature_ids": [],
                     "impact_hypothesis": "x", "counterargument": "y", "calibrated_probability": None,
                     "calibration_model_id": None}],
        "limitations": ["exploratory"],
    }
    obj.update(over)
    return obj


def prospective_forecast(pkt, **over):
    obj = base(packet_id=pkt.packet_id, evidence_class="prospective_registered", cutoff_at=pkt.cutoff_at.isoformat(),
               issued_at=(pkt.cutoff_at + timedelta(minutes=30)).isoformat(),
               deadline_at=(pkt.deadline_at or pkt.cutoff_at).isoformat())
    obj["ranking"][0]["document_ids"] = []
    obj.update(over)
    return obj


def archive_and_seal(tmp_path, obj, pkt, *, authority="fixture", attested_at=None, verifier=None):
    """Flujo real: la predicción se serializa con el hash del paquete, se archiva y se sella (autoridad de prueba)."""
    store = RawStore(tmp_path, verifiers={authority: verifier or (lambda rec, rc: rc.digest == rec.sha256)})
    obj["raw_response_hash"] = hashlib.sha256(b"model raw response").hexdigest()   # conocido al emitir
    raw = sealed_forecast_bytes(obj, pkt)                                          # predicción completa + hash del paquete
    rec = store.put(source_id="forecast", dataset=obj["experiment_id"], payload=raw, url="model://fable")
    store.attach_receipt(rec.capture_id, receipt_id=f"{authority}:f1", authority=authority, digest=rec.sha256,
                         attested_at=attested_at or rec.ingested_at)
    obj["independent_timestamp_receipt_id"] = f"{authority}:f1"                    # asignado después del sello
    return store, rec


def validate_test(obj, pkt, store):
    return vp(obj, pkt, store=store, allow_test_authorities=True)


def test_valid_prediction_passes():
    assert vp(base(), packet()) == []
    assert semantic_problems(base()) == []


def test_r07_04_calendar_is_required_to_verify_a_packet_plan():
    assert "calendar_required_to_verify_packet_plan" in validate_prediction(base(), packet())
    assert validate_prediction(base(), packet(), calendar=CAL) == []
    assert "packet_calendar_version_mismatch" in validate_prediction(base(), packet(), calendar=CAL_2030) or \
        "packet_plan_not_reproducible" in " ".join(validate_prediction(base(), packet(), calendar=CAL_2030))


def test_weekly_deadline_derives_from_protocol_and_calendar(cal):
    assert weekly_deadline(CUTOFF, cal) == DEADLINE
    assert weekly_deadline(taipei(date(2026, 2, 8), time(18, 0)), cal) == taipei(date(2026, 2, 9), time(8, 30))
    with pytest.raises(NoSessionsInWeek):
        weekly_deadline(taipei(date(2026, 2, 15), time(18, 0)), cal)      # R03-03: no salta a la semana siguiente


def test_experiment_registry_is_loaded_from_spec():
    assert {"Q0", "Q1", "H1", "L1", "L2"} <= registered_experiment_ids()
    assert any(p.startswith("experiment_id_not_registered") for p in vp(base(experiment_id="ZZ")))
    assert any(p.startswith("experiment_id_not_registered") for p in vp(base(experiment_id=[]), packet()))


def test_txt05_unknown_document_reference_fails():
    obj = base()
    obj["ranking"][0]["document_ids"] = ["doc-1", "ghost"]
    assert any(p.startswith("TXT-05") for p in vp(obj, packet()))


def test_txt07_probability_without_calibrator_fails():
    obj = base()
    obj["ranking"][0]["calibrated_probability"] = 0.9
    assert any("calibration_model_id" in p for p in vp(obj))


def test_r01_22_r02_09_r03_17_calibrator_registry_with_validated_temporal_evidence():
    obj = base()
    obj["ranking"][0].update(calibrated_probability=0.9, calibration_model_id="inventado")
    assert any(p.startswith("TXT-07") for p in vp(obj, packet()))
    assert any("registry_missing" in p for p in vp(obj, packet(), known_calibrators=frozenset({"inventado"})))  # type: ignore[arg-type]
    obj["ranking"][0]["calibration_model_id"] = "cal-2025"
    assert vp(obj, packet(), known_calibrators=CALS) == []
    future = {"trained-2027": CalibratorRecord("trained-2027", datetime(2027, 1, 1, tzinfo=TAIPEI), True)}
    obj["ranking"][0]["calibration_model_id"] = "trained-2027"
    assert any("trained_after_cutoff" in p for p in vp(obj, packet(), known_calibrators=future))
    unevaluated = {"cal-x": CalibratorRecord("cal-x", datetime(2025, 1, 1, tzinfo=TAIPEI), False)}
    obj["ranking"][0]["calibration_model_id"] = "cal-x"
    assert any("not_evaluated_out_of_sample" in p for p in vp(obj, packet(), known_calibrators=unevaluated))
    with pytest.raises(TypeError):
        CalibratorRecord("cal", datetime(2025, 12, 31, tzinfo=TAIPEI), "false")   # type: ignore[arg-type]
    with pytest.raises(ValueError):
        CalibratorRecord("cal", datetime(2025, 12, 31), True)                        # naive
    obj["ranking"][0]["calibration_model_id"] = "cal"
    assert any("calibrator_record_invalid" in p for p in vp(obj, packet(), known_calibrators={"cal": "not a record"}))  # type: ignore[dict-item]


def test_abstained_requires_reason_and_empty_ranking():
    assert vp(base(status="abstained", ranking=[])) != []
    assert vp(base(status="abstained", ranking=[], status_reason="insufficient evidence")) == []


# ---- cadena prospectiva: sello ↔ predicción ↔ paquete ---------------------------
def test_r02_07_r03_04_r04_02_r04_03_seal_covers_forecast_and_packet(tmp_path):
    pkt = prospective_packet()
    obj = prospective_forecast(pkt)
    assert any("independent_timestamp_receipt_id" in p for p in vp(obj))
    obj["independent_timestamp_receipt_id"] = "inventado"
    assert any(p.startswith("prospective_requires_raw_store") for p in vp(obj, pkt))
    assert any(p.startswith("evidence_class_incompatible") for p in vp(obj, packet()))
    store, rec = archive_and_seal(tmp_path, obj, pkt)
    assert validate_test(obj, pkt, store) == []
    assert rec.sha256 == sealed_forecast_digest(obj, pkt)
    # R04-02: cambiar el ranking o el identificador tras sellar invalida el sello
    tampered = deepcopy(obj)
    tampered["ranking"][0]["security_id"] = "FUTURE-WINNER"
    assert "prospective_seal_digest_does_not_cover_this_forecast_and_packet" in validate_test(tampered, pkt, store)
    tampered2 = deepcopy(obj)
    tampered2["forecast_id"] = "retroactive-replacement"
    assert "prospective_seal_digest_does_not_cover_this_forecast_and_packet" in validate_test(tampered2, pkt, store)
    # R04-03: el mismo sello no sirve para otro paquete (el hash del paquete está dentro del digest)
    other = prospective_packet(cutoff=CUTOFF_2030 + timedelta(days=14))
    moved = prospective_forecast(other, independent_timestamp_receipt_id=obj["independent_timestamp_receipt_id"],
                                 raw_response_hash=obj["raw_response_hash"])
    assert "prospective_seal_digest_does_not_cover_this_forecast_and_packet" in validate_test(moved, other, store)
    # un recibo ajeno (otros bytes) tampoco
    foreign = store.put(source_id="weather", dataset="rain", payload=b"weather:rain=0", url="u")
    store.attach_receipt(foreign.capture_id, receipt_id="fixture:w", authority="fixture", digest=foreign.sha256, attested_at=foreign.ingested_at)
    obj2 = deepcopy(obj)
    obj2["independent_timestamp_receipt_id"] = "fixture:w"
    assert "prospective_seal_digest_does_not_cover_this_forecast_and_packet" in validate_test(obj2, pkt, store)


def test_packet_archive_round_trip_preserves_hash(tmp_path):
    pkt = packet()
    raw = packet_to_json(pkt)
    back = packet_from_json(raw)
    assert back.packet_hash() == pkt.packet_hash() and back.admitted_ids() == {"doc-1"} and back.deadline_at == DEADLINE
    with pytest.raises(ValueError):
        packet_from_json(raw.replace(b'"pkt-1"', b'"pkt-9"'))


def test_r05_04_rejections_visible_to_the_predictor_are_inside_the_seal(tmp_path):
    pkt = prospective_packet()
    obj = prospective_forecast(pkt)
    store, _ = archive_and_seal(tmp_path, obj, pkt)
    assert validate_test(obj, pkt, store) == []
    changed = replace(pkt, rejected=(Rejection("future", "available_after_cutoff", "2030-W02 future winner A +50%"),))
    assert changed.packet_hash() != pkt.packet_hash()
    assert "prospective_seal_digest_does_not_cover_this_forecast_and_packet" in validate_test(obj, changed, store)


def test_r04_01_r05_01_seals_cannot_be_supplied_or_trusted_from_the_caller(tmp_path):
    pkt = prospective_packet()
    obj = prospective_forecast(pkt, independent_timestamp_receipt_id="fake", raw_response_hash="0" * 64)
    fake = SealInfo("fake", "fixture", "nonexistent", "0" * 64, CUTOFF_2030, CUTOFF_2030, True, {"packet_hash": pkt.packet_hash()})
    with pytest.raises(TypeError):
        validate_prediction(obj, pkt, seals={"fake": fake})   # type: ignore[call-arg]
    assert any(p.startswith("prospective_requires_raw_store") for p in vp(obj, pkt, store={"fake": fake}))  # type: ignore[arg-type]
    empty = RawStore(tmp_path / "empty")
    assert any(p.startswith("prospective_receipt_not_sealed") for p in vp(obj, pkt, store=empty))
    obj2 = prospective_forecast(pkt)
    store, _ = archive_and_seal(tmp_path / "trivial", obj2, pkt, verifier=lambda rec, rc: True)
    assert any(p.startswith("prospective_receipt_not_sealed") for p in vp(obj2, pkt, store=store))
    assert validate_test(obj2, pkt, store) == []
    from twlab.store import UntrustedVerifier
    with pytest.raises(UntrustedVerifier):
        RawStore(tmp_path / "prod", verifiers={"opentimestamps": lambda rec, rc: True})


def test_r04_04_attestation_after_deadline_is_rejected(tmp_path):
    pkt = prospective_packet()
    obj = prospective_forecast(pkt)
    late = (pkt.deadline_at + timedelta(days=7)).isoformat()
    store, _ = archive_and_seal(tmp_path, obj, pkt, attested_at=late, verifier=lambda rec, rc: rc.digest == rec.sha256)
    assert store.seals(allow_test_authorities=True) and store.seals(not_after=pkt.deadline_at, allow_test_authorities=True) == {}
    assert any(p.startswith("prospective_receipt_not_sealed") for p in validate_test(obj, pkt, store))


def test_r05_09_invalid_week_prospective_run_can_be_registered_after_the_cutoff(tmp_path):
    pkt = prospective_packet(cutoff=CUTOFF_2030_EMPTY)
    assert pkt.week_status == "invalid:no_sessions" and pkt.deadline_at is None
    assert pkt.registration_deadline_at == taipei(date(2030, 1, 21), time(0, 0))
    obj = prospective_forecast(pkt, status="invalid", ranking=[], status_reason="no_sessions",
                               deadline_at=CUTOFF_2030_EMPTY.isoformat())
    store, rec = archive_and_seal(tmp_path, obj, pkt)
    assert validate_test(obj, pkt, store) == []
    late = (pkt.registration_deadline_at + timedelta(hours=1)).isoformat()
    store2, _ = archive_and_seal(tmp_path / "late", obj, pkt, attested_at=late, verifier=lambda rec, rc: True)
    assert any(p.startswith("prospective_receipt_not_sealed") for p in validate_test(obj, pkt, store2))


def test_r06_05_registration_deadline_cannot_extend_the_seal_window(tmp_path):
    pkt = prospective_packet()
    forged = replace(pkt, registration_deadline_at=pkt.deadline_at + timedelta(days=7))
    obj = prospective_forecast(forged)
    store, _ = archive_and_seal(tmp_path, obj, forged, attested_at=forged.registration_deadline_at.isoformat())
    assert validate_test(obj, forged, store)             # el plan es inconsistente y el sello llega tarde


def test_r07_04_shifted_deadline_within_the_week_is_rejected_because_the_calendar_is_mandatory(tmp_path):
    pkt = prospective_packet()
    shifted = replace(pkt, deadline_at=pkt.deadline_at + timedelta(days=4), registration_deadline_at=pkt.deadline_at + timedelta(days=4),
                      entry_at=pkt.entry_at + timedelta(days=4))
    obj = prospective_forecast(shifted, issued_at=(shifted.deadline_at - timedelta(minutes=1)).isoformat())
    store, _ = archive_and_seal(tmp_path, obj, shifted, attested_at=shifted.deadline_at.isoformat())
    problems = validate_test(obj, shifted, store)
    assert "packet_plan_does_not_match_calendar" in problems
    assert "calendar_required_to_verify_packet_plan" in validate_prediction(obj, shifted, store=store, allow_test_authorities=True)


def test_r07_05_no_sessions_packet_must_have_null_deadline():
    p = prospective_packet(cutoff=CUTOFF_2030_EMPTY)
    forged = replace(p, deadline_at=p.cutoff_at + timedelta(days=100))
    obj = prospective_forecast(p, evidence_class="historical_current_llm_exploratory", status="invalid", ranking=[], status_reason="no_sessions")
    assert "packet_no_sessions_week_cannot_have_deadline_entry_or_exit" in vp(obj, forged)


def test_r06_01_trust_model_registry_is_read_only():
    from types import MappingProxyType
    from twlab import seals
    assert isinstance(seals.PRODUCTION_VERIFIERS, MappingProxyType) and dict(seals.PRODUCTION_VERIFIERS) == {}
    with pytest.raises(TypeError):
        seals.PRODUCTION_VERIFIERS["opentimestamps"] = lambda r, c: True  # type: ignore[index]


def test_packet_id_mismatch_is_reported():
    assert any(p.startswith("packet_id_mismatch") for p in vp(base(packet_id="other"), packet()))


def test_r01_18_r02_06_r03_02_temporal_order_and_deadline_come_from_the_protocol():
    late = vp(base(issued_at="2026-09-12T10:00:00+08:00", cutoff_at="2026-09-01T18:00:00+08:00"), packet())
    assert any(p.startswith("temporal:late_forecast") for p in late)
    assert any(p.startswith("cutoff_mismatch") for p in late)
    assert any(p.startswith("temporal:issued_not_after_cutoff") for p in vp(base(issued_at="2026-09-06T10:00:00+08:00"), packet()))
    assert any(p.startswith("temporal:issued_not_after_cutoff") for p in vp(base(issued_at="2026-09-06T18:00:00+08:00"), packet()))
    own = base(issued_at="2026-09-12T10:00:00+08:00", deadline_at="2026-09-13T08:30:00+08:00")
    assert any(p.startswith("deadline_mismatch") for p in vp(own, packet()))
    assert any(p.startswith("packet_required_for_selected") for p in vp(own, None))
    assert any(p.startswith("packet_without_protocol_week_plan") for p in vp(base(), packet(calendar=None), calendar=CAL))
    ok = vp(base(issued_at="2026-09-12T10:00:00+08:00", status="invalid", ranking=[], status_reason="late"), packet())
    assert not any(p.startswith("temporal:late") for p in ok)
    assert "temporal:cutoff_is_not_the_weekly_protocol_cutoff" in semantic_problems(base(cutoff_at="2026-09-10T02:00:00+08:00"))


def test_r05_11_validator_does_not_trust_a_caller_built_packet_plan():
    thursday = datetime.fromisoformat("2026-09-10T02:00:00+08:00")
    forged = replace(packet(), cutoff_at=thursday, deadline_at=datetime.fromisoformat("2026-09-10T08:30:00+08:00"),
                     entry_at=datetime.fromisoformat("2026-09-10T09:00:00+08:00"))
    obj = base(cutoff_at=thursday.isoformat(), issued_at="2026-09-10T07:00:00+08:00", deadline_at=forged.deadline_at.isoformat())
    assert "packet_cutoff_is_not_the_weekly_protocol_cutoff" in vp(obj, forged)
    # un week_status fuera del catálogo ya no puede ni construirse (R13-01); el validador conserva su comprobación
    with pytest.raises(ValueError, match="week_status"):
        replace(packet(), week_status="valid_typo")
    early_entry = replace(packet(), entry_at=DEADLINE - timedelta(hours=1))
    assert "packet_plan_inconsistent_with_protocol" in vp(base(), early_entry)
    moved_deadline = replace(packet(), deadline_at=DEADLINE + timedelta(days=1), registration_deadline_at=DEADLINE + timedelta(days=1))
    assert "packet_plan_does_not_match_calendar" in vp(base(deadline_at=(DEADLINE + timedelta(days=1)).isoformat()), moved_deadline)
    wrong_week = replace(packet(), week_id="1900-W01")
    assert "packet_week_id_does_not_match_cutoff" in vp(base(), wrong_week)
    shifted = replace(packet(), deadline_at=DEADLINE + timedelta(days=7), registration_deadline_at=DEADLINE + timedelta(days=7),
                      entry_at=DEADLINE + timedelta(days=7, minutes=30), exit_at=DEADLINE + timedelta(days=11))
    assert "packet_plan_inconsistent_with_protocol" in vp(base(deadline_at=(DEADLINE + timedelta(days=7)).isoformat()), shifted)
    extended = replace(packet(), registration_deadline_at=DEADLINE + timedelta(days=7))
    assert "packet_registration_deadline_must_equal_forecast_deadline" in vp(base(), extended)
    lny = packet(cutoff_at=taipei(date(2026, 2, 15), time(18, 0)))
    with_entry = replace(lny, entry_at=taipei(date(2026, 2, 16), time(9, 0)), exit_at=taipei(date(2026, 2, 20), time(13, 30)))
    inv2 = base(cutoff_at=lny.cutoff_at.isoformat(), issued_at=(lny.cutoff_at + timedelta(hours=1)).isoformat(),
                deadline_at=lny.cutoff_at.isoformat(), status="invalid", ranking=[], status_reason="no_sessions")
    assert "packet_no_sessions_week_cannot_have_deadline_entry_or_exit" in vp(inv2, with_entry)


def test_r03_03_r04_13_week_without_sessions_records_invalid_with_null_window():
    lny_cutoff = taipei(date(2026, 2, 15), time(18, 0))
    p = packet(cutoff_at=lny_cutoff)
    assert p.deadline_at is None and p.registration_deadline_at == taipei(date(2026, 2, 23), time(0, 0))
    common = dict(cutoff_at=lny_cutoff.isoformat(), issued_at=(lny_cutoff + timedelta(hours=1)).isoformat())
    sel = base(deadline_at=(lny_cutoff + timedelta(days=1)).isoformat(), **common)
    problems = vp(sel, p)
    assert any(x.startswith("week_invalid:no_sessions") for x in problems)
    assert any(x.startswith("week_invalid:deadline_must_equal_cutoff") for x in problems)
    inv = base(deadline_at=lny_cutoff.isoformat(), status="invalid", ranking=[], status_reason="no_sessions", **common)
    assert vp(inv, p) == []          # sin plazo ficticio: ventana nula


def test_r01_19_duplicate_securities_or_ranks_rejected():
    obj = base()
    obj["ranking"] = [deepcopy(obj["ranking"][0]) for _ in range(5)]
    problems = vp(obj, packet())
    assert any(p.startswith("duplicate_security_id") for p in problems)
    assert any(p.startswith("duplicate_rank") for p in problems)
    obj2 = base()
    second = deepcopy(obj2["ranking"][0])
    second.update(security_id="SEC-2", rank=3)
    obj2["ranking"].append(second)
    assert "ranks_not_contiguous_from_1" in vp(obj2, packet())


def test_r02_20_r03_13_malformed_responses_yield_problems_not_exceptions():
    obj = base()
    obj["ranking"][0]["security_id"] = []
    obj["ranking"][0]["rank"] = "1"
    obj["ranking"][0]["document_ids"] = "doc-1"
    assert vp(obj, packet())
    obj2 = base(ranking="nope", cutoff_at="ayer", issued_at=None, experiment_id=[], status=[], evidence_class=3)
    assert vp(obj2, packet())
    assert vp("not a dict", packet()) == ["not_an_object"]  # type: ignore[arg-type]
