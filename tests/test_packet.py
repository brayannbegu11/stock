import json
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest

from twlab.packet import (
    MODE_HISTORICAL, MODE_PROSPECTIVE, R_AVAILABLE_AFTER_CUTOFF, R_DERIVATION_MISMATCH, R_INCONSISTENT_METADATA,
    R_NO_CAPTURE_EVIDENCE, R_NOT_RECEIVED_BEFORE_CUTOFF, R_PROVENANCE_MISMATCH, R_SYNTHETIC_CAPTURE,
    R_UNKNOWN_AVAILABILITY, AccessDenied, Document, EvaluatorView, PredictorView, build_packet, open_workspace,
    validate_document_references,
)
from twlab.store import RawStore
from twlab.timeutil import AvailabilityQuality as Q, derive_available_at, taipei
from twlab.weekly import STATUS_NO_SESSIONS, STATUS_VALID

NY = ZoneInfo("America/New_York")
CLEAN = "historical_numeric_temporally_controlled"
def _json_extractor(raw: bytes):
    payload = json.loads(raw)
    ids = payload.get("security_ids", ["SEC-1"]) if isinstance(payload, dict) else ["SEC-1"]
    return {"payload": payload, "security_ids": list(ids)}


EXTRACTORS = {"json": _json_extractor, "text": lambda b: {"payload": {"text": b.decode("utf-8")}, "security_ids": ["SEC-1"]}}


def T(d, h, m=0):
    return taipei(d, time(h, m))


def doc(doc_id, available_at, *, quality=Q.VERIFIED_ORIGINAL, first_seen=None, kind="news", capture=None,
        source_id="test", **kw):
    if capture is not None:
        kw.setdefault("capture_id", capture.capture_id)
        kw.setdefault("source_sha256", capture.sha256)
        kw.setdefault("derivation", "json")
        kw.setdefault("payload", {"doc": doc_id})
        source_id = capture.source_id
    return Document(doc_id=doc_id, kind=kind, source_id=source_id, security_ids=("SEC-1",),
                    available_at=available_at, availability_quality=quality, first_seen_at=first_seen, **kw)


def build(docs, cutoff, mode=MODE_HISTORICAL, **kw):
    return build_packet(packet_id="pkt-test", cutoff_at=cutoff, documents=docs, mode=mode,
                        evidence_class=CLEAN, **kw)


def rejected_reasons(p):
    return {r.doc_id: r.reason for r in p.rejected}


@pytest.fixture
def capture(tmp_path):
    """Captura sintética con reloj inyectado: sirve para probar el enlace, nunca como prospectiva real."""
    stores = {}

    def make(doc_id, ingested_at, *, source_id="test", payload=None):
        store = RawStore(tmp_path / doc_id, clock=lambda: ingested_at)
        rec = store.put(source_id=source_id, dataset=doc_id, url="u", http_status=200, content_type="application/json",
                        payload=payload if payload is not None else json.dumps({"doc": doc_id}).encode("utf-8"))
        stores[rec.capture_id] = store
        return rec

    make.read = lambda rec: stores[rec.capture_id].read(rec)  # type: ignore[attr-defined]
    return make


def build_pro(docs, cutoff, captures, capture, **kw):
    return build(docs, cutoff, MODE_PROSPECTIVE, captures={c.capture_id: c for c in captures},
                 read_bytes=capture.read, extractors=EXTRACTORS, allow_injected_clock=True, **kw)


# ---- PIT ----------------------------------------------------------------
def test_pit01_news_after_cutoff_excluded(sunday_cutoff):
    p = build([doc("late", T(date(2026, 9, 6), 19, 0)), doc("ok", T(date(2026, 9, 6), 17, 59))], sunday_cutoff)
    assert p.admitted_ids() == {"ok"}
    assert rejected_reasons(p)["late"] == R_AVAILABLE_AFTER_CUTOFF


def test_pit02_period_end_does_not_make_a_filing_available(sunday_cutoff):
    filing = doc("q2", T(date(2026, 9, 7), 10, 0), kind="filing", period_end=date(2026, 6, 30),
                 published_at=T(date(2026, 9, 7), 10, 0))
    p = build([filing], sunday_cutoff)
    assert p.admitted == () and rejected_reasons(p)["q2"] == R_AVAILABLE_AFTER_CUTOFF


def test_pit03_edited_version_after_cutoff_keeps_verified_original(sunday_cutoff):
    v1 = doc("art-v1", T(date(2026, 9, 3), 10, 0), version=1)
    v2 = doc("art-v2", T(date(2026, 9, 7), 9, 0), version=2, supersedes="art-v1")
    p = build([v1, v2], sunday_cutoff)
    assert p.admitted_ids() == {"art-v1"}
    assert build([v2], sunday_cutoff).admitted == ()


def test_pit04_and_pit06_prospective_requires_capture_before_cutoff(sunday_cutoff, capture):
    rec_old = capture("old-2021", T(date(2026, 9, 9), 12, 0))
    old = doc("old-2021", T(date(2021, 3, 1), 10, 0), capture=rec_old)
    hist = build([old], T(date(2021, 3, 7), 18, 0), MODE_HISTORICAL)
    assert hist.admitted_ids() == {"old-2021"}            # reconstrucción con evidencia de disponibilidad
    pro = build_pro([old], T(date(2021, 3, 7), 18, 0), [rec_old], capture)
    assert rejected_reasons(pro)["old-2021"] == R_NOT_RECEIVED_BEFORE_CUTOFF   # no llegó a tiempo al sistema
    rec_late = capture("sat-news", T(date(2026, 9, 6), 19, 0))
    late = doc("sat-news", T(date(2026, 9, 5), 10, 0), capture=rec_late)
    assert rejected_reasons(build_pro([late], sunday_cutoff, [rec_late], capture))["sat-news"] == R_NOT_RECEIVED_BEFORE_CUTOFF


def test_pit05_date_only_document_uses_conservative_policy(cal, sunday_cutoff):
    av = derive_available_at(date(2026, 9, 6), calendar=cal)     # domingo sin hora
    d = doc("date-only", av.available_at, quality=av.quality)
    p = build([d], sunday_cutoff)
    assert rejected_reasons(p)["date-only"] == R_AVAILABLE_AFTER_CUTOFF
    av2 = derive_available_at(date(2026, 9, 6), time(15, 0), calendar=cal, time_is_verified=True)
    assert build([doc("timed", av2.available_at)], sunday_cutoff).admitted_ids() == {"timed"}


def test_pit07_weekend_article_never_enables_friday_entry(cal, sunday_cutoff, capture):
    rec = capture("sat", T(date(2026, 9, 5), 11, 0))
    sat = doc("sat", T(date(2026, 9, 5), 10, 0), capture=rec)
    p = build_pro([sat], sunday_cutoff, [rec], capture, calendar=cal)
    assert p.admitted_ids() == {"sat"}
    assert p.admitted[0].first_seen_at == rec.ingested_at_dt        # tomado de la captura, no del llamante
    assert p.entry_at == T(date(2026, 9, 7), 9, 0)                    # entrada derivada del plan semanal
    assert p.entry_at > cal.session_close(date(2026, 9, 4))


def test_pit08_foreign_close_same_calendar_day_after_taiwan_cutoff():
    daily_cutoff = T(date(2026, 9, 4), 8, 0)                                   # viernes 08:00 Taipei
    thu_close = datetime(2026, 9, 3, 16, 0, tzinfo=NY)                          # = vie 04:00 Taipei
    fri_close = datetime(2026, 9, 4, 16, 0, tzinfo=NY)                          # = sáb 04:00 Taipei
    p = build([doc("us-thu", thu_close), doc("us-fri", fri_close)], daily_cutoff)
    assert p.admitted_ids() == {"us-thu"}
    assert rejected_reasons(p)["us-fri"] == R_AVAILABLE_AFTER_CUTOFF


def test_pit09_scheduled_event_admitted_outcome_rejected(sunday_cutoff):
    sched = doc("tsmc-cal", T(date(2026, 9, 1), 9, 0), kind="calendar_event", scheduled_for=T(date(2026, 9, 10), 14, 0))
    outcome = doc("tsmc-aug-rev", T(date(2026, 9, 10), 14, 5), kind="filing")
    p = build([sched, outcome], sunday_cutoff)
    assert p.admitted_ids() == {"tsmc-cal"}
    assert rejected_reasons(p)["tsmc-aug-rev"] == R_AVAILABLE_AFTER_CUTOFF


def test_unknown_availability_never_enters_primary_packet(sunday_cutoff):
    p = build([doc("mystery", T(date(2026, 9, 1), 9, 0), quality=Q.UNKNOWN)], sunday_cutoff)
    assert rejected_reasons(p)["mystery"] == R_UNKNOWN_AVAILABILITY


def test_naive_datetimes_are_rejected(sunday_cutoff):
    with pytest.raises(ValueError):
        doc("naive", datetime(2026, 9, 1, 9, 0))
    with pytest.raises(ValueError):
        build([], datetime(2026, 9, 6, 18, 0))


# ---- Ronda 1 de Astra ---------------------------------------------------
def test_r01_02_future_publication_cannot_be_backdated(sunday_cutoff):
    old = T(date(2026, 9, 6), 17, 0)
    future = T(date(2026, 9, 7), 10, 0)
    d = Document("late", "filing", "test", ("A",), old, Q.VERIFIED_ORIGINAL, published_at=future,
                 first_seen_at=old, payload={"revenue": 999})
    p = build([d], sunday_cutoff)
    assert not p.admitted and rejected_reasons(p)["late"] == R_INCONSISTENT_METADATA


def test_r01_02_prospective_requires_capture_link_and_real_clock(sunday_cutoff, capture):
    unlinked = doc("nolink", T(date(2026, 9, 5), 10, 0), first_seen=T(date(2026, 9, 5), 11, 0))
    p = build_pro([unlinked], sunday_cutoff, [], capture)
    assert rejected_reasons(p)["nolink"] == R_NO_CAPTURE_EVIDENCE
    rec = capture("linked", T(date(2026, 9, 5), 11, 0))
    linked = doc("linked", T(date(2026, 9, 5), 10, 0), capture=rec)
    strict = build([linked], sunday_cutoff, MODE_PROSPECTIVE, captures={rec.capture_id: rec},
                   read_bytes=capture.read, extractors=EXTRACTORS)
    assert rejected_reasons(strict)["linked"] == R_SYNTHETIC_CAPTURE
    lying = doc("linked", T(date(2026, 9, 5), 10, 0), capture=rec, first_seen=T(date(2026, 9, 5), 9, 0))
    assert rejected_reasons(build_pro([lying], sunday_cutoff, [rec], capture))["linked"] == R_INCONSISTENT_METADATA
    with pytest.raises(ValueError):
        build_packet(packet_id="p", cutoff_at=sunday_cutoff, documents=[linked], mode=MODE_PROSPECTIVE,
                     evidence_class="prospective_registered", captures={rec.capture_id: rec},
                     read_bytes=capture.read, extractors=EXTRACTORS, allow_injected_clock=True)
    with pytest.raises(ValueError):
        build([linked], sunday_cutoff, MODE_PROSPECTIVE)   # sin registro de capturas ni extractores
    with pytest.raises(ValueError):
        build_packet(packet_id="p", cutoff_at=sunday_cutoff, documents=[], mode=MODE_HISTORICAL,
                     evidence_class="prospective_registered")   # evidencia prospectiva sin modo prospectivo


def test_r01_03_dst_fold_does_not_admit_future():
    cutoff = datetime(2026, 11, 1, 1, 30, tzinfo=NY, fold=0)
    future = datetime(2026, 11, 1, 1, 15, tzinfo=NY, fold=1)
    assert future.timestamp() > cutoff.timestamp()
    p = build([doc("future", future)], cutoff)
    assert not p.admitted and rejected_reasons(p)["future"] == R_AVAILABLE_AFTER_CUTOFF


def test_r01_04_delivered_content_is_immutable_and_fully_hashed(sunday_cutoff):
    p = build([doc("d", T(date(2026, 9, 1), 9, 0), payload={"x": 1, "nested": {"y": [1, 2]}})], sunday_cutoff)
    before = p.packet_hash()
    with pytest.raises(TypeError):
        p.admitted[0].payload["future_close"] = 999
    with pytest.raises(TypeError):
        p.admitted[0].payload["nested"]["y"] = 5
    assert p.packet_hash() == before
    other_source = build([doc("d", T(date(2026, 9, 1), 9, 0), payload={"x": 1, "nested": {"y": [1, 2]}}, kind="filing")],
                         sunday_cutoff)
    assert other_source.packet_hash() != before            # el hash cubre metadatos, no sólo payload


def test_r01_05_predictor_view_cannot_reach_outcomes(sunday_cutoff):
    p = build([], sunday_cutoff)
    with pytest.raises(ValueError):
        open_workspace(role="predictor", packet=p, outcomes={"SEC-1": 0.12})
    w = open_workspace(role="predictor", packet=p)
    assert isinstance(w, PredictorView) and not hasattr(w, "_outcomes")
    with pytest.raises(AttributeError):
        w.role = "evaluator"          # el rol no es un campo modificable
    with pytest.raises(AttributeError):
        w.outcomes_store = {}         # __slots__: no se pueden colgar atributos nuevos
    with pytest.raises(AccessDenied):
        w.outcomes()
    assert len(w.security_log) == 1 and w.security_log[0].action == "read_outcomes"
    ev = open_workspace(role="evaluator", outcomes={"SEC-1": 0.12})
    assert isinstance(ev, EvaluatorView) and ev.outcomes() == {"SEC-1": 0.12}


# ---- Rondas 2 y 3 de Astra --------------------------------------------------
def test_r02_01_capture_from_other_source_cannot_attest_document(sunday_cutoff, capture):
    rain = capture("rain", T(date(2026, 9, 5), 11, 0), source_id="weather", payload=b'{"rain":0}')
    forged = doc("revenue", T(date(2026, 9, 5), 10, 0), capture_id=rain.capture_id, source_sha256=rain.sha256,
                 source_id="test", derivation="json", payload={"revenue": 999})
    assert rejected_reasons(build_pro([forged], sunday_cutoff, [rain], capture))["revenue"] == R_PROVENANCE_MISMATCH
    wrong_sha = doc("revenue", T(date(2026, 9, 5), 10, 0), capture_id=rain.capture_id, source_sha256="0" * 64,
                    source_id="weather", derivation="json", payload={"rain": 0})
    assert rejected_reasons(build_pro([wrong_sha], sunday_cutoff, [rain], capture))["revenue"] == R_PROVENANCE_MISMATCH
    no_sha = doc("revenue", T(date(2026, 9, 5), 10, 0), capture_id=rain.capture_id, source_id="weather", derivation="json")
    assert rejected_reasons(build_pro([no_sha], sunday_cutoff, [rain], capture))["revenue"] == R_PROVENANCE_MISMATCH
    genuine = doc("rain-doc", T(date(2026, 9, 5), 10, 0), capture=rain, payload={"rain": 0})
    assert build_pro([genuine], sunday_cutoff, [rain], capture).admitted_ids() == {"rain-doc"}


def test_r03_01_payload_must_be_reproducible_from_archived_bytes(sunday_cutoff, capture):
    rec = capture("revenue", T(date(2026, 9, 5), 11, 0), payload=b'{"revenue":100}')
    forged = doc("v2", T(date(2026, 9, 5), 10, 0), capture=rec, quality=Q.VERIFIED_VERSION, version=2,
                 payload={"revenue": 999})
    assert rejected_reasons(build_pro([forged], sunday_cutoff, [rec], capture))["v2"] == R_DERIVATION_MISMATCH
    no_extractor = doc("v2", T(date(2026, 9, 5), 10, 0), capture=rec, derivation=None, payload={"revenue": 100})
    assert rejected_reasons(build_pro([no_extractor], sunday_cutoff, [rec], capture))["v2"] == R_DERIVATION_MISMATCH
    unknown_extractor = doc("v2", T(date(2026, 9, 5), 10, 0), capture=rec, derivation="magic", payload={"revenue": 100})
    assert rejected_reasons(build_pro([unknown_extractor], sunday_cutoff, [rec], capture))["v2"] == R_DERIVATION_MISMATCH
    genuine = doc("v2", T(date(2026, 9, 5), 10, 0), capture=rec, payload={"revenue": 100})
    assert build_pro([genuine], sunday_cutoff, [rec], capture).admitted_ids() == {"v2"}


def test_r04_07_json_identity_distinguishes_true_from_1(sunday_cutoff, capture):
    rec = capture("flag", T(date(2026, 9, 5), 11, 0), payload=b'{"revenue":true}')
    forged = doc("flag", T(date(2026, 9, 5), 10, 0), capture=rec, payload={"revenue": 1})
    assert rejected_reasons(build_pro([forged], sunday_cutoff, [rec], capture))["flag"] == R_DERIVATION_MISMATCH
    exact = doc("flag", T(date(2026, 9, 5), 10, 0), capture=rec, payload={"revenue": True})
    assert build_pro([exact], sunday_cutoff, [rec], capture).admitted_ids() == {"flag"}


def test_r04_14_security_identity_must_come_from_the_extraction(sunday_cutoff, capture):
    raw = b'{"security_ids":["SEC-1"],"revenue":100}'
    rec = capture("rev", T(date(2026, 9, 5), 11, 0), payload=raw)
    misattributed = Document(doc_id="rev", kind="filing", source_id=rec.source_id, security_ids=("SEC-2",),
                             available_at=T(date(2026, 9, 5), 10, 0), availability_quality=Q.VERIFIED_ORIGINAL,
                             capture_id=rec.capture_id, source_sha256=rec.sha256, derivation="json", payload=json.loads(raw))
    assert rejected_reasons(build_pro([misattributed], sunday_cutoff, [rec], capture))["rev"] == R_DERIVATION_MISMATCH
    faithful = doc("rev", T(date(2026, 9, 5), 10, 0), capture=rec, payload=json.loads(raw))
    assert build_pro([faithful], sunday_cutoff, [rec], capture).admitted_ids() == {"rev"}
    bad_extractor = {"json": lambda b: json.loads(b)}      # sin security_ids → no acredita identidad
    p = build(
        [faithful], sunday_cutoff, MODE_PROSPECTIVE, captures={rec.capture_id: rec}, read_bytes=capture.read,
        extractors=bad_extractor, allow_injected_clock=True,
    )
    assert rejected_reasons(p)["rev"] == R_DERIVATION_MISMATCH


def test_r04_05_packet_rejects_non_protocol_cutoff_when_planning_the_week(cal):
    from twlab.weekly import ProtocolViolation
    with pytest.raises(ProtocolViolation):
        build([], T(date(2026, 9, 10), 2, 0), calendar=cal)
    assert build([], T(date(2026, 9, 10), 2, 0)).week_status is None     # sin calendario no hay plan semanal


def test_r02_02_duplicate_doc_ids_are_an_error_not_a_hash_collision(sunday_cutoff):
    a = doc("same", T(date(2026, 9, 1), 9, 0), payload={"value": 1})
    b = doc("same", T(date(2026, 9, 1), 9, 0), payload={"value": 999})
    with pytest.raises(ValueError):
        build([a, b], sunday_cutoff)


def test_r02_10_prospective_nested_payload_survives_replace(sunday_cutoff, capture):
    payload = {"nested": {"value": 1, "list": [1, {"a": 2}]}}
    rec = capture("nested", T(date(2026, 9, 5), 11, 0), payload=json.dumps(payload).encode("utf-8"))
    d = doc("nested", T(date(2026, 9, 5), 10, 0), capture=rec, payload=payload)
    p = build_pro([d], sunday_cutoff, [rec], capture)
    assert p.admitted_ids() == {"nested"}
    assert p.admitted[0].payload["nested"]["list"][1]["a"] == 2
    with pytest.raises(TypeError):
        p.admitted[0].payload["nested"]["value"] = 5


def test_r02_06_r03_02_deadline_is_derived_from_calendar_and_protocol(cal, sunday_cutoff):
    p = build([], sunday_cutoff, calendar=cal)
    assert p.week_id == "2026-W37" and p.week_status == STATUS_VALID
    assert p.deadline_at == T(date(2026, 9, 7), 8, 30)
    assert p.entry_at == T(date(2026, 9, 7), 9, 0) and p.exit_at == T(date(2026, 9, 11), 13, 30)
    assert p.calendar_version.startswith("S06:")
    assert build([], sunday_cutoff).packet_hash() != p.packet_hash()       # el plan semanal forma parte del hash
    lny = build([], T(date(2026, 2, 15), 18, 0), calendar=cal)
    assert lny.week_status == STATUS_NO_SESSIONS and lny.deadline_at is None and lny.entry_at is None
    with pytest.raises(TypeError):
        build([], sunday_cutoff, deadline_at=T(date(2026, 9, 13), 8, 30))   # ya no existe un plazo libre


def test_txt05_reference_to_document_outside_packet(sunday_cutoff):
    p = build([doc("in", T(date(2026, 9, 1), 9, 0))], sunday_cutoff)
    assert validate_document_references(["in", "ghost"], p) == ["ghost"]


def test_packet_hash_is_stable_and_content_sensitive(sunday_cutoff):
    a = build([doc("d", T(date(2026, 9, 1), 9, 0), payload={"x": 1})], sunday_cutoff)
    b = build([doc("d", T(date(2026, 9, 1), 9, 0), payload={"x": 1})], sunday_cutoff)
    c = build([doc("d", T(date(2026, 9, 1), 9, 0), payload={"x": 2})], sunday_cutoff)
    assert a.packet_hash() == b.packet_hash() != c.packet_hash()
