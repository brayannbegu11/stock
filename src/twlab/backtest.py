"""Recorrido semanal del protocolo sobre datos archivados, con pronosticadores intercambiables.

Generaliza la demo Q0 (informe 11): por cada corte dominical construye el paquete con las barras
disponibles según la política declarada, pide a cada pronosticador su selección **viendo sólo el
paquete**, valida y archiva la predicción, simula la cesta de cinco puestos en un libro propio,
procesa acciones corporativas sin huecos, mide el intervalo apertura→cierre sobre el patrimonio
contable y empareja cada pronosticador con el comparador aleatorio de la misma semana.

Nada aquí mide rentabilidad futura: los costes son ilustrativos, el universo histórico procede del
censo vigente y varios valores del protocolo siguen sin congelar (informe 11 §4). Si el corte más
reciente aún no tiene desenlace, la selección se emite y archiva igualmente (``pending_outcome``).
"""
from __future__ import annotations

import collections
import json
import random
import statistics
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, time, timedelta
from decimal import Decimal as D
from pathlib import Path
from typing import Callable, Mapping, Optional, Protocol, Sequence

from .calendar import TradingCalendar
from .evaluation import IntervalMismatch, IntervalReturn, WeeklyObservation, block_bootstrap_mean, paired_excess
from .ledger import CorporateAction, CostModel, LedgerError, MissingPrice, PaperLedger
from .master import SecurityMaster, SecurityVersion, TerminalEvent, UnknownSymbol, classify_coverage, security_id_for
from .models import q1 as q1mod
from .packet import Document, Packet, PredictorView, build_packet, canonical_bytes, packet_to_json
from .schemas import validate_prediction
from .simulation import basket_report, enter_basket, exit_basket
from .sources import finmind
from .sources.finmind import SourceIdentityMismatch
from .store import RawStore
from .timeutil import TAIPEI, AvailabilityQuality, taipei
from .weekly import WeekPlan, plan_week

EVIDENCE = "historical_numeric_temporally_controlled"
PRE_OPEN = time(8, 59)


@dataclass
class BacktestConfig:
    start: date
    end: date
    slots: int = 5
    notional: int = 1_000_000
    sizing: str = "proportional"              # proportional | fixed
    exposure_tolerance: D = D("0.10")
    block_length: int = 4
    n_boot: int = 2000
    seed: int = 20260909
    commission_per_side: D = D("0.001425")
    sell_tax: D = D("0.003")
    slippage_bps: int = 10
    min_history_sessions: int = 120
    liquidity_multiple: int = 20               # mediana(importe 20 sesiones) ≥ multiple × nocional
    par_value: D = D(10)
    baseline: str = "A1"
    label: str = "backtest"


@dataclass
class Security:
    symbol: str
    security_id: str
    market: str
    name: str
    listing_date: date
    delisting_date: Optional[date]
    bars: list[finmind.Bar]
    dividends: list[finmind.DividendRow]
    price_capture: object


@dataclass
class MarketData:
    securities: dict[str, Security]            # por security_id
    by_symbol: dict[str, str]                  # símbolo → security_id
    master: SecurityMaster
    calendar: TradingCalendar
    by_session: dict[str, dict[date, finmind.Bar]]
    traded_days: set[date]
    dropped_no_regular_price: int
    source_manifest: str


def load_market(store: RawStore, manifest_path: Path, calendar: TradingCalendar, *, default_market: str = "TWSE") -> MarketData:
    """Carga barras y dividendos desde las capturas listadas en un manifiesto (muestra o universo), comprobando identidad."""
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    listing: dict[str, date] = {}
    delisting: dict[str, date] = {}
    names: dict[str, str] = {}
    markets: dict[str, str] = {}
    for row in manifest.get("listed", []):
        listing[row["symbol"]] = date.fromisoformat(row["listing_date"])
        names[row["symbol"]] = row.get("name", "")
    for row in manifest.get("delisted", []):
        delisting[row["symbol"]] = date.fromisoformat(row["delisting_date"])
        names[row["symbol"]] = row.get("name", "")
    now = datetime.now(TAIPEI)
    master = SecurityMaster()
    securities: dict[str, Security] = {}
    by_symbol: dict[str, str] = {}
    by_session: dict[str, dict[date, finmind.Bar]] = {}
    dropped = 0
    for sid, caps in manifest["captures"].items():
        if caps.get("price_rows", 0) <= 0:
            continue
        rec = store.get(caps["price"])
        if rec.source_id != "finmind" or rec.dataset != f"TaiwanStockPrice/{sid}":
            raise SourceIdentityMismatch(f"{sid}: manifest points to capture {rec.capture_id} ({rec.dataset})")
        raw_bars = finmind.bars_from_rows(finmind.rows(store, rec), stock_id=sid)
        bars = [b for b in raw_bars if b.has_regular_price]
        dropped += len(raw_bars) - len(bars)
        if not bars:
            continue
        divs: list[finmind.DividendRow] = []
        if caps.get("dividend_rows", 0) > 0:
            drec = store.get(caps["dividend"])
            if drec.dataset != f"TaiwanStockDividend/{sid}":
                raise SourceIdentityMismatch(f"{sid}: manifest points to dividend capture {drec.capture_id} ({drec.dataset})")
            divs = finmind.dividends_from_rows(finmind.rows(store, drec), stock_id=sid)
        market = caps.get("market", markets.get(sid, default_market))
        vf = date.fromisoformat(caps["listing_date"]) if caps.get("listing_date") else listing.get(sid, bars[0].session)
        name = caps.get("name", names.get(sid, ""))
        sec_id = security_id_for(market, sid, vf)
        sv = SecurityVersion(security_id=sec_id, issuer_id=sec_id, symbol=sid, name_zh=name, market=market, board="main",
                             instrument_type="ordinary_equity", valid_from=vf, valid_to=None, recorded_at=now, source_id=manifest_path.name)
        master.add(sv)
        dl = delisting.get(sid)
        if dl:
            later = now + timedelta(seconds=1)
            master.close_version(sec_id, valid_to=dl, recorded_at=later, source_id="twse:suspendListing",
                                 terminal=TerminalEvent(sec_id, "delisting", dl, later, "twse:suspendListing"))
        securities[sec_id] = Security(sid, sec_id, market, name, vf, dl, bars, divs, rec)
        by_symbol[sid] = sec_id
        by_session[sec_id] = {b.session: b for b in bars}
    traded: set[date] = set().union(*[set(m) for m in by_session.values()]) if by_session else set()
    return MarketData(securities, by_symbol, master, calendar, by_session, traded, dropped, manifest_path.name)


# ---------------------------------------------------------------------------------------------------
# Pronosticadores: sólo ven el paquete (PredictorView) y la lista de candidatos derivada de él.
# ---------------------------------------------------------------------------------------------------

@dataclass
class Candidate:
    security_id: str
    symbol: str
    doc_id: str
    sessions: list                 # [[fecha, apertura, cierre, volumen, importe], ...] del documento
    scorable: bool
    eligible: bool
    reasons: tuple[str, ...]


@dataclass
class Selection:
    security_id: str
    score: float
    doc_ids: list[str]
    feature_ids: list[str] = field(default_factory=list)


class Forecaster(Protocol):
    name: str
    model_id: str
    version: str

    def forecast(self, view: PredictorView, plan: WeekPlan, candidates: Sequence[Candidate], *, slots: int) -> tuple[list[Selection], dict]:
        """Devuelve selecciones ordenadas (como máximo ``slots``) y metadatos (training_manifest_id, limitaciones)."""


class MomentumForecaster:
    """Q0: rentabilidad de 20 sesiones sobre las barras nominales del paquete. Control transparente."""
    name, model_id, version = "Q0", "rule:momentum_20_sessions_v1", "q0_v1"

    def forecast(self, view, plan, candidates, *, slots):
        scored = []
        for c in candidates:
            if not (c.scorable and c.eligible) or len(c.sessions) < 21:
                continue
            closes = [D(s[2]) for s in c.sessions]
            scored.append(Selection(c.security_id, float(closes[-1] / closes[-21] - 1), [c.doc_id], ["ret_20s", "median_value_20s"]))
        return sorted(scored, key=lambda s: s.score, reverse=True)[:slots], {"training_manifest_id": None}


class RandomForecaster:
    """A1: cinco valores al azar entre los elegibles de la semana, con semilla declarada."""
    name, model_id, version = "A1", "rule:random_eligible_v1", "a1_v1"

    def __init__(self, seed: int) -> None:
        self.rng = random.Random(seed)

    def forecast(self, view, plan, candidates, *, slots):
        eligible = [c for c in candidates if c.eligible]
        picks = self.rng.sample(eligible, min(slots, len(eligible))) if eligible else []
        return [Selection(c.security_id, 0.0, [c.doc_id], []) for c in picks], {"training_manifest_id": None}


class TabularForecaster:
    """Q1: características de precio/volumen del paquete y modelo entrenado sólo con etiquetas conocidas al corte."""
    name, model_id, version = "Q1", q1mod.MODEL_ID, "q1_v1"

    def __init__(self, market: MarketData, *, retrain_every_weeks: int = 4, min_weeks: int = 52, seed: int = 20260909) -> None:
        self.market = market
        self.retrain_every = retrain_every_weeks
        self.min_weeks = min_weeks
        self.seed = seed
        self.model: Optional[q1mod.Q1Model] = None
        self.trained_for: Optional[datetime] = None
        self.weeks_since_train = 0
        self.cache: dict = {}
        self.history: list[str] = []

    def maybe_train(self, cutoff_at: datetime) -> None:
        if self.model is not None and self.weeks_since_train < self.retrain_every:
            self.weeks_since_train += 1
            return
        first = min(b.session for s in self.market.securities.values() for b in s.bars[:1])
        cutoffs = []
        d = first + timedelta(days=(6 - first.weekday()) % 7)
        while d < cutoff_at.date():
            cutoffs.append(taipei(d, time(18, 0)))
            d += timedelta(days=7)
        bars = {sec_id: s.bars for sec_id, s in self.market.securities.items()}
        rows = q1mod.build_training_rows(bars, cutoffs, now_cutoff=cutoff_at, calendar=self.market.calendar, cache=self.cache)
        self.model = q1mod.fit_q1(rows, trained_at=cutoff_at, min_weeks=self.min_weeks, seed=self.seed)
        self.trained_for = cutoff_at
        self.weeks_since_train = 1
        self.history.append(f"{cutoff_at.date().isoformat()}: {self.model.training_manifest_id if self.model else 'insufficient_history'}")

    def forecast(self, view, plan, candidates, *, slots):
        self.maybe_train(plan.cutoff_at)
        meta = {"training_manifest_id": self.model.training_manifest_id if self.model else None}
        if self.model is None:
            return [], {**meta, "status_reason": "insufficient_training_history"}
        feats, elig = [], []
        for c in candidates:
            if not (c.scorable and c.eligible):
                continue
            bars = [q1mod.BarLike(date.fromisoformat(s[0]), D(s[1]), D(s[2]), D(s[4]), plan.cutoff_at) for s in c.sessions]
            f = q1mod.features_from_bars(bars, plan.cutoff_at)
            if f is not None:
                feats.append(f)
                elig.append(c)
        if not feats:
            return [], {**meta, "status_reason": "no_eligible_securities"}
        scores = self.model.predict(feats)
        ranked = sorted(zip(elig, scores), key=lambda t: t[1], reverse=True)[:slots]
        return [Selection(c.security_id, float(s), [c.doc_id], list(q1mod.FEATURE_NAMES)) for c, s in ranked], meta


# ---------------------------------------------------------------------------------------------------

def _week_costs(slots) -> D:
    total = D(0)
    for s_ in slots:
        for f in (s_.entry, s_.exit):
            if f is not None:
                total += f.commission + f.tax + f.slippage_cost
    return total


def _sundays(start: date, end: date):
    d = start + timedelta(days=(6 - start.weekday()) % 7)
    while d <= end:
        yield d
        d += timedelta(days=7)


class Runner:
    def __init__(self, store: RawStore, market: MarketData, cfg: BacktestConfig, forecasters: Sequence[Forecaster]) -> None:
        self.store, self.market, self.cfg = store, market, cfg
        self.forecasters = {f.name: f for f in forecasters}
        if cfg.baseline not in self.forecasters:
            raise ValueError(f"baseline {cfg.baseline!r} is not among the forecasters")
        costs = CostModel(commission_per_side=cfg.commission_per_side, sell_tax=cfg.sell_tax, slippage_bps_per_side=cfg.slippage_bps)
        self.costs = costs
        self.initial = D(cfg.notional * cfg.slots)
        self.ledgers = {n: PaperLedger(ledger_id=n, initial_cash=self.initial, cost_model=costs) for n in self.forecasters}
        self.open_slots: dict[str, list] = {n: [] for n in self.forecasters}
        self.prev_equity = {n: self.initial for n in self.forecasters}
        self.cursor = {n: cfg.start - timedelta(days=1) for n in self.forecasters}
        self.weeks: list[dict] = []
        self.last_data_day = max(market.traded_days) if market.traded_days else cfg.start

    # -- precios y eventos --------------------------------------------------------------------------
    def marks(self, session: date, ledger: PaperLedger, kind: str) -> tuple[dict[str, D], list[str]]:
        out, stale = {}, []
        for sec, pos in ledger.positions.items():
            if pos.status.startswith("delisted"):
                continue
            b = self.market.by_session.get(sec, {}).get(session)
            if b is None:
                prev = [x for x in self.market.securities[sec].bars if x.session <= session]
                if prev:
                    out[sec] = prev[-1].close
                    stale.append(f"stale_price:{sec}:{prev[-1].session.isoformat()}")
            else:
                out[sec] = b.open if kind == "open" else b.close
        return out, stale

    def apply_actions(self, name: str, upto: date) -> int:
        ledger = self.ledgers[name]
        since = self.cursor[name]
        if upto <= since:
            return 0
        events = []
        for sec in list(ledger.positions):
            s = self.market.securities[sec]
            for dv in s.dividends:
                for kind, exd in (("cash", dv.cash_ex_date), ("stock", dv.stock_ex_date)):
                    if exd is not None and since < exd <= upto:
                        events.append((exd, kind, sec, dv))
            if s.delisting_date and since < s.delisting_date <= upto:
                events.append((s.delisting_date, "delisting", sec, None))
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
                                                                  stock_ratio=dv.stock_per_share / self.cfg.par_value))
                elif kind == "delisting":
                    ledger.apply_corporate_action(CorporateAction(f"{sec}:delisting:{exd}", sec, "delisting", at, terminal_price=None))
                else:
                    continue
                n += 1
            except LedgerError as exc:
                self.weeks[-1].setdefault("action_errors", []).append(f"{name}:{sec}:{kind}:{exd}:{exc}")
        self.cursor[name] = upto
        return n

    # -- paquete y candidatos ------------------------------------------------------------------------
    def build_week_packet(self, plan: WeekPlan) -> tuple[Packet, object, list[Candidate]]:
        cutoff = plan.cutoff_at
        docs = []
        for sec_id, s in self.market.securities.items():
            known = [b for b in s.bars if b.available_at <= cutoff]
            if not known:
                continue
            docs.append(Document(
                doc_id=f"{s.symbol}:bars:{plan.week_id}", kind="price_bar_series", source_id="finmind", security_ids=(sec_id,),
                available_at=known[-1].available_at, availability_quality=AvailabilityQuality.CONSERVATIVE_INFERENCE,
                capture_id=s.price_capture.capture_id, source_sha256=s.price_capture.sha256, derivation="finmind_price_bars_v1",
                payload={"history_sessions": len(known), "last_session": known[-1].session.isoformat(),
                         "sessions": [[b.session.isoformat(), str(b.open), str(b.close), b.volume_shares, str(b.value_twd)] for b in known[-130:]]},
            ))
        packet = build_packet(packet_id=f"pkt-{self.cfg.label}-{plan.week_id}", cutoff_at=cutoff, documents=docs, mode="historical",
                              evidence_class=EVIDENCE, calendar=self.market.calendar)
        rec = self.store.put(source_id="packet", dataset=f"{self.cfg.label}/{plan.week_id}", payload=packet_to_json(packet),
                             url="local://backtest", content_type="application/json",
                             extra={"packet_hash": packet.packet_hash(), "evidence_class": EVIDENCE})
        last_session = self.market.calendar.prev_session(before=cutoff.date())
        candidates: list[Candidate] = []
        for doc in packet.admitted:
            sec_id = doc.security_ids[0]
            s = self.market.securities[sec_id]
            sessions = list(doc.payload["sessions"])
            values = [D(x[4]) for x in sessions[-20:]]
            try:
                sv = self.market.master.resolve_symbol(s.symbol, as_of=last_session)
            except UnknownSymbol:
                candidates.append(Candidate(sec_id, s.symbol, doc.doc_id, sessions, False, False, ("not_in_catalog_as_of_last_session",)))
                continue
            median_value = statistics.median(values) if values else D(0)
            status_ok = doc.payload["last_session"] == last_session.isoformat()
            cov = classify_coverage(sv, price_history_sessions=int(doc.payload["history_sessions"]),
                                    min_history_sessions=self.cfg.min_history_sessions,
                                    trading_status="normal" if status_ok else "no_bar_on_last_session",
                                    liquidity_ok=median_value >= D(self.cfg.liquidity_multiple * self.cfg.notional))
            candidates.append(Candidate(sv.security_id, s.symbol, doc.doc_id, sessions, cov.numerically_scorable, cov.simulation_eligible, cov.reasons))
        return packet, rec, candidates

    def make_forecast(self, f: Forecaster, plan: WeekPlan, packet: Packet, selections: list[Selection], meta: dict, candidates) -> dict:
        eligible = [c for c in candidates if c.eligible]
        scorable = [c for c in candidates if c.scorable]
        obj = {
            "schema_version": "2.0", "forecast_id": f"{f.name}-{plan.week_id}", "experiment_id": f.name, "protocol_version": "2.0-draft-backtest",
            "packet_id": packet.packet_id, "cutoff_at": plan.cutoff_at.isoformat(), "issued_at": (plan.cutoff_at + timedelta(minutes=5)).isoformat(),
            "deadline_at": plan.deadline_at.isoformat(), "timezone": "Asia/Taipei", "evidence_class": EVIDENCE,
            "model": {"requested_id": f.model_id, "returned_id": f.model_id, "revision_id": None,
                      "prompt_or_feature_version": f.version, "training_manifest_id": meta.get("training_manifest_id")},
            "coverage": {"catalog_count": len(self.market.securities), "scored_count": len(scorable), "deep_review_count": 0,
                         "eligible_count": len(eligible), "missing_critical_sources": []},
            "status": "selected" if selections else "abstained",
            "ranking": [{"security_id": s.security_id, "ticker_as_of": self.market.securities[s.security_id].symbol, "market": self.market.securities[s.security_id].market,
                         "rank": i + 1, "score": s.score, "score_definition": f"{f.model_id} sobre barras nominales del paquete",
                         "document_ids": s.doc_ids, "feature_ids": s.feature_ids, "impact_hypothesis": None, "counterargument": None,
                         "calibrated_probability": None, "calibration_model_id": None} for i, s in enumerate(selections)],
            "limitations": ["universo del censo vigente (sesgo de supervivencia)", "disponibilidad de barras por política de 24 h, no verificada",
                            "costes ilustrativos; deslizamiento central no congelado", "regla de liquidez provisional, no del protocolo"],
        }
        if not selections:
            obj["status_reason"] = meta.get("status_reason", "no_eligible_securities")
        return obj

    # -- una semana ------------------------------------------------------------------------------------
    def run_week(self, sunday: date) -> None:
        cfg = self.cfg
        cutoff = taipei(sunday, time(18, 0))
        plan = plan_week(cutoff, self.market.calendar)
        record: dict = {"week_id": plan.week_id, "cutoff_at": cutoff.isoformat(), "status": plan.status, "forecasters": {}}
        self.weeks.append(record)
        if not plan.is_valid:
            week_end = plan.target_monday + timedelta(days=6)
            last_close = self.market.calendar.prev_session(before=week_end + timedelta(days=1))
            for name, lg in self.ledgers.items():
                self.apply_actions(name, week_end)
                lg.advance_to(taipei(week_end, time(23, 59)))
                prices, stale = self.marks(last_close, lg, "close")
                try:
                    v = lg.valuation(prices=prices, at=taipei(week_end, time(23, 59)))
                    record["forecasters"][name] = {"equity_end": float(v.total), "flags": list(v.flags)[:6] + stale}
                    self.prev_equity[name] = v.total
                except MissingPrice as exc:
                    record["forecasters"][name] = {"equity_end": None, "flags": [f"missing_price:{exc}"] + stale}
            record["note"] = "invalid:no_sessions (registrado, sin operaciones; eventos procesados)"
            return
        packet, pkt_rec, candidates = self.build_week_packet(plan)
        view = PredictorView(packet)
        entry_s, exit_s = plan.entry_at.date(), plan.exit_at.date()
        pending = exit_s > self.last_data_day
        record.update(eligible=sum(1 for c in candidates if c.eligible), scored=sum(1 for c in candidates if c.scorable),
                      coverage_reasons=dict(collections.Counter(r.split(":")[0] for c in candidates for r in c.reasons)),
                      pending_outcome=pending)
        picks: dict[str, list[str]] = {}
        for name, f in self.forecasters.items():
            selections, meta = f.forecast(view, plan, candidates, slots=cfg.slots)
            obj = self.make_forecast(f, plan, packet, selections, meta, candidates)
            problems = validate_prediction(obj, packet, calendar=self.market.calendar, experiment_ids=list(self.forecasters))
            if problems:
                obj["status"], obj["ranking"], obj["status_reason"] = "invalid", [], "; ".join(problems[:3])
            self.store.put(source_id="forecast", dataset=f"{cfg.label}/{name}/{plan.week_id}",
                           payload=canonical_bytes({"forecast": obj, "packet_hash": packet.packet_hash()}), url="local://backtest",
                           content_type="application/json", extra={"packet_hash": packet.packet_hash(), "packet_capture": pkt_rec.capture_id})
            picks[name] = [s.security_id for s in selections] if obj["status"] == "selected" else []
            record["forecasters"][name] = {"picks": [{"security_id": p, "symbol": self.market.securities[p].symbol,
                                                      "name": self.market.securities[p].name} for p in picks[name]],
                                           "forecast_status": obj["status"], "status_reason": obj.get("status_reason"),
                                           "training_manifest_id": meta.get("training_manifest_id"), "validation_problems": problems}
        if pending:
            record["note"] = f"pending_outcome: salida prevista {exit_s.isoformat()} posterior al último dato {self.last_data_day.isoformat()}"
            return
        open_prices = {sec: m[entry_s].open for sec, m in self.market.by_session.items() if entry_s in m}
        close_prices = {sec: m[exit_s].close for sec, m in self.market.by_session.items() if exit_s in m}
        intervals: dict[str, IntervalReturn] = {}
        for name, lg in self.ledgers.items():
            self.apply_actions(name, entry_s)
            lg.advance_to(plan.entry_at)
            open_marks, stale0 = self.marks(entry_s, lg, "open")
            try:
                equity_start = lg.valuation(prices=open_marks, at=plan.entry_at).total
            except MissingPrice as exc:
                equity_start = None
                stale0.append(f"missing_open_price:{exc}")
            notional = (lg.cash / cfg.slots).to_integral_value(rounding="ROUND_DOWN") if cfg.sizing == "proportional" else D(cfg.notional)
            slots = enter_basket(lg, picks=picks[name], slots=cfg.slots, notional_per_slot=notional, open_prices=open_prices,
                                 at=plan.entry_at, week_id=plan.week_id)
            self.open_slots[name].append((plan.week_id, slots))
            open_marks_after, _ = self.marks(entry_s, lg, "open")
            try:
                positions_value_open = lg.valuation(prices=open_marks_after, at=plan.entry_at).positions_value
            except MissingPrice:
                positions_value_open = None
            exposure = (positions_value_open / equity_start) if (equity_start and positions_value_open is not None) else D(0)
            self.apply_actions(name, exit_s)
            for wid, ss in self.open_slots[name]:
                exit_basket(lg, ss, close_prices=close_prices, at=plan.exit_at, week_id=wid)
            self.open_slots[name] = [(wid, ss) for wid, ss in self.open_slots[name]
                                     if any(s.status == "exit_blocked" or (s.status == "exited" and not s.liquidated) for s in ss)]
            close_marks, stale1 = self.marks(exit_s, lg, "close")
            try:
                val = lg.valuation(prices=close_marks, at=plan.exit_at)
                equity_end, flags = val.total, list(val.flags) + stale0 + stale1
            except MissingPrice as exc:
                equity_end, flags = None, [f"missing_price:{exc}"] + stale0 + stale1
            measurable = (equity_start is not None and equity_end is not None and equity_start > 0
                          and positions_value_open is not None and not stale0 and not stale1)
            rep = basket_report(plan.week_id, slots, equity_start=equity_start if measurable else self.prev_equity[name],
                                equity_end=equity_end if measurable else self.prev_equity[name])
            interval_return = (equity_end / equity_start - 1) if measurable else None
            chain_return = (equity_end / self.prev_equity[name] - 1) if equity_end is not None and self.prev_equity[name] else None
            invested = sum((s.entry.gross for s in slots if s.entry is not None), D(0))
            costs_twd = _week_costs(slots)
            pick_returns = {s.security_id: (float(s.gross_pick_return) if s.gross_pick_return is not None else None) for s in slots if s.security_id}
            fr = record["forecasters"][name]
            for p in fr["picks"]:
                p["gross_return"] = pick_returns.get(p["security_id"])
            fr.update({"notional_per_slot": float(notional), "filled": rep.filled_slots, "failed": rep.failed_slots,
                       "exit_blocked": rep.exit_blocked_slots, "fail_reasons": [s.reason for s in slots if s.status == "entry_failed"],
                       "mean_gross_pick_return": float(rep.mean_gross_pick_return) if rep.mean_gross_pick_return is not None else None,
                       "portfolio_net_return_open_close": float(interval_return) if interval_return is not None else None,
                       "portfolio_net_return_week_over_week": float(chain_return) if chain_return is not None else None,
                       "exposure_at_open": float(exposure), "costs_twd": float(costs_twd),
                       "costs_over_invested": float(costs_twd / invested) if invested else None,
                       "equity_open": float(equity_start) if equity_start is not None else None,
                       "equity_end": float(equity_end) if equity_end is not None else None, "flags": flags[:6],
                       "stale_prices": stale0 + stale1, "baskets_in_follow_up": len(self.open_slots[name])})
            if measurable and rep.filled_slots > 0:
                intervals[name] = IntervalReturn(label=name, start_at=plan.entry_at, end_at=plan.exit_at, start_price_kind="open",
                                                 end_price_kind="close", value=interval_return.quantize(D("0.0000001")),
                                                 exposure=exposure.quantize(D("0.0001")), week_id=plan.week_id)
            if equity_end is not None:
                self.prev_equity[name] = equity_end
        eligible_ids = [c.security_id for c in candidates if c.eligible]
        ew = [float(self.market.by_session[s][exit_s].close / self.market.by_session[s][entry_s].open - 1) for s in eligible_ids
              if entry_s in self.market.by_session[s] and exit_s in self.market.by_session[s]]
        record["universe_ew_gross_open_close"] = statistics.fmean(ew) if ew else None
        closure = entry_s not in self.market.traded_days or exit_s not in self.market.traded_days
        if closure:
            closed = entry_s if entry_s not in self.market.traded_days else exit_s
            record["note"] = f"extraordinary_closure_unhandled:{closed.isoformat()}"
        base = cfg.baseline
        record["paired"] = {}
        for name in self.forecasters:
            if name == base:
                continue
            entry = {"paired": False, "excess_net_vs_baseline": None, "unpaired_reason": None}
            if closure:
                entry["unpaired_reason"] = "extraordinary_closure_unhandled"
            elif record["forecasters"][name]["stale_prices"] or record["forecasters"][base]["stale_prices"]:
                entry["unpaired_reason"] = "stale_price_in_interval"
            elif name in intervals and base in intervals:
                try:
                    entry["excess_net_vs_baseline"] = float(paired_excess(intervals[name], intervals[base], exposure_tolerance=cfg.exposure_tolerance))
                    entry["paired"] = True
                except IntervalMismatch as exc:
                    entry["unpaired_reason"] = f"interval_mismatch:{exc}"
            else:
                entry["unpaired_reason"] = "missing_interval:" + ",".join(n for n in (name, base) if n not in intervals)
            record["paired"][name] = entry

    # -- todo el periodo -------------------------------------------------------------------------------
    def run(self) -> dict:
        cfg = self.cfg
        for sunday in _sundays(cfg.start, cfg.end):
            self.run_week(sunday)
        end_at = taipei(cfg.end, time(23, 59))
        last_close = self.market.calendar.prev_session(before=min(cfg.end, self.last_data_day) + timedelta(days=1))
        final: dict[str, dict] = {}
        for name, lg in self.ledgers.items():
            self.apply_actions(name, cfg.end)
            lg.advance_to(end_at)
            prices, stale = self.marks(last_close, lg, "close")
            try:
                v = lg.valuation(prices=prices, at=end_at)
                final[name] = {"equity": float(v.total), "cash": float(v.cash), "receivables": float(v.receivables),
                               "positions_value": float(v.positions_value), "unresolved": list(v.unresolved), "flags": list(v.flags) + stale,
                               "valued_at": end_at.isoformat(), "prices_session": last_close.isoformat(),
                               "events_processed_through": self.cursor[name].isoformat()}
            except MissingPrice as exc:
                final[name] = {"equity": None, "error": str(exc), "flags": stale, "valued_at": end_at.isoformat()}
        operated = [w for w in self.weeks if w["status"] == "valid" and not w.get("pending_outcome")]
        summary: dict = {
            "label": cfg.label, "period": [cfg.start.isoformat(), cfg.end.isoformat()], "manifest": self.market.source_manifest,
            "universe_size": len(self.market.securities), "weeks_total": len(self.weeks), "weeks_operated": len(operated),
            "weeks_invalid_no_sessions": sum(1 for w in self.weeks if w["status"] == "invalid:no_sessions"),
            "weeks_pending_outcome": [w["week_id"] for w in self.weeks if w.get("pending_outcome")],
            "weeks_extraordinary_closure_unhandled": [w["week_id"] for w in self.weeks if str(w.get("note", "")).startswith("extraordinary")],
            "bars_without_regular_price_dropped": self.market.dropped_no_regular_price,
            "universe_ew": {"mean_weekly_gross_open_close": self._mean(operated, lambda w: w["universe_ew_gross_open_close"])},
            "assumptions": {**{k: (str(v) if isinstance(v, D) else (v.isoformat() if isinstance(v, date) else v)) for k, v in asdict(cfg).items()},
                            "costs": asdict(self.costs), "price_availability_lag_hours": 24,
                            "liquidity_rule": f"mediana(importe 20 sesiones) >= {cfg.liquidity_multiple} x nocional",
                            "planning_calendar": f"{self.market.calendar.source_id}@{self.market.calendar.version}"},
            "forecasters": {},
        }
        for name, f in self.forecasters.items():
            fw = [w["forecasters"][name] for w in operated]
            entry = {
                "model_id": f.model_id, "mean_weekly_net_return_open_close": self._mean(fw, lambda r: r.get("portfolio_net_return_open_close")),
                "mean_weekly_net_return_week_over_week": self._mean(fw, lambda r: r.get("portfolio_net_return_week_over_week")),
                "mean_weekly_gross_pick_return": self._mean(fw, lambda r: r.get("mean_gross_pick_return")),
                "mean_costs_over_invested": self._mean(fw, lambda r: r.get("costs_over_invested")),
                "weeks_positive": sum(1 for r in fw if (r.get("portfolio_net_return_open_close") or 0) > 0),
                "weeks_selected": sum(1 for r in fw if r.get("forecast_status") == "selected"),
                "entry_failures": sum(r.get("failed", 0) for r in fw), "exit_blocked": sum(r.get("exit_blocked", 0) for r in fw),
                "final_equity": final[name]["equity"],
                "total_net_return": (final[name]["equity"] / float(self.initial) - 1) if final[name]["equity"] is not None else None,
                "final_valuation": final[name],
                "open_positions_at_end": [{"security_id": sec, "status": pos.status, "quantity": str(pos.total_quantity),
                                           "unresolved_fraction": str(pos.unresolved_fraction)} for sec, pos in sorted(self.ledgers[name].positions.items())],
                "baskets_in_follow_up_at_end": [wid for wid, _ in self.open_slots[name]],
            }
            if hasattr(f, "history"):
                entry["training_history"] = list(getattr(f, "history"))
            if name != cfg.baseline:
                obs = [WeeklyObservation(w["week_id"], f"{name}-{w['week_id']}", EVIDENCE, None, bool(w["paired"][name]["paired"]),
                                         w["paired"][name]["excess_net_vs_baseline"]) for w in self.weeks if w["status"] == "valid" and not w.get("pending_outcome")]
                try:
                    boot = block_bootstrap_mean(obs, block_length=cfg.block_length, n_boot=cfg.n_boot, seed=cfg.seed)
                    entry["paired_excess_vs_baseline"] = {"baseline": cfg.baseline, "mean": boot.mean, "ci95": [boot.ci_low, boot.ci_high],
                                                          "n_used": boot.n_used, "n_excluded": boot.n_invalid_excluded,
                                                          "block_length": boot.block_length, "n_segments": boot.n_segments,
                                                          "resample_mean": boot.resample_mean}
                except Exception as exc:
                    entry["paired_excess_vs_baseline"] = {"baseline": cfg.baseline, "error": str(exc)}
                entry["unpaired_reasons"] = dict(collections.Counter((w["paired"][name]["unpaired_reason"] or "").split(":")[0]
                                                                     for w in operated if not w["paired"][name]["paired"]))
            summary["forecasters"][name] = entry
        return {"summary": summary, "weeks": self.weeks}

    @staticmethod
    def _mean(rows, getter) -> Optional[float]:
        xs = [getter(r) for r in rows]
        xs = [x for x in xs if x is not None]
        return statistics.fmean(xs) if xs else None


def markdown_report(result: dict, *, title: str) -> str:
    s = result["summary"]
    lines = [f"# {title}", "",
             f"Periodo {s['period'][0]} → {s['period'][1]} · universo {s['universe_size']} valores ({s['manifest']}) · "
             f"{s['weeks_operated']} semanas operadas, {s['weeks_invalid_no_sessions']} sin sesiones, "
             f"{len(s['weeks_pending_outcome'])} pendientes de desenlace.", "",
             "Costes ilustrativos (no contratados); universo del censo vigente; disponibilidad de barras por política de 24 h. "
             "Nada de esto es una estimación de rendimiento futuro.", "",
             "| Pronosticador | Media semanal neta apertura→cierre | Media bruta de las selecciones | Costes/semana sobre invertido | Semanas > 0 | Patrimonio final | Exceso neto vs " + s["assumptions"]["baseline"] + " (IC 95 %) |",
             "|---|---|---|---|---|---|---|"]
    for name, e in s["forecasters"].items():
        pe = e.get("paired_excess_vs_baseline")
        pe_txt = "—" if not pe or "error" in (pe or {}) else f"{pe['mean']*100:+.2f} % [{pe['ci_low' if 'ci_low' in pe else 'ci95'][0]*100:+.2f} %, {pe['ci95'][1]*100:+.2f} %] n={pe['n_used']}" if pe and "ci95" in pe else "—"
        fmt = lambda x: "—" if x is None else f"{x*100:+.2f} %"
        lines.append(f"| {name} (`{e['model_id']}`) | {fmt(e['mean_weekly_net_return_open_close'])} | {fmt(e['mean_weekly_gross_pick_return'])} | "
                     f"{fmt(e['mean_costs_over_invested'])} | {e['weeks_positive']}/{s['weeks_operated']} | "
                     f"{e['final_equity']:,.0f} TWD | {pe_txt} |")
    ew = s["universe_ew"]["mean_weekly_gross_open_close"]
    lines += ["", f"Referencia equiponderada del universo elegible (bruta, apertura→cierre): {ew*100:+.2f} % semanal." if ew is not None else "", ""]
    lines += ["## Selecciones semana a semana", ""]
    names = list(s["forecasters"])
    lines.append("| Semana | " + " | ".join(names) + " |")
    lines.append("|---|" + "---|" * len(names))
    for w in result["weeks"]:
        if w["status"] != "valid":
            lines.append(f"| {w['week_id']} | " + " | ".join([w.get("note", w["status"])] + [""] * (len(names) - 1)) + " |")
            continue
        cells = []
        for n in names:
            fr = w["forecasters"].get(n, {})
            picks = fr.get("picks", [])
            if not picks:
                cells.append(f"({fr.get('forecast_status', '—')}: {fr.get('status_reason') or ''})".strip())
                continue
            txt = ", ".join(f"{p['symbol']} {p['name']}" + (f" {p['gross_return']*100:+.1f} %" if p.get("gross_return") is not None else "") for p in picks)
            net = fr.get("portfolio_net_return_open_close")
            cells.append(txt + (f" → neto {net*100:+.2f} %" if net is not None else " → pendiente"))
        lines.append(f"| {w['week_id']} | " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n"
