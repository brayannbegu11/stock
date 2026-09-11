"""Pruebas del exportador del sitio (scripts/export_site_data.py): R17-07 y R17-13."""
import importlib.util
import json
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


def test_r20_06_inputs_must_be_ingested_before_the_cutoff(tmp_path, monkeypatch):
    from datetime import datetime, timezone
    from twlab.store import RawStore
    ex = _load(); monkeypatch.setattr(ex, "RAW", tmp_path); ex._MANIFEST = None; ex._INPUTS_CACHE.clear()
    clock = {"t": datetime(2026, 9, 12, 8, 0, tzinfo=timezone.utc)}                # sábado: antes del corte
    store = RawStore(tmp_path, clock=lambda: clock["t"])
    cap = store.put(source_id="twse", dataset="MI/2026-09-11", payload=b"x", url="u", content_type="application/json")
    pkt = {"mode": "historical", "packet_hash": "h1", "admitted": [{"kind": "price_bar_series", "capture_id": cap.capture_id},
                                              {"kind": "capture_manifest", "capture_id": cap.capture_id, "payload": {"session_captures": {"2026-09-11": cap.capture_id}}}]}
    p = store.put(source_id="packet", dataset="lab/2026-W38", payload=json.dumps(pkt).encode(), url="u", content_type="application/json")
    _mark_system(tmp_path); ex._MANIFEST = None; ex._INPUTS_CACHE.clear()          # el fixture simula el reloj real
    assert ex.inputs_before_cutoff(p.capture_id, "2026-09-13T18:00:00+08:00", "h1")["ok"] is True
    clock["t"] = datetime(2026, 9, 13, 12, 0, tzinfo=timezone.utc)                 # domingo 20:00 Taipei: después del corte
    late_cap = store.put(source_id="tpex", dataset="DQ/2026-09-11", payload=b"y", url="u", content_type="application/json")
    pkt2 = {"mode": "historical", "packet_hash": "h2", "admitted": [{"kind": "capture_manifest", "capture_id": late_cap.capture_id, "payload": {"session_captures": {"2026-09-11": late_cap.capture_id}}}]}
    p2 = store.put(source_id="packet", dataset="lab/2026-W39", payload=json.dumps(pkt2).encode(), url="u", content_type="application/json")
    _mark_system(tmp_path); ex._MANIFEST = None; ex._INPUTS_CACHE.clear()
    res = ex.inputs_before_cutoff(p2.capture_id, "2026-09-13T18:00:00+08:00", "h2")
    assert res["ok"] is False and res["reason"] == "late_inputs"
    assert ex.inputs_before_cutoff(None, "2026-09-13T18:00:00+08:00")["ok"] is False


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
    body = json.dumps({"forecast": {"deadline_at": "2026-09-14T08:30:00+08:00"}}).encode("utf-8")
    import hashlib
    sha = hashlib.sha256(body).hexdigest()
    (tmp_path / "f.json").write_bytes(body)
    for at, expected in (("2026-09-14T00:30:00+00:00", True), ("2026-09-14T00:30:01+00:00", False)):
        rec = {"source_id": "forecast", "dataset": "lab/Q0/2026-W38", "ingested_at": at, "path": "f.json", "sha256": sha, "clock_source": "system"}
        (tmp_path / "manifest.jsonl").write_text(json.dumps(rec) + "\n", encoding="utf-8")
        ex._MANIFEST = None
        assert ex.forecast_archive("lab", "2026-W38", {"Q0": sha})["before_deadline"] is expected


def _week_fixture(tmp_path, monkeypatch):
    """Semana sintética íntegra: fuentes antes del corte, paquete, tres predicciones antes del plazo, reloj del sistema."""
    from datetime import datetime, timezone
    from twlab.store import RawStore
    ex = _load(); monkeypatch.setattr(ex, "RAW", tmp_path); ex._MANIFEST = None; ex._INPUTS_CACHE.clear()
    clock = {"t": datetime(2026, 9, 12, 8, 0, tzinfo=timezone.utc)}
    store = RawStore(tmp_path, clock=lambda: clock["t"])
    src = store.put(source_id="twse", dataset="MI/2026-09-11", payload=b"x", url="u", content_type="application/json")
    pkt_body = {"mode": "historical", "packet_hash": "h1", "admitted": [
        {"kind": "price_bar_series", "capture_id": src.capture_id},
        {"kind": "capture_manifest", "capture_id": src.capture_id, "payload": {"session_captures": {"2026-09-11": src.capture_id}}}]}
    pkt = store.put(source_id="packet", dataset="lab/2026-W38", payload=json.dumps(pkt_body).encode(), url="u", content_type="application/json", extra={"packet_hash": "h1"})
    clock["t"] = datetime(2026, 9, 13, 12, 0, tzinfo=timezone.utc)                      # domingo 20:00 Taipei, antes del plazo del lunes
    fc = {}
    for f in ("Q0", "Q1", "A1"):
        body = {"forecast": {"deadline_at": "2026-09-14T08:30:00+08:00", "status": "selected", "ranking": [{"security_id": "TWSE:A@2000-01-01"}]}, "packet_hash": "h1"}
        fc[f] = store.put(source_id="forecast", dataset=f"lab/{f}/2026-W38", payload=json.dumps(body).encode(), url="u", content_type="application/json")
    lines = [json.loads(l) for l in (tmp_path / "manifest.jsonl").read_text(encoding="utf-8").splitlines()]
    for l in lines:
        l["clock_source"] = "system"                                                     # el fixture simula el reloj real
    (tmp_path / "manifest.jsonl").write_text("\n".join(json.dumps(l) for l in lines) + "\n", encoding="utf-8")
    ex._MANIFEST = None; ex._INPUTS_CACHE.clear()
    expected = {f: {"sha": fc[f].sha256, "picks": ["TWSE:A@2000-01-01"], "packet_hash": "h1"} for f in fc}
    return ex, store, pkt, fc, expected


def test_r21_01_every_forecaster_needs_an_identity(tmp_path, monkeypatch):
    ex, store, pkt, fc, expected = _week_fixture(tmp_path, monkeypatch)
    assert ex.forecast_archive("lab", "2026-W38", expected)["before_deadline"] is True
    for bad in (None, ""):
        e2 = dict(expected); e2["Q1"] = {"sha": bad, "picks": ["TWSE:A@2000-01-01"], "packet_hash": "h1"}
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
    assert ex.inputs_before_cutoff(pkt.capture_id, cutoff, "h1")["ok"] is True
    src = store.captures(source_id="twse")[0]
    (store.root / src.path).write_bytes(b"broken")                                     # fuente corrupta
    ex._INPUTS_CACHE.clear()
    r = ex.inputs_before_cutoff(pkt.capture_id, cutoff, "h1"); assert r["ok"] is False and r["reason"] == "unverified_inputs"
    (store.root / src.path).unlink()                                                   # fuente ausente
    ex._INPUTS_CACHE.clear()
    assert ex.inputs_before_cutoff(pkt.capture_id, cutoff, "h1")["reason"] == "unverified_inputs"
    (store.root / src.path).write_bytes(b"x")
    lines = [json.loads(l) for l in (tmp_path / "manifest.jsonl").read_text(encoding="utf-8").splitlines()]
    for l in lines:
        if l["capture_id"] == src.capture_id:
            l["clock_source"] = "injected"                                             # reloj inyectado en la fuente
    (tmp_path / "manifest.jsonl").write_text("\n".join(json.dumps(l) for l in lines) + "\n", encoding="utf-8")
    ex._MANIFEST = None; ex._INPUTS_CACHE.clear()
    assert ex.inputs_before_cutoff(pkt.capture_id, cutoff, "h1")["reason"] == "unverified_inputs"
    # paquete alterado sin actualizar su sha
    ex2, store2, pkt2, fc2, _ = _week_fixture(tmp_path / "b", monkeypatch)
    (store2.root / pkt2.path).write_bytes(b'{"mode":"historical","packet_hash":"h1","admitted":[]}')
    ex2._INPUTS_CACHE.clear()
    assert ex2.inputs_before_cutoff(pkt2.capture_id, cutoff, "h1")["reason"].startswith("packet_")
    # documento admitido sin captura o manifiesto vacío
    ex3, store3, _, _, _ = _week_fixture(tmp_path / "c", monkeypatch)
    src3 = store3.captures(source_id="twse")[0]
    for body in ({"mode": "historical", "packet_hash": "h1", "admitted": [{"kind": "price_bar_series"}]},
                 {"mode": "historical", "packet_hash": "h1", "admitted": [{"kind": "capture_manifest", "capture_id": src3.capture_id, "payload": {"session_captures": {}}}]}):
        p = store3.put(source_id="packet", dataset="lab/2026-W39", payload=json.dumps(body).encode(), url="u", content_type="application/json")
        lines = [json.loads(l) for l in (tmp_path / "c" / "manifest.jsonl").read_text(encoding="utf-8").splitlines()]
        for l in lines: l["clock_source"] = "system"
        (tmp_path / "c" / "manifest.jsonl").write_text("\n".join(json.dumps(l) for l in lines) + "\n", encoding="utf-8")
        ex3._MANIFEST = None; ex3._INPUTS_CACHE.clear()
        assert ex3.inputs_before_cutoff(p.capture_id, cutoff, "h1")["ok"] is False


def test_r21_04_cache_is_keyed_by_cutoff(tmp_path, monkeypatch):
    ex, store, pkt, fc, expected = _week_fixture(tmp_path, monkeypatch)
    assert ex.inputs_before_cutoff(pkt.capture_id, "2026-09-13T18:00:00+08:00", "h1")["ok"] is True
    assert ex.inputs_before_cutoff(pkt.capture_id, "2026-09-11T18:00:00+08:00", "h1")["ok"] is False


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
    r = ex.inputs_before_cutoff(pkt.capture_id, "2026-09-13T18:00:00+08:00", "h1")
    assert r["ok"] is False and r["reason"] == "packet_incomplete_record:path"
