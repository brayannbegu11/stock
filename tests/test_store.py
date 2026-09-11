import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from twlab.seals import PRODUCTION_VERIFIERS
from twlab.store import RECEIPT_INVALID, RECEIPT_PENDING, RECEIPT_VERIFIED, CaptureRecord, RawStore, UntrustedVerifier
from twlab.timeutil import TAIPEI, UTC

FIXED = datetime(2026, 9, 9, 12, 0, tzinfo=UTC)
REPO = Path(__file__).resolve().parents[1]


def digest_matches(rec, receipt):
    return receipt.digest == rec.sha256


def test_pit04_ingested_at_is_the_real_capture_time(tmp_path):
    clock_now = datetime(2026, 9, 9, 12, 0, tzinfo=TAIPEI)
    store = RawStore(tmp_path, clock=lambda: clock_now)
    rec = store.put(source_id="finmind", dataset="TaiwanStockPrice/2330",
                    payload=b'{"date":"2021-01-04","close":536.0}', url="https://api.finmindtrade.com/...",
                    http_status=200, content_type="application/json", extra={"covers": "2021-01-04"})
    assert rec.ingested_at_dt == clock_now.astimezone(UTC)
    assert rec.clock_source == "injected"           # nunca se confunde con una captura real
    assert store.captures(known_at=datetime(2021, 3, 7, 18, 0, tzinfo=TAIPEI)) == []
    assert [r.capture_id for r in store.captures(known_at=clock_now)] == [rec.capture_id]
    assert store.read(rec) == b'{"date":"2021-01-04","close":536.0}'


def test_system_clock_records_are_marked_system(tmp_path):
    rec = RawStore(tmp_path).put(source_id="s", dataset="d", payload=b"x", url="u")
    assert rec.clock_source == "system"
    assert rec.ingested_at_dt.tzinfo is not None


def test_pit12_receipt_digest_must_match_and_pending_is_not_a_seal(tmp_path):
    store = RawStore(tmp_path, clock=lambda: FIXED)
    rec = store.put(source_id="s", dataset="d", payload=b"forecast", url="u")
    assert not store.is_sealed(rec)
    with pytest.raises(ValueError):
        store.attach_receipt(rec.capture_id, receipt_id="ots:x", authority="opentimestamps", digest="0" * 64)
    pending = store.attach_receipt(rec.capture_id, receipt_id="ots:x", authority="opentimestamps",
                                   digest=rec.sha256, attested_at="2026-09-09T12:05:00+00:00")
    assert pending.receipt_obj.status == RECEIPT_PENDING and not store.is_sealed(pending)
    assert store.captures()[0].receipt_obj.receipt_id == "ots:x"      # la línea nueva gana, la antigua no se borra
    assert store.verify() == []


def test_r05_01_production_verifiers_cannot_be_injected_and_registry_is_empty(tmp_path):
    with pytest.raises(UntrustedVerifier):
        RawStore(tmp_path, verifiers={"opentimestamps": lambda r, rc: True})
    store = RawStore(tmp_path)
    with pytest.raises(UntrustedVerifier):
        store.register_verifier("rfc3161", lambda r, rc: True)
    assert PRODUCTION_VERIFIERS == {}
    rec = store.put(source_id="s", dataset="d", payload=b"forecast", url="u")
    store.attach_receipt(rec.capture_id, receipt_id="ots:x", authority="opentimestamps", digest=rec.sha256, attested_at=rec.ingested_at)
    assert not store.is_sealed(store.get(rec.capture_id))        # sin adaptador real, nada está sellado
    assert store.seals() == {} and store.seals(allow_test_authorities=True) == {}


def test_r01_20_r02_07_seal_is_recomputed_never_read(tmp_path):
    real = RawStore(tmp_path / "real")
    rec = real.put(source_id="s", dataset="d", payload=b"forecast", url="u", extra={"packet_hash": "abc"})
    real.attach_receipt(rec.capture_id, receipt_id="fx:x", authority="fixture", digest=rec.sha256,
                        attested_at="2026-09-09T12:05:00+00:00")
    assert not real.is_sealed(real.get(rec.capture_id))             # sin verificador registrado no hay sello
    bad = real.verify_receipt(rec.capture_id, method="fake")
    assert bad.receipt_obj.status == RECEIPT_INVALID
    real.register_verifier("fixture", digest_matches)
    good = real.verify_receipt(rec.capture_id, method="fake-digest-only")
    assert good.receipt_obj.status == RECEIPT_VERIFIED and real.is_sealed(good)
    assert real.seals() == {}                                        # autoridad de prueba: fuera del protocolo
    seals = real.seals(allow_test_authorities=True)
    assert set(seals) == {"fx:x"} and seals["fx:x"].digest == rec.sha256 and not seals["fx:x"].production
    # la misma captura leída por un almacén sin verificador no está sellada: el estado no es un campo
    other = RawStore(tmp_path / "real")
    assert not other.is_sealed(other.get(rec.capture_id))
    # captura sintética: nunca sella, ni con verificador que acepte todo
    synthetic = RawStore(tmp_path / "synthetic", clock=lambda: FIXED, verifiers={"fixture": lambda r, rc: True})
    srec = synthetic.put(source_id="s", dataset="d", payload=b"forecast", url="u")
    synthetic.attach_receipt(srec.capture_id, receipt_id="fx:z", authority="fixture", digest=srec.sha256,
                             attested_at="2026-09-09T12:05:00+00:00")
    assert not synthetic.is_sealed(synthetic.get(srec.capture_id))


def test_r02_07_fabricated_verified_receipt_does_not_seal(tmp_path):
    store = RawStore(tmp_path)
    rec = store.put(source_id="s", dataset="d", payload=b"forecast", url="u")
    forged = CaptureRecord(**{**rec.__dict__, "receipt": {"receipt_id": "x", "authority": "yo", "digest": rec.sha256,
                                                          "status": "verified", "attested_at": "not-a-date"}})
    assert not store.is_sealed(forged)
    forged2 = CaptureRecord(**{**rec.__dict__, "receipt": {"receipt_id": "x", "authority": "yo", "digest": rec.sha256,
                                                           "status": "verified", "attested_at": "2026-09-09T12:05:00+00:00"}})
    assert not store.is_sealed(forged2)          # 'yo' no tiene verificador registrado


def test_r03_05_seal_requires_intact_archived_bytes(tmp_path):
    s = RawStore(tmp_path, verifiers={"fixture": digest_matches})
    r = s.put(source_id="s", dataset="d", payload=b"original", url="u")
    r = s.attach_receipt(r.capture_id, receipt_id="r", authority="fixture", digest=r.sha256, attested_at=r.ingested_at)
    assert s.is_sealed(r)
    (tmp_path / r.path).write_bytes(b"CHANGED")
    assert not s.is_sealed(r) and s.seals(allow_test_authorities=True) == {}


def test_r03_06_capture_archived_after_deadline_is_not_prospective(tmp_path):
    s = RawStore(tmp_path)
    old = datetime(2020, 1, 1, tzinfo=UTC)
    r = s.put(source_id="s", dataset="d", payload=b"old-content", url="u")
    s.register_verifier("fixture", lambda rec, receipt: receipt.digest == r.sha256 and receipt.attested_at == old.isoformat())
    r = s.attach_receipt(r.capture_id, receipt_id="r", authority="fixture", digest=r.sha256, attested_at=old.isoformat())
    assert r.ingested_at_dt > old + timedelta(days=1)
    assert s.is_sealed(r)                                              # sin plazo, el recibo es válido
    assert not s.is_sealed(r, not_after=old + timedelta(days=1))       # con plazo: la captura llegó tarde
    info = s.seal_info(r)
    assert info is not None and info.attested_at == old and info.ingested_at == r.ingested_at_dt


def test_r02_11_legacy_manifest_lines_are_readable(tmp_path):
    legacy = {"capture_id": "twse:FRMSA:2026-09-09T18:04:26.306637+00:00:abc", "source_id": "twse", "dataset": "FRMSA",
              "path": "twse/FRMSA/x.json", "sha256": "0" * 64, "bytes": 500, "ingested_at": "2026-09-09T18:04:26.306637+00:00",
              "url": "u", "http_status": 200, "content_type": "application/json", "clock_source": "system",
              "extra": {"rows": 6}, "receipt_id": None, "receipt_authority": None}
    (tmp_path / "manifest.jsonl").write_text(json.dumps(legacy) + "\n", encoding="utf-8")
    recs = RawStore(tmp_path).captures()
    assert len(recs) == 1 and recs[0].receipt is None and recs[0].extra["rows"] == 6


def test_r02_11_archived_audit_manifest_is_readable(tmp_path):
    src = REPO / "data" / "audit" / "manifest_2026-09-09.jsonl"
    (tmp_path / "manifest.jsonl").write_bytes(src.read_bytes())
    recs = RawStore(tmp_path).captures()
    assert len(recs) == 37 and all(r.clock_source == "system" for r in recs)
    assert {r.source_id for r in recs} == {"twse", "tpex", "finmind"}


@pytest.mark.skipif(not (REPO / "data" / "raw" / "manifest.jsonl").exists(), reason="archivo crudo no presente")
def test_r02_11_real_archive_verifies():
    store = RawStore(REPO / "data" / "raw")
    assert store.captures()
    assert store.verify() == []


def test_verify_detects_tampering(tmp_path):
    store = RawStore(tmp_path, clock=lambda: FIXED)
    rec = store.put(source_id="s", dataset="d", payload=b"original", url="u")
    (tmp_path / rec.path).write_bytes(b"tampered")
    assert store.verify() == [f"hash_mismatch:{rec.capture_id}"]


def test_find_returns_the_earliest_identical_capture_and_writes_nothing(tmp_path):
    clock = [datetime(2026, 9, 13, 12, 0, tzinfo=UTC)]
    store = RawStore(tmp_path, clock=lambda: clock[0])
    first = store.put(source_id="forecast", dataset="lab/Q0/2026-W38", payload=b'{"a":1}', url="local://t", content_type="application/json")
    clock[0] += timedelta(days=7)
    second = store.put(source_id="forecast", dataset="lab/Q0/2026-W38", payload=b'{"a":1}', url="local://t", content_type="application/json")
    assert second.capture_id != first.capture_id
    found = store.find(source_id="forecast", dataset="lab/Q0/2026-W38", sha256=first.sha256)
    assert found is not None and found.capture_id == first.capture_id           # la primera ingestión, no la última
    assert store.find(source_id="forecast", dataset="lab/Q0/2026-W39", sha256=first.sha256) is None
    assert store.find(source_id="packet", dataset="lab/2026-W38", extra_equal={"packet_hash": "x"}) is None
    p = store.put(source_id="packet", dataset="lab/2026-W38", payload=b'{"created_at":"t1"}', url="local://t", content_type="application/json", extra={"packet_hash": "h1"})
    clock[0] += timedelta(days=7)
    store.put(source_id="packet", dataset="lab/2026-W38", payload=b'{"created_at":"t2"}', url="local://t", content_type="application/json", extra={"packet_hash": "h1"})
    assert store.find(source_id="packet", dataset="lab/2026-W38", extra_equal={"packet_hash": "h1"}).capture_id == p.capture_id
    n = sum(1 for _ in (tmp_path / "manifest.jsonl").open(encoding="utf-8"))
    assert n == 4                                                                # find() no escribe
    with pytest.raises(ValueError):
        store.find(source_id="packet", dataset="lab/2026-W38")
