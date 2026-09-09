from datetime import date, time, timedelta
from decimal import Decimal as D

import pytest

from twlab.evaluation import (
    IntervalMismatch, IntervalReturn, ObservationError, WeeklyObservation, block_bootstrap_mean, paired_excess,
)
from twlab.ledger import (
    CorporateAction, CostModel, DuplicateCorporateAction, Fill, LedgerError, MissingPrice, OutOfOrderEvent, PaperLedger,
    Rejection, q_twd,
)
from twlab.simulation import basket_report, enter_basket, exit_basket
from twlab.timeutil import taipei

COSTS = CostModel(commission_per_side=D("0.001425"), sell_tax=D("0.003"), slippage_bps_per_side=0)
FREE = CostModel(commission_per_side=D(0), sell_tax=D(0))
MON = taipei(date(2026, 9, 7), time(9, 0))
TUE = MON + timedelta(days=1)
FRI = taipei(date(2026, 9, 11), time(13, 30))
P90 = {k: D("90") for k in "ABCDEFGHIJ"}


def ledger(cash="1000000", costs=COSTS):
    return PaperLedger(ledger_id="t", initial_cash=D(cash), cost_model=costs)


# ---- costes y redondeo ---------------------------------------------------
def test_round_trip_friction_rate_0585_percent_with_declared_rounding():
    """0,1425 % + 0,1425 % + 0,3 % = 0,585 % (585 TWD sobre 100.000 antes de redondear a TWD entero)."""
    lg = ledger()
    lg.buy(security_id="A", price=D("100"), shares=1000, at=MON, event_id="b")
    lg.sell(security_id="A", price=D("100"), shares=1000, at=FRI, event_id="s")
    assert lg.initial_cash - lg.cash == D("584")          # floor por componente: 142 + 142 + 300
    lg2 = ledger(costs=CostModel(commission_per_side=D("0.001425"), rounding="half_up"))
    lg2.buy(security_id="A", price=D("100"), shares=1000, at=MON, event_id="b")
    lg2.sell(security_id="A", price=D("100"), shares=1000, at=FRI, event_id="s")
    assert lg2.initial_cash - lg2.cash == D("586")        # half_up por componente: 143 + 143 + 300


def test_r01_13_tax_and_commission_use_executed_consideration():
    lg = ledger(costs=CostModel(D("0.001425"), slippage_bps_per_side=25))
    lg.buy(security_id="A", price=D(100), shares=1000, at=MON, event_id="b")
    f = lg.sell(security_id="A", price=D(100), shares=1000, at=FRI, event_id="s")
    assert f.executed == f.gross - f.slippage_cost == D("99750")
    assert f.tax == q_twd((f.gross - f.slippage_cost) * D("0.003")) == D("299")
    assert f.commission == D("142")


def test_r01_14_fill_cash_reconciles_with_components():
    lg = ledger()
    b = lg.buy(security_id="A", price=D(100), shares=1000, at=MON, event_id="b")
    assert b.cash_delta == -(b.gross + b.slippage_cost + b.commission)
    f = lg.sell(security_id="A", price=D(100), shares=1000, at=FRI, event_id="s")
    assert f.cash_delta == f.gross - f.slippage_cost - f.commission - f.tax == D("99558")
    assert lg.cash == lg.initial_cash + b.cash_delta + f.cash_delta


def test_ledger_refuses_adjusted_series():
    with pytest.raises(ValueError):
        PaperLedger(ledger_id="x", initial_cash=D(1), cost_model=COSTS, price_series_kind="adjusted")


def test_r01_16_negative_or_invalid_inputs_are_rejected_before_state_changes():
    lg = ledger()
    with pytest.raises(LedgerError):
        lg.buy(security_id="A", price=D(-100), shares=1000, at=MON, event_id="b")
    with pytest.raises(LedgerError):
        lg.buy(security_id="A", price=D("NaN"), shares=1000, at=MON, event_id="b")
    with pytest.raises(LedgerError):
        lg.buy(security_id="A", price=D(100), shares=0, at=MON, event_id="b")
    assert lg.cash == lg.initial_cash and lg.events == []
    with pytest.raises(LedgerError):
        CostModel(commission_per_side=D("-0.1"))


# ---- tiempo y derechos ---------------------------------------------------
def test_r01_12_events_are_chronological_and_rights_belong_to_holder_at_effective_date():
    lg = ledger()
    lg.buy(security_id="A", price=D(100), shares=1000, at=MON, event_id="b")
    cash = lg.cash
    with pytest.raises(LedgerError):
        lg.apply_corporate_action(CorporateAction("old-div", "A", "cash_dividend", MON - timedelta(days=1), per_share_cash=D("2.5")))
    assert lg.cash == cash
    with pytest.raises(OutOfOrderEvent):
        lg.sell(security_id="A", price=D(100), shares=1000, at=MON - timedelta(hours=1), event_id="s")


def test_dividend_rights_and_payment_are_separated():
    lg = ledger()
    lg.buy(security_id="A", price=D(100), shares=1000, at=MON, event_id="b")
    pay = taipei(date(2026, 9, 25), time(9, 0))
    lg.apply_corporate_action(CorporateAction("div", "A", "cash_dividend", FRI, per_share_cash=D("2.5"), pay_at=pay))
    v = lg.valuation(prices={"A": D(100)}, at=FRI)
    assert v.receivables == D("2500") and lg.cash == D("1000000") - D("100142") and "receivables_pending" in v.flags
    # el efectivo no financia compras antes de la fecha de pago
    r = lg.buy(security_id="B", price=D(900), shares=1000, at=taipei(date(2026, 9, 14), time(9, 0)), event_id="b2")
    assert isinstance(r, Rejection) and r.reason == "insufficient_cash"
    lg.sell(security_id="A", price=D(100), shares=1000, at=taipei(date(2026, 9, 28), time(9, 0)), event_id="s")
    assert lg.receivables == [] and any(e.kind == "receivable_settled" for e in lg.events)


def test_r02_05_missing_payment_date_never_creates_spendable_cash():
    lg = ledger(costs=FREE)
    lg.buy(security_id="A", price=D(100), shares=1000, at=MON, event_id="b")
    before = lg.available_cash()
    lg.apply_corporate_action(CorporateAction("div", "A", "cash_dividend", FRI, per_share_cash=D("2.5")))
    assert lg.available_cash() == before
    v = lg.valuation(prices={"A": D(100)}, at=FRI + timedelta(days=30))
    assert v.cash == before and v.receivables == D(2500) and "receivables_without_payment_date" in v.flags
    lg.set_payment_date("div", pay_at=FRI + timedelta(days=14), at=FRI + timedelta(days=3))
    lg.advance_to(FRI + timedelta(days=14))
    assert lg.available_cash() == before + D(2500)
    with pytest.raises(LedgerError):
        lg.set_payment_date("div", pay_at=FRI, at=FRI + timedelta(days=15))      # ya no hay cobro sin fecha


def test_r03_08_payment_date_knowledge_is_dated_when_learned():
    lg = ledger(costs=FREE)
    lg.buy(security_id="A", price=D(100), shares=1000, at=MON, event_id="b")
    lg.apply_corporate_action(CorporateAction("div", "A", "cash_dividend", MON, per_share_cash=D(1)))
    lg.mark_suspended("A", at=FRI)
    lg.set_payment_date("div", pay_at=FRI + timedelta(days=3), at=FRI + timedelta(hours=1))
    ats = [e.at for e in lg.events]
    assert ats == sorted(ats)
    assert lg.events[-1].kind == "payment_date_set" and lg.events[-1].at == FRI + timedelta(hours=1)
    lg2 = ledger(costs=FREE)
    lg2.buy(security_id="A", price=D(100), shares=1000, at=MON, event_id="b")
    lg2.apply_corporate_action(CorporateAction("div", "A", "cash_dividend", MON, per_share_cash=D(1)))
    with pytest.raises(OutOfOrderEvent):
        lg2.set_payment_date("div", pay_at=FRI, at=MON - timedelta(hours=1))   # no se puede fechar el conocimiento en el pasado


def test_r03_15_dividend_payable_at_effective_instant_is_paid_immediately():
    lg = ledger(costs=FREE)
    lg.buy(security_id="A", price=D(100), shares=1000, at=MON, event_id="b")
    lg.apply_corporate_action(CorporateAction("div", "A", "cash_dividend", FRI, per_share_cash=D(1), pay_at=FRI))
    assert lg.available_cash() == D(901000) and lg.receivables == []
    assert lg.valuation(prices={"A": D(100)}, at=FRI).cash == D(901000)


def test_r03_09_valuation_before_ledger_clock_is_refused():
    lg = ledger(costs=FREE)
    lg.buy(security_id="A", price=D(100), shares=1000, at=MON, event_id="b")
    lg.apply_corporate_action(CorporateAction("div", "A", "cash_dividend", MON, per_share_cash=D(1), pay_at=FRI))
    lg.advance_to(FRI)
    with pytest.raises(LedgerError):
        lg.valuation(prices={"A": D(100)}, at=TUE)
    assert lg.valuation(prices={"A": D(100)}, at=FRI).cash == D(901000)


def test_r02_16_receivables_settle_in_payment_order():
    lg = ledger(costs=FREE)
    lg.buy(security_id="A", price=D(100), shares=1000, at=MON, event_id="b")
    lg.apply_corporate_action(CorporateAction("d1", "A", "cash_dividend", MON, per_share_cash=D(1), pay_at=MON + timedelta(days=4)))
    lg.apply_corporate_action(CorporateAction("d2", "A", "cash_dividend", TUE, per_share_cash=D(1), pay_at=MON + timedelta(days=3)))
    lg.mark_suspended("A", at=MON + timedelta(days=7))
    ats = [e.at for e in lg.events]
    assert ats == sorted(ats)
    settled = [e for e in lg.events if e.kind == "receivable_settled"]
    assert [e.event_id for e in settled] == ["d2", "d1"]


def test_r02_17_due_receivable_is_reflected_and_advance_to_pays_without_trading():
    lg = ledger(costs=FREE)
    lg.buy(security_id="A", price=D(100), shares=1000, at=MON, event_id="b")
    lg.apply_corporate_action(CorporateAction("div", "A", "cash_dividend", MON, per_share_cash=D(1), pay_at=FRI))
    v = lg.valuation(prices={"A": D(100)}, at=FRI)
    assert v.receivables == 0 and v.cash == D(901000)
    assert lg.cash == D(900000)                       # la valoración no abona: es pura
    lg.advance_to(FRI)                                # semana sin negociación: los pagos se procesan igualmente
    assert lg.cash == D(901000) and lg.receivables == []


def test_r02_15_valuation_is_pure_and_cannot_rewrite_past_prices():
    lg = ledger(costs=FREE)
    lg.buy(security_id="A", price=D(100), shares=1000, at=MON, event_id="b")
    lg.valuation(prices={"A": D(999)}, at=FRI)
    assert lg.positions["A"].last_price == D(100) and lg.clock == MON
    lg.mark_suspended("A", at=TUE)
    assert lg.valuation(prices={}, at=TUE).positions_value == D(100000)


# ---- SIM ----------------------------------------------------------------
def test_sim01_split_without_economic_move_has_no_fake_loss():
    lg = ledger()
    lg.buy(security_id="A", price=D("100"), shares=1000, at=MON, event_id="b")
    before = lg.valuation(prices={"A": D("100")}, at=MON).total
    lg.apply_corporate_action(CorporateAction("split-1", "A", "split", MON, split_ratio=D("2")))
    after = lg.valuation(prices={"A": D("50")}, at=FRI).total
    assert lg.positions["A"].shares == 2000
    assert after == before


def test_r02_13_reverse_split_preserves_quantity():
    lg = ledger(costs=FREE)
    lg.buy(security_id="A", price=D(100), shares=1000, at=MON, event_id="b")
    lg.apply_corporate_action(CorporateAction("rs", "A", "split", FRI, split_ratio=D("0.0005")))
    p = lg.positions["A"]
    assert p.shares == 0 and p.unresolved_fraction == D("0.5") and p.total_quantity == D("0.5")
    assert p.last_price == D(200000)
    v = lg.valuation(prices={}, at=FRI)
    assert v.positions_value == D(100000) and "A:fractional_shares_unresolved" in v.flags


def test_stock_dividend_fraction_is_flagged_not_dropped():
    lg = ledger()
    lg.buy(security_id="A", price=D("100"), shares=1000, at=MON, event_id="b")
    lg.apply_corporate_action(CorporateAction("sd", "A", "stock_dividend", FRI, stock_ratio=D("0.1005")))
    assert lg.positions["A"].shares == 1100 and lg.positions["A"].unresolved_fraction == D("0.5")
    assert "A:fractional_shares_unresolved" in lg.valuation(prices={"A": D("90")}, at=FRI).flags


def test_r02_14_fraction_remains_pending_after_selling_whole_shares():
    lg = ledger(costs=FREE)
    lg.buy(security_id="A", price=D(100), shares=1000, at=MON, event_id="b")
    lg.apply_corporate_action(CorporateAction("sd", "A", "stock_dividend", FRI, stock_ratio=D("0.0005")))
    lg.sell(security_id="A", price=D(100), shares=1000, at=FRI, event_id="s")
    assert "A" in lg.positions and lg.positions["A"].shares == 0
    v = lg.valuation(prices={}, at=FRI)
    assert v.flags and "A:fractional_shares_unresolved" in v.flags and v.positions_value == D(50)


def test_sim02_corporate_action_exactly_once_and_r01_11_failed_action_keeps_id():
    lg = ledger()
    lg.buy(security_id="A", price=D("100"), shares=1000, at=MON, event_id="b")   # coste 100.142 (floor)
    with pytest.raises(LedgerError):
        lg.apply_corporate_action(CorporateAction("div-2026-1", "A", "cash_dividend", FRI))   # sin importe
    div = CorporateAction("div-2026-1", "A", "cash_dividend", FRI, per_share_cash=D("2.5"), pay_at=FRI + timedelta(days=10))
    lg.apply_corporate_action(div)
    with pytest.raises(DuplicateCorporateAction):
        lg.apply_corporate_action(div)
    assert lg.cash == D("1000000") - D("100142")
    lg.advance_to(FRI + timedelta(days=10))
    assert lg.cash == D("1000000") - D("100142") + D("2500")


def test_sim03_sale_during_suspension_keeps_position_and_r01_23_flag_survives_supplied_price():
    lg = ledger()
    lg.buy(security_id="A", price=D("100"), shares=1000, at=MON, event_id="b")
    lg.mark_suspended("A", at=FRI, detail="trading halt")
    res = lg.sell(security_id="A", price=D("100"), shares=1000, at=FRI, event_id="s")
    assert isinstance(res, Rejection) and res.reason == "exit_blocked_suspended"
    assert "A" in lg.positions
    v = lg.valuation(prices={}, at=FRI)
    assert "A:suspended_stale_price" in v.flags and v.positions_value == D("100000")
    v2 = lg.valuation(prices={"A": D("100")}, at=FRI)
    assert "A:suspended" in v2.flags


def test_sim05_stuck_cash_is_not_reused():
    lg = ledger("500000")
    s1 = enter_basket(lg, picks=["A", "B", "C", "D", "E"], slots=5, notional_per_slot=D("100000"),
                      open_prices=P90, at=MON, week_id="w1")
    assert all(s.status == "filled" for s in s1)
    lg.mark_suspended("E", at=FRI)
    exit_basket(lg, s1, close_prices=P90, at=FRI, week_id="w1")
    assert lg.positions["E"].status == "suspended"
    mon2 = taipei(date(2026, 9, 14), time(9, 0))
    s2 = enter_basket(lg, picks=["F", "G", "H", "I", "J"], slots=5, notional_per_slot=D("100000"),
                      open_prices=P90, at=mon2, week_id="w2")
    filled = [s for s in s2 if s.status == "filled"]
    failed = [s for s in s2 if s.status == "entry_failed"]
    assert len(filled) == 4 and len(failed) == 1            # el dinero atrapado en E no financia el 5.º puesto
    assert failed[0].reason == "insufficient_cash"
    assert lg.cash < D("90128")


def test_sim07_higher_costs_never_improve_net_return():
    def run(costs):
        lg = ledger("1000000", costs)
        lg.buy(security_id="A", price=D("100"), shares=1000, at=MON, event_id="b")
        lg.sell(security_id="A", price=D("110"), shares=1000, at=FRI, event_id="s")
        return lg.cash
    cheap = run(COSTS)
    dear = run(CostModel(commission_per_side=D("0.001425"), sell_tax=D("0.003"), slippage_bps_per_side=25))
    assert dear < cheap


def test_sim08_delisting_without_terminal_price_is_flagged_not_deleted():
    lg = ledger()
    lg.buy(security_id="A", price=D("100"), shares=1000, at=MON, event_id="b")
    lg.apply_corporate_action(CorporateAction("delist-A", "A", "delisting", FRI, terminal_price=None))
    v = lg.valuation(prices={}, at=FRI)
    assert v.unresolved == ("A",) and "A" in lg.positions
    with pytest.raises(MissingPrice):
        lg.valuation(prices={}, at=FRI, unresolved_policy="raise")


def test_missing_price_for_open_position_is_an_error_not_zero():
    lg = ledger()
    lg.buy(security_id="A", price=D("100"), shares=1000, at=MON, event_id="b")
    with pytest.raises(MissingPrice):
        lg.valuation(prices={}, at=FRI)


def test_sim09_failed_entry_keeps_cash_no_redistribution():
    lg = ledger("500000")
    prices = {k: D("90") for k in "ABDE"}                    # C sin precio de apertura
    slots = enter_basket(lg, picks=["A", "B", "C", "D", "E"], slots=5, notional_per_slot=D("100000"),
                         open_prices=prices, at=MON, week_id="w")
    assert slots[2].status == "entry_failed" and slots[2].reason == "no_open_price"
    filled = [s for s in slots if s.status == "filled"]
    assert len(filled) == 4 and all(s.entry.shares == 1000 for s in filled)
    assert lg.cash == D("500000") - 4 * D("90128")


def test_r01_09_exit_sells_current_position_after_split():
    lg = ledger("100000", FREE)
    slots = enter_basket(lg, picks=["A"], slots=5, notional_per_slot=D("100000"), open_prices={"A": D(100)}, at=MON, week_id="w")
    lg.apply_corporate_action(CorporateAction("split", "A", "split", MON, split_ratio=D(2)))
    exit_basket(lg, slots, close_prices={"A": D(50)}, at=FRI, week_id="w")
    assert not lg.positions and lg.cash == D(100000)
    rep = basket_report("w", slots, equity_start=D(100000), equity_end=lg.valuation(prices={}, at=FRI).total)
    assert rep.mean_gross_pick_return == D(0) and rep.portfolio_net_return == D(0)


def test_r02_04_partial_lot_exit_after_split_is_not_a_loss():
    lg = ledger("100000", FREE)
    s = enter_basket(lg, picks=["A"], slots=1, notional_per_slot=D(100000), open_prices={"A": D(100)}, at=MON, week_id="w")
    lg.apply_corporate_action(CorporateAction("split", "A", "split", MON, split_ratio=D("1.1")))
    exit_basket(lg, s, close_prices={"A": D(100) / D("1.1")}, at=FRI, week_id="w")
    assert s[0].status == "exited" and s[0].exit_residual_quantity == D(100)
    assert s[0].gross_pick_return == D(0)
    assert lg.positions["A"].shares == 100                   # el residuo sigue en el libro, anotado
    assert any(n.startswith("residual_quantity_in_ledger") for n in s[0].notes)


def test_r03_10_residual_from_a_previous_week_is_not_new_profit():
    lg = ledger("300000", FREE)
    args = dict(picks=["A"], slots=1, notional_per_slot=D(100000), open_prices={"A": D(100)})
    a = enter_basket(lg, **args, at=MON, week_id="w1")
    lg.apply_corporate_action(CorporateAction("sp", "A", "split", MON, split_ratio=D("1.1")))
    exit_basket(lg, a, close_prices={"A": D(100) / D("1.1")}, at=FRI, week_id="w1")
    assert lg.positions["A"].shares == 100 and a[0].gross_pick_return == D(0)
    b = enter_basket(lg, **args, at=MON + timedelta(days=7), week_id="w2")
    assert any(n.startswith("pre_existing_quantity") for n in b[0].notes)
    exit_basket(lg, b, close_prices={"A": D(100)}, at=FRI + timedelta(days=7), week_id="w2")
    assert b[0].exit_attributed_quantity == D(1000) and b[0].exit_residual_quantity == D(0)
    assert b[0].gross_pick_return == D(0)
    assert lg.positions["A"].owner_quantity("w1:1") == D(100)        # el residuo antiguo sigue siendo de la semana 1


def test_r04_09_blocked_basket_retry_sells_only_its_own_lots():
    lg = ledger("300000", FREE)
    args = dict(picks=["A"], slots=1, notional_per_slot=D(100000), open_prices={"A": D(100)})
    w1 = enter_basket(lg, **args, at=MON, week_id="w1")
    exit_basket(lg, w1, close_prices={}, at=FRI, week_id="w1")                  # bloqueada: sin precio
    w2 = enter_basket(lg, **args, at=MON + timedelta(days=7), week_id="w2")
    exit_basket(lg, w1, close_prices={"A": D(100)}, at=FRI + timedelta(days=7), week_id="w1")
    assert w1[0].status == "exited" and w1[0].gross_pick_return == D(0)
    assert lg.positions["A"].owner_quantity("w2:1") == D(w2[0].entry.shares) == D(1000)


def test_r04_10_residual_follows_the_owner_not_a_proportion():
    lg = ledger("400000", FREE)
    lg.buy(security_id="A", price=D(100), shares=1000, at=MON, event_id="old")     # lote sin cesta
    w = enter_basket(lg, picks=["A"], slots=1, notional_per_slot=D(100000), open_prices={"A": D(100)}, at=MON, week_id="w")
    lg.apply_corporate_action(CorporateAction("sp", "A", "split", MON, split_ratio=D("1.1")))
    exit_basket(lg, w, close_prices={"A": D(100) / D("1.1")}, at=FRI, week_id="w")
    assert lg.positions["A"].total_quantity == D(1200)                            # 1.100 antiguas + 100 residuo
    assert w[0].exit_attributed_quantity == D(1100) and w[0].exit_residual_quantity == D(100)
    assert lg.positions["A"].owner_quantity("w:1") == D(100) and w[0].gross_pick_return == D(0)


def test_r04_11_cash_dividends_belong_to_the_gross_total_pick_return():
    lg = ledger("100000", FREE)
    w = enter_basket(lg, picks=["A"], slots=1, notional_per_slot=D(100000), open_prices={"A": D(100)}, at=MON, week_id="w")
    lg.apply_corporate_action(CorporateAction("div", "A", "cash_dividend", TUE, per_share_cash=D(1), pay_at=FRI))
    exit_basket(lg, w, close_prices={"A": D(99)}, at=FRI, week_id="w")
    assert lg.cash == D(100000)
    assert w[0].dividends_declared == D(1000) and w[0].gross_pick_return == D(0)


def test_r05_05_a_basket_is_entered_once_per_ledger():
    lg = ledger("300000", FREE)
    args = dict(picks=["A"], slots=1, notional_per_slot=D(100000), open_prices={"A": D(100)}, at=MON, week_id="2030-W02")
    first = enter_basket(lg, **args)
    with pytest.raises(ValueError):
        enter_basket(lg, **args)
    exit_basket(lg, first, close_prices={"A": D(100)}, at=FRI, week_id="2030-W02")
    assert first[0].gross_pick_return == D(0) and lg.positions.get("A") is None


def test_r05_06_partial_sales_by_the_owner_count_in_the_pick_return():
    lg = ledger("400000", FREE)
    w = enter_basket(lg, picks=["A"], slots=1, notional_per_slot=D(200000), open_prices={"A": D(100)}, at=MON, week_id="w")
    other = enter_basket(lg, picks=["A"], slots=1, notional_per_slot=D(100000), open_prices={"A": D(100)}, at=MON, week_id="other")
    lg.sell(security_id="A", price=D(110), shares=1000, at=MON, event_id="partial", owner=w[0].owner)
    assert lg.positions["A"].owner_quantity(other[0].owner) == D(1000)
    exit_basket(lg, w, close_prices={"A": D(90)}, at=FRI, week_id="w")
    assert w[0].sale_gross_total == D(200000) and w[0].gross_pick_return == D(0)


def test_r05_07_fractions_of_different_owners_do_not_cancel_out():
    lg = ledger("300000", FREE)
    enter_basket(lg, picks=["A"], slots=1, notional_per_slot=D(100000), open_prices={"A": D(100)}, at=MON, week_id="owner-a")
    enter_basket(lg, picks=["A"], slots=1, notional_per_slot=D(100000), open_prices={"A": D(100)}, at=MON, week_id="owner-b")
    lg.apply_corporate_action(CorporateAction("split", "A", "split", MON, split_ratio=D("0.5005")))
    assert [lot.quantity for lot in lg.positions["A"].lots] == [D("500.5"), D("500.5")]
    assert lg.positions["A"].unresolved_fraction == D("1.0") and lg.positions["A"].shares == 1001
    assert "A:fractional_shares_unresolved" in lg.valuation(prices={"A": D(100) / D("0.5005")}, at=FRI).flags


def test_r05_08_dividend_cash_does_not_depend_on_how_the_purchase_was_split():
    def paid(quantities):
        lg = ledger("300000", FREE)
        for i, n in enumerate(quantities):
            lg.buy(security_id="A", price=D(100), shares=n, at=MON, event_id=f"b{i}", owner="same")
        lg.apply_corporate_action(CorporateAction("div", "A", "cash_dividend", MON, per_share_cash=D("1.2345"), pay_at=FRI))
        lg.advance_to(FRI)
        return lg.cash
    assert paid([1000, 1000]) == paid([2000]) == D("300000") - D("200000") + D("2469")


def test_r06_06_empty_or_failed_basket_still_reserves_its_identity():
    for picks in ([], ["A"]):
        lg = ledger("300000", FREE)
        first = enter_basket(lg, picks=picks, slots=1, notional_per_slot=D(100000), open_prices={}, at=MON, week_id="2030-W02")
        assert first[0].status in ("empty", "entry_failed") and "2030-W02:1" in lg.owners_seen
        with pytest.raises(ValueError):
            enter_basket(lg, picks=["A"], slots=1, notional_per_slot=D(100000), open_prices={"A": D(100)}, at=MON, week_id="2030-W02")


def test_r06_07_fifo_sale_without_owner_attributes_proceeds_to_consumed_lots():
    lg = ledger("400000", FREE)
    w = enter_basket(lg, picks=["A"], slots=1, notional_per_slot=D(200000), open_prices={"A": D(100)}, at=MON, week_id="w")
    other = enter_basket(lg, picks=["A"], slots=1, notional_per_slot=D(100000), open_prices={"A": D(100)}, at=MON, week_id="other")
    lg.sell(security_id="A", price=D(110), shares=1000, at=MON, event_id="fifo")           # sin owner: FIFO global
    assert lg.positions["A"].owner_quantity(other[0].owner) == D(1000)
    assert lg.owner_sale_gross("A", w[0].owner) == D(110000)
    exit_basket(lg, w, close_prices={"A": D(90)}, at=FRI, week_id="w")
    assert w[0].gross_pick_return == D(0)


def test_r06_08_full_liquidation_before_exit_keeps_the_result():
    lg = ledger("300000", FREE)
    w = enter_basket(lg, picks=["A"], slots=1, notional_per_slot=D(100000), open_prices={"A": D(100)}, at=MON, week_id="w")
    lg.sell(security_id="A", price=D(110), shares=1000, at=MON, event_id="full", owner=w[0].owner)
    exit_basket(lg, w, close_prices={"A": D(110)}, at=FRI, week_id="w")
    assert w[0].status == "exited" and w[0].liquidated and w[0].gross_pick_return == D("0.1")


def test_r06_09_residual_turned_round_lot_is_sold_on_retry():
    lg = ledger("400000", FREE)
    w = enter_basket(lg, picks=["A"], slots=1, notional_per_slot=D(100000), open_prices={"A": D(100)}, at=MON, week_id="w")
    other = enter_basket(lg, picks=["A"], slots=1, notional_per_slot=D(100000), open_prices={"A": D(100)}, at=MON, week_id="other")
    lg.apply_corporate_action(CorporateAction("stock", "A", "stock_dividend", MON, stock_ratio=D("0.5")))
    exit_basket(lg, w, close_prices={"A": D(60)}, at=FRI, week_id="w")
    assert w[0].status == "exited" and lg.positions["A"].owner_quantity(w[0].owner) == D(500)
    lg.apply_corporate_action(CorporateAction("split", "A", "split", FRI, split_ratio=D(2)))
    lg.apply_corporate_action(CorporateAction("div", "A", "cash_dividend", FRI, per_share_cash=D(1), pay_at=FRI))
    exit_basket(lg, w, close_prices={"A": D(30)}, at=FRI, week_id="w")
    assert lg.positions["A"].owner_quantity(w[0].owner) == D(0) and w[0].liquidated
    assert lg.positions["A"].owner_quantity(other[0].owner) == D(3000)
    # valor recibido: 1.000×60 + 1.000×30 + dividendo 1×1.000 = 91.000 sobre 100.000 de entrada
    assert w[0].gross_pick_return == D("-0.09")


def test_r06_10_dividend_attribution_uses_the_unrounded_reference_value():
    lg = ledger("200000", FREE)
    w = enter_basket(lg, picks=["A"], slots=1, notional_per_slot=D(100000), open_prices={"A": D(100)}, at=MON, week_id="w")
    lg.apply_corporate_action(CorporateAction("div", "A", "cash_dividend", MON, per_share_cash=D("1.2345"), pay_at=FRI))
    exit_basket(lg, w, close_prices={"A": D(100)}, at=FRI, week_id="w")
    assert w[0].gross_pick_return == D("0.012345")
    assert lg.cash == D("200000") - D("100000") + D("100000") + D("1234")      # el efectivo cobrado sí se redondea (floor)


def _residue(lg):
    """W37 compra 1.000 a 100, recibe 50 % en acciones y vende 1.000 a 60: quedan 500."""
    w = enter_basket(lg, picks=["A"], slots=1, notional_per_slot=D(100000), open_prices={"A": D(100)}, at=MON, week_id="2026-W37")
    lg.apply_corporate_action(CorporateAction("stock", "A", "stock_dividend", MON, stock_ratio=D("0.5")))
    exit_basket(lg, w, close_prices={"A": D(60)}, at=FRI, week_id="2026-W37")
    assert w[0].status == "exited" and w[0].exit_residual_quantity == D(500)
    return w


def test_r07_06_blocked_retry_of_an_exited_slot_is_reported_blocked_with_fresh_figures():
    lg = ledger("1000000", FREE)
    w = _residue(lg)
    at = MON + timedelta(days=7)
    lg.apply_corporate_action(CorporateAction("split", "A", "split", at, split_ratio=D(2)))
    lg.apply_corporate_action(CorporateAction("div", "A", "cash_dividend", at, per_share_cash=D(2)))
    lg.mark_suspended("A", at=at)
    exit_basket(lg, w, close_prices={"A": D(30)}, at=FRI + timedelta(days=7), week_id="2026-W37")
    assert w[0].status == "exit_blocked" and w[0].gross_pick_return is None
    assert w[0].exit_residual_quantity == D(1000) and w[0].dividends_declared == D(2000)
    report = basket_report("2026-W37", w, equity_start=D(100000), equity_end=D(92000))
    assert report.exit_blocked_slots == 1


def test_r07_07_exits_respect_the_ledger_clock():
    lg = ledger("1000000", FREE)
    w = enter_basket(lg, picks=["A"], slots=1, notional_per_slot=D(100000), open_prices={"A": D(100)}, at=MON, week_id="2026-W37")
    lg.sell(security_id="A", price=D(200), shares=1000, at=MON + timedelta(days=21), event_id="future-sale", owner=w[0].owner)
    with pytest.raises(OutOfOrderEvent):
        exit_basket(lg, w, close_prices={}, at=FRI, week_id="2026-W37")
    lg2 = ledger("1000000", FREE)
    w2 = _residue(lg2)
    lg2.apply_corporate_action(CorporateAction("div", "A", "cash_dividend", MON + timedelta(days=14), per_share_cash=D(20), pay_at=MON + timedelta(days=14)))
    with pytest.raises(OutOfOrderEvent):
        exit_basket(lg2, w2, close_prices={"A": D(60)}, at=FRI, week_id="2026-W37")   # salida fechada antes del dividendo


@pytest.mark.parametrize("price", [D(-60), D(0), D("NaN")])
def test_r07_08_residual_valuation_rejects_invalid_prices(price):
    lg = ledger("1000000", FREE)
    w = _residue(lg)
    with pytest.raises(LedgerError):
        exit_basket(lg, w, close_prices={"A": price}, at=FRI + timedelta(days=7), week_id="2026-W37")


def test_r07_09_fifo_sale_never_consumes_fractional_rights():
    lg = ledger("1000000", FREE)
    a = enter_basket(lg, picks=["A"], slots=1, notional_per_slot=D(100000), open_prices={"A": D(100)}, at=MON, week_id="2026-W37")
    b = enter_basket(lg, picks=["A"], slots=1, notional_per_slot=D(100000), open_prices={"A": D(100)}, at=MON + timedelta(days=7), week_id="2026-W38")
    at = MON + timedelta(days=14)
    lg.apply_corporate_action(CorporateAction("reverse", "A", "split", at, split_ratio=D("0.5005")))
    res = lg.sell(security_id="A", price=D(200), shares=1000, at=at, event_id="fifo")
    assert isinstance(res, Fill)
    assert lg.positions["A"].owner_quantity(a[0].owner) == D("0.5") and lg.positions["A"].owner_quantity(b[0].owner) == D("0.5")
    assert lg.positions["A"].unresolved_fraction == D("1.0")
    assert isinstance(lg.sell(security_id="A", price=D(200), shares=1000, at=at, event_id="none-left"), Rejection)


def test_r04_08_late_known_payment_date_never_backdates_cash():
    lg = ledger(costs=FREE)
    lg.buy(security_id="A", price=D(100), shares=1000, at=MON, event_id="b")
    lg.apply_corporate_action(CorporateAction("div", "A", "cash_dividend", MON, per_share_cash=D(1)))
    lg.advance_to(FRI)
    lg.set_payment_date("div", pay_at=TUE, at=FRI)
    ats = [e.at for e in lg.events]
    assert ats == sorted(ats) and lg.cash == D(901000)
    settled = [e for e in lg.events if e.kind == "receivable_settled"]
    assert settled and settled[-1].at == FRI and "contractual pay_at" in settled[-1].detail


def test_r01_10_blocked_exit_can_be_retried_after_resumption():
    lg = ledger("100000", FREE)
    slots = enter_basket(lg, picks=["A"], slots=1, notional_per_slot=D(100000), open_prices={"A": D(100)}, at=MON, week_id="w")
    lg.mark_suspended("A", at=FRI)
    exit_basket(lg, slots, close_prices={"A": D(100)}, at=FRI, week_id="w")
    assert slots[0].status == "exit_blocked"
    lg.mark_resumed("A", at=FRI)
    exit_basket(lg, slots, close_prices={"A": D(100)}, at=FRI, week_id="w")
    assert not lg.positions and slots[0].status == "exited"


def test_r01_15_partial_sale_reduces_cost_basis_and_records_realized_pnl():
    lg = ledger(costs=FREE)
    lg.buy(security_id="A", price=D(100), shares=2000, at=MON, event_id="b")
    f = lg.sell(security_id="A", price=D(110), shares=1000, at=FRI, event_id="s")
    assert lg.positions["A"].cost_twd == D(100000) and f.realized_pnl == D(10000)


def test_r01_17_odd_lot_sale_is_not_executable_in_regular_session():
    lg = ledger()
    lg.buy(security_id="A", price=D(100), shares=1000, at=MON, event_id="b")
    f = lg.sell(security_id="A", price=D(100), shares=1, at=FRI, event_id="s")
    assert isinstance(f, Rejection) and f.reason == "odd_lot_requires_separate_mechanism"
    r = lg.buy(security_id="B", price=D("100"), shares=500, at=FRI, event_id="b2")
    assert isinstance(r, Rejection) and r.reason == "not_round_lot"


def test_sim11_mean_pick_return_differs_from_portfolio_return():
    lg = ledger("500000")
    slots = enter_basket(lg, picks=["A", "B", "C"], slots=5, notional_per_slot=D("100000"),
                         open_prices=P90, at=MON, week_id="w")
    start = lg.valuation(prices=P90, at=MON).total
    exit_basket(lg, slots, close_prices={k: D("99") for k in "ABC"}, at=FRI, week_id="w")
    end = lg.valuation(prices={}, at=FRI).total
    rep = basket_report("w", slots, equity_start=start, equity_end=end)
    assert rep.empty_slots == 2 and rep.filled_slots == 3
    assert rep.mean_gross_pick_return == D("0.1")
    assert rep.portfolio_net_return < D("0.06")           # 3/5 invertido, menos costes


def test_r01_19_duplicate_picks_are_rejected():
    with pytest.raises(ValueError):
        enter_basket(ledger("500000"), picks=["A", "A"], slots=5, notional_per_slot=D("100000"), open_prices=P90, at=MON, week_id="w")


# ---- evaluación ----------------------------------------------------------
def test_sim12_close_index_is_not_an_open_entry():
    a = IntervalReturn("cartera", MON, FRI, "open", "close", D("0.01"), exposure=D("0.6"))
    b = IntervalReturn("formosa", taipei(date(2026, 9, 4), time(13, 30)), FRI, "close", "close", D("0.005"), exposure=D("0.6"))
    with pytest.raises(IntervalMismatch):
        paired_excess(a, b)
    c = IntervalReturn("formosa_open_close", MON, FRI, "open", "close", D("0.005"), exposure=D("0.6"))
    assert paired_excess(a, c) == D("0.005")


def test_r01_21_unmatched_exposure_currency_or_cost_basis_is_not_paired():
    h1 = IntervalReturn("H1", MON, FRI, "open", "close", D("0.10"), exposure=D("1.0"))
    q1 = IntervalReturn("Q1", MON, FRI, "open", "close", D("0.02"), exposure=D("0.2"))
    with pytest.raises(IntervalMismatch):
        paired_excess(h1, q1)
    with pytest.raises(IntervalMismatch):
        paired_excess(h1, IntervalReturn("Q1", MON, FRI, "open", "close", D("0.02"), exposure=D("1.0"), net_of_costs=False))
    with pytest.raises(IntervalMismatch):
        paired_excess(h1, IntervalReturn("Q1", MON, FRI, "open", "close", D("0.02"), exposure=D("1.0"), currency="USD"))


CLEAN = "historical_numeric_temporally_controlled"


def obs(week, value, *, valid=True, cls=CLEAN, seal=None):
    return WeeklyObservation(week, f"f-{week}", cls, seal, valid, value)


def test_sta01_bootstrap_unit_is_the_iso_week():
    weeks = [obs(f"2026-W{w:02d}", v) for w, v in zip(range(30, 38), [0.01, -0.02, 0.005, 0.0, 0.03, -0.01, 0.02, -0.005])]
    r = block_bootstrap_mean(weeks, block_length=2, n_boot=200, seed=20260909)
    assert r.ci_low <= r.mean <= r.ci_high and r.n_used == 8 and r.n_invalid_excluded == 0
    with pytest.raises(TypeError):
        block_bootstrap_mean(weeks, n_boot=10, seed=1)  # type: ignore[call-arg]
    with pytest.raises(ObservationError):
        block_bootstrap_mean(weeks + [obs("2026-W37", 0.1)], block_length=2, n_boot=10, seed=1)      # semana duplicada
    with pytest.raises(ObservationError):
        block_bootstrap_mean(weeks + [obs("2026-W38", 0.1, cls="historical_current_llm_exploratory")],
                             block_length=2, n_boot=10, seed=1)                                        # clases mezcladas
    with pytest.raises(ObservationError):
        block_bootstrap_mean([obs("2026-W30", 0.1)], block_length=1, n_boot=10, seed=1, require_sealed=True)


PRO = "prospective_registered"


def _eval(store, rec, week, pkt, *, forecast_id="f-1", packets=None, calendar=None, **kw):
    from tests.test_schema import CAL_2030
    packets = packets if packets is not None else {pkt.packet_hash(): pkt}
    return block_bootstrap_mean([WeeklyObservation(week, forecast_id, PRO, rec.capture_id, True, 0.1)],
                                block_length=1, n_boot=10, seed=1, store=store, packets=packets,
                                calendar=calendar or CAL_2030, allow_test_authorities=True, **kw)


def test_r04_01_r05_02_r05_03_r05_10_prospective_evaluation_binds_each_week_to_its_archived_forecast(tmp_path):
    from tests.test_schema import CAL_2030, archive_and_seal, prospective_forecast, prospective_packet
    pro = [WeeklyObservation("2030-W02", "f-1", PRO, "cap-1", True, 0.1)]
    with pytest.raises(ObservationError):
        block_bootstrap_mean(pro, block_length=1, n_boot=10, seed=1)                    # sin archivo: no hay sello
    with pytest.raises(ObservationError):
        block_bootstrap_mean(pro, block_length=1, n_boot=10, seed=1, store={"cap-1": True})   # type: ignore[arg-type]
    pkt = prospective_packet()
    obj = prospective_forecast(pkt)                                                       # forecast_id f-1, semana 2030-W02
    store, rec = archive_and_seal(tmp_path, obj, pkt)
    packets = {pkt.packet_hash(): pkt}
    with pytest.raises(ObservationError):
        block_bootstrap_mean([WeeklyObservation("2030-W02", "f-1", PRO, rec.capture_id, True, 0.1)],
                             block_length=1, n_boot=10, seed=1, store=store, packets=packets, calendar=CAL_2030)   # prueba: bloqueado
    with pytest.raises(ObservationError):
        block_bootstrap_mean([WeeklyObservation("2030-W02", "f-1", PRO, rec.capture_id, True, 0.1)],
                             block_length=1, n_boot=10, seed=1, store=store, allow_test_authorities=True)         # sin paquetes ni calendario
    assert _eval(store, rec, "2030-W02", pkt).n_used == 1
    # R05-02: una captura ajena (otros bytes) o reutilizada no acredita semanas
    weather = store.put(source_id="weather", dataset="rain", payload=b"weather:rain=0", url="u")
    store.attach_receipt(weather.capture_id, receipt_id="fixture:w", authority="fixture", digest=weather.sha256, attested_at=weather.ingested_at)
    for rows in ([WeeklyObservation("2030-W02", "never-archived", PRO, weather.capture_id, True, 0.1)],
                 [WeeklyObservation("2030-W02", "f-1", PRO, rec.capture_id, True, 0.1),
                  WeeklyObservation("2030-W03", "f-1", PRO, rec.capture_id, True, 0.1)],
                 [WeeklyObservation("2030-W03", "f-1", PRO, rec.capture_id, True, 0.1)]):      # semana distinta a la archivada
        with pytest.raises(ObservationError):
            block_bootstrap_mean(rows, block_length=1, n_boot=10, seed=1, store=store, packets=packets, calendar=CAL_2030,
                                 allow_test_authorities=True)
    # R05-03: acreditación tardía rechazada también en evaluación
    late_obj = prospective_forecast(pkt, forecast_id="f-late")
    late_store, late_rec = archive_and_seal(tmp_path / "late", late_obj, pkt, attested_at=(pkt.deadline_at + timedelta(days=7)).isoformat())
    with pytest.raises(ObservationError):
        _eval(late_store, late_rec, "2030-W02", pkt, forecast_id="f-late")
    # R05-10: una corrida inválida sin predicción se cuenta como excluida sin exigirle sello
    rows = [WeeklyObservation("2030-W02", "f-1", PRO, rec.capture_id, True, 0.1),
            WeeklyObservation("2030-W03", "failed-run", PRO, None, False, None)]
    r2 = block_bootstrap_mean(rows, block_length=1, n_boot=10, seed=1, store=store, packets=packets, calendar=CAL_2030,
                              allow_test_authorities=True)
    assert r2.n_used == 1 and r2.n_invalid_excluded == 1


def test_r06_02_r06_03_r06_04_r07_01_r07_02_r07_03_evaluator_validates_the_archived_forecast_completely(tmp_path):
    import json
    from tests.test_schema import CUTOFF_2030_EMPTY, archive_and_seal, prospective_forecast, prospective_packet
    from twlab.store import RawStore

    def archive_body(root, body):
        s = RawStore(root, verifiers={"fixture": lambda r, rc: rc.digest == r.sha256})
        raw = json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")
        r = s.put(source_id="forecast", dataset="x", payload=raw, url="u")
        s.attach_receipt(r.capture_id, receipt_id="fixture:x", authority="fixture", digest=r.sha256, attested_at=r.ingested_at)
        return s, r

    pkt = prospective_packet()
    # R06-02: un sobre incompleto (sin ranking, modelo, packet_hash...) no es una predicción del contrato
    s, r = archive_body(tmp_path / "a", {"forecast": {"forecast_id": "f-1", "cutoff_at": "2030-01-06T18:00:00+08:00",
                                                       "deadline_at": "2030-01-07T08:30:00+08:00", "evidence_class": PRO},
                                         "packet_hash": pkt.packet_hash()})
    with pytest.raises(ObservationError):
        _eval(s, r, "2030-W02", pkt)
    # R06-03: el plazo archivado no puede anular ni extender el límite de registro, ni el corte dejar de ser semanal
    for cutoff, deadline in (("2021-01-03T18:00:00+08:00", "2021-01-03T18:00:00+08:00"),
                             ("2021-01-03T18:00:00+08:00", "2099-01-05T08:30:00+08:00"),
                             ("2030-01-10T18:00:00+08:00", "2030-01-11T08:30:00+08:00")):
        obj = prospective_forecast(pkt, cutoff_at=cutoff, issued_at=cutoff.replace("18:00", "18:30"), deadline_at=deadline)
        s2, r2 = archive_and_seal(tmp_path / cutoff[:10] / deadline[:10], obj, pkt)
        with pytest.raises(ObservationError):
            _eval(s2, r2, "2021-W01" if cutoff.startswith("2021") else "2030-W02", pkt)
    # R06-04: una corrida archivada como inválida no puede entrar como observación válida
    p_empty = prospective_packet(cutoff=CUTOFF_2030_EMPTY)
    inv = prospective_forecast(p_empty, status="invalid", ranking=[], status_reason="no_sessions", deadline_at=CUTOFF_2030_EMPTY.isoformat())
    s3, r3 = archive_and_seal(tmp_path / "inv", inv, p_empty)
    with pytest.raises(ObservationError):
        _eval(s3, r3, p_empty.week_id, p_empty)
    # R07-01: orden temporal también en el evaluador
    for issued in ((pkt.cutoff_at - timedelta(days=1)).isoformat(), (pkt.deadline_at + timedelta(days=4)).isoformat()):
        o = prospective_forecast(pkt, issued_at=issued)
        s4, r4 = archive_and_seal(tmp_path / "t" / issued[:13], o, pkt)
        with pytest.raises(ObservationError):
            _eval(s4, r4, "2030-W02", pkt)
    # R07-02: reglas semánticas sin paquete (experimento, rangos, calibrador)
    for over in ({"experiment_id": "UNREGISTERED-99"},):
        o = prospective_forecast(pkt, **over)
        s5, r5 = archive_and_seal(tmp_path / "sem" / over["experiment_id"], o, pkt)
        with pytest.raises(ObservationError):
            _eval(s5, r5, "2030-W02", pkt)
    dup = prospective_forecast(pkt)
    dup["ranking"] = [dict(dup["ranking"][0]), dict(dup["ranking"][0])]
    s6, r6 = archive_and_seal(tmp_path / "dup", dup, pkt)
    with pytest.raises(ObservationError):
        _eval(s6, r6, "2030-W02", pkt)
    # R07-03: el paquete acreditado debe existir en el registro, con el mismo hash y las referencias válidas
    ghost = prospective_forecast(pkt, packet_id="nonexistent-packet")
    ghost["ranking"][0]["document_ids"] = ["future-result-2099"]
    s7, r7 = archive_body(tmp_path / "ghost", {"forecast": ghost, "packet_hash": "0" * 64})
    with pytest.raises(ObservationError):
        _eval(s7, r7, "2030-W02", pkt)
    ok = prospective_forecast(pkt)
    s8, r8 = archive_and_seal(tmp_path / "ok", ok, pkt)
    with pytest.raises(ObservationError):
        _eval(s8, r8, "2030-W02", pkt, packets={})                   # paquete no archivado
    assert _eval(s8, r8, "2030-W02", pkt).n_used == 1


def test_r02_08_daily_rows_are_not_weeks_and_blocks_do_not_bridge_gaps():
    rows = [WeeklyObservation(f"2026-09-{d:02d}", f"f-{d}", CLEAN, None, True, 0.1) for d in range(7, 12)]
    with pytest.raises(ObservationError):
        block_bootstrap_mean(rows, block_length=1, n_boot=10, seed=1)
    gap = [obs("2026-W30", 0.1), obs("2026-W31", None, valid=False), obs("2026-W32", -0.1)]
    r = block_bootstrap_mean(gap, block_length=1, n_boot=50, seed=1)       # con bloque 1 se cuenta la inválida
    assert r.n_used == 2 and r.n_invalid_excluded == 1
    # Con bloque 2 la semana inválida parte la serie en dos tramos de una semana: cada tramo es un bloque
    # propio y ningún bloque une W30 con W32 (C-08-01; antes se rechazaba toda la evaluación).
    r2 = block_bootstrap_mean(gap, block_length=2, n_boot=50, seed=1)
    assert r2.n_used == 2 and r2.n_invalid_excluded == 1 and r2.n_segments == 2
    missing = [obs("2026-W30", 0.1), obs("2026-W32", -0.1)]
    assert block_bootstrap_mean(missing, block_length=2, n_boot=10, seed=1).n_segments == 2


def test_c08_01_blocks_are_sampled_inside_contiguous_segments_only():
    from twlab.evaluation import _block_starts, _segments, week_monday
    mondays = [week_monday(w) for w in ("2026-W30", "2026-W31", "2026-W32", "2026-W34", "2026-W35", "2026-W37")]
    assert _segments(mondays) == [(0, 3), (3, 2), (5, 1)]
    starts = _block_starts(mondays, 2)
    assert starts == [(0, 2), (1, 2), (3, 2), (5, 1)]          # W32→W34 y W35→W37 no forman bloque
    for s0, ln in starts:
        for k in range(1, ln):
            assert (mondays[s0 + k] - mondays[s0 + k - 1]).days == 7
    assert _block_starts(mondays[:3], 2) == [(0, 2), (1, 2)]   # sin huecos: bloques móviles clásicos
    assert _block_starts(mondays[:3], 5) == [(0, 3)]           # tramo más corto que el bloque: un bloque propio
    assert _block_starts([], 2) == []
    # sin huecos el resultado es idéntico al del bootstrap clásico con la misma semilla
    rows = [obs(f"2026-W{w}", v) for w, v in zip(range(30, 38), (0.1, -0.2, 0.05, 0.0, 0.3, -0.1, 0.02, 0.07))]
    r = block_bootstrap_mean(rows, block_length=3, n_boot=200, seed=7)
    assert r.n_segments == 1 and r.n_used == 8 and r.ci_low <= r.mean <= r.ci_high


def test_c08_02_paired_excess_exposure_tolerance_is_declared_not_inferred():
    from dataclasses import replace
    a = IntervalReturn("Q0", MON, FRI, "open", "close", D("0.010"), D("0.95"), week_id="2026-W37")
    b = replace(a, label="A1", value=D("0.020"), exposure=D("1.00"))
    with pytest.raises(IntervalMismatch):
        paired_excess(a, b)                                          # por defecto: igualdad exacta (SIM-12)
    assert paired_excess(a, b, exposure_tolerance=D("0.05")) == D("-0.010")
    with pytest.raises(IntervalMismatch):
        paired_excess(a, replace(b, exposure=D("0.80")), exposure_tolerance=D("0.10"))
    with pytest.raises(IntervalMismatch):
        paired_excess(a, replace(b, end_price_kind="open"), exposure_tolerance=D("0.50"))   # la tolerancia no relaja el marco
    for bad in (D("1"), D("-0.1"), D("NaN")):
        with pytest.raises(ValueError):
            paired_excess(a, b, exposure_tolerance=bad)


def test_r08_11_segments_are_weighted_by_length_not_by_block_count():
    # dos tramos constantes (4 valores 1, 8 valores 0) separados por una semana ausente; media exacta 1/3.
    # Con bloque 4 el primer tramo aporta 1 bloque y el segundo 5: muestrear bloques uniformemente sesgaba a 0,165.
    rows = [obs(f"2026-W{w}", 1.0) for w in range(20, 24)] + [obs(f"2026-W{w}", 0.0) for w in range(25, 33)]
    r = block_bootstrap_mean(rows, block_length=4, n_boot=4000, seed=1)
    assert r.n_used == 12 and r.n_segments == 2 and abs(r.mean - 1 / 3) < 1e-9
    assert abs(r.resample_mean - 1 / 3) < 0.03
    assert r.ci_low <= r.mean <= r.ci_high


def test_r08_01_recovered_packet_is_readmitted_document_by_document(tmp_path):
    from dataclasses import replace
    from datetime import timedelta
    from twlab.packet import Document, readmission_problems
    from twlab.store import RawStore
    from twlab.timeutil import AvailabilityQuality
    from tests.test_schema import archive_and_seal, prospective_forecast, prospective_packet
    pkt = prospective_packet()
    future = Document(doc_id="future-result-2099", kind="news", source_id="x", security_ids=("SEC-1",),
                      available_at=pkt.cutoff_at + timedelta(days=30), availability_quality=AvailabilityQuality.CONSERVATIVE_INFERENCE,
                      payload={"future_profit": 999})
    unknown = Document(doc_id="unknown-availability", kind="news", source_id="x", security_ids=("SEC-1",),
                       available_at=pkt.cutoff_at - timedelta(days=1), availability_quality=AvailabilityQuality.UNKNOWN,
                       capture_id="cap-none", source_sha256="00" * 32, derivation="d")
    # un paquete construido a mano (no por build_packet) con un documento futuro admitido: su hash es válido, su contenido no
    for bad_doc in (future, unknown):
        forged = replace(pkt, admitted=(bad_doc,))
        problems = readmission_problems(forged, store=RawStore(tmp_path / "archive"))
        assert problems and all(p.startswith(bad_doc.doc_id) for p in problems)
        o = prospective_forecast(forged)
        o["ranking"][0]["document_ids"] = [bad_doc.doc_id]
        store, rec = archive_and_seal(tmp_path / bad_doc.doc_id, o, forged)
        with pytest.raises(ObservationError, match="readmission"):
            _eval(store, rec, "2030-W02", forged)
    assert readmission_problems(pkt, store=RawStore(tmp_path / "empty")) == []      # el paquete legítimo pasa (con archivo)


def test_r09_01_r09_02_r09_03_readmission_requires_the_archive_checks_bytes_and_rederives_payloads(tmp_path):
    import json
    from dataclasses import replace
    from datetime import timedelta
    from twlab.packet import Document, Rejection, readmission_problems
    from twlab.store import RawStore
    from twlab.timeutil import AvailabilityQuality
    from tests.test_schema import prospective_packet
    pkt = prospective_packet()
    store = RawStore(tmp_path)
    rec = store.put(source_id="x", dataset="d", payload=b'{"profit": 1}', url="u", content_type="application/json")
    doc = Document(doc_id="d1", kind="news", source_id="x", security_ids=("SEC-1",), available_at=pkt.cutoff_at - timedelta(days=1),
                   availability_quality=AvailabilityQuality.VERIFIED_ORIGINAL, capture_id=rec.capture_id, source_sha256=rec.sha256,
                   derivation="ext", first_seen_at=rec.ingested_at_dt, payload={"profit": 1})
    ext = {"ext": lambda raw: {"payload": json.loads(raw), "security_ids": ["SEC-1"]}}
    good = replace(pkt, admitted=(doc,))
    assert readmission_problems(good, store=store, extractors=ext) == []
    # R09-02: sin archivo la readmisión prospectiva falla cerrada, aunque los metadatos cuadren
    assert any("archive_required" in p for p in readmission_problems(good, extractors=ext))
    # sin extractor registrado el payload no puede re-derivarse: no se readmite
    assert any("not registered" in p for p in readmission_problems(good, store=store))
    # payload que no sale de los bytes archivados
    bad_payload = replace(good, admitted=(replace(doc, payload={"profit": 999}),))
    assert any("derivation_mismatch" in p for p in readmission_problems(bad_payload, store=store, extractors=ext))
    # R09-03: rechazos duplicados o con motivo fuera del catálogo
    forged_rej = replace(good, rejected=(Rejection("ghost", "invented_reason", "profit in 2099 = 999"), Rejection("ghost", "invented_reason", "x")))
    probs = readmission_problems(forged_rej, store=store, extractors=ext)
    assert any("invented_reason" in p for p in probs) and any("duplicate rejection" in p for p in probs)
    # R09-01: bytes archivados sustituidos conservando el manifiesto
    (store.root / rec.path).write_bytes(b'{"profit": 999}')
    assert any("integrity" in p for p in readmission_problems(good, store=store, extractors=ext))


def test_r09_12_segment_weights_are_preserved_when_segments_are_shorter_than_the_block():
    # tramos de 1 y 8 (valores 1 y 0): media 1/9; con bloque 4 una extracción del tramo corto aporta 1 observación y
    # una del largo 4, así que el tramo corto debe elegirse con probabilidad ∝ 1/1 frente a 8/4.
    # Remuestreo estratificado (ronda 10): cada tramo aporta exactamente su longitud → el peso es exacto, no aproximado.
    rows = [obs("2026-W20", 1.0)] + [obs(f"2026-W{w}", 0.0) for w in range(22, 30)]
    r = block_bootstrap_mean(rows, block_length=4, n_boot=500, seed=1)
    assert abs(r.mean - 1 / 9) < 1e-9 and abs(r.resample_mean - 1 / 9) < 1e-12 and r.ci_low == r.ci_high == r.mean
    rows2 = [obs("2026-W20", 1.0), obs("2026-W21", 1.0)] + [obs(f"2026-W{w}", 0.0) for w in range(23, 31)]
    r2 = block_bootstrap_mean(rows2, block_length=4, n_boot=500, seed=1)
    assert abs(r2.mean - 0.2) < 1e-9 and abs(r2.resample_mean - 0.2) < 1e-12
    # y dentro de un tramo con valores distintos sigue habiendo variabilidad (es un bootstrap, no una media fija)
    rows3 = [obs(f"2026-W{w}", v) for w, v in zip(range(20, 30), (1, 0, 1, 0, 1, 0, 1, 0, 1, 0))]
    r3 = block_bootstrap_mean(rows3, block_length=3, n_boot=500, seed=1)
    assert r3.ci_low < r3.mean < r3.ci_high


def test_r09_03_rejection_details_must_be_build_packet_templates():
    from dataclasses import replace
    from twlab.packet import Rejection, readmission_problems, rejection_detail_is_canonical
    from twlab.store import RawStore
    from tests.test_schema import prospective_packet
    ok = "available_at=2030-02-05T18:00:00+08:00 > cutoff=2030-01-06T18:00:00+08:00"
    assert rejection_detail_is_canonical("available_after_cutoff", ok)
    assert not rejection_detail_is_canonical("available_after_cutoff", "profit in 2099 = 999")
    assert not rejection_detail_is_canonical("available_after_cutoff", ok + " profit in 2099 = 999")
    assert rejection_detail_is_canonical("derivation_mismatch", "extractor news_v1 failed: ValueError")
    assert not rejection_detail_is_canonical("derivation_mismatch", "extractor news_v1 failed: ValueError: buy SEC-1, profit 999")
    pkt = prospective_packet()
    smuggling = replace(pkt, rejected=(Rejection("ghost", "available_after_cutoff", "profit in 2099 = 999"),))
    probs = readmission_problems(smuggling, store=RawStore.__new__(RawStore)) if False else None   # (no se necesita archivo real aquí)
    from twlab.packet import readmission_problems as rp
    import tempfile, pathlib
    with tempfile.TemporaryDirectory() as tmp:
        store = RawStore(pathlib.Path(tmp))
        assert any("not one of the templates" in p for p in rp(smuggling, store=store))
        canonical = replace(pkt, rejected=(Rejection("ghost", "available_after_cutoff", ok),))
        assert rp(canonical, store=store) == []


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf"), True, "0.1"])
def test_r03_14_non_finite_or_non_numeric_values_are_rejected(value):
    with pytest.raises(ObservationError):
        block_bootstrap_mean([obs("2026-W37", value)], block_length=1, n_boot=10, seed=1)


def test_sta04_invalid_runs_are_counted_not_hidden():
    weeks = [obs("2026-W30", 0.01), obs("2026-W31", None, valid=False), obs("2026-W32", 0.02)]
    r = block_bootstrap_mean(weeks, block_length=1, n_boot=50, seed=1)
    assert r.n_used == 2 and r.n_invalid_excluded == 1
