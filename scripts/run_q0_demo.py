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

Reglas de la demo tras la ronda 8 de Astra: el plan semanal usa el calendario
oficial conocido al corte (sin cierres inferidos a posteriori); una sesión
oficial sin negociación en toda la muestra se marca como cierre sobrevenido
sin gestionar (política del protocolo pendiente); las acciones corporativas se
procesan sin huecos (también en semanas sin sesiones); una cesta sigue en
seguimiento mientras conserve cantidad en el libro; los intervalos emparejados
se miden de apertura del lunes a cierre del viernes sobre el patrimonio valorado
en ambos instantes, con todas las posiciones arrastradas.

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

from twlab.calendar import load_twse_reference_calendar  # noqa: E402
from twlab.evaluation import IntervalMismatch, IntervalReturn, WeeklyObservation, block_bootstrap_mean, paired_excess  # noqa: E402
from twlab.ledger import CorporateAction, CostModel, LedgerError, MissingPrice, PaperLedger  # noqa: E402
from twlab.master import SecurityMaster, SecurityVersion, TerminalEvent, UnknownSymbol, classify_coverage, security_id_for  # noqa: E402
from twlab.packet import Document, build_packet, canonical_bytes, packet_to_json  # noqa: E402
from twlab.schemas import validate_prediction  # noqa: E402
from twlab.simulation import basket_report, enter_basket, exit_basket  # noqa: E402
from twlab.sources import finmind  # noqa: E402
from twlab.sources.finmind import SourceIdentityMismatch  # noqa: E402
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
    official = load_twse_reference_calendar()          # calendario conocido al corte: lista anual oficial, sin cierres sobrevenidos

    # ---- datos de la muestra (identidad de cada captura comprobada, R08-06) -------------------------
    bars: dict[str, list[finmind.Bar]] = {}
    divs: dict[str, list[finmind.DividendRow]] = {}
    price_caps: dict[str, object] = {}
    listing: dict[str, date] = {}
    delisting: dict[str, date] = {}
    names: dict[str, str] = {}
    dropped_no_regular_price = 0
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
        if rec.source_id != "finmind" or rec.dataset != f"TaiwanStockPrice/{sid}":
            raise SourceIdentityMismatch(f"{sid}: manifest points to capture {rec.capture_id} ({rec.dataset})")
        price_caps[sid] = rec
        raw_bars = finmind.bars_from_rows(finmind.rows(store, rec), stock_id=sid)
        # OHLC a cero = sin precio de sesión regular (puede haber lotes menores): sin ejecución ni valoración (R08-12)
        bars[sid] = [b for b in raw_bars if b.has_regular_price]
        dropped_no_regular_price += len(raw_bars) - len(bars[sid])
        if caps["dividend_rows"] > 0:
            drec = store.get(caps["dividend"])
            if drec.dataset != f"TaiwanStockDividend/{sid}":
                raise SourceIdentityMismatch(f"{sid}: manifest points to dividend capture {drec.capture_id} ({drec.dataset})")
            divs[sid] = finmind.dividends_from_rows(finmind.rows(store, drec), stock_id=sid)
        else:
            divs[sid] = []
    by_session: dict[str, dict[date, finmind.Bar]] = {sid: {b.session: b for b in bs} for sid, bs in bars.items()}

    # ---- diagnóstico: sesiones oficiales sin negociación en toda la muestra (cierres sobrevenidos) ----------
    traded_days: set[date] = set().union(*[set(m) for m in by_session.values()])
    span_start, span_end = date(2021, 1, 1), min(end, max(traded_days))
    inferred = sorted(s for s in official.sessions_between(span_start, span_end) if s not in traded_days)

    # ---- maestro de la muestra (identidad = símbolo + fecha de alta, R08-05) ----------------------------
    master = SecurityMaster()
    now = datetime.now(TAIPEI)
    sec_of: dict[str, str] = {}
    sym_of: dict[str, str] = {}
    for sid in bars:
        vf = listing.get(sid, bars[sid][0].session)
        sec_id = security_id_for("TWSE", sid, vf)
        sec_of[sid], sym_of[sec_id] = sec_id, sid
        sv = SecurityVersion(security_id=sec_id, issuer_id=sec_id, symbol=sid, name_zh=names.get(sid, ""), market="TWSE",
                             board="main", instrument_type="ordinary_equity", valid_from=vf, valid_to=None, recorded_at=now,
                             source_id="sample_universe.json")
        master.add(sv)
        if sid in delisting:
            later = now + timedelta(seconds=1)          # revisión posterior a la fila de alta (R04-12)
            master.close_version(sec_id, valid_to=delisting[sid], recorded_at=later, source_id="twse:suspendListing",
                                 terminal=TerminalEvent(sec_id, "delisting", delisting[sid], later, "twse:suspendListing"))

    costs = CostModel(commission_per_side=D("0.001425"), sell_tax=D("0.003"), slippage_bps_per_side=args.slippage_bps)
    initial = D(args.notional * args.slots)
    ledgers = {"Q0": PaperLedger(ledger_id="Q0", initial_cash=initial, cost_model=costs),
               "A1": PaperLedger(ledger_id="A1", initial_cash=initial, cost_model=costs)}
    open_slots: dict[str, list] = {"Q0": [], "A1": []}
    prev_equity = {"Q0": initial, "A1": initial}          # patrimonio al cierre de la última semana operada (curva)
    cursor: dict[str, date] = {"Q0": start - timedelta(days=1), "A1": start - timedelta(days=1)}   # eventos procesados hasta (inclusive)
    weeks: list[dict] = []
    rng = random.Random(args.seed)

    def marks(session: date, ledger: PaperLedger, kind: str) -> tuple[dict[str, D], list[str]]:
        """Precios de la sesión (apertura o cierre); si un valor no tiene precio regular ese día, último cierre
        conocido con aviso explícito: no es un precio de mercado."""
        out, stale = {}, []
        for sec in ledger.positions:
            sid = sym_of[sec]
            b = by_session.get(sid, {}).get(session)
            if b is None:
                prev = [x for x in bars.get(sid, []) if x.session <= session]
                if prev:
                    out[sec] = prev[-1].close
                    stale.append(f"stale_price:{sec}:{prev[-1].session.isoformat()}")
            else:
                out[sec] = b.open if kind == "open" else b.close
        return out, stale

    def week_costs(slots) -> D:
        total = D(0)
        for s_ in slots:
            for f in (s_.entry, s_.exit):
                if f is not None:
                    total += f.commission + f.tax + f.slippage_cost
        return total

    def apply_actions(name: str, upto: date) -> int:
        """Aplica, en orden, todos los eventos de las posiciones del libro con fecha en (cursor, upto]; sin huecos (R08-09)."""
        ledger = ledgers[name]
        since = cursor[name]
        if upto <= since:
            return 0
        events = []
        for sec in list(ledger.positions):
            sid = sym_of[sec]
            for dv in divs.get(sid, []):
                for kind, exd in (("cash", dv.cash_ex_date), ("stock", dv.stock_ex_date)):
                    if exd is not None and since < exd <= upto:
                        events.append((exd, kind, sec, dv))
            dl = delisting.get(sid)
            if dl and since < dl <= upto:
                events.append((dl, "delisting", sec, None))
        n = 0
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
                weeks[-1].setdefault("action_errors", []).append(f"{name}:{sec}:{kind}:{exd}:{exc}")
        cursor[name] = upto
        return n

    for sunday in sundays(start, end):
        cutoff = taipei(sunday, time(18, 0))
        plan = plan_week(cutoff, official)
        record = {"week_id": plan.week_id, "cutoff_at": cutoff.isoformat(), "status": plan.status}
        weeks.append(record)
        if plan.is_valid and plan.exit_at.date() > end:
            weeks.pop()                                   # la semana no cabe en el periodo con datos: no se opera
            break
        if not plan.is_valid:
            week_end = plan.target_monday + timedelta(days=6)
            for name, lg in ledgers.items():
                apply_actions(name, week_end)             # los derechos no se detienen en una semana sin sesiones (T2)
                lg.advance_to(taipei(week_end, time(23, 59)))
            record["note"] = "invalid:no_sessions (registrado, sin operaciones; eventos procesados)"
            continue
        entry_s, exit_s = plan.entry_at.date(), plan.exit_at.date()
        if entry_s not in traded_days or exit_s not in traded_days:
            # sesión oficial sin negociación en toda la muestra: cierre sobrevenido. El protocolo aún no dice cómo se
            # replanifica (informe 11 §4); la demo no opera y lo declara. No se usa conocimiento posterior al corte.
            closed = entry_s if entry_s not in traded_days else exit_s
            for name, lg in ledgers.items():
                apply_actions(name, exit_s)
                lg.advance_to(plan.exit_at)
            record.update(note=f"extraordinary_closure_unhandled:{closed.isoformat()}", paired=False,
                          unpaired_reason="extraordinary_closure_unhandled", excess_net_q0_minus_a1=None)
            record["status"] = "valid:not_operated"
            continue
        last_session = official.prev_session(before=sunday)
        # ---- paquete ---------------------------------------------------------------------
        docs = []
        for sid, bs in bars.items():
            known = [b for b in bs if b.available_at <= cutoff]
            if not known:
                continue
            rec = price_caps[sid]
            docs.append(Document(
                doc_id=f"{sid}:bars:{plan.week_id}", kind="price_bar_series", source_id="finmind", security_ids=(sec_of[sid],),
                available_at=known[-1].available_at, availability_quality=AvailabilityQuality.CONSERVATIVE_INFERENCE,
                capture_id=rec.capture_id, source_sha256=rec.sha256, derivation="finmind_price_bars_v1",
                payload={"history_sessions": len(known), "last_session": known[-1].session.isoformat(),
                         "sessions": [[b.session.isoformat(), str(b.open), str(b.close), b.volume_shares, str(b.value_twd)] for b in known[-130:]]},
            ))
        packet = build_packet(packet_id=f"pkt-Q0-{plan.week_id}", cutoff_at=cutoff, documents=docs, mode="historical",
                              evidence_class=EVIDENCE, calendar=official)
        pkt_rec = store.put(source_id="packet", dataset=f"Q0/{plan.week_id}", payload=packet_to_json(packet), url="local://demo",
                            content_type="application/json", extra={"packet_hash": packet.packet_hash(), "evidence_class": EVIDENCE})
        # ---- predictor Q0: sólo ve el paquete ----------------------------------------------
        scored = []
        eligible: list[str] = []
        coverage_reasons: dict[str, int] = {}
        for doc in packet.admitted:
            sid = sym_of[doc.security_ids[0]]
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
                scored.append((sv.security_id, sid, momentum, doc.doc_id, cov.simulation_eligible))
            if cov.simulation_eligible:
                eligible.append(sv.security_id)
        ranked = sorted([s for s in scored if s[4]], key=lambda s: s[2], reverse=True)[: args.slots]
        forecast = {
            "schema_version": "2.0", "forecast_id": f"Q0-{plan.week_id}", "experiment_id": "Q0", "protocol_version": "2.0-draft-demo",
            "packet_id": packet.packet_id, "cutoff_at": cutoff.isoformat(), "issued_at": (cutoff + timedelta(minutes=5)).isoformat(),
            "deadline_at": plan.deadline_at.isoformat(), "timezone": "Asia/Taipei", "evidence_class": EVIDENCE,
            "model": {"requested_id": "rule:momentum_20_sessions_v1", "returned_id": "rule:momentum_20_sessions_v1", "revision_id": None,
                      "prompt_or_feature_version": "q0_v1", "training_manifest_id": None},
            "coverage": {"catalog_count": len(bars), "scored_count": len(scored), "deep_review_count": 0, "eligible_count": len(eligible),
                         "missing_critical_sources": []},
            "status": "selected" if ranked else "abstained",
            "ranking": [{"security_id": sec_id, "ticker_as_of": sid, "market": "TWSE", "rank": i + 1, "score": float(m),
                         "score_definition": "close[-1]/close[-21]-1 sobre barras nominales del paquete", "document_ids": [doc_id],
                         "feature_ids": ["ret_20s", "median_value_20s"], "impact_hypothesis": None, "counterargument": None,
                         "calibrated_probability": None, "calibration_model_id": None} for i, (sec_id, sid, m, doc_id, _) in enumerate(ranked)],
            "limitations": ["muestra del censo vigente (sesgo de supervivencia)", "disponibilidad de barras por política de 24 h, no verificada",
                            "costes ilustrativos; deslizamiento central no congelado", "regla de liquidez de la demo, no del protocolo"],
        }
        if not ranked:
            forecast["status_reason"] = "no_eligible_securities"
        problems = validate_prediction(forecast, packet, calendar=official)
        if problems:
            forecast["status"], forecast["ranking"], forecast["status_reason"] = "invalid", [], "; ".join(problems[:3])
            record["validation_problems"] = problems
        store.put(source_id="forecast", dataset=f"Q0/{plan.week_id}", payload=canonical_bytes({"forecast": forecast, "packet_hash": packet.packet_hash()}),
                  url="local://demo", content_type="application/json", extra={"packet_hash": packet.packet_hash(), "packet_capture": pkt_rec.capture_id})
        record.update(eligible=len(eligible), scored=len(scored), coverage_reasons=coverage_reasons,
                      picks=[sid for _, sid, _, _, _ in ranked], forecast_status=forecast["status"])
        # ---- simulación: Q0 y comparador aleatorio emparejado A1 ---------------------------------
        picks = {"Q0": [sec_id for sec_id, _, _, _, _ in ranked] if forecast["status"] == "selected" else [],
                 "A1": rng.sample(eligible, min(args.slots, len(eligible))) if eligible else []}
        open_prices = {sec_of[sid]: m[entry_s].open for sid, m in by_session.items() if entry_s in m}
        close_prices = {sec_of[sid]: m[exit_s].close for sid, m in by_session.items() if exit_s in m}
        intervals: dict[str, IntervalReturn] = {}
        for name, lg in ledgers.items():
            apply_actions(name, entry_s)                  # todo lo pendiente hasta el lunes 08:59 inclusive (derechos antes de comprar)
            lg.advance_to(plan.entry_at)                  # abona cobros vencidos antes de dimensionar
            open_marks, stale0 = marks(entry_s, lg, "open")
            try:                                          # patrimonio en la apertura, con las posiciones arrastradas (R08-10)
                equity_start = lg.valuation(prices=open_marks, at=plan.entry_at).total
            except MissingPrice as exc:
                equity_start = None
                stale0.append(f"missing_open_price:{exc}")
            if args.sizing == "proportional":
                notional = (lg.cash / args.slots).to_integral_value(rounding="ROUND_DOWN")
            else:
                notional = D(args.notional)
            slots = enter_basket(lg, picks=picks[name], slots=args.slots, notional_per_slot=notional, open_prices=open_prices,
                                 at=plan.entry_at, week_id=plan.week_id)
            open_slots[name].append((plan.week_id, slots))
            open_marks_after, _ = marks(entry_s, lg, "open")
            positions_value_open = sum((pos.total_quantity * open_marks_after[sec] for sec, pos in lg.positions.items() if sec in open_marks_after), D(0))
            exposure = (positions_value_open / equity_start) if equity_start else D(0)
            apply_actions(name, exit_s)                   # derechos durante la semana, en orden
            for wid, ss in open_slots[name]:
                exit_basket(lg, ss, close_prices=close_prices, at=plan.exit_at, week_id=wid)
            # una cesta sigue en seguimiento mientras algún puesto conserve cantidad en el libro (R08-08)
            open_slots[name] = [(wid, ss) for wid, ss in open_slots[name]
                                if any(s.status == "exit_blocked" or (s.status == "exited" and not s.liquidated) for s in ss)]
            close_marks, stale1 = marks(exit_s, lg, "close")
            try:
                val = lg.valuation(prices=close_marks, at=plan.exit_at)
                equity_end = val.total
                flags = list(val.flags) + stale0 + stale1
            except MissingPrice as exc:
                equity_end, flags = None, [f"missing_price:{exc}"] + stale0 + stale1
            measurable = equity_start is not None and equity_end is not None and equity_start > 0
            rep = basket_report(plan.week_id, slots, equity_start=equity_start if measurable else prev_equity[name],
                                equity_end=equity_end if measurable else prev_equity[name])
            interval_return = (equity_end / equity_start - 1) if measurable else None
            chain_return = (equity_end / prev_equity[name] - 1) if equity_end is not None and prev_equity[name] else None
            invested = sum((s.entry.gross for s in slots if s.entry is not None), D(0))
            costs_twd = week_costs(slots)
            record[name] = {"picks": [sym_of[p] for p in picks[name]], "notional_per_slot": float(notional), "filled": rep.filled_slots,
                            "failed": rep.failed_slots, "exit_blocked": rep.exit_blocked_slots,
                            "fail_reasons": [s.reason for s in slots if s.status == "entry_failed"],
                            "mean_gross_pick_return": float(rep.mean_gross_pick_return) if rep.mean_gross_pick_return is not None else None,
                            "portfolio_net_return_open_close": float(interval_return) if interval_return is not None else None,
                            "portfolio_net_return_week_over_week": float(chain_return) if chain_return is not None else None,
                            "exposure_at_open": float(exposure), "costs_twd": float(costs_twd),
                            "costs_over_invested": float(costs_twd / invested) if invested else None,
                            "equity_open": float(equity_start) if equity_start is not None else None,
                            "equity_end": float(equity_end) if equity_end is not None else None, "flags": flags[:6],
                            "baskets_in_follow_up": len(open_slots[name])}
            if measurable and rep.filled_slots > 0:
                intervals[name] = IntervalReturn(label=name, start_at=plan.entry_at, end_at=plan.exit_at, start_price_kind="open",
                                                 end_price_kind="close", value=interval_return.quantize(D("0.0000001")),
                                                 exposure=exposure.quantize(D("0.0001")), week_id=plan.week_id)
            if equity_end is not None:
                prev_equity[name] = equity_end
        # ---- referencia equiponderada del universo elegible, mismo intervalo apertura→cierre ---------
        ew = [float(by_session[sym_of[s]][exit_s].close / by_session[sym_of[s]][entry_s].open - 1) for s in eligible
              if entry_s in by_session[sym_of[s]] and exit_s in by_session[sym_of[s]]]
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
    operated = [w for w in weeks if w["status"] == "valid"]
    not_operated = [w for w in weeks if w["status"] == "valid:not_operated"]
    paired = [w for w in operated if w["paired"]]
    obs = [WeeklyObservation(w["week_id"], f"Q0-{w['week_id']}", EVIDENCE, None, bool(w.get("paired")), w.get("excess_net_q0_minus_a1"))
           for w in weeks if w["status"].startswith("valid")]
    boot = None
    boot_err = ""
    try:
        boot = block_bootstrap_mean(obs, block_length=args.block_length, n_boot=2000, seed=args.seed)
    except Exception as exc:
        boot_err = str(exc)

    def mean_of(key, name=None):
        xs = [(w[name][key] if name else w[key]) for w in operated if (w[name][key] if name else w[key]) is not None]
        return statistics.fmean(xs) if xs else None

    summary = {
        "period": [args.start, args.end], "sample_size": len(bars), "weeks_total": len(weeks), "weeks_operated": len(operated),
        "weeks_invalid_no_sessions": len([w for w in weeks if w["status"] == "invalid:no_sessions"]),
        "weeks_extraordinary_closure_unhandled": [w["week_id"] for w in not_operated], "weeks_paired": len(paired),
        "official_sessions_without_trading_in_sample": [d.isoformat() for d in inferred],
        "bars_without_regular_price_dropped": dropped_no_regular_price,
        "Q0": {"mean_weekly_net_return_open_close": mean_of("portfolio_net_return_open_close", "Q0"),
               "mean_weekly_net_return_week_over_week": mean_of("portfolio_net_return_week_over_week", "Q0"),
               "mean_weekly_gross_pick_return": mean_of("mean_gross_pick_return", "Q0"),
               "final_equity": float(prev_equity["Q0"]), "total_net_return": float(prev_equity["Q0"] / initial - 1),
               "entry_failures": sum(w["Q0"]["failed"] for w in operated), "exit_blocked": sum(w["Q0"]["exit_blocked"] for w in operated)},
        "A1": {"mean_weekly_net_return_open_close": mean_of("portfolio_net_return_open_close", "A1"),
               "mean_weekly_net_return_week_over_week": mean_of("portfolio_net_return_week_over_week", "A1"),
               "final_equity": float(prev_equity["A1"]), "total_net_return": float(prev_equity["A1"] / initial - 1),
               "entry_failures": sum(w["A1"]["failed"] for w in operated), "exit_blocked": sum(w["A1"]["exit_blocked"] for w in operated)},
        "universe_ew": {"mean_weekly_gross_open_close": mean_of("universe_ew_gross_open_close")},
        "paired_excess_q0_minus_a1": {"mean": boot.mean, "ci95": [boot.ci_low, boot.ci_high], "n_used": boot.n_used,
                                      "n_excluded": boot.n_invalid_excluded, "block_length": boot.block_length,
                                      "n_segments": boot.n_segments, "resample_mean": boot.resample_mean} if boot else {"error": boot_err},
        "assumptions": {"sizing": args.sizing, "notional_per_slot_twd_if_fixed": args.notional, "initial_cash_twd": float(initial), "slots": args.slots,
                        "exposure_pairing_tolerance": args.exposure_tolerance, "costs": asdict(costs), "price_availability_lag_hours": 24,
                        "liquidity_rule_demo": f"mediana(importe 20 sesiones) >= 20 x nocional ({20 * args.notional:,} TWD)",
                        "min_history_sessions": 120, "par_value_for_stock_dividends": str(PAR_VALUE), "seed": args.seed,
                        "planning_calendar": f"{official.source_id}@{official.version}"},
        "unpaired_reasons": dict(collections.Counter((w.get("unpaired_reason") or "").split(":")[0] for w in operated if not w["paired"])),
        "mean_costs_over_invested": {name: mean_of("costs_over_invested", name) for name in ledgers},
        "open_positions_at_end": {name: [{"security_id": sec, "status": pos.status, "quantity": str(pos.total_quantity),
                                          "unresolved_fraction": str(pos.unresolved_fraction), "last_note": (pos.notes[-1] if pos.notes else "")}
                                         for sec, pos in sorted(lg.positions.items())] for name, lg in ledgers.items()},
        "baskets_in_follow_up_at_end": {name: [wid for wid, _ in open_slots[name]] for name in ledgers},
    }
    out = {"summary": summary, "weeks": weeks}
    out_path = ROOT / "data" / "store" / f"q0_demo_{args.start}_{args.end}.json"
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=1, default=str))
    print(f"\nescrito {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
