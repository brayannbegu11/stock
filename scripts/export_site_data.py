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
from collections.abc import Mapping
import hashlib
import json
import re
import subprocess
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))          # twlab.packet se necesita para recalcular el hash lógico (R22-02), también fuera de pytest
STORE = ROOT / "data" / "store"
RAW = ROOT / "data" / "raw"
_TAIPEI = ZoneInfo("Asia/Taipei")
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
                "forecast_sha256": x.get("forecast_sha256"),
                "forecast_capture_id": x.get("forecast_capture_id"),
                "deadline_at": x.get("deadline_at"),
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
            "packet_capture": w.get("packet_capture"),
            "master_capture": w.get("master_capture"),
            "master_sha256": w.get("master_sha256"),
            "packet_hash": w.get("packet_hash"),
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


_MANIFEST: list[dict] | None = None
_BY_ID: dict[str, dict] = {}


def manifest() -> list[dict]:
    """Registros del archivo (una lectura por ejecución)."""
    global _MANIFEST, _BY_ID
    if _MANIFEST is None:
        _MANIFEST = []
        mf = RAW / "manifest.jsonl"
        if mf.exists():
            with mf.open(encoding="utf-8") as fh:
                for line in fh:
                    try:
                        rec = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if not isinstance(rec, dict):
                        continue                                        # una línea que no es un registro no es evidencia (R23-02)
                    _MANIFEST.append(rec)
        _BY_ID = {r.get("capture_id"): r for r in _MANIFEST}
    return _MANIFEST


def _aware(s: str | None) -> datetime | None:
    """ISO-8601 con zona; una marca sin zona no sirve como evidencia temporal (R20-02)."""
    if not s or not isinstance(s, str):
        return None
    try:
        d = datetime.fromisoformat(s)
    except (ValueError, TypeError):
        return None
    return d if d.tzinfo is not None else None


def _intact(rec: dict) -> bool:
    try:
        p = RAW / str(rec.get("path", ""))
        return hashlib.sha256(p.read_bytes()).hexdigest() == rec.get("sha256")
    except (OSError, TypeError, ValueError):
        return False


def _instant(s: str | None) -> datetime | None:
    d = _aware(s)
    return d.astimezone(timezone.utc) if d else None


def _record_ok(rec: dict | None) -> str | None:
    """Motivo por el que un registro del manifiesto no sirve como evidencia; None si sirve."""
    if not isinstance(rec, dict):
        return "missing_record"
    for k in ("path", "sha256", "ingested_at", "clock_source"):
        if not rec.get(k) or not isinstance(rec.get(k), str):
            return f"incomplete_record:{k}"
    if rec.get("clock_source") != "system":
        return f"clock:{rec.get('clock_source')}"
    try:
        if _instant(rec.get("ingested_at")) is None:
            return "time_unusable"
    except (TypeError, ValueError):
        return "time_unusable"
    if not _intact(rec):
        return "corrupt"
    return None


def forecast_archive(archive_label: str, week_id: str, expected: dict | None = None) -> dict:
    """Clasificación temporal de la lista de una semana, pronosticador a pronosticador.

    ``expected`` describe cada pronosticador de la semana: ``{"sha": <sha256 de la predicción evaluada>,
    "picks": [security_id…], "packet_hash": <hash del paquete de la semana>}`` (una cadena vale como sha sin más
    comprobaciones). Para cada pronosticador se localiza la **primera** ingestión por instante de un registro
    íntegro con exactamente esos bytes, escrito por el reloj del sistema (R20-01/03, R21-05); se exige que la lista
    mostrada coincida con el ``ranking`` archivado y que la predicción declare el mismo ``packet_hash`` que la
    semana (R21-02); y que esa primera ingestión sea anterior o igual al ``deadline_at`` que la propia predicción
    declara (R20-02). ``before_deadline`` sólo es True si **todos** los pronosticadores esperados tienen identidad y
    cumplen (R21-01). Sin identidad no hay predicción, pero se informa de la primera ingestión íntegra por dataset."""
    out: dict = {"archived_at": {}, "archived_at_latest": {}, "deadline_at": {}, "clock_source": {}, "before_deadline": None,
                 "reasons": [], "ranking": {}, "master_sha256": {}}
    prefix = f"{archive_label}/"
    recs_week = [r for r in manifest() if r.get("source_id") == "forecast" and isinstance(r.get("dataset"), str)
                 and r["dataset"].startswith(prefix) and r["dataset"].endswith("/" + week_id)]
    for r in recs_week:
        f = r["dataset"][len(prefix):].split("/", 1)[0]
        t = r.get("ingested_at")
        if isinstance(t, str):                                          # un registro con hora no textual no data nada (R23-02)
            out["archived_at_latest"][f] = max(out["archived_at_latest"].get(f, ""), t)
    norm: dict[str, dict] = {}
    for f, v in (expected or {}).items():
        norm[f] = {"sha": v} if isinstance(v, str) else dict(v or {})
    if not norm or any(not (v.get("sha") or "") for v in norm.values()):
        out["before_deadline"] = False
        out["reasons"].append("no_forecast_identity" if not norm else "no_forecast_identity:" + ",".join(f for f, v in norm.items() if not v.get("sha")))
        for r in sorted(recs_week, key=lambda r: (_instant(r.get("ingested_at")) or datetime.max.replace(tzinfo=timezone.utc))):
            f = r["dataset"][len(prefix):].split("/", 1)[0]
            if f in out["archived_at"] or _record_ok(r):
                continue
            out["archived_at"][f] = r["ingested_at"]
            out["clock_source"][f] = r.get("clock_source")
            try:
                body = json.loads((RAW / r["path"]).read_text(encoding="utf-8"))
                out["deadline_at"][f] = (body.get("forecast") or {}).get("deadline_at")
            except (OSError, json.JSONDecodeError):
                out["deadline_at"][f] = None
        return out
    ok = True
    for f, spec in norm.items():
        sha = spec["sha"]
        same = [r for r in recs_week if r["dataset"][len(prefix):].split("/", 1)[0] == f and r.get("sha256") == sha]
        same.sort(key=lambda r: (_instant(r.get("ingested_at")) or datetime.max.replace(tzinfo=timezone.utc)))
        # la primera ingestión ÍNTEGRA por instante (un archivo corrupto no prueba nada; saltarlo sólo puede retrasar la
        # fecha, nunca adelantarla); es esa primera la que debe llevar reloj del sistema (R21-05)
        first = next((r for r in same if _record_ok(r) in (None, "clock:injected") or (_record_ok(r) or "").startswith("clock:")), None)
        why = _record_ok(first)
        if why:
            ok = False; out["reasons"].append(f"{'missing_or_corrupt' if why in ('missing_record', 'corrupt') else why}:{f}")
            continue
        out["archived_at"][f] = first["ingested_at"]
        out["clock_source"][f] = first.get("clock_source")
        try:
            body = json.loads((RAW / first["path"]).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            body = None
        fc = (body or {}).get("forecast") if isinstance(body, dict) else None
        fc = fc if isinstance(fc, dict) else {}
        dl = fc.get("deadline_at")
        out["deadline_at"][f] = dl if isinstance(dl, str) else None
        t, d = _instant(first["ingested_at"]), _instant(dl)
        if body is None or d is None:
            ok = False; out["reasons"].append(f"deadline_or_time_unusable:{f}")
            continue
        if t > d:
            ok = False; out["reasons"].append(f"late:{f}")
        # contrato de la predicción archivada (R22-01): sólo «selected» con ranking no vacío y sin repetidos, o «abstained»
        # con ranking vacío, son decisiones válidas; «invalid» o incoherencias no pueden ser predicción
        status = fc.get("status")
        ranking = fc.get("ranking") if isinstance(fc.get("ranking"), list) else None
        well_formed = bool(ranking) and all(isinstance(x, dict) and isinstance(x.get("security_id"), str) and x["security_id"]
                                            for x in ranking)
        ranked = [x["security_id"] for x in ranking] if well_formed else []
        contract_ok = (status == "selected" and well_formed and len(set(ranked)) == len(ranked)) or (status == "abstained" and ranking == [])
        if not contract_ok:
            ok = False; out["reasons"].append(f"forecast_contract:{f}:{status}")
        elif status == "selected" and not (all(type(x.get("rank")) is int for x in ranking)          # ni bool ni float (R23-03)
                                           and [x["rank"] for x in ranking] == list(range(1, len(ranking) + 1))):
            # el orden mostrado es el del array archivado; los campos ``rank`` deben ser enteros y declarar exactamente ese
            # orden (1..n), de lo contrario la predicción es ambigua y no puede contarse (falla cerrado)
            ok = False; out["reasons"].append(f"forecast_contract:{f}:rank_order")
        if contract_ok:
            out["ranking"][f] = [{"security_id": x["security_id"], "ticker_as_of": x.get("ticker_as_of")} for x in ranking]
        out["master_sha256"][f] = (body or {}).get("master_sha256")       # vínculo con el maestro evaluado (R24-02)
        if "status" in spec and spec.get("status") != status:
            ok = False; out["reasons"].append(f"status_mismatch:{f}")
        if "picks" in spec:
            if list(spec.get("picks") or []) != ranked:
                ok = False; out["reasons"].append(f"picks_mismatch:{f}")
        if "symbols" in spec and status == "selected":
            # el símbolo que ve el usuario debe ser el ticker archivado en la predicción (R22-05)
            tickers = [x.get("ticker_as_of") if isinstance(x, dict) else None for x in (ranking or [])]
            if list(spec.get("symbols") or []) != tickers:
                ok = False; out["reasons"].append(f"symbol_mismatch:{f}")
        if "packet_hash" in spec and (body or {}).get("packet_hash") != spec.get("packet_hash"):
            ok = False; out["reasons"].append(f"packet_link_mismatch:{f}")
        if "cutoff_at" in spec and (_instant(fc.get("cutoff_at")) is None or _instant(fc.get("cutoff_at")) != _instant(spec.get("cutoff_at"))):
            ok = False; out["reasons"].append(f"cutoff_mismatch:{f}")                 # corte de la predicción archivada (R22-03)
    out["before_deadline"] = ok
    return out


_INPUTS_CACHE: dict[tuple, dict] = {}


def inputs_before_cutoff(packet_capture_id: str | None, cutoff_at: str, packet_hash: str | None = None) -> dict:
    """Procedencia completa de las entradas del paquete archivado (R20-06, R21-03).

    Se exige: registro del paquete completo e íntegro (sha256 de los bytes), paquete deserializable cuyo
    ``packet_hash`` coincide con el de la semana, todo documento admitido con ``capture_id``, todo manifiesto con
    ``session_captures`` no vacío, y cada captura referenciada con registro completo, íntegra, escrita por el reloj
    del sistema e ingerida antes o en el corte. Cualquier fallo devuelve ``ok=False`` con su motivo; sólo
    ``late_inputs`` significa «recibido después del corte»: lo demás es procedencia no acreditada."""
    key = (packet_capture_id, cutoff_at, packet_hash)
    if key in _INPUTS_CACHE:
        return _INPUTS_CACHE[key]
    res = _inputs_before_cutoff(packet_capture_id, cutoff_at, packet_hash)
    _INPUTS_CACHE[key] = res
    return res


def _inputs_before_cutoff(packet_capture_id, cutoff_at, packet_hash) -> dict:
    if not packet_capture_id:
        return {"ok": False, "reason": "no_packet_capture"}
    manifest()
    rec = _BY_ID.get(packet_capture_id)
    why = _record_ok(rec)
    if why:
        return {"ok": False, "reason": f"packet_{why}"}
    try:
        raw = (RAW / rec["path"]).read_bytes()
    except (OSError, TypeError):
        return {"ok": False, "reason": "packet_unreadable_or_empty"}
    # el paquete se deserializa con el contrato del laboratorio y su hash lógico se recalcula (R22-02): el campo
    # packet_hash del archivo no se toma como cierto; cualquier fallo de contrato o tipo cierra la clasificación (R22-04)
    try:
        from twlab.packet import packet_from_json
        pk = packet_from_json(raw)
        logical = pk.packet_hash()
    except Exception as exc:  # noqa: BLE001 - un paquete que no cumple el contrato no acredita nada
        return {"ok": False, "reason": f"packet_contract:{type(exc).__name__}"}
    try:
        declared = json.loads(raw).get("packet_hash")
    except Exception:  # noqa: BLE001
        declared = None
    if packet_hash is not None and logical != packet_hash:
        return {"ok": False, "reason": "packet_hash_mismatch", "mode": pk.mode}
    if declared != logical:
        return {"ok": False, "reason": "packet_hash_mismatch", "mode": pk.mode}
    extra = rec.get("extra")
    if not isinstance(extra, Mapping) or not isinstance(extra.get("packet_hash"), str):
        return {"ok": False, "reason": "packet_record_hash_missing", "mode": pk.mode}   # el registro debe declararlo (R23-04)
    if extra["packet_hash"] != logical:
        return {"ok": False, "reason": "packet_hash_mismatch", "mode": pk.mode}
    if not pk.admitted:
        return {"ok": False, "reason": "packet_unreadable_or_empty", "mode": pk.mode}
    cutoff = _instant(cutoff_at)
    pk_cutoff = pk.cutoff_at.astimezone(timezone.utc) if pk.cutoff_at is not None and pk.cutoff_at.tzinfo else None
    if cutoff is None or pk_cutoff is None:
        return {"ok": False, "reason": "cutoff_unusable", "mode": pk.mode}
    if pk_cutoff != cutoff:
        return {"ok": False, "reason": "cutoff_mismatch", "mode": pk.mode}   # el corte del paquete archivado manda (R22-03)
    ids: set[str] = set()
    for d in pk.admitted:
        if not d.capture_id:
            return {"ok": False, "reason": "admitted_without_capture", "mode": pk.mode}
        ids.add(d.capture_id)
        if d.kind == "capture_manifest":
            sc = d.payload.get("session_captures") if isinstance(d.payload, Mapping) else None
            if not isinstance(sc, Mapping) or not sc or not all(isinstance(v, str) and v for v in sc.values()):
                return {"ok": False, "reason": "empty_capture_manifest", "mode": pk.mode}
            ids.update(sc.values())
    # nombres archivados por valor (R22-05): el nombre que ve el usuario debe ser el del paquete, no el del JSON de resultados
    names: dict[str, str] = {}
    series: list[dict] = []
    for d in pk.admitted:
        if d.kind == "price_bar_series":
            series.append({"security_id": d.security_ids[0] if d.security_ids else None, "doc_id": d.doc_id})
            if d.security_ids and isinstance(d.payload, Mapping) and isinstance(d.payload.get("name"), str):
                names[d.security_ids[0]] = d.payload["name"]
    late, bad, latest = [], [], None
    for cid in sorted(ids):
        r = _BY_ID.get(cid)
        w = _record_ok(r)
        if w:
            bad.append(f"{cid}:{w}"); continue
        t = _instant(r["ingested_at"])
        if t > pk_cutoff:
            late.append(cid)
        if latest is None or t > latest:
            latest = t
    reason = None if not late and not bad else ("late_inputs" if late and not bad else "unverified_inputs")
    return {"ok": reason is None, "captures": len(ids), "late": len(late), "unverified": len(bad),
            "latest_ingested_at": latest.isoformat() if latest else None, "mode": pk.mode, "packet_cutoff_at": pk.cutoff_at.isoformat(),
            "names": names, "series": series, "reason": reason}


_MASTER_CACHE: dict[str, dict] = {}


_MASTER_FIELDS = {"security_id", "issuer_id", "symbol", "name_zh", "market", "board", "instrument_type", "source_id", "currency"}


def _master_row(row):
    """Fila de la instantánea del maestro con tipos estrictos (R24-03); ``None`` si no es un segmento."""
    from twlab.master import SecurityVersion
    if not isinstance(row, dict):
        raise ValueError("row_not_object")
    row = dict(row)
    if row.pop("kind", "segment") != "segment":
        return None
    unknown = set(row) - _MASTER_FIELDS - {"name_en", "valid_from", "valid_to", "recorded_at"}
    if unknown:
        raise ValueError("unknown_field:" + ",".join(sorted(unknown)))
    for k in _MASTER_FIELDS:
        if not isinstance(row.get(k), str) or not row[k]:
            raise ValueError(f"field_not_text:{k}")
    if row.get("name_en") is not None and not isinstance(row.get("name_en"), str):
        raise ValueError("field_not_text:name_en")
    if not isinstance(row.get("valid_from"), str):
        raise ValueError("field_not_text:valid_from")
    row["valid_from"] = date.fromisoformat(row["valid_from"])
    if row.get("valid_to") is None:
        row["valid_to"] = None
    elif isinstance(row["valid_to"], str) and row["valid_to"]:
        row["valid_to"] = date.fromisoformat(row["valid_to"])
    else:
        raise ValueError("field_not_date:valid_to")
    if not isinstance(row.get("recorded_at"), str):
        raise ValueError("field_not_text:recorded_at")
    row["recorded_at"] = datetime.fromisoformat(row["recorded_at"])
    if row["recorded_at"].tzinfo is None:
        raise ValueError("recorded_at_naive")
    return SecurityVersion(**row)


def _load_master(rec: dict):
    """Maestro archivado reconstruido fila a fila con ``SecurityMaster.add`` (mismas validaciones que el laboratorio)."""
    from twlab.master import SecurityMaster
    key = f"{rec.get('capture_id')}|{rec.get('sha256')}"
    m = _MASTER_CACHE.get(key)
    if m is None:
        m = SecurityMaster()
        for line in (RAW / rec["path"]).read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            v = _master_row(json.loads(line))
            if v is not None:
                m.add(v)
        _MASTER_CACHE[key] = m
    return m


def master_identity(master_capture_id, cutoff_at, ranking: Mapping[str, list], *, archive_label: str | None = None,
                    deadlines: Mapping[str, str | None] | None = None, links: Mapping[str, str | None] | None = None) -> dict:
    """Identidad económica de cada valor seleccionado según el maestro **archivado** por la corrida (R23-01, R24-01..05).

    Se exige: registro completo, íntegro y con reloj del sistema, de la fuente ``master`` y del dataset del maestro de
    la corrida (R24-05); que cada predicción archivada declare exactamente el sha256 de esos bytes (R24-02) y que su
    primera ingestión íntegra sea anterior o igual al plazo de cada predicción (R24-02); filas con tipos estrictos y
    validadas por el propio ``SecurityMaster`` (R24-03); y, con la vista del maestro **conocida al corte** (R24-01),
    que cada ``security_id`` del ranking tenga un segmento vigente en la fecha del corte cuyo símbolo sea exactamente
    el ``ticker_as_of`` archivado."""
    if not isinstance(master_capture_id, str) or not master_capture_id:
        return {"ok": False, "reasons": ["no_master_identity"]}
    manifest()
    rec = _BY_ID.get(master_capture_id)
    why = _record_ok(rec)
    if why:
        return {"ok": False, "reasons": [f"master_{why}"]}
    dataset = f"{archive_label}/master" if archive_label else None
    if rec.get("source_id") != "master" or (dataset is not None and rec.get("dataset") != dataset):
        return {"ok": False, "reasons": ["master_record_mismatch"]}
    sha = rec["sha256"]
    reasons: list[str] = []
    for f, declared in (links or {}).items():
        if declared != sha:
            reasons.append(f"master_link_mismatch:{f}")
    # oportunidad temporal: la primera ingestión íntegra (por instante) de esos bytes en el dataset del maestro, con reloj
    # del sistema, no puede ser posterior al plazo de ninguna predicción (un maestro repuesto después no acredita nada)
    same = [r for r in manifest() if r.get("source_id") == "master" and r.get("dataset") == rec.get("dataset") and r.get("sha256") == sha]
    same.sort(key=lambda r: (_instant(r.get("ingested_at")) or datetime.max.replace(tzinfo=timezone.utc)))
    first = next((r for r in same if _record_ok(r) is None or (_record_ok(r) or "").startswith("clock:")), None)
    why = _record_ok(first)
    if why:
        return {"ok": False, "reasons": reasons + [f"master_{why}"]}
    t_first = _instant(first["ingested_at"])
    for f, dl in (deadlines or {}).items():
        d = _instant(dl)
        if d is None or t_first > d:
            reasons.append(f"master_late:{f}")
    try:
        m = _load_master(rec)
    except Exception as exc:  # noqa: BLE001 - un maestro que no cumple el contrato no acredita nada
        return {"ok": False, "reasons": reasons + [f"master_contract:{type(exc).__name__}"]}
    cutoff = _aware(cutoff_at)
    if cutoff is None:
        return {"ok": False, "reasons": reasons + ["cutoff_unusable"]}
    known_at = cutoff.astimezone(timezone.utc)
    seg_index: dict[str, list] = {}
    for v in m._effective(known_at):  # noqa: SLF001 - vista del maestro conocida al corte (R24-01)
        seg_index.setdefault(v.security_id, []).append(v)
    as_of = cutoff.astimezone(_TAIPEI).date()
    for f, entries in (ranking or {}).items():
        for e in entries or []:
            sid = e.get("security_id")
            covering = [v for v in seg_index.get(sid, []) if v.covers(as_of)]
            if not covering:
                reasons.append(f"identity_unknown_security:{f}:{sid}"); continue
            seg = max(covering, key=lambda v: v.valid_from)
            if seg.symbol != e.get("ticker_as_of"):
                reasons.append(f"identity_symbol_mismatch:{f}:{sid}")
    return {"ok": not reasons, "reasons": reasons, "securities": len(seg_index), "archived_at": first["ingested_at"],
            "as_of": as_of.isoformat(), "segments": seg_index}


def classify_week(archive_label: str, w: dict) -> dict:
    """Clasificación temporal completa de una semana del JSON de resultados (exportador y ensamblador comparten esta función).

    predicción ⇔ identidad, contrato, plazo, reloj y vínculo de cada predicción (`forecast_archive`) **y** procedencia
    íntegra del paquete con entradas antes del corte (`inputs_before_cutoff`) **y** nombres mostrados iguales a los del
    paquete archivado (R22-05) **y** código y símbolo de cada valor vigentes en el maestro archivado (`master_identity`,
    R23-01). Cualquier excepción durante la clasificación cierra la semana como no acreditada (R23-02).
    Devuelve `fa`, `inp`, `master`, `prospective` y `reasons`."""
    return _classify_week(archive_label, w)


def _stage(fn, fallback):
    """Ejecuta una etapa de la clasificación; una excepción cierra esa etapa con motivo y no borra las anteriores (R24-06)."""
    try:
        return fn()
    except Exception as exc:  # noqa: BLE001 - datos malformados: no se aborta, no se acredita
        return fallback(f"classification_error:{type(exc).__name__}")


def _classify_week(archive_label: str, w: dict) -> dict:
    not_checked = {"ok": None, "reason": "not_checked"}
    fa = _stage(lambda: forecast_archive(archive_label, w["week_id"], {
        f: {"sha": x.get("forecast_sha256"), "picks": [p.get("security_id") for p in x.get("picks") or []],
            "symbols": [p.get("symbol") for p in x.get("picks") or []], "status": x.get("forecast_status", x.get("status")),
            "packet_hash": w.get("packet_hash"), "cutoff_at": w.get("cutoff_at")} for f, x in (w.get("forecasters") or {}).items()}),
        lambda why: {"archived_at": {}, "archived_at_latest": {}, "deadline_at": {}, "clock_source": {}, "before_deadline": False,
                     "reasons": [why], "ranking": {}, "master_sha256": {}})
    reasons = list(fa["reasons"])
    if not fa["before_deadline"]:
        return {"fa": fa, "inp": dict(not_checked), "master": {"ok": None, "reasons": []}, "prospective": False, "reasons": reasons}
    mi = _stage(lambda: master_identity(w.get("master_capture"), w["cutoff_at"], fa.get("ranking") or {}, archive_label=archive_label,
                                        deadlines=fa.get("deadline_at") or {}, links=fa.get("master_sha256") or {}),
                lambda why: {"ok": False, "reasons": [why]})
    reasons.extend(mi["reasons"])
    inp = _stage(lambda: inputs_before_cutoff(w.get("packet_capture"), w["cutoff_at"], w.get("packet_hash")),
                 lambda why: {"ok": False, "reason": why})
    if inp.get("reason"):
        reasons.append(inp["reason"])
    coherent = inp.get("ok") is True

    def names_and_packet():
        ok = True
        archived = inp.get("names") or {}
        for f, x in (w.get("forecasters") or {}).items():
            for p in x.get("picks") or []:
                if archived.get(p.get("security_id")) is None or archived.get(p.get("security_id")) != p.get("name"):
                    ok = False; reasons.append(f"name_mismatch:{f}"); break
        if mi.get("ok") is True:
            # coherencia paquete-maestro (R24-04): cada serie del paquete pertenece a un valor con segmento vigente al
            # corte y su identificador de documento lleva el símbolo de ese segmento (así los construye el Runner)
            as_of = date.fromisoformat(mi["as_of"])
            for s in inp.get("series") or []:
                sid = s.get("security_id")
                covering = [v for v in (mi.get("segments") or {}).get(sid, []) if v.covers(as_of)]
                if not covering:
                    ok = False; reasons.append(f"packet_unknown_security:{sid}"); continue
                seg = max(covering, key=lambda v: v.valid_from)
                doc_id = s.get("doc_id") or ""
                if ":bars:" not in doc_id or doc_id.split(":bars:", 1)[0] != seg.symbol:
                    ok = False; reasons.append(f"packet_symbol_mismatch:{sid}")
        return ok

    if coherent:
        coherent = _stage(names_and_packet, lambda why: reasons.append(why) or False)
    return {"fa": fa, "inp": inp, "master": mi, "reasons": reasons,
            "prospective": bool(fa["before_deadline"]) and inp.get("ok") is True and coherent and mi.get("ok") is True}


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
                # clasificación completa (informes 26-28): identidad, contrato, plazo, reloj, vínculo, procedencia y nombres
                c = classify_week(alabel, w)
                fa, inp = c["fa"], c["inp"]
                w["forecast_archived_at"] = fa["archived_at"]
                w["forecast_deadline_at"] = fa["deadline_at"]
                w["forecast_before_deadline"] = fa["before_deadline"]
                w["forecast_reasons"] = c["reasons"]
                w["inputs_before_cutoff"] = inp.get("ok")
                w["inputs_reason"] = inp.get("reason")
                w["identity_ok"] = c["master"].get("ok")
                w["packet_mode"] = inp.get("mode")
                w["prospective"] = c["prospective"]
                if w["prospective"]:
                    prospective_weeks.append(w["week_id"])
            sc["prospective_weeks"] = prospective_weeks
            pending = [w for w in sc["weeks"] if w["pending_outcome"]]
            if pending:
                w = pending[-1]
                sc["current_week"] = {"week_id": w["week_id"], "archived_at": w["forecast_archived_at"], "deadline_at": w["forecast_deadline_at"],
                                      "before_deadline": w["forecast_before_deadline"], "inputs_before_cutoff": w["inputs_before_cutoff"],
                                      "prospective": w["prospective"], "reasons": w["forecast_reasons"],
                                      "packet_mode": w["packet_mode"]}
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
        now = datetime.now(timezone.utc)
        while nxt <= now:                       # instante completo del corte (18:00 Taipei), no la fecha UTC (R20-07)
            nxt += timedelta(days=7)
        next_cutoff = nxt.date().isoformat()
    phase = 3 if prospective else (2 if backtested else 1)
    return {"phase": phase, "phases_total": 4, "prospective_weeks": prospective, "prospective_count": len(prospective),
            "pending_weeks": pending, "backtested_weeks": backtested, "next_cutoff": next_cutoff,
            "weekly_pipeline": "scripts/weekly_prospective.ps1", "external_timestamp": False,
            "prospective_mode_admission": False}


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
