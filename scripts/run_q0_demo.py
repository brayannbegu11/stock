"""Demostración completa del motor con la regla transparente Q0 (momentum de 20 sesiones).

Recorre semana a semana el protocolo sobre la muestra archivada por
``fetch_history_sample.py``: paquete por corte (domingo 18:00 Taipei) con las
barras disponibles según la política declarada, predicción Q0 validada contra
el contrato, archivo de paquete y predicción, cesta simulada de cinco puestos
en el libro (lotes, costes, dividendos, retiradas), comparador aleatorio
emparejado (A1) y referencia equiponderada del universo elegible.

**Qué demuestra:** que la cadena datos → paquete → predicción → libro →
evaluación funciona de extremo a extremo sin LLM y con control temporal.
**Qué NO demuestra:** rentabilidad. La muestra procede del censo vigente
(sesgo de supervivencia), los costes son ilustrativos y varios valores del
protocolo siguen sin congelar; todo eso se declara en el informe de salida.

Uso: python scripts/run_q0_demo.py --start 2024-01-01 --end 2025-12-31
"""
from __future__ import annotations

import argparse
import collections
import json
import random
import statistics
import sys
from dataclasses import asdict
from datetime import date, datetime, time, timedelta
from decimal import Decimal as D
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from twlab.calendar import TradingCalendar, load_twse_reference_calendar  # noqa: E402
from twlab.evaluation import IntervalMismatch, IntervalReturn, WeeklyObservation, block_bootstrap_mean, paired_excess  # noqa: E402
from twlab.ledger import CorporateAction, CostModel, LedgerError, MissingPrice, PaperLedger  # noqa: E402
from twlab.master import SecurityMaster, SecurityVersion, TerminalEvent, UnknownSymbol, classify_coverage  # noqa: E402
from twlab.packet import Document, build_packet, canonical_bytes, packet_to_json  # noqa: E402
from twlab.schemas import validate_prediction  # noqa: E402
from twlab.simulation import basket_report, enter_basket, exit_basket  # noqa: E402
from twlab.sources import finmind  # noqa: E402
from twlab.store import RawStore  # noqa: E402
from twlab.timeutil import TAIPEI, AvailabilityQuality, taipei  # noqa: E402
from twlab.weekly import plan_week  # noqa: E402

EVIDENCE = "historical_numeric_temporally_controlled"
PRE_OPEN = time(8, 59)      # instante de derechos: antes de la apertura del día ex
PAR_VALUE = D(10)           # supuesto: valor nominal 10 TWD por acción para convertir dividendos en acciones


def sundays(start: date, end: date):
    d = start + timedelta(days=(6 - start.weekday()) % 7)
    while d <= end:
        yield d
        d += timedelta(days=7)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2024-01-01")
    ap.add_argument("--end", default="2025-12-31")
    ap.add_argument("--notional", type=int, default=1_000_000)
    ap.add_argument("--slots", type=int, default=5)
    ap.add_argument("--seed", type=int, default=20260909)
    ap.add_argument("--block-length", type=int, default=4)
    ap.add_argument("--slippage-bps", type=int, default=10)
    ap.add_argument("--sizing", choices=("proportional", "fixed"), default="proportional",
                    help="proportional: nocional = efectivo disponible / puestos (autofinanciado); fixed: nocional fijo (exige colchón de efectivo)")
    ap.add_argument("--exposure-tolerance", default="0.10",
                    help="tolerancia de exposición para emparejar intervalos (valor provisional del protocolo; el redondeo a lotes la hace necesaria)")
    args = ap.parse_args()
    start, end = date.fromisoformat(args.start), date.fromisoformat(args.end)
    store = RawStore(ROOT / "data" / "raw")
    manifest = json.loads((ROOT / "data" / "store" / "sample_universe.json").read_text(encoding="utf-8"))
    official = load_twse_reference_calendar()

    # ---- datos de la muestra -----------------------------------------------------------
    bars: dict[str, list[finmind.Bar]] = {}
    divs: dict[str, list[finmind.DividendRow]] = {}
    price_caps: dict[str, object] = {}
    listing: dict[str, date] = {}
    delisting: dict[str, date] = {}
    names: dict[str, str] = {}
    dropped_zero_bars = 0
    for row in manifest["listed"]:
        listing[row["symbol"]] = date.fromisoformat(row["listing_date"])
        names[row["symbol"]] = row["name"]
    for row in manifest["delisted"]:
        delisting[row["symbol"]] = date.fromisoformat(row["delisting_date"])
        names[row["symbol"]] = row["name"]
    for sid, caps in manifest["captures"].items():
        if caps["price_rows"] <= 0:
            continue
        rec = store.get(caps["price"])
        price_caps[sid] = rec
        raw_bars = finmind.bars_from_rows(finmind.rows(store, rec))
        # una barra con cierre 0 es un día sin negociación (suspensión): se trata como ausencia de barra
        bars[sid] = [b for b in raw_bars if b.close > 0 and b.open > 0]
        dropped_zero_bars += len(raw_bars) - len(bars[sid])
        divs[sid] = finmind.dividends_from_rows(finmind.rows(store, store.get(caps["dividend"]))) if caps["dividend_rows"] > 0 else []
    by_session: dict[str, dict[date, finmind.Bar]] = {sid: {b.session: b for b in bs} for sid, bs in bars.items()}

    # ---- cierres extraordinarios inferidos (la lista anual oficial no los trae) -----------
    traded_days: set[date] = set().union(*[set(m) for m in by_session.values()])
    span_start, span_end = date(2021, 1, 1), min(end, max(traded_days))
    inferred = sorted(s for s in official.sessions_between(span_start, span_end) if s not in traded_days)
    demo_cal = TradingCalendar(start=official.start, end=official.end, closures=set(official.closures) | set(inferred),
                               source_id=f"{official.source_id}+inferred_closures(sample)", recorded_at=datetime.now(TAIPEI),
                               version=f"{official.version}+inferred:{len(inferred)}")

    # ---- maestro de la muestra ---------------------------------------------------------------
    master = SecurityMaster()
    now = datetime.now(TAIPEI)
    for sid in bars:
        vf = listing.get(sid, bars[sid][0].session)
        sv = SecurityVersion(security_id=f"TWSE:{sid}", issuer_id=sid, symbol=sid, name_zh=names.get(sid, ""), market="TWSE",
                             board="main", instrument_type="ordinary_equity", valid_from=vf, valid_to=None, recorded_at=now,
                             source_id="sample_universe.json")
        master.add(sv)
        if sid in delisting:
            # la fila de retirada es una revisión posterior a la de alta: necesita recorded_at estrictamente mayor (R04-12)
            later = now + timedelta(seconds=1)
            master.close_version(sv.security_id, valid_to=delisting[sid], recorded_at=later, source_id="twse:suspendListing",
                                 terminal=TerminalEvent(sv.security_id, "delisting", delisting[sid], later, "twse:suspendListing"))

    costs = CostModel(commission_per_side=D("0.001425"), sell_tax=D("0.003"), slippage_bps_per_side=args.slippage_bps)
    initial = D(args.notional * args.slots)
    ledgers = {"Q0": PaperLedger(ledger_id="Q0", initial_cash=initial, cost_model=costs),
               "A1": PaperLedger(ledger_id="A1", initial_cash=initial, cost_model=costs)}
    open_slots: dict[str, list] = {"Q0": [], "A1": []}
    prev_equity = {"Q0": initial, "A1": initial}
    weeks: list[dict] = []
    rng = random.Random(args.seed)

    def mark_prices(session: date, ledger: PaperLedger) -> tuple[dict[str, D], list[str]]:
        """Cierres de la sesión; si un valor no negoció, último cierre conocido y aviso explícito (no es un precio de mercado)."""
        out, stale = {}, []
        for sec in ledger.positions:
            sid = sec.split(":", 1)[1]
            b = by_session.get(sid, {}).get(session)
            if b is None:
                prev = [x for x in bars.get(sid, []) if x.session <= session]
                if prev:
                    out[sec] = prev[-1].close
                    stale.append(f"stale_price:{sec}:{prev[-1].session.isoformat()}")
            else:
                out[sec] = b.close
        return out, stale

    def week_costs(slots) -> D:
        total = D(0)
        for s_ in slots:
            for f in (s_.entry, s_.exit):
                if f is not None:
                    total += f.commission + f.tax + f.slippage_cost
        return total

    def apply_actions(ledger: PaperLedger, window_start: date, window_end: date, *, include_start: bool) -> int:
        n = 0
        events = []
        for sec in list(ledger.positions):
            sid = sec.split(":", 1)[1]
            for dv in divs.get(sid, []):
                for kind, exd in (("cash", dv.cash_ex_date), ("stock", dv.stock_ex_date)):
                    if exd is None:
                        continue
                    if (exd == window_start and include_start) or (window_start < exd <= window_end):
                        events.append((exd, kind, sec, dv))
            dl = delisting.get(sid)
            if dl and ((dl == window_start and include_start) or (window_start < dl <= window_end)):
                events.append((dl, "delisting", sec, None))
        for exd, kind, sec, dv in sorted(events, key=lambda e: (e[0], e[1])):
            at = taipei(exd, PRE_OPEN)
            try:
                if kind == "cash" and dv.cash_per_share > 0:
                    pay = taipei(dv.cash_pay_date, time(9, 0)) if dv.cash_pay_date else None
                    ledger.apply_corporate_action(CorporateAction(f"{sec}:cash:{exd}:{dv.period}", sec, "cash_dividend", at,
                                                                  per_share_cash=dv.cash_per_share, pay_at=pay))
                elif kind == "stock" and dv.stock_per_share > 0:
                    ledger.apply_corporate_action(CorporateAction(f"{sec}:stock:{exd}:{dv.period}", sec, "stock_dividend", at,
                                                                  stock_ratio=dv.stock_per_share / PAR_VALUE))
                elif kind == "delisting":
                    ledger.apply_corporate_action(CorporateAction(f"{sec}:delisting:{exd}", sec, "delisting", at, terminal_price=None))
                else:
                    continue
                n += 1
            except LedgerError as exc:
                weeks[-1].setdefault("action_errors", []).append(f"{sec}:{kind}:{exd}:{exc}")
        return n

    for wi, sunday in enumerate(sundays(start, end)):
        cutoff = taipei(sunday, time(18, 0))
        plan = plan_week(cutoff, demo_cal)
        record = {"week_id": plan.week_id, "cutoff_at": cutoff.isoformat(), "status": plan.status}
        weeks.append(record)
        if plan.is_valid and plan.exit_at.date() > end:
            weeks.pop()                                   # la semana no cabe en el periodo con datos: no se opera
            break
        if not plan.is_valid:
            for lg in ledgers.values():
                lg.advance_to(taipei(plan.target_monday + timedelta(days=6), time(23, 59)))
            record["note"] = "invalid:no_sessions (registrado, sin operaciones)"
            continue
        last_session = demo_cal.prev_session(before=sunday)
        # ---- paquete ---------------------------------------------------------------------
        docs = []
        for sid, bs in bars.items():
            known = [b for b in bs if b.available_at <= cutoff]
            if not known:
                continue
            rec = price_caps[sid]
            docs.append(Document(
                doc_id=f"{sid}:bars:{plan.week_id}", kind="price_bar_series", source_id="finmind", security_ids=(f"TWSE:{sid}",),
                available_at=known[-1].available_at, availability_quality=AvailabilityQuality.CONSERVATIVE_INFERENCE,
                capture_id=rec.capture_id, source_sha256=rec.sha256, derivation="finmind_price_bars_v1",
                payload={"history_sessions": len(known), "last_session": known[-1].session.isoformat(),
                         "sessions": [[b.session.isoformat(), str(b.open), str(b.close), b.volume_shares, str(b.value_twd)] for b in known[-130:]]},
            ))
        packet = build_packet(packet_id=f"pkt-Q0-{plan.week_id}", cutoff_at=cutoff, documents=docs, mode="historical",
                              evidence_class=EVIDENCE, calendar=demo_cal)
        pkt_rec = store.put(source_id="packet", dataset=f"Q0/{plan.week_id}", payload=packet_to_json(packet), url="local://demo",
                            content_type="application/json", extra={"packet_hash": packet.packet_hash(), "evidence_class": EVIDENCE})
        # ---- predictor Q0: sólo ve el paquete ----------------------------------------------
        scored = []
        eligible_ids = []
        coverage_reasons: dict[str, int] = {}
        for doc in packet.admitted:
            sid = doc.security_ids[0].split(":", 1)[1]
            sessions = list(doc.payload["sessions"])
            closes = [D(s[2]) for s in sessions]
            values = [D(s[4]) for s in sessions[-20:]]
            try:
                sv = master.resolve_symbol(sid, as_of=last_session)
            except UnknownSymbol:                       # retirada antes de la última sesión: fuera del censo vigente
                coverage_reasons["not_in_catalog_as_of_last_session"] = coverage_reasons.get("not_in_catalog_as_of_last_session", 0) + 1
                continue
            median_value = statistics.median(values) if values else D(0)
            status_ok = doc.payload["last_session"] == last_session.isoformat()
            cov = classify_coverage(sv, price_history_sessions=int(doc.payload["history_sessions"]), min_history_sessions=120,
                                    trading_status="normal" if status_ok else "no_bar_on_last_session",
                                    liquidity_ok=median_value >= D(20 * args.notional))
            for r in cov.reasons:
                coverage_reasons[r.split(":")[0]] = coverage_reasons.get(r.split(":")[0], 0) + 1
            if cov.numerically_scorable and len(closes) >= 21:
                momentum = closes[-1] / closes[-21] - 1
                scored.append((sid, momentum, doc.doc_id, cov.simulation_eligible))
            if cov.simulation_eligible:
                eligible_ids.append(sid)
        ranked = sorted([s for s in scored if s[3]], key=lambda s: s[1], reverse=True)[: args.slots]
        forecast = {
            "schema_version": "2.0", "forecast_id": f"Q0-{plan.week_id}", "experiment_id": "Q0", "protocol_version": "2.0-draft-demo",
            "packet_id": packet.packet_id, "cutoff_at": cutoff.isoformat(), "issued_at": (cutoff + timedelta(minutes=5)).isoformat(),
            "deadline_at": plan.deadline_at.isoformat(), "timezone": "Asia/Taipei", "evidence_class": EVIDENCE,
            "model": {"requested_id": "rule:momentum_20_sessions_v1", "returned_id": "rule:momentum_20_sessions_v1", "revision_id": None,
                      "prompt_or_feature_version": "q0_v1", "training_manifest_id": None},
            "coverage": {"catalog_count": len(bars), "scored_count": len(scored), "deep_review_count": 0, "eligible_count": len(eligible_ids),
                         "missing_critical_sources": []},
            "status": "selected" if ranked else "abstained",
            "ranking": [{"security_id": f"TWSE:{sid}", "ticker_as_of": sid, "market": "TWSE", "rank": i + 1, "score": float(m),
                         "score_definition": "close[-1]/close[-21]-1 sobre barras nominales del paquete", "document_ids": [doc_id],
                         "feature_ids": ["ret_20s", "median_value_20s"], "impact_hypothesis": None, "counterargument": None,
                         "calibrated_probability": None, "calibration_model_id": None} for i, (sid, m, doc_id, _) in enumerate(ranked)],
            "limitations": ["muestra del censo vigente (sesgo de supervivencia)", "disponibilidad de barras por política de 24 h, no verificada",
                            "costes ilustrativos; deslizamiento central no congelado", "regla de liquidez de la demo, no del protocolo"],
        }
        if not ranked:
            forecast["status_reason"] = "no_eligible_securities"
        problems = validate_prediction(forecast, packet, calendar=demo_cal)
        if problems:
            forecast["status"], forecast["ranking"], forecast["status_reason"] = "invalid", [], "; ".join(problems[:3])
            record["validation_problems"] = problems
        store.put(source_id="forecast", dataset=f"Q0/{plan.week_id}", payload=canonical_bytes({"forecast": forecast, "packet_hash": packet.packet_hash()}),
                  url="local://demo", content_type="application/json", extra={"packet_hash": packet.packet_hash(), "packet_capture": pkt_rec.capture_id})
        record.update(eligible=len(eligible_ids), scored=len(scored), coverage_reasons=coverage_reasons,
                      picks=[sid for sid, _, _, _ in ranked], forecast_status=forecast["status"])
        # ---- simulación: Q0 y comparador aleatorio emparejado A1 ---------------------------------
        entry_s, exit_s = plan.entry_at.date(), plan.exit_at.date()
        picks = {"Q0": [f"TWSE:{sid}" for sid, _, _, _ in ranked] if forecast["status"] == "selected" else [],
                 "A1": [f"TWSE:{s}" for s in rng.sample(eligible_ids, min(args.slots, len(eligible_ids)))] if eligible_ids else []}
        open_prices = {f"TWSE:{sid}": m[entry_s].open for sid, m in by_session.items() if entry_s in m and m[entry_s].open > 0}
        close_prices = {f"TWSE:{sid}": m[exit_s].close for sid, m in by_session.items() if exit_s in m and m[exit_s].close > 0}
        intervals: dict[str, IntervalReturn] = {}
        for name, lg in ledgers.items():
            apply_actions(lg, entry_s, entry_s, include_start=True)          # derechos del día de entrada, antes de comprar
            lg.advance_to(plan.entry_at)                                     # abona cobros vencidos antes de dimensionar
            if args.sizing == "proportional":
                notional = (lg.cash / args.slots).to_integral_value(rounding="ROUND_DOWN")
            else:
                notional = D(args.notional)
            slots = enter_basket(lg, picks=picks[name], slots=args.slots, notional_per_slot=notional, open_prices=open_prices,
                                 at=plan.entry_at, week_id=plan.week_id)
            open_slots[name].append((plan.week_id, slots))
            apply_actions(lg, entry_s, exit_s, include_start=False)          # derechos durante la semana
            for wid, ss in open_slots[name]:
                exit_basket(lg, ss, close_prices=close_prices, at=plan.exit_at, week_id=wid)
            open_slots[name] = [(wid, ss) for wid, ss in open_slots[name] if any(s.status == "exit_blocked" for s in ss)]
            prices_now, stale = mark_prices(exit_s, lg)
            try:
                val = lg.valuation(prices=prices_now, at=plan.exit_at)
                equity = val.total
                flags = list(val.flags) + stale
            except MissingPrice as exc:
                equity, flags = None, [f"missing_price:{exc}"] + stale
            rep = basket_report(plan.week_id, slots, equity_start=prev_equity[name], equity_end=equity if equity is not None else prev_equity[name])
            invested = sum((s.entry.gross for s in slots if s.entry is not None), D(0))
            exposure = (invested / prev_equity[name]) if prev_equity[name] else D(0)
            costs_twd = week_costs(slots)
            record[name] = {"picks": picks[name], "notional_per_slot": float(notional), "filled": rep.filled_slots, "failed": rep.failed_slots,
                            "exit_blocked": rep.exit_blocked_slots, "fail_reasons": [s.reason for s in slots if s.status == "entry_failed"],
                            "mean_gross_pick_return": float(rep.mean_gross_pick_return) if rep.mean_gross_pick_return is not None else None,
                            "portfolio_net_return": float(rep.portfolio_net_return) if equity is not None else None,
                            "exposure": float(exposure), "costs_twd": float(costs_twd),
                            "costs_over_invested": float(costs_twd / invested) if invested else None,
                            "equity_end": float(equity) if equity is not None else None, "flags": flags[:6]}
            if equity is not None and rep.filled_slots > 0:
                intervals[name] = IntervalReturn(label=name, start_at=plan.entry_at, end_at=plan.exit_at, start_price_kind="open",
                                                 end_price_kind="close", value=rep.portfolio_net_return,
                                                 exposure=exposure.quantize(D("0.0001")), week_id=plan.week_id)
            if equity is not None:
                prev_equity[name] = equity
        # ---- referencia equiponderada del universo elegible, mismo intervalo apertura→cierre ---------
        ew = [float(by_session[s][exit_s].close / by_session[s][entry_s].open - 1) for s in eligible_ids
              if entry_s in by_session[s] and exit_s in by_session[s] and by_session[s][entry_s].open > 0]
        record["universe_ew_gross_open_close"] = statistics.fmean(ew) if ew else None
        record["paired"], record["excess_net_q0_minus_a1"], record["unpaired_reason"] = False, None, None
        if "Q0" in intervals and "A1" in intervals:
            try:                                  # SIM-12: sólo se restan intervalos estrictamente comparables (con tolerancia de exposición declarada)
                record["excess_net_q0_minus_a1"] = float(paired_excess(intervals["Q0"], intervals["A1"],
                                                                       exposure_tolerance=D(args.exposure_tolerance)))
                record["paired"] = True
            except IntervalMismatch as exc:
                record["unpaired_reason"] = f"interval_mismatch:{exc}"
        else:
            record["unpaired_reason"] = "missing_interval:" + ",".join(n for n in ("Q0", "A1") if n not in intervals)

    # ---- agregados ---------------------------------------------------------------------------
    valid = [w for w in weeks if w["status"] == "valid"]
    paired = [w for w in valid if w["paired"]]
    obs = [WeeklyObservation(w["week_id"], f"Q0-{w['week_id']}", EVIDENCE, None, w["paired"], w["excess_net_q0_minus_a1"]) for w in valid]
    boot = None
    boot_err = ""
    try:
        boot = block_bootstrap_mean(obs, block_length=args.block_length, n_boot=2000, seed=args.seed)
    except Exception as exc:
        boot_err = str(exc)

    def mean_of(key, name=None):
        xs = [(w[name][key] if name else w[key]) for w in valid if (w[name][key] if name else w[key]) is not None]
        return statistics.fmean(xs) if xs else None

    summary = {
        "period": [args.start, args.end], "sample_size": len(bars), "weeks_total": len(weeks), "weeks_valid": len(valid),
        "weeks_invalid_no_sessions": len([w for w in weeks if w["status"] != "valid"]), "weeks_paired": len(paired),
        "inferred_extraordinary_closures": [d.isoformat() for d in inferred], "zero_price_bars_dropped": dropped_zero_bars,
        "Q0": {"mean_weekly_net_return": mean_of("portfolio_net_return", "Q0"), "mean_weekly_gross_pick_return": mean_of("mean_gross_pick_return", "Q0"),
               "final_equity": float(prev_equity["Q0"]), "total_net_return": float(prev_equity["Q0"] / initial - 1),
               "entry_failures": sum(w["Q0"]["failed"] for w in valid), "exit_blocked": sum(w["Q0"]["exit_blocked"] for w in valid)},
        "A1": {"mean_weekly_net_return": mean_of("portfolio_net_return", "A1"), "final_equity": float(prev_equity["A1"]),
               "total_net_return": float(prev_equity["A1"] / initial - 1), "entry_failures": sum(w["A1"]["failed"] for w in valid)},
        "universe_ew": {"mean_weekly_gross_open_close": mean_of("universe_ew_gross_open_close")},
        "paired_excess_q0_minus_a1": {"mean": boot.mean, "ci95": [boot.ci_low, boot.ci_high], "n_used": boot.n_used,
                                      "n_excluded": boot.n_invalid_excluded, "block_length": boot.block_length,
                                      "n_segments": boot.n_segments} if boot else {"error": boot_err},
        "assumptions": {"sizing": args.sizing, "notional_per_slot_twd_if_fixed": args.notional, "initial_cash_twd": float(initial), "slots": args.slots,
                        "exposure_pairing_tolerance": args.exposure_tolerance, "costs": asdict(costs), "price_availability_lag_hours": 24,
                        "liquidity_rule_demo": f"mediana(importe 20 sesiones) >= 20 x nocional ({20 * args.notional:,} TWD)",
                        "min_history_sessions": 120, "par_value_for_stock_dividends": str(PAR_VALUE), "seed": args.seed},
        "unpaired_reasons": dict(collections.Counter((w.get("unpaired_reason") or "").split(":")[0] for w in valid if not w["paired"])),
        "mean_costs_over_invested": {name: mean_of("costs_over_invested", name) for name in ledgers},
        "open_positions_at_end": {name: [{"security_id": sec, "status": pos.status, "quantity": str(pos.total_quantity),
                                          "unresolved_fraction": str(pos.unresolved_fraction), "last_note": (pos.notes[-1] if pos.notes else "")}
                                         for sec, pos in sorted(lg.positions.items())] for name, lg in ledgers.items()},
    }
    out = {"summary": summary, "weeks": weeks}
    out_path = ROOT / "data" / "store" / f"q0_demo_{args.start}_{args.end}.json"
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=1, default=str))
    print(f"\nescrito {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
