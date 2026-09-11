"""Pruebas del exportador del sitio (scripts/export_site_data.py): R17-07 y R17-13."""
import importlib.util
import json

import pytest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load():
    spec = importlib.util.spec_from_file_location("export_site_data", ROOT / "scripts" / "export_site_data.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_r17_07_paired_summary_keeps_bootstrap_warnings():
    ex = _load()
    p = ex.paired_summary({"mean": -0.0105, "ci95": [-0.064, 0.0016], "n_used": 12, "n_excluded": 5, "degenerate": False,
                           "n_fixed_observations": 4, "variability_limited": True, "n_segments": 3})
    assert p["n_fixed_observations"] == 4 and p["variability_limited"] is True and p["n_segments"] == 3
    assert p["ci95"] == [-0.064, 0.0016] and p["degenerate"] is False


def test_r17_13_master_stats_count_only_segments(tmp_path):
    ex = _load()
    rows = [{"kind": "segment", "security_id": "TWSE:1@2000-01-01"}, {"kind": "segment", "security_id": "TWSE:2@2000-01-01"},
            {"kind": "delisting", "security_id": "TWSE:3@2000-01-01"}]
    (tmp_path / "master_2026-09-09.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    st = ex.master_stats(tmp_path)
    assert st["segments"] == 2 and st["other_rows"] == {"delisting": 1} and st["as_of"] == "2026-09-09"


def test_r17_05_review_stats_derive_only_from_identifiable_verifications():
    ex = _load()
    rounds = [
        {"round": 1, "new_findings": [{"id": "R01-01", "severity": "bloqueante"}, {"id": "R01-02", "severity": "alta"}], "verifications": []},
        {"round": 2, "new_findings": [{"id": "R02-01", "severity": "media"}],
         "verifications": [{"id": "R01-01", "state": "reproducido"}, {"id": "R01-02", "state": "no_reproducido"}]},
    ]
    st = ex.review_stats(rounds)
    assert st == {"new_total": 3, "verified_total": 1, "blocking_new": 1, "blocking_verified": 1, "unverified_ids": ["R01-02", "R02-01"]}


def test_r18_03_review_stats_require_full_identifiers_and_later_rounds():
    ex = _load()
    rounds = [
        {"round": 1, "new_findings": [{"id": "R01-01", "severity": "bloqueante"}], "verifications": [{"id": "R01-01", "state": "reproducido"}]},
        {"round": 2, "new_findings": [{"id": "R02-01", "severity": "media"}], "verifications": [{"id": "R02-01", "state": "reproducido"}]},
    ]
    st = ex.review_stats(rounds)
    assert st["verified_total"] == 0 and st["blocking_verified"] == 0            # misma ronda: no cuenta
    rounds.append({"round": 3, "new_findings": [], "verifications": [{"id": "R01-01", "state": "reproducido"}, {"id": "R99-01", "state": "reproducido"}]})
    st = ex.review_stats(rounds)
    assert st["verified_total"] == 1 and st["blocking_verified"] == 1 and st["unverified_ids"] == ["R02-01"]


def test_r18_03_verification_identifier_must_match_completely(tmp_path, monkeypatch):
    ex = _load()
    out = tmp_path / "review" / "out"; out.mkdir(parents=True)
    (tmp_path / "docs" / "informes").mkdir(parents=True)
    hall = [{"id": "R01-01/verificacion", "estado_verificacion": "reproducido"}, {"id": "R01-02/verificacion_extra", "estado_verificacion": "reproducido"},
            {"id": "R01-03/otra/verificacion", "estado_verificacion": "reproducido"}, {"id": "R02-01", "severidad": "media"}]
    (out / "ronda2_verificacion_20260910T000000Z.json").write_text(json.dumps({"ronda": 2, "veredicto": "rechazado", "resumen": "", "hallazgos": hall}), encoding="utf-8")
    monkeypatch.setattr(ex, "ROOT", tmp_path)
    rounds = ex.export_rounds()
    assert [v["id"] for v in rounds[0]["verifications"]] == ["R01-01"]
    assert [h["id"] for h in rounds[0]["new_findings"]] == ["R02-01"]


def test_r18_08_export_keeps_final_valuation_conditions(tmp_path, monkeypatch):
    ex = _load()
    store = tmp_path / "data" / "store"; store.mkdir(parents=True)
    d = {"summary": {"label": "x", "assumptions": {"notional": 1000, "slots": 5}, "universe_ew": {}, "forecasters": {
            "Q0": {"model_id": "m", "final_equity": 2021351.0, "total_net_return": -0.5, "weeks_measured": 16,
                   "final_valuation": {"flags": ["TWSE:1436@1988-04-11:fractional_shares_unresolved"], "valued_at": "2025-12-31T23:59:00+08:00", "prices_session": "2025-12-31"}}}},
         "weeks": []}
    (store / "backtest_x.json").write_text(json.dumps(d), encoding="utf-8")
    monkeypatch.setattr(ex, "STORE", store)
    sc = ex.export_scenario("t", "x", "i.md")
    q = sc["forecasters"]["Q0"]
    assert q["final_flags"] == ["TWSE:1436@1988-04-11:fractional_shares_unresolved"] and q["final_valued_at"].startswith("2025-12-31") and q["weeks_measured"] == 16


def _put(store, dataset, body, **extra):
    return store.put(source_id="forecast", dataset=dataset, payload=json.dumps(body).encode("utf-8"), url="local://t", content_type="application/json", **extra)


def test_r20_01_02_03_prediction_requires_exact_bytes_per_forecaster_deadline_and_system_clock(tmp_path, monkeypatch):
    from datetime import datetime, timezone
    from twlab.store import RawStore
    ex = _load(); monkeypatch.setattr(ex, "RAW", tmp_path); ex._MANIFEST = None
    dl = "2026-09-14T08:30:00+08:00"
    store = RawStore(tmp_path)                                                   # reloj del sistema
    early = _put(store, "lab/Q0/2026-W38", {"forecast": {"deadline_at": dl, "ranking": ["A"]}})
    late = _put(store, "lab/Q0/2026-W38", {"forecast": {"deadline_at": dl, "ranking": ["B"]}})
    # la lista mostrada es la tardía (bytes de `late`): no hereda la hora de la temprana (R20-01)
    fa = ex.forecast_archive("lab", "2026-W38", {"Q0": late.sha256})
    assert fa["archived_at"]["Q0"] == late.ingested_at
    # un pronosticador esperado sin archivo → False (R20-02)
    fa = ex.forecast_archive("lab", "2026-W38", {"Q0": early.sha256, "Q1": "0" * 64})
    assert fa["before_deadline"] is False and "missing_or_corrupt:Q1" in fa["reasons"]
    # sin identidad esperada no hay predicción
    assert ex.forecast_archive("lab", "2026-W38", None)["before_deadline"] is False
    # reloj inyectado, aunque sea temprano, no es evidencia (R20-03)
    ex._MANIFEST = None
    injected = RawStore(tmp_path / "inj", clock=lambda: datetime(2026, 9, 13, 12, tzinfo=timezone.utc))
    r = _put(injected, "lab/Q0/2026-W38", {"forecast": {"deadline_at": dl}})
    monkeypatch.setattr(ex, "RAW", tmp_path / "inj"); ex._MANIFEST = None
    fa = ex.forecast_archive("lab", "2026-W38", {"Q0": r.sha256})
    assert fa["before_deadline"] is False and any(x.startswith("clock:") and x.endswith(":Q0") for x in fa["reasons"])
    # plazo sin zona horaria: inutilizable, no un TypeError
    r2 = _put(injected, "lab/Q1/2026-W38", {"forecast": {"deadline_at": "2026-09-14T08:30:00"}})
    ex._MANIFEST = None
    fa = ex.forecast_archive("lab", "2026-W38", {"Q1": r2.sha256})
    assert fa["before_deadline"] is False


def test_r20_02_each_forecaster_is_checked_against_its_own_deadline(tmp_path, monkeypatch):
    from datetime import datetime, timezone
    from twlab.store import RawStore
    ex = _load(); monkeypatch.setattr(ex, "RAW", tmp_path); ex._MANIFEST = None
    clock = {"t": datetime(2026, 9, 14, 0, 20, tzinfo=timezone.utc)}
    store = RawStore(tmp_path, clock=lambda: clock["t"])
    q0 = _put(store, "lab/Q0/2026-W38", {"forecast": {"deadline_at": "2026-09-14T10:30:00+08:00"}})
    clock["t"] = datetime(2026, 9, 14, 0, 40, tzinfo=timezone.utc)                # 08:40 Taipei: diez minutos tarde para Q1
    q1 = _put(store, "lab/Q1/2026-W38", {"forecast": {"deadline_at": "2026-09-14T08:30:00+08:00"}})
    for r in (q0, q1):
        # el reloj inyectado no cuenta (R20-03); aquí sólo se comprueba el plazo individual marcando system a mano
        pass
    lines = [json.loads(l) for l in (tmp_path / "manifest.jsonl").read_text(encoding="utf-8").splitlines()]
    for l in lines:
        l["clock_source"] = "system"
    (tmp_path / "manifest.jsonl").write_text("\n".join(json.dumps(l) for l in lines) + "\n", encoding="utf-8")
    ex._MANIFEST = None
    fa = ex.forecast_archive("lab", "2026-W38", {"Q0": q0.sha256, "Q1": q1.sha256})
    assert fa["before_deadline"] is False and "late:Q1" in fa["reasons"]


def _mark_system(tmp_path):
    lines = [json.loads(l) for l in (tmp_path / "manifest.jsonl").read_text(encoding="utf-8").splitlines()]
    for l in lines:
        l["clock_source"] = "system"
    (tmp_path / "manifest.jsonl").write_text("\n".join(json.dumps(l) for l in lines) + "\n", encoding="utf-8")


def _real_packet(store, cal, cutoff, src, dataset, packet_id):
    from twlab.packet import build_packet, packet_to_json, Document, AvailabilityQuality
    from twlab.timeutil import taipei
    from datetime import date, time
    docs = [Document(doc_id="A:bars:x", kind="price_bar_series", source_id="twse", security_ids=("TWSE:A@2000-01-01",),
                     available_at=taipei(date(2026, 9, 12), time(13, 30)), availability_quality=AvailabilityQuality.CONSERVATIVE_INFERENCE,
                     capture_id=src.capture_id, source_sha256=src.sha256, derivation="twse_mi_index_daily_v1",
                     payload={"history_sessions": 1, "last_session": "2026-09-11", "sessions": [["2026-09-11", "10", "10", 1000, "10000"]], "captures_doc": "twse:captures:x"}),
            Document(doc_id="twse:captures:x", kind="capture_manifest", source_id="twse", security_ids=(),
                     available_at=taipei(date(2026, 9, 12), time(13, 30)), availability_quality=AvailabilityQuality.CONSERVATIVE_INFERENCE,
                     capture_id=src.capture_id, source_sha256=src.sha256, derivation="capture_manifest_v1", payload={"session_captures": {"2026-09-11": src.capture_id}})]
    pk = build_packet(packet_id=packet_id, cutoff_at=cutoff, documents=docs, mode="historical", evidence_class="historical_numeric_temporally_controlled", calendar=cal)
    rec = store.put(source_id="packet", dataset=dataset, payload=packet_to_json(pk), url="u", content_type="application/json", extra={"packet_hash": pk.packet_hash()})
    return pk, rec


def test_r20_06_inputs_must_be_ingested_before_the_cutoff(tmp_path, monkeypatch):
    from datetime import datetime, timezone, date, time
    from twlab.calendar import TradingCalendar
    from twlab.timeutil import taipei
    ex, store, pkt, pk, fc, week = _real_week_fixture(tmp_path, monkeypatch)             # fuentes del sábado: antes del corte
    cutoff = week["cutoff_at"]
    assert ex.inputs_before_cutoff(pkt.capture_id, cutoff, pk.packet_hash())["ok"] is True
    cal = TradingCalendar(start=date(2026, 1, 1), end=date(2026, 12, 31), closures=[], source_id="synthetic", recorded_at=taipei(date(2026, 1, 1)))
    from twlab.store import RawStore
    clock = {"t": datetime(2026, 9, 13, 12, 0, tzinfo=timezone.utc)}                     # domingo 20:00 Taipei: después del corte
    store2 = RawStore(tmp_path, clock=lambda: clock["t"])
    late_cap = store2.put(source_id="tpex", dataset="dailyQuotes/2026-09-11", payload=b"y", url="u", content_type="application/json")
    pk2, rec2 = _real_packet(store2, cal, taipei(date(2026, 9, 13), time(18, 0)), late_cap, "lab/2026-W38b", "pkt-lab-2026-W38b")
    _mark_system(tmp_path); ex._MANIFEST = None; ex._INPUTS_CACHE.clear()
    res = ex.inputs_before_cutoff(rec2.capture_id, cutoff, pk2.packet_hash())
    assert res["ok"] is False and res["reason"] == "late_inputs"
    assert ex.inputs_before_cutoff(None, cutoff)["ok"] is False


def test_r20_07_next_cutoff_uses_the_full_instant(monkeypatch):
    from datetime import datetime, timezone
    ex = _load()
    scenarios = [{"weeks": [{"week_id": "2026-W37", "cutoff_at": "2026-09-06T18:00:00+08:00", "pending_outcome": True}], "weeks_operated": 17, "prospective_weeks": []}]
    class FakeDT(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 9, 13, 0, 0, tzinfo=timezone.utc)                # 08:00 Taipei del domingo 13: el corte aún no ha pasado
    monkeypatch.setattr(ex, "datetime", FakeDT)
    assert ex.project_status(scenarios)["next_cutoff"] == "2026-09-13"
    class FakeDT2(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 9, 13, 10, 30, tzinfo=timezone.utc)              # 18:30 Taipei: ya pasó
    monkeypatch.setattr(ex, "datetime", FakeDT2)
    assert ex.project_status(scenarios)["next_cutoff"] == "2026-09-20"


def test_r20_05_report_headers_survive_a_pending_entry_week():
    import importlib.util
    spec = importlib.util.spec_from_file_location("asm", ROOT / "scripts" / "assemble_backtest_reports.py")
    asm = importlib.util.module_from_spec(spec); spec.loader.exec_module(asm)
    cw = {"week_id": "2026-W38", "cutoff_at": "2026-09-13T18:00:00+08:00", "packet_capture": None,
          "forecasters": {f: {"picks": [{"symbol": "2330", "name": "台積電"}], "forecast_status": "selected"} for f in ("Q0", "Q1", "A1")}}
    txt = asm.picks_table(cw, "Estado")
    assert "entrada pendiente" in txt and "KeyError" not in txt


def test_r20_02_boundary_equal_instant_counts_as_on_time(tmp_path, monkeypatch):
    """Ingestión exactamente en el plazo (00:30 UTC = 08:30 Taipei) es «a tiempo»; un segundo después, tarde."""
    ex = _load(); monkeypatch.setattr(ex, "RAW", tmp_path); ex._MANIFEST = None
    body = json.dumps({"forecast": {"deadline_at": "2026-09-14T08:30:00+08:00", "status": "selected",
                                    "ranking": [{"security_id": "TWSE:A@2000-01-01", "ticker_as_of": "A", "rank": 1}]}}).encode("utf-8")
    import hashlib
    sha = hashlib.sha256(body).hexdigest()
    (tmp_path / "f.json").write_bytes(body)
    for at, expected in (("2026-09-14T00:30:00+00:00", True), ("2026-09-14T00:30:01+00:00", False)):
        rec = {"source_id": "forecast", "dataset": "lab/Q0/2026-W38", "ingested_at": at, "path": "f.json", "sha256": sha, "clock_source": "system"}
        (tmp_path / "manifest.jsonl").write_text(json.dumps(rec) + "\n", encoding="utf-8")
        ex._MANIFEST = None
        assert ex.forecast_archive("lab", "2026-W38", {"Q0": sha})["before_deadline"] is expected


def _week_fixture(tmp_path, monkeypatch):
    """Semana sintética íntegra con paquete real del contrato (véase _real_week_fixture)."""
    ex, store, pkt, pk, fc, week = _real_week_fixture(tmp_path, monkeypatch)
    expected = {f: {"sha": fc[f].sha256, "picks": ["TWSE:A@2000-01-01"], "packet_hash": pk.packet_hash()} for f in fc}
    return ex, store, pkt, fc, expected


def test_r21_01_every_forecaster_needs_an_identity(tmp_path, monkeypatch):
    ex, store, pkt, fc, expected = _week_fixture(tmp_path, monkeypatch)
    assert ex.forecast_archive("lab", "2026-W38", expected)["before_deadline"] is True
    for bad in (None, ""):
        e2 = dict(expected); e2["Q1"] = {"sha": bad, "picks": ["TWSE:A@2000-01-01"], "packet_hash": pkt.extra["packet_hash"]}
        fa = ex.forecast_archive("lab", "2026-W38", e2)
        assert fa["before_deadline"] is False and any(r.startswith("no_forecast_identity") for r in fa["reasons"])


def test_r21_02_shown_picks_and_packet_must_match_the_archived_bytes(tmp_path, monkeypatch):
    ex, store, pkt, fc, expected = _week_fixture(tmp_path, monkeypatch)
    e2 = json.loads(json.dumps(expected)); e2["Q0"]["picks"] = ["TWSE:FAKE@2000-01-01"]
    fa = ex.forecast_archive("lab", "2026-W38", e2)
    assert fa["before_deadline"] is False and "picks_mismatch:Q0" in fa["reasons"]
    e3 = json.loads(json.dumps(expected)); e3["A1"]["packet_hash"] = "other"
    fa = ex.forecast_archive("lab", "2026-W38", e3)
    assert fa["before_deadline"] is False and "packet_link_mismatch:A1" in fa["reasons"]
    assert ex.inputs_before_cutoff(pkt.capture_id, "2026-09-13T18:00:00+08:00", "other")["reason"] == "packet_hash_mismatch"


def test_r21_03_inputs_need_integrity_system_clock_and_complete_provenance(tmp_path, monkeypatch):
    ex, store, pkt, fc, expected = _week_fixture(tmp_path, monkeypatch)
    cutoff = "2026-09-13T18:00:00+08:00"
    assert ex.inputs_before_cutoff(pkt.capture_id, cutoff, pkt.extra["packet_hash"])["ok"] is True
    src = store.captures(source_id="twse")[0]
    (store.root / src.path).write_bytes(b"broken")                                     # fuente corrupta
    ex._INPUTS_CACHE.clear()
    r = ex.inputs_before_cutoff(pkt.capture_id, cutoff, pkt.extra["packet_hash"]); assert r["ok"] is False and r["reason"] == "unverified_inputs"
    (store.root / src.path).unlink()                                                   # fuente ausente
    ex._INPUTS_CACHE.clear()
    assert ex.inputs_before_cutoff(pkt.capture_id, cutoff, pkt.extra["packet_hash"])["reason"] == "unverified_inputs"
    (store.root / src.path).write_bytes(b"x")
    lines = [json.loads(l) for l in (tmp_path / "manifest.jsonl").read_text(encoding="utf-8").splitlines()]
    for l in lines:
        if l["capture_id"] == src.capture_id:
            l["clock_source"] = "injected"                                             # reloj inyectado en la fuente
    (tmp_path / "manifest.jsonl").write_text("\n".join(json.dumps(l) for l in lines) + "\n", encoding="utf-8")
    ex._MANIFEST = None; ex._INPUTS_CACHE.clear()
    assert ex.inputs_before_cutoff(pkt.capture_id, cutoff, pkt.extra["packet_hash"])["reason"] == "unverified_inputs"
    # paquete alterado sin actualizar su sha
    ex2, store2, pkt2, fc2, _ = _week_fixture(tmp_path / "b", monkeypatch)
    (store2.root / pkt2.path).write_bytes(b'{"mode":"historical","packet_hash":pkt.extra["packet_hash"],"admitted":[]}')
    ex2._INPUTS_CACHE.clear()
    assert ex2.inputs_before_cutoff(pkt2.capture_id, cutoff, pkt.extra["packet_hash"])["reason"].startswith("packet_")
    # documento admitido sin captura o manifiesto vacío
    ex3, store3, _, _, _ = _week_fixture(tmp_path / "c", monkeypatch)
    src3 = store3.captures(source_id="twse")[0]
    for body in ({"mode": "historical", "packet_hash": pkt.extra["packet_hash"], "admitted": [{"kind": "price_bar_series"}]},
                 {"mode": "historical", "packet_hash": pkt.extra["packet_hash"], "admitted": [{"kind": "capture_manifest", "capture_id": src3.capture_id, "payload": {"session_captures": {}}}]}):
        p = store3.put(source_id="packet", dataset="lab/2026-W39", payload=json.dumps(body).encode(), url="u", content_type="application/json")
        lines = [json.loads(l) for l in (tmp_path / "c" / "manifest.jsonl").read_text(encoding="utf-8").splitlines()]
        for l in lines: l["clock_source"] = "system"
        (tmp_path / "c" / "manifest.jsonl").write_text("\n".join(json.dumps(l) for l in lines) + "\n", encoding="utf-8")
        ex3._MANIFEST = None; ex3._INPUTS_CACHE.clear()
        assert ex3.inputs_before_cutoff(p.capture_id, cutoff, pkt.extra["packet_hash"])["ok"] is False


def test_r21_04_cache_is_keyed_by_cutoff(tmp_path, monkeypatch):
    ex, store, pkt, fc, expected = _week_fixture(tmp_path, monkeypatch)
    assert ex.inputs_before_cutoff(pkt.capture_id, "2026-09-13T18:00:00+08:00", pkt.extra["packet_hash"])["ok"] is True
    assert ex.inputs_before_cutoff(pkt.capture_id, "2026-09-11T18:00:00+08:00", pkt.extra["packet_hash"])["ok"] is False


def test_r21_05_first_ingestion_is_chosen_by_instant_across_offsets(tmp_path, monkeypatch):
    ex = _load(); monkeypatch.setattr(ex, "RAW", tmp_path); ex._MANIFEST = None
    import hashlib
    body = json.dumps({"forecast": {"deadline_at": "2026-09-14T08:30:00+08:00"}}).encode(); sha = hashlib.sha256(body).hexdigest()
    (tmp_path / "f.json").write_bytes(body)
    recs = [{"source_id": "forecast", "dataset": "lab/Q0/2026-W38", "ingested_at": "2026-09-13T19:00:00+08:00", "path": "f.json", "sha256": sha, "clock_source": "injected"},
            {"source_id": "forecast", "dataset": "lab/Q0/2026-W38", "ingested_at": "2026-09-13T12:00:00+00:00", "path": "f.json", "sha256": sha, "clock_source": "system"}]
    (tmp_path / "manifest.jsonl").write_text("\n".join(json.dumps(r) for r in recs) + "\n", encoding="utf-8")
    fa = ex.forecast_archive("lab", "2026-W38", {"Q0": sha})
    assert fa["before_deadline"] is False and any(r.startswith("clock:injected") for r in fa["reasons"])   # 19:00+08 = 11:00 UTC es la primera


def test_r21_06_incomplete_packet_record_fails_closed(tmp_path, monkeypatch):
    ex, store, pkt, fc, expected = _week_fixture(tmp_path, monkeypatch)
    lines = [json.loads(l) for l in (tmp_path / "manifest.jsonl").read_text(encoding="utf-8").splitlines()]
    for l in lines:
        if l["capture_id"] == pkt.capture_id:
            del l["path"]
    (tmp_path / "manifest.jsonl").write_text("\n".join(json.dumps(l) for l in lines) + "\n", encoding="utf-8")
    ex._MANIFEST = None; ex._INPUTS_CACHE.clear()
    r = ex.inputs_before_cutoff(pkt.capture_id, "2026-09-13T18:00:00+08:00", pkt.extra["packet_hash"])
    assert r["ok"] is False and r["reason"] == "packet_incomplete_record:path"


def _real_week_fixture(tmp_path, monkeypatch):
    """Semana sintética con paquete real (contrato twlab) y predicciones con el contrato del laboratorio."""
    from datetime import datetime, timezone, date, time
    from twlab.store import RawStore
    from twlab.packet import build_packet, packet_to_json, Document, AvailabilityQuality
    from twlab.calendar import TradingCalendar
    from twlab.timeutil import taipei
    tmp_path.mkdir(parents=True, exist_ok=True)
    ex = _load(); monkeypatch.setattr(ex, "RAW", tmp_path); monkeypatch.setattr(ex, "STORE", tmp_path); ex._MANIFEST = None; ex._INPUTS_CACHE.clear()
    clock = {"t": datetime(2026, 9, 12, 8, 0, tzinfo=timezone.utc)}
    store = RawStore(tmp_path, clock=lambda: clock["t"])
    src = store.put(source_id="twse", dataset="MI_INDEX_ALLBUT0999/2026-09-11", payload=b"x", url="u", content_type="application/json")
    cal = TradingCalendar(start=date(2026, 1, 1), end=date(2026, 12, 31), closures=[], source_id="synthetic", recorded_at=taipei(date(2026, 1, 1)))
    cutoff = taipei(date(2026, 9, 13), time(18, 0))
    docs = [Document(doc_id="A:bars:2026-W38", kind="price_bar_series", source_id="twse", security_ids=("TWSE:A@2000-01-01",),
                     available_at=taipei(date(2026, 9, 12), time(13, 30)), availability_quality=AvailabilityQuality.CONSERVATIVE_INFERENCE,
                     capture_id=src.capture_id, source_sha256=src.sha256, derivation="twse_mi_index_daily_v1",
                     payload={"history_sessions": 1, "last_session": "2026-09-11", "name": "甲公司", "sessions": [["2026-09-11", "10", "10", 1000, "10000"]], "captures_doc": "twse:captures:2026-W38"}),
            Document(doc_id="twse:captures:2026-W38", kind="capture_manifest", source_id="twse", security_ids=(),
                     available_at=taipei(date(2026, 9, 12), time(13, 30)), availability_quality=AvailabilityQuality.CONSERVATIVE_INFERENCE,
                     capture_id=src.capture_id, source_sha256=src.sha256, derivation="capture_manifest_v1", payload={"session_captures": {"2026-09-11": src.capture_id}})]
    pk = build_packet(packet_id="pkt-lab-2026-W38", cutoff_at=cutoff, documents=docs, mode="historical", evidence_class="historical_numeric_temporally_controlled", calendar=cal)
    pkt = store.put(source_id="packet", dataset="lab/2026-W38", payload=packet_to_json(pk), url="u", content_type="application/json", extra={"packet_hash": pk.packet_hash()})
    # maestro archivado por la corrida (R23-01): A es el símbolo vigente de TWSE:A@2000-01-01
    from twlab.master import SecurityMaster, SecurityVersion
    from twlab.backtest import master_snapshot_bytes
    master = SecurityMaster()
    master.add(SecurityVersion(security_id="TWSE:A@2000-01-01", issuer_id="A", symbol="A", name_zh="甲公司", market="TWSE", board="main",
                               instrument_type="ordinary_equity", valid_from=date(2000, 1, 1), valid_to=None,
                               recorded_at=datetime(2026, 1, 1, tzinfo=timezone.utc), source_id="synthetic"))
    mrec = store.put(source_id="master", dataset="lab/master", payload=master_snapshot_bytes(master), url="u", content_type="application/x-ndjson")
    clock["t"] = datetime(2026, 9, 13, 12, 0, tzinfo=timezone.utc)
    fc = {}
    for f in ("Q0", "Q1", "A1"):
        body = {"forecast": {"cutoff_at": cutoff.isoformat(), "deadline_at": "2026-09-14T08:30:00+08:00", "status": "selected",
                             "ranking": [{"security_id": "TWSE:A@2000-01-01", "ticker_as_of": "A", "rank": 1}]}, "packet_hash": pk.packet_hash(),
                "master_sha256": mrec.sha256}
        fc[f] = store.put(source_id="forecast", dataset=f"lab/{f}/2026-W38", payload=json.dumps(body).encode(), url="u", content_type="application/json")
    _mark_system(tmp_path); ex._MANIFEST = None; ex._INPUTS_CACHE.clear(); ex._MASTER_CACHE.clear()
    week = {"week_id": "2026-W38", "cutoff_at": cutoff.isoformat(), "packet_capture": pkt.capture_id, "packet_hash": pk.packet_hash(),
            "master_capture": mrec.capture_id, "master_sha256": mrec.sha256,
            "forecasters": {f: {"forecast_sha256": fc[f].sha256, "forecast_status": "selected",
                                "picks": [{"security_id": "TWSE:A@2000-01-01", "symbol": "A", "name": "甲公司"}]} for f in fc}}
    return ex, store, pkt, pk, fc, week


def _classify(ex, week):
    c = ex.classify_week("lab", week)
    fa = dict(c["fa"]); fa["reasons"] = c["reasons"]
    return fa, c["inp"], c["prospective"]


def test_r22_real_packet_and_valid_contract_is_a_prediction(tmp_path, monkeypatch):
    ex, store, pkt, pk, fc, week = _real_week_fixture(tmp_path, monkeypatch)
    fa, inp, pro = _classify(ex, week)
    assert pro is True, (fa["reasons"], inp)


def _save_forecast(store, tmp_path, f, mutate, pk):
    body = {"forecast": {"cutoff_at": pk.cutoff_at.isoformat(), "deadline_at": "2026-09-14T08:30:00+08:00", "status": "selected",
                         "ranking": [{"security_id": "TWSE:A@2000-01-01", "ticker_as_of": "A", "rank": 1}]}, "packet_hash": pk.packet_hash(),
            "master_sha256": store.captures(source_id="master")[0].sha256}
    mutate(body["forecast"])
    rec = store.put(source_id="forecast", dataset=f"lab/{f}/2026-W38", payload=json.dumps(body).encode(), url="u", content_type="application/json")
    _mark_system(tmp_path)
    return rec


def test_r22_01_invalid_or_incoherent_forecasts_are_not_predictions(tmp_path, monkeypatch):
    ex, store, pkt, pk, fc, week = _real_week_fixture(tmp_path, monkeypatch)
    cases = [
        (lambda f: f.update(status="invalid", ranking=[]), [], "invalid"),
        (lambda f: f.update(status="selected", ranking=[]), [], "selected"),
        (lambda f: f.update(status="abstained"), [], "abstained"),
        (lambda f: f.update(ranking=[{"security_id": "TWSE:A@2000-01-01", "ticker_as_of": "A"}, {"security_id": "TWSE:A@2000-01-01", "ticker_as_of": "A"}]),
         [{"security_id": "TWSE:A@2000-01-01", "symbol": "A", "name": "甲公司"}] * 2, "selected"),
    ]
    for mutate, picks, status in cases:
        rec = _save_forecast(store, tmp_path, "Q0", mutate, pk)
        ex._MANIFEST = None; ex._INPUTS_CACHE.clear()
        w = json.loads(json.dumps(week)); w["forecasters"]["Q0"].update(forecast_sha256=rec.sha256, forecast_status=status, picks=picks)
        fa, inp, pro = _classify(ex, w)
        assert pro is False and any(r.startswith("forecast_contract:Q0") or r.startswith("picks_mismatch:Q0") for r in fa["reasons"]), (mutate, fa["reasons"])
    # abstención válida: ranking vacío y picks vacíos
    rec = _save_forecast(store, tmp_path, "Q0", lambda f: f.update(status="abstained", ranking=[]), pk)
    ex._MANIFEST = None; ex._INPUTS_CACHE.clear()
    w = json.loads(json.dumps(week)); w["forecasters"]["Q0"].update(forecast_sha256=rec.sha256, forecast_status="abstained", picks=[])
    assert _classify(ex, w)[2] is True


def test_r22_02_logical_packet_hash_is_recomputed_from_the_contract(tmp_path, monkeypatch):
    ex, store, pkt, pk, fc, week = _real_week_fixture(tmp_path, monkeypatch)
    body = json.loads(store.read(pkt))
    for mutate in (lambda b: b["admitted"][0].update(payload={"fabricated": 123}),
                   lambda b: b["admitted"][0].update(source_sha256="0" * 64),
                   lambda b: b.__setitem__("rejected", [["X", "unknown_availability", "availability could not be established"]]),
                   lambda b: b.pop("packet_id")):
        b2 = json.loads(json.dumps(body)); mutate(b2)
        raw = json.dumps(b2).encode()
        lines = [json.loads(l) for l in (tmp_path / "manifest.jsonl").read_text(encoding="utf-8").splitlines()]
        import hashlib
        for l in lines:
            if l["capture_id"] == pkt.capture_id:
                (tmp_path / l["path"]).write_bytes(raw); l["sha256"] = hashlib.sha256(raw).hexdigest()   # sha de bytes correcto, hash lógico no
        (tmp_path / "manifest.jsonl").write_text("\n".join(json.dumps(l) for l in lines) + "\n", encoding="utf-8")
        ex._MANIFEST = None; ex._INPUTS_CACHE.clear()
        inp = ex.inputs_before_cutoff(pkt.capture_id, week["cutoff_at"], week["packet_hash"])
        assert inp["ok"] is False and inp["reason"].startswith(("packet_hash_mismatch", "packet_contract")), (inp, mutate)


def test_r22_03_cutoff_comes_from_the_archived_packet_and_forecasts(tmp_path, monkeypatch):
    ex, store, pkt, pk, fc, week = _real_week_fixture(tmp_path, monkeypatch)
    w = json.loads(json.dumps(week)); w["cutoff_at"] = "2026-09-13T23:00:00+08:00"          # corte «movido» sólo en el JSON de resultados
    fa, inp, pro = _classify(ex, w)
    assert pro is False and (any(r.startswith("cutoff_mismatch") for r in fa["reasons"]) or inp.get("reason") == "cutoff_mismatch")


def test_r22_04_malformed_records_and_packets_fail_closed(tmp_path, monkeypatch):
    ex, store, pkt, pk, fc, week = _real_week_fixture(tmp_path, monkeypatch)
    lines = [json.loads(l) for l in (tmp_path / "manifest.jsonl").read_text(encoding="utf-8").splitlines()]
    for field, value in (("path", 42), ("ingested_at", 42)):
        l2 = json.loads(json.dumps(lines))
        for l in l2:
            if l["capture_id"] == pkt.capture_id:
                l[field] = value
        (tmp_path / "manifest.jsonl").write_text("\n".join(json.dumps(l) for l in l2) + "\n", encoding="utf-8")
        ex._MANIFEST = None; ex._INPUTS_CACHE.clear()
        r = ex.inputs_before_cutoff(pkt.capture_id, week["cutoff_at"], week["packet_hash"])
        assert r["ok"] is False and r["reason"].startswith("packet_")
    (tmp_path / "manifest.jsonl").write_text("\n".join(json.dumps(l) for l in lines) + "\n", encoding="utf-8")
    for bad in (b'{"admitted":["bad"]}', b'{"admitted":[{"kind":"capture_manifest","capture_id":"x","payload":{"session_captures":["bad"]}}]}'):
        import hashlib
        p = store.put(source_id="packet", dataset="lab/2026-W39", payload=bad, url="u", content_type="application/json")
        _mark_system(tmp_path); ex._MANIFEST = None; ex._INPUTS_CACHE.clear()
        r = ex.inputs_before_cutoff(p.capture_id, week["cutoff_at"], None)
        assert r["ok"] is False


def test_r22_05_displayed_symbol_and_name_must_match_archive_and_master(tmp_path, monkeypatch):
    ex, store, pkt, pk, fc, week = _real_week_fixture(tmp_path, monkeypatch)
    w = json.loads(json.dumps(week)); w["forecasters"]["Q0"]["picks"][0].update(symbol="9999")
    fa, _, pro = _classify(ex, w); assert pro is False and "symbol_mismatch:Q0" in fa["reasons"]
    w = json.loads(json.dumps(week)); w["forecasters"]["Q1"]["picks"][0].update(name="EMPRESA INVENTADA")
    fa, _, pro = _classify(ex, w); assert pro is False and "name_mismatch:Q1" in fa["reasons"]


def test_r22_exporter_imports_twlab_outside_pytest():
    """El exportador debe poder recalcular el hash lógico también cuando se ejecuta como script (sin pythonpath de pytest)."""
    import subprocess, sys
    r = subprocess.run([sys.executable, "-c", "import importlib.util,sys; spec=importlib.util.spec_from_file_location('x', r'%s'); m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m); import twlab.packet; print('ok')" % (ROOT / "scripts" / "export_site_data.py")],
                       capture_output=True, text=True, env={k: v for k, v in __import__("os").environ.items() if k != "PYTHONPATH"}, cwd=str(ROOT))
    assert r.returncode == 0 and "ok" in r.stdout, r.stderr[-400:]


def test_r22_classify_week_accepts_exported_and_raw_week_shapes(tmp_path, monkeypatch):
    ex, store, pkt, pk, fc, week = _real_week_fixture(tmp_path, monkeypatch)
    raw_shape = json.loads(json.dumps(week))
    exported_shape = json.loads(json.dumps(week))
    for f in exported_shape["forecasters"]:
        exported_shape["forecasters"][f]["status"] = exported_shape["forecasters"][f].pop("forecast_status")
    assert ex.classify_week("lab", raw_shape)["prospective"] is True
    assert ex.classify_week("lab", exported_shape)["prospective"] is True


def test_r22_rank_fields_must_declare_the_array_order(tmp_path, monkeypatch):
    """Un ranking archivado cuyo campo ``rank`` no es 1..n en el orden del array es ambiguo: no cuenta como predicción."""
    ex, store, pkt, pk, fc, week = _real_week_fixture(tmp_path, monkeypatch)
    assert ex.classify_week("lab", week)["prospective"] is True
    body = json.loads(store.read(fc["Q0"]))
    body["forecast"]["ranking"][0]["rank"] = 2                       # rango declarado distinto del orden del array
    rec = store.put(source_id="forecast", dataset="lab/Q0/" + week["week_id"], payload=json.dumps(body).encode(), url="u", content_type="application/json")
    _mark_system(tmp_path); ex._MANIFEST = None; ex._INPUTS_CACHE.clear()
    week["forecasters"]["Q0"]["forecast_sha256"] = rec.sha256
    c = ex.classify_week("lab", week)
    assert c["prospective"] is False and "forecast_contract:Q0:rank_order" in c["reasons"], c


def test_r22_assembler_names_unverified_provenance(tmp_path, monkeypatch):
    """La frase del ensamblador para el estado «procedencia sin acreditar» debe decirlo literalmente."""
    ex, store, pkt, pk, fc, week = _real_week_fixture(tmp_path, monkeypatch)
    (store.root / store.get(pk.admitted[0].capture_id).path).unlink()
    c = ex.classify_week("lab", week)
    assert c["inp"]["reason"] == "unverified_inputs"
    import importlib.util
    spec = importlib.util.spec_from_file_location("assemble_backtest_reports", ROOT / "scripts" / "assemble_backtest_reports.py")
    asm = importlib.util.module_from_spec(spec); spec.loader.exec_module(asm)
    monkeypatch.setattr(ex, "RAW", store.root, raising=False)
    real_spec = importlib.util.spec_from_file_location
    def redirected(name, *a, **k):
        sp = real_spec(name, *a, **k)
        if name == "export_site_data":
            orig = sp.loader.exec_module
            def run(m):
                orig(m); m.RAW = store.root
            sp.loader.exec_module = run
        return sp
    monkeypatch.setattr(importlib.util, "spec_from_file_location", redirected)
    txt = asm.temporal_sentence({"label": "lab", "assumptions": {"archive_label": "lab"}}, week)
    assert "procedencia de las entradas no queda acreditada" in txt and "unverified_inputs" in txt


def _rearchive_forecast(ex, store, tmp_path, week, fc, f, mutate, packet_hash=None, master_sha256=None):
    """Vuelve a archivar la predicción de ``f`` con una mutación y apunta la semana a los bytes nuevos."""
    body = json.loads(store.read(fc[f]))
    mutate(body["forecast"])
    if packet_hash is not None:
        body["packet_hash"] = packet_hash
    if master_sha256 is not None:
        body["master_sha256"] = master_sha256
    rec = store.put(source_id="forecast", dataset=f"lab/{f}/{week['week_id']}", payload=json.dumps(body).encode(), url="u", content_type="application/json")
    _mark_system(tmp_path); ex._MANIFEST = None; ex._INPUTS_CACHE.clear(); ex._MASTER_CACHE.clear()
    week["forecasters"][f]["forecast_sha256"] = rec.sha256
    return rec


def _rewrite_manifest(ex, tmp_path, rows, prefix=""):
    (tmp_path / "manifest.jsonl").write_text(prefix + "\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    ex._MANIFEST = None; ex._INPUTS_CACHE.clear(); ex._MASTER_CACHE.clear()


def _manifest_rows(tmp_path):
    return [json.loads(l) for l in (tmp_path / "manifest.jsonl").read_text(encoding="utf-8").splitlines()]


def test_r23_01_ticker_of_another_security_is_not_a_prediction(tmp_path, monkeypatch):
    """security_id de A con ticker_as_of «B» (y símbolo «B» mostrado): coincide JSON con archivo, pero no con el maestro."""
    ex, store, pkt, pk, fc, week = _real_week_fixture(tmp_path, monkeypatch)
    _rearchive_forecast(ex, store, tmp_path, week, fc, "Q0", lambda fo: fo["ranking"][0].update(ticker_as_of="B"))
    week["forecasters"]["Q0"]["picks"][0]["symbol"] = "B"
    c = ex.classify_week("lab", week)
    assert c["prospective"] is False and "identity_symbol_mismatch:Q0:TWSE:A@2000-01-01" in c["reasons"], c


def test_r23_01_unknown_security_is_not_a_prediction_even_if_the_packet_has_a_series(tmp_path, monkeypatch):
    from twlab.packet import packet_from_json, packet_to_json
    from dataclasses import replace
    ex, store, pkt, pk, fc, week = _real_week_fixture(tmp_path, monkeypatch)
    ghost = "TWSE:GHOST@2000-01-01"
    bars = next(d for d in pk.admitted if d.kind == "price_bar_series")
    payload = dict(bars.payload); payload["name"] = "GHOST"
    pk2 = replace(pk, admitted=pk.admitted + (replace(bars, doc_id="GHOST:bars:2026-W38", security_ids=(ghost,), payload=payload),))
    prec = store.put(source_id="packet", dataset="lab/2026-W38", payload=packet_to_json(pk2), url="u", content_type="application/json",
                     extra={"packet_hash": pk2.packet_hash()})
    assert packet_from_json(store.read(prec)).packet_hash() == pk2.packet_hash()
    week.update(packet_capture=prec.capture_id, packet_hash=pk2.packet_hash())
    for f in ("Q0", "Q1", "A1"):
        _rearchive_forecast(ex, store, tmp_path, week, fc, f, lambda fo: fo["ranking"][0].update(security_id=ghost, ticker_as_of="GHOST"),
                            packet_hash=pk2.packet_hash())
        week["forecasters"][f]["picks"] = [{"security_id": ghost, "symbol": "GHOST", "name": "GHOST"}]
    c = ex.classify_week("lab", week)
    assert c["prospective"] is False and f"identity_unknown_security:Q0:{ghost}" in c["reasons"], c


def test_r23_01_week_without_archived_master_is_not_a_prediction(tmp_path, monkeypatch):
    ex, store, pkt, pk, fc, week = _real_week_fixture(tmp_path, monkeypatch)
    assert ex.classify_week("lab", week)["prospective"] is True
    week.pop("master_capture")
    c = ex.classify_week("lab", week)
    assert c["prospective"] is False and "no_master_identity" in c["reasons"], c
    week["master_capture"] = pkt.capture_id                       # un registro que no es un maestro tampoco acredita nada
    ex._MASTER_CACHE.clear()
    c = ex.classify_week("lab", week)
    assert c["prospective"] is False and "master_record_mismatch" in c["reasons"], c        # fuente/dataset (R24-05) antes que el contrato


@pytest.mark.parametrize("kind", ["forecast_sid_list", "forecast_time_number", "forecast_dataset_list", "packet_extra_list", "manifest_row_not_object"])
def test_r23_02_malformed_archive_records_fail_closed(tmp_path, monkeypatch, kind):
    ex, store, pkt, pk, fc, week = _real_week_fixture(tmp_path, monkeypatch)
    if kind == "forecast_sid_list":
        _rearchive_forecast(ex, store, tmp_path, week, fc, "Q0", lambda fo: fo["ranking"][0].update(security_id=["A"]))
    else:
        rows = _manifest_rows(tmp_path)
        for row in rows:
            if kind == "packet_extra_list" and row["capture_id"] == pkt.capture_id:
                row["extra"] = ["bad"]
            if row["capture_id"] == fc["Q0"].capture_id:
                if kind == "forecast_time_number":
                    row["ingested_at"] = 42
                elif kind == "forecast_dataset_list":
                    row["dataset"] = ["bad"]
        _rewrite_manifest(ex, tmp_path, rows, prefix='["not", "an", "object"]\n' if kind == "manifest_row_not_object" else "")
    c = ex.classify_week("lab", week)                          # no lanza: cierra (o ignora la línea que no es un registro)
    assert c["prospective"] is (kind == "manifest_row_not_object"), (kind, c)


def test_r23_02_any_exception_inside_the_classification_closes_the_week(tmp_path, monkeypatch):
    ex, store, pkt, pk, fc, week = _real_week_fixture(tmp_path, monkeypatch)
    def boom(*a, **k):
        raise RuntimeError("boom")
    monkeypatch.setattr(ex, "inputs_before_cutoff", boom)
    c = ex.classify_week("lab", week)
    assert c["prospective"] is False and "classification_error:RuntimeError" in c["reasons"], c


@pytest.mark.parametrize("value", [True, 1.0, "1"])
def test_r23_03_rank_must_be_a_strict_integer(tmp_path, monkeypatch, value):
    ex, store, pkt, pk, fc, week = _real_week_fixture(tmp_path, monkeypatch)
    _rearchive_forecast(ex, store, tmp_path, week, fc, "Q0", lambda fo: fo["ranking"][0].update(rank=value))
    c = ex.classify_week("lab", week)
    assert c["prospective"] is False and "forecast_contract:Q0:rank_order" in c["reasons"], c


def test_r23_04_packet_record_must_declare_the_logical_hash(tmp_path, monkeypatch):
    ex, store, pkt, pk, fc, week = _real_week_fixture(tmp_path, monkeypatch)
    rows = _manifest_rows(tmp_path)
    for row in rows:
        if row["capture_id"] == pkt.capture_id:
            row["extra"].pop("packet_hash")
    _rewrite_manifest(ex, tmp_path, rows)
    c = ex.classify_week("lab", week)
    assert c["prospective"] is False and "packet_record_hash_missing" in c["reasons"], c


def _master_rows(store, week):
    return [json.loads(l) for l in store.read(store.get(week["master_capture"])).decode("utf-8").splitlines()]


def _replace_master(ex, store, tmp_path, week, fc, rows, *, source_id="master", dataset="lab/master", relink=True):
    """Archiva otra instantánea del maestro y, si ``relink``, vuelve a archivar las tres predicciones citándola."""
    payload = ("\n".join(json.dumps(r, ensure_ascii=False, sort_keys=True) for r in rows) + "\n").encode("utf-8")
    rec = store.put(source_id=source_id, dataset=dataset, payload=payload, url="u", content_type="application/x-ndjson")
    week["master_capture"] = rec.capture_id
    if relink:
        for f in ("Q0", "Q1", "A1"):
            _rearchive_forecast(ex, store, tmp_path, week, fc, f, lambda fo: None, master_sha256=rec.sha256)
    _mark_system(tmp_path); ex._MANIFEST = None; ex._INPUTS_CACHE.clear(); ex._MASTER_CACHE.clear()
    return rec


@pytest.mark.parametrize("kind", ["recorded_after_cutoff", "revision_after_cutoff", "revision_before_cutoff", "expired_at_cutoff", "nonsegment"])
def test_r24_01_master_view_is_the_one_known_at_the_cutoff(tmp_path, monkeypatch, kind):
    """Sólo las filas registradas hasta el corte (2026-09-13 18:00 Taipéi = 10:00 UTC) acreditan identidad."""
    ex, store, pkt, pk, fc, week = _real_week_fixture(tmp_path, monkeypatch)
    rows = _master_rows(store, week)
    row = rows[0]
    if kind == "recorded_after_cutoff":
        row["recorded_at"] = "2026-09-13T11:00:00+00:00"
    elif kind in ("revision_after_cutoff", "revision_before_cutoff"):
        row["symbol"] = "OLD"
        revised = dict(row, symbol="A", recorded_at="2026-09-13T11:00:00+00:00" if kind == "revision_after_cutoff" else "2026-09-13T09:00:00+00:00")
        rows.append(revised)
    elif kind == "expired_at_cutoff":
        row["valid_to"] = "2026-09-13"
    elif kind == "nonsegment":
        row["kind"] = "terminal_event"
    _replace_master(ex, store, tmp_path, week, fc, rows)
    c = ex.classify_week("lab", week)
    assert c["prospective"] is (kind == "revision_before_cutoff"), (kind, c)
    if kind == "revision_after_cutoff":
        assert "identity_symbol_mismatch:Q0:TWSE:A@2000-01-01" in c["reasons"]
    if kind in ("recorded_after_cutoff", "expired_at_cutoff", "nonsegment"):
        assert "identity_unknown_security:Q0:TWSE:A@2000-01-01" in c["reasons"]


def test_r24_02_master_archived_after_the_deadline_does_not_accredit(tmp_path, monkeypatch):
    """Maestro original corrupto y repuesto (mismos bytes) después del plazo: la primera ingestión íntegra es tardía."""
    from datetime import datetime, timezone
    ex, store, pkt, pk, fc, week = _real_week_fixture(tmp_path, monkeypatch)
    original = store.get(week["master_capture"])
    payload = store.read(original)
    (store.root / original.path).write_bytes(b"corrupt")
    store._clock = lambda: datetime(2026, 9, 15, 12, 0, tzinfo=timezone.utc)      # martes, después del plazo del lunes 08:30
    rec = store.put(source_id="master", dataset="lab/master", payload=payload, url="u", content_type="application/x-ndjson")
    assert rec.sha256 == original.sha256
    week["master_capture"] = rec.capture_id
    _mark_system(tmp_path); ex._MANIFEST = None; ex._INPUTS_CACHE.clear(); ex._MASTER_CACHE.clear()
    c = ex.classify_week("lab", week)
    assert c["prospective"] is False and "master_late:Q0" in c["reasons"], c


def test_r24_02_forecast_must_declare_the_master_bytes_it_used(tmp_path, monkeypatch):
    ex, store, pkt, pk, fc, week = _real_week_fixture(tmp_path, monkeypatch)
    rows = _master_rows(store, week)
    _replace_master(ex, store, tmp_path, week, fc, rows + [dict(rows[0], security_id="TWSE:B@2000-01-01", issuer_id="B", symbol="B", name_zh="乙公司")],
                    relink=False)                                                 # maestro nuevo, predicciones sin volver a archivar
    c = ex.classify_week("lab", week)
    assert c["prospective"] is False and {"master_link_mismatch:Q0", "master_link_mismatch:Q1", "master_link_mismatch:A1"} <= set(c["reasons"]), c
    _replace_master(ex, store, tmp_path, week, fc, _master_rows(store, week))       # mismas filas, predicciones re-archivadas citándolas
    assert ex.classify_week("lab", week)["prospective"] is True


@pytest.mark.parametrize("field,value", [("valid_to", False), ("valid_to", 0), ("valid_to", []), ("valid_to", ""), ("valid_to", 42),
                                         ("recorded_at", "2026-01-01T00:00:00"), ("recorded_at", 42), ("valid_from", []),
                                         ("security_id", ["A"]), ("symbol", ["A"]), ("currency", None), ("extra_field", "x")])
def test_r24_03_master_rows_with_invalid_types_do_not_accredit(tmp_path, monkeypatch, field, value):
    ex, store, pkt, pk, fc, week = _real_week_fixture(tmp_path, monkeypatch)
    rows = _master_rows(store, week)
    rows[0][field] = value
    _replace_master(ex, store, tmp_path, week, fc, rows)
    c = ex.classify_week("lab", week)
    assert c["prospective"] is False and any(r.startswith("master_contract:") for r in c["reasons"]), (field, value, c)


def test_r24_03_conflicting_rows_with_equal_recorded_at_are_invalid(tmp_path, monkeypatch):
    """Dos filas del mismo segmento con el mismo recorded_at y distinto símbolo: SecurityMaster.add las rechaza."""
    ex, store, pkt, pk, fc, week = _real_week_fixture(tmp_path, monkeypatch)
    rows = _master_rows(store, week)
    rows.append(dict(rows[0], symbol="OTHER"))
    _replace_master(ex, store, tmp_path, week, fc, rows)
    c = ex.classify_week("lab", week)
    assert c["prospective"] is False and "master_contract:ValueError" in c["reasons"], c


@pytest.mark.parametrize("kind", ["series_of_another_symbol", "unselected_ghost_series"])
def test_r24_04_packet_series_must_be_coherent_with_the_master(tmp_path, monkeypatch, kind):
    from twlab.packet import packet_to_json
    from dataclasses import replace
    ex, store, pkt, pk, fc, week = _real_week_fixture(tmp_path, monkeypatch)
    bars = next(d for d in pk.admitted if d.kind == "price_bar_series")
    if kind == "series_of_another_symbol":
        docs = tuple(replace(d, doc_id="B:bars:2026-W38") if d is bars else d for d in pk.admitted)   # serie de B con identidad de A
        expected = "packet_symbol_mismatch:TWSE:A@2000-01-01"
    else:
        payload = dict(bars.payload); payload["name"] = "GHOST"
        docs = pk.admitted + (replace(bars, doc_id="GHOST:bars:2026-W38", security_ids=("TWSE:GHOST@2000-01-01",), payload=payload),)
        expected = "packet_unknown_security:TWSE:GHOST@2000-01-01"
    pk2 = replace(pk, admitted=docs)
    prec = store.put(source_id="packet", dataset="lab/2026-W38", payload=packet_to_json(pk2), url="u", content_type="application/json",
                     extra={"packet_hash": pk2.packet_hash()})
    week.update(packet_capture=prec.capture_id, packet_hash=pk2.packet_hash())
    for f in ("Q0", "Q1", "A1"):
        _rearchive_forecast(ex, store, tmp_path, week, fc, f, lambda fo: None, packet_hash=pk2.packet_hash())
    c = ex.classify_week("lab", week)
    assert c["prospective"] is False and expected in c["reasons"], (kind, c)


@pytest.mark.parametrize("source_id,dataset", [("untrusted", "lab/master"), ("master", "other/not-master"), ("packet", "lab/master")])
def test_r24_05_master_record_must_come_from_the_master_source_and_dataset(tmp_path, monkeypatch, source_id, dataset):
    ex, store, pkt, pk, fc, week = _real_week_fixture(tmp_path, monkeypatch)
    _replace_master(ex, store, tmp_path, week, fc, _master_rows(store, week), source_id=source_id, dataset=dataset)
    c = ex.classify_week("lab", week)
    assert c["prospective"] is False and "master_record_mismatch" in c["reasons"], c


def test_r24_06_a_failing_stage_keeps_the_evidence_already_verified(tmp_path, monkeypatch):
    ex, store, pkt, pk, fc, week = _real_week_fixture(tmp_path, monkeypatch)
    before = ex.classify_week("lab", week)
    assert before["fa"]["before_deadline"] is True and before["prospective"] is True
    week["packet_capture"] = ["malformed"]
    after = ex.classify_week("lab", week)
    assert after["prospective"] is False
    assert after["reasons"] == ["classification_error:TypeError"], after["reasons"]
    assert after["fa"]["before_deadline"] is True and after["fa"]["archived_at"] == before["fa"]["archived_at"]
    assert after["master"]["ok"] is True and after["inp"]["reason"] == "classification_error:TypeError"
    # la etapa de identidad también cierra sola cuando falla
    week["packet_capture"] = pkt.capture_id
    monkeypatch.setattr(ex, "master_identity", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    c = ex.classify_week("lab", week)
    assert c["prospective"] is False and c["fa"]["before_deadline"] is True and "classification_error:RuntimeError" in c["reasons"], c
