"""Exporta a docs/site/data.json (y lo incrusta en docs/index.html) los datos que muestra el sitio.

Lee únicamente artefactos ya producidos por el laboratorio:
- data/store/backtest_<etiqueta>.json  (escenarios del backtest; cada uno se declara en SCENARIOS)
- review/out/ronda*_*.json             (rondas de revisión de Astra)
- data/raw/manifest.jsonl              (hora real de archivo de las listas semanales)
- docs/informes/*.md, docs/spec/v2/    (índice documental)
- data/raw/twse, data/raw/tpex         (cobertura de sesiones capturadas)

No consulta la red ni recalcula nada: si un escenario no existe todavía, se omite y el sitio lo indica.
El resultado se escribe con `sort_keys` y sin NaN, para que el archivo sea reproducible y diffable.

Uso: python scripts/export_site_data.py [--no-inline]
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STORE = ROOT / "data" / "store"
RAW = ROOT / "data" / "raw"
SITE = ROOT / "docs" / "site"
INDEX = ROOT / "docs" / "index.html"
REPO_URL = "https://github.com/brayannbegu11/stock"

# id, patrón del JSON del backtest (se toma el más reciente), informe asociado
SCENARIOS = [
    ("standard", "backtest_universe_2026-05-04_*.json", "15_backtest_universo_2026.md"),
    ("user", "backtest_user_75kTWD_oddlots_*.json", "15b_backtest_universo_2026_lotes_sueltos.md"),
    ("longhist", "backtest_universe_longhist_2021_*.json", "15c_backtest_universo_2026_historial_2021.md"),
]
FORECASTERS = ("Q0", "Q1", "A1")


def _num(x):
    """Convierte Decimal/str numéricos a float; deja None y cadenas no numéricas tal cual."""
    if x is None:
        return None
    if isinstance(x, (int, float)):
        return x
    try:
        return float(x)
    except (TypeError, ValueError):
        return x


def _pick(p: dict) -> dict:
    sid = p.get("security_id", "")
    market = sid.split(":", 1)[0] if ":" in sid else None
    return {
        "symbol": p.get("symbol"),
        "name": p.get("name"),
        "market": market,
        "security_id": sid,
        "gross_return": _num(p.get("gross_return")),
        "entry_status": p.get("entry_status"),
        "entry_reason": p.get("entry_reason"),
    }


def paired_summary(pe: dict) -> dict:
    """Resumen del exceso emparejado sin perder sus advertencias (R17-07): observaciones fijas y variabilidad limitada."""
    return {
        "mean": _num(pe.get("mean")),
        "ci95": [_num(v) for v in pe["ci95"]] if pe.get("ci95") else None,
        "n_used": pe.get("n_used"),
        "n_excluded": pe.get("n_excluded"),
        "degenerate": pe.get("degenerate"),
        "n_fixed_observations": pe.get("n_fixed_observations"),
        "variability_limited": pe.get("variability_limited"),
        "n_segments": pe.get("n_segments"),
    }


def latest_json(glob: str) -> Path | None:
    files = sorted(STORE.glob(glob), key=lambda p: p.stat().st_mtime)
    return files[-1] if files else None


def export_scenario(sid: str, glob: str, informe: str) -> dict | None:
    path = latest_json(glob) if any(ch in glob for ch in "*?") else STORE / f"backtest_{glob}.json"   # sin comodines: etiqueta
    if path is None or not path.exists():
        return None
    d = json.loads(path.read_text(encoding="utf-8"))
    s = d["summary"]
    a = s.get("assumptions", {})
    label = s.get("label")
    forecasters = {}
    for f in FORECASTERS:
        fs = s.get("forecasters", {}).get(f)
        if not fs:
            continue
        pe = fs.get("paired_excess_vs_baseline") or {}
        forecasters[f] = {
            "model_id": fs.get("model_id"),
            "mean_weekly_net": _num(fs.get("mean_weekly_net_return_open_close")),
            "mean_weekly_gross_picks": _num(fs.get("mean_weekly_gross_pick_return")),
            "mean_costs_over_invested": _num(fs.get("mean_costs_over_invested")),
            "weeks_positive": fs.get("weeks_positive"),
            "weeks_selected": fs.get("weeks_selected"),
            "entry_failures": fs.get("entry_failures"),
            "exit_blocked": fs.get("exit_blocked"),
            "final_equity": _num(fs.get("final_equity")),
            "total_net_return": _num(fs.get("total_net_return")),
            "final_valuation": {k: (fs.get("final_valuation") or {}).get(k) for k in ("equity", "flags", "valued_at", "prices_session", "unresolved")},
            "final_flags": list((fs.get("final_valuation") or {}).get("flags") or []),           # condiciones de la valoración final (R18-08)
            "final_valued_at": (fs.get("final_valuation") or {}).get("valued_at"),
            "final_prices_session": (fs.get("final_valuation") or {}).get("prices_session"),
            "weeks_measured": fs.get("weeks_measured"),
            "paired": paired_summary(pe) if pe else None,
            "unpaired_reasons": fs.get("unpaired_reasons") or {},
        }
    weeks = []
    for w in d["weeks"]:
        fw = {}
        for f in FORECASTERS:
            x = w["forecasters"].get(f)
            if not x:
                continue
            paired = (w.get("paired") or {}).get(f) or {}
            fw[f] = {
                "status": x.get("forecast_status"),
                "status_reason": x.get("status_reason"),
                "net": _num(x.get("portfolio_net_return_open_close")),
                "gross_picks": _num(x.get("mean_gross_pick_return")),
                "filled": x.get("filled"),
                "failed": x.get("failed"),
                "exit_blocked": x.get("exit_blocked"),
                "fail_reasons": x.get("fail_reasons") or [],
                "exposure": _num(x.get("exposure_at_open")),
                "costs_twd": _num(x.get("costs_twd")),
                "notional_per_slot": _num(x.get("notional_per_slot")),
                "equity_open": _num(x.get("equity_open")),
                "equity_end": _num(x.get("equity_end")),
                "flags": x.get("flags") or [],
                "paired": paired.get("paired"),
                "excess_net": _num(paired.get("excess_net_vs_baseline")),
                "unpaired_reason": (paired.get("unpaired_reason") or "").split(":", 1)[0] or None,
                "picks": [_pick(p) for p in x.get("picks") or []],
            }
        weeks.append({
            "week_id": w["week_id"],
            "cutoff_at": w["cutoff_at"],
            "status": w["status"],
            "pending_outcome": bool(w.get("pending_outcome")),
            "eligible": w.get("eligible"),
            "scored": w.get("scored"),
            "coverage_reasons": w.get("coverage_reasons") or {},
            "ew_gross": _num(w.get("universe_ew_gross_open_close")),
            "forecasters": fw,
        })
    initial = (a.get("notional") or 0) * (a.get("slots") or 0)
    return {
        "id": sid,
        "label": label,
        "archive_label": a.get("archive_label") or label,
        "source_file": path.name,
        "informe": informe,
        "period": s.get("period"),
        "manifest": s.get("manifest"),
        "universe_size": s.get("universe_size"),
        "weeks_total": s.get("weeks_total"),
        "weeks_operated": s.get("weeks_operated"),
        "weeks_pending_outcome": s.get("weeks_pending_outcome") or [],
        "weeks_extraordinary_closure_unhandled": s.get("weeks_extraordinary_closure_unhandled") or [],
        "bars_without_regular_price_dropped": s.get("bars_without_regular_price_dropped"),
        "market_warnings": s.get("market_warnings") or [],
        "simulation_bound": s.get("simulation_bound"),
        "universe_ew_mean_weekly_gross": _num((s.get("universe_ew") or {}).get("mean_weekly_gross_open_close")),
        "assumptions": {
            "initial_cash_twd": initial,
            "slots": a.get("slots"),
            "notional_per_slot_twd": a.get("notional"),
            "sizing": a.get("sizing"),
            "lot_size": a.get("lot_size", 1000),
            "min_commission_twd": _num(a.get("min_commission_twd", 0)),
            "commission_per_side": _num(a.get("commission_per_side")),
            "sell_tax": _num(a.get("sell_tax")),
            "slippage_bps": a.get("slippage_bps"),
            "exposure_tolerance": _num(a.get("exposure_tolerance")),
            "block_length": a.get("block_length"),
            "n_boot": a.get("n_boot"),
            "seed": a.get("seed"),
            "min_history_sessions": a.get("min_history_sessions"),
            "liquidity_multiple": a.get("liquidity_multiple"),
            "baseline": a.get("baseline"),
            "costs_label": (a.get("costs") or {}).get("label"),
        },
        "forecasters": forecasters,
        "weeks": weeks,
    }


def forecast_archive(archive_label: str, week_id: str) -> dict:
    """Primera hora real de archivo (ingested_at) de la lista de cada pronosticador para esa semana, el plazo del
    protocolo que declara la predicción archivada y si la primera ingestión fue anterior a ese plazo.

    La primera ingestión es la única que vale como fecha de emisión; una corrida posterior que vuelva a archivar los
    mismos bytes no la adelanta ni la retrasa (RawStore.find). «Anterior al plazo» se decide con el reloj del sistema
    de la máquina que archivó: no hay sello externo, y así se declara en el sitio."""
    out: dict = {"archived_at": {}, "archived_at_latest": {}, "deadline_at": None, "before_deadline": None}
    mf = RAW / "manifest.jsonl"
    if not mf.exists():
        return out
    prefix = f"{archive_label}/"
    first_rec: dict[str, dict] = {}
    with mf.open(encoding="utf-8") as fh:
        for line in fh:
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if rec.get("source_id") != "forecast":
                continue
            ds = rec.get("dataset", "")
            if not ds.startswith(prefix) or not ds.endswith("/" + week_id):
                continue
            f = ds[len(prefix):].split("/", 1)[0]
            t = rec.get("ingested_at", "")
            if f not in out["archived_at"] or t < out["archived_at"][f]:
                out["archived_at"][f] = t
                first_rec[f] = rec
            out["archived_at_latest"][f] = max(out["archived_at_latest"].get(f, ""), t)
    for f, rec in first_rec.items():
        try:
            body = json.loads((RAW / rec["path"]).read_text(encoding="utf-8"))
            dl = (body.get("forecast") or {}).get("deadline_at")
        except (OSError, json.JSONDecodeError):
            dl = None
        if dl:
            out["deadline_at"] = out["deadline_at"] or dl
    if out["deadline_at"] and out["archived_at"]:
        dl = datetime.fromisoformat(out["deadline_at"])
        out["before_deadline"] = all(datetime.fromisoformat(t) <= dl for t in out["archived_at"].values())
    return out


def export_rounds() -> list[dict]:
    rounds = []
    informes = {p.name: p for p in (ROOT / "docs" / "informes").glob("*.md")}
    for p in sorted((ROOT / "review" / "out").glob("ronda*_*.json")):
        m = re.match(r"ronda(\d+)_", p.name)
        if not m:
            continue
        n = int(m.group(1))
        d = json.loads(p.read_text(encoding="utf-8"))
        new = [h for h in d.get("hallazgos", []) if re.fullmatch(rf"R0*{n}-\d+", str(h.get("id", "")))]
        verifications = []
        for h in d.get("hallazgos", []):
            mv = re.fullmatch(r"(R\d+-\d+)/verificacion", str(h.get("id", "")))      # identificador completo (R18-03)
            if mv:
                verifications.append({"id": mv.group(1), "state": h.get("estado_verificacion"), "severity": h.get("severidad"),
                                      "claim": h.get("afirmacion")})
        sev: dict[str, int] = {}
        for h in new:
            k = str(h.get("severidad") or "sin_severidad")
            sev[k] = sev.get(k, 0) + 1
        response = None
        for name in sorted(informes):
            title = _first_heading(informes[name])
            if re.search(rf"\bronda {n}\b", title):
                response = name
        tests = None
        mt = re.search(r"(\d+) pruebas", str(d.get("resumen", "")))
        if mt:
            tests = int(mt.group(1))
        rounds.append({
            "round": n,
            "file": f"review/out/{p.name}",
            "timestamp": re.search(r"_(\d{8}T\d{6}Z)", p.name).group(1),
            "verdict": d.get("veredicto"),
            "summary": d.get("resumen"),
            "findings_total": len(d.get("hallazgos", [])),
            "findings_new": len(new),
            "verifications": verifications,
            "severity": sev,
            "tests_passing": tests,
            "response": f"docs/informes/{response}" if response else None,
            "new_findings": [
                {"id": h.get("id"), "severity": h.get("severidad"), "category": h.get("categoria"),
                 "file": h.get("archivo"), "claim": h.get("afirmacion")}
                for h in new
            ],
        })
    rounds.sort(key=lambda r: r["round"])
    return rounds


def review_stats(rounds: list[dict]) -> dict:
    """Recuentos derivados sólo de entradas identificables (R17-05): hallazgos nuevos emitidos y verificaciones de Astra.

    Una verificación cuenta como tal si Astra la registró con estado ``reproducido`` en una ronda posterior; el texto de la
    verificación puede declararla parcial, y eso no se interpreta aquí: se publica el recuento y el enlace al JSON."""
    new_by_id: dict[str, str] = {}
    emitted_round: dict[str, int] = {}
    for r in rounds:
        for h in r["new_findings"]:
            new_by_id[h["id"]] = h.get("severity") or ""
            emitted_round[h["id"]] = r["round"]
    verified: set[str] = set()
    for r in rounds:
        for v in r["verifications"]:
            # sólo cuenta una verificación de un hallazgo existente, en una ronda posterior a su emisión (R18-03)
            if v["id"] in new_by_id and v["state"] == "reproducido" and r["round"] > emitted_round[v["id"]]:
                verified.add(v["id"])
    blocking = {i for i, s in new_by_id.items() if s == "bloqueante"}
    return {"new_total": len(new_by_id), "verified_total": len(verified), "blocking_new": len(blocking),
            "blocking_verified": len(blocking & verified), "unverified_ids": sorted(set(new_by_id) - verified)}


def _first_heading(p: Path) -> str:
    with p.open(encoding="utf-8") as fh:
        for line in fh:
            if line.startswith("# "):
                return line[2:].strip()
    return p.stem


def export_docs() -> dict:
    informes = [{"file": f"docs/informes/{p.name}", "title": _first_heading(p)}
                for p in sorted((ROOT / "docs" / "informes").glob("*.md"))]
    spec = [{"file": f"docs/spec/v2/{p.name}"} for p in sorted((ROOT / "docs" / "spec" / "v2").iterdir()) if p.is_file()]
    return {"informes": informes, "spec": spec}


def count_tests() -> int | None:
    try:
        r = subprocess.run([sys.executable, "-m", "pytest", "--co", "-q", "-p", "no:cacheprovider"],
                           cwd=ROOT, capture_output=True, text=True, timeout=300)
    except (OSError, subprocess.TimeoutExpired):
        return None
    total = 0
    for line in r.stdout.splitlines():
        m = re.fullmatch(r"(\S+\.py): (\d+)", line.strip())
        if m:
            total += int(m.group(2))
    return total or None


def raw_coverage() -> dict:
    out = {}
    for src, ds in (("twse", "MI_INDEX_ALLBUT0999"), ("tpex", "dailyQuotes")):
        d = RAW / src / ds
        days = sorted(p.name for p in d.iterdir() if p.is_dir()) if d.exists() else []
        out[src] = {"sessions": len(days), "first": days[0] if days else None, "last": days[-1] if days else None}
    return out


def master_stats(store: Path = STORE) -> dict:
    """Segmentos del maestro: sólo las filas ``kind == "segment"`` (R17-13); los eventos terminales se cuentan aparte."""
    latest = sorted(store.glob("master_*.jsonl"))
    if not latest:
        return {}
    p = latest[-1]
    kinds: dict[str, int] = {}
    with p.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            k = str(json.loads(line).get("kind", "segment"))
            kinds[k] = kinds.get(k, 0) + 1
    return {"file": p.name, "segments": kinds.get("segment", 0), "other_rows": {k: v for k, v in kinds.items() if k != "segment"},
            "as_of": p.stem.split("_", 1)[1]}


def build() -> dict:
    rounds = export_rounds()
    scenarios = []
    for sid, label, informe in SCENARIOS:
        sc = export_scenario(sid, label, informe)
        if sc:
            alabel = sc["archive_label"]
            prospective_weeks = []
            for w in sc["weeks"]:
                fa = forecast_archive(alabel, w["week_id"])
                w["forecast_archived_at"] = fa["archived_at"]
                w["forecast_deadline_at"] = fa["deadline_at"]
                w["forecast_before_deadline"] = fa["before_deadline"]
                if fa["before_deadline"]:
                    prospective_weeks.append(w["week_id"])
            sc["prospective_weeks"] = prospective_weeks
            pending = [w for w in sc["weeks"] if w["pending_outcome"]]
            if pending:
                wk = pending[-1]["week_id"]
                fa = forecast_archive(alabel, wk)
                sc["current_week"] = {"week_id": wk, "archived_at": fa["archived_at"], "archived_at_latest": fa["archived_at_latest"],
                                      "deadline_at": fa["deadline_at"], "before_deadline": fa["before_deadline"]}
            scenarios.append(sc)
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "repo": REPO_URL,
        "status": project_status(scenarios),
        "tests": count_tests(),
        "raw_coverage": raw_coverage(),
        "master": master_stats(),
        "scenarios": scenarios,
        "rounds": rounds,
        "review_stats": review_stats(rounds),
        "docs": export_docs(),
    }


def project_status(scenarios: list[dict]) -> dict:
    """Fase del proyecto derivada de los artefactos: 1 construir, 2 probar con el pasado, 3 predecir cada semana, 4 decidir.

    La fase 3 empieza cuando existe al menos una semana cuya lista se archivó antes del plazo (reloj del sistema);
    hasta entonces la primera lista prospectiva posible es la del siguiente corte dominical posterior a la última
    semana pendiente."""
    prospective = sorted({w for sc in scenarios for w in sc.get("prospective_weeks", [])})
    pending = sorted({w["week_id"] for sc in scenarios for w in sc["weeks"] if w["pending_outcome"]})
    backtested = max((sc["weeks_operated"] for sc in scenarios), default=0)
    next_cutoff = None
    if scenarios:
        last = max(datetime.fromisoformat(w["cutoff_at"]) for sc in scenarios for w in sc["weeks"])
        nxt = last + timedelta(days=7)
        while nxt.date() <= datetime.now(timezone.utc).date():
            nxt += timedelta(days=7)
        next_cutoff = nxt.date().isoformat()
    phase = 3 if prospective else (2 if backtested else 1)
    return {"phase": phase, "phases_total": 4, "prospective_weeks": prospective, "prospective_count": len(prospective),
            "pending_weeks": pending, "backtested_weeks": backtested, "next_cutoff": next_cutoff,
            "weekly_pipeline": "scripts/weekly_prospective.ps1", "external_timestamp": False}


def inline_into_index(payload: str) -> bool:
    if not INDEX.exists():
        return False
    html = INDEX.read_text(encoding="utf-8")
    pat = re.compile(r'(<script type="application/json" id="site-data">)(.*?)(</script>)', re.S)
    if not pat.search(html):
        return False
    safe = payload.replace("</", "<\\/")
    html = pat.sub(lambda m: m.group(1) + "\n" + safe + "\n" + m.group(3), html, count=1)
    INDEX.write_text(html, encoding="utf-8", newline="\n")
    return True


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-inline", action="store_true", help="no incrustar el JSON en docs/index.html")
    args = ap.parse_args()
    data = build()
    SITE.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(data, ensure_ascii=False, sort_keys=True, allow_nan=False, indent=None, separators=(",", ":"))
    (SITE / "data.json").write_text(payload, encoding="utf-8", newline="\n")
    inlined = False if args.no_inline else inline_into_index(payload)
    print(f"docs/site/data.json: {len(payload):,} bytes · escenarios={[s['id'] for s in data['scenarios']]} · "
          f"rondas={len(data['rounds'])} · pruebas={data['tests']} · incrustado_en_index={inlined}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
