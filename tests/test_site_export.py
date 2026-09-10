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
