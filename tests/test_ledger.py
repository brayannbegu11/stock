from datetime import date, time, timedelta
from decimal import Decimal as D

import pytest

from twlab.evaluation import (
    IntervalMismatch, IntervalReturn, ObservationError, WeeklyObservation, block_bootstrap_mean, paired_excess,
)
from twlab.ledger import (
    CorporateAction, CostModel, DuplicateCorporateAction, LedgerError, MissingPrice, OutOfOrderEvent, PaperLedger,
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


def test_r04_01_r05_02_r05_03_r05_10_prospective_evaluation_binds_each_week_to_its_archived_forecast(tmp_path):
    from tests.test_schema import CUTOFF_2030, archive_and_seal, prospective_forecast, prospective_packet
    from twlab.store import RawStore
    PRO = "prospective_registered"
    pro = [WeeklyObservation("2030-W02", "f-1", PRO, "cap-1", True, 0.1)]
    with pytest.raises(ObservationError):
        block_bootstrap_mean(pro, block_length=1, n_boot=10, seed=1)                    # sin archivo: no hay sello
    with pytest.raises(ObservationError):
        block_bootstrap_mean(pro, block_length=1, n_boot=10, seed=1, store={"cap-1": True})   # type: ignore[arg-type]
    pkt = prospective_packet()
    obj = prospective_forecast(pkt)                                                       # forecast_id f-1, semana 2030-W02
    store, rec = archive_and_seal(tmp_path, obj, pkt)
    good = [WeeklyObservation("2030-W02", "f-1", PRO, rec.capture_id, True, 0.1)]
    with pytest.raises(ObservationError):
        block_bootstrap_mean(good, block_length=1, n_boot=10, seed=1, store=store)      # autoridad de prueba: bloqueado
    r = block_bootstrap_mean(good, block_length=1, n_boot=10, seed=1, store=store, allow_test_authorities=True)
    assert r.n_used == 1
    # R05-02: una captura ajena (otros bytes) o reutilizada no acredita semanas
    weather = store.put(source_id="weather", dataset="rain", payload=b"weather:rain=0", url="u")
    store.attach_receipt(weather.capture_id, receipt_id="fixture:w", authority="fixture", digest=weather.sha256, attested_at=weather.ingested_at)
    for rows in ([WeeklyObservation("2030-W02", "never-archived", PRO, weather.capture_id, True, 0.1)],
                 [WeeklyObservation("2030-W02", "f-1", PRO, rec.capture_id, True, 0.1),
                  WeeklyObservation("2030-W03", "f-1", PRO, rec.capture_id, True, 0.1)],
                 [WeeklyObservation("2030-W03", "f-1", PRO, rec.capture_id, True, 0.1)]):      # semana distinta a la archivada
        with pytest.raises(ObservationError):
            block_bootstrap_mean(rows, block_length=1, n_boot=10, seed=1, store=store, allow_test_authorities=True)
    # R05-03: acreditación tardía rechazada también en evaluación
    late_obj = prospective_forecast(pkt, forecast_id="f-late")
    late_store, late_rec = archive_and_seal(tmp_path / "late", late_obj, pkt, attested_at=(pkt.deadline_at + timedelta(days=7)).isoformat())
    with pytest.raises(ObservationError):
        block_bootstrap_mean([WeeklyObservation("2030-W02", "f-late", PRO, late_rec.capture_id, True, 0.1)],
                             block_length=1, n_boot=10, seed=1, store=late_store, allow_test_authorities=True)
    # R05-10: una corrida inválida sin predicción se cuenta como excluida sin exigirle sello
    rows = [WeeklyObservation("2030-W02", "f-1", PRO, rec.capture_id, True, 0.1),
            WeeklyObservation("2030-W03", "failed-run", PRO, None, False, None)]
    r2 = block_bootstrap_mean(rows, block_length=1, n_boot=10, seed=1, store=store, allow_test_authorities=True)
    assert r2.n_used == 1 and r2.n_invalid_excluded == 1


def test_r06_02_r06_03_r06_04_evaluator_validates_the_archived_forecast_not_declared_fields(tmp_path):
    import json
    from tests.test_schema import CUTOFF_2030_EMPTY, archive_and_seal, prospective_forecast, prospective_packet
    from twlab.store import RawStore
    PRO = "prospective_registered"

    def archive_body(root, body):
        s = RawStore(root, verifiers={"fixture": lambda r, rc: rc.digest == r.sha256})
        raw = json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")
        r = s.put(source_id="forecast", dataset="x", payload=raw, url="u")
        s.attach_receipt(r.capture_id, receipt_id="fixture:x", authority="fixture", digest=r.sha256, attested_at=r.ingested_at)
        return s, r

    def evaluate(s, r, week, forecast_id="f-1"):
        return block_bootstrap_mean([WeeklyObservation(week, forecast_id, PRO, r.capture_id, True, 0.1)],
                                    block_length=1, n_boot=10, seed=1, store=s, allow_test_authorities=True)

    # R06-02: un sobre incompleto (sin ranking, modelo, packet_hash...) no es una predicción del contrato
    s, r = archive_body(tmp_path / "a", {"forecast": {"forecast_id": "f-1", "cutoff_at": "2030-01-06T18:00:00+08:00",
                                                       "deadline_at": "2030-01-07T08:30:00+08:00", "evidence_class": PRO}})
    with pytest.raises(ObservationError):
        evaluate(s, r, "2030-W02")
    # R06-03: el plazo archivado no puede anular ni extender el límite de registro, ni el corte dejar de ser semanal
    pkt = prospective_packet()
    for cutoff, deadline in (("2021-01-03T18:00:00+08:00", "2021-01-03T18:00:00+08:00"),
                             ("2021-01-03T18:00:00+08:00", "2099-01-05T08:30:00+08:00"),
                             ("2030-01-10T18:00:00+08:00", "2030-01-11T08:30:00+08:00")):
        obj = prospective_forecast(pkt, cutoff_at=cutoff, issued_at=cutoff.replace("18:00", "18:30"), deadline_at=deadline)
        s2, r2 = archive_and_seal(tmp_path / cutoff[:10] / deadline[:10], obj, pkt)
        with pytest.raises(ObservationError):
            evaluate(s2, r2, "2021-W01" if cutoff.startswith("2021") else "2030-W02")
    # R06-04: una corrida archivada como inválida no puede entrar como observación válida
    p_empty = prospective_packet(cutoff=CUTOFF_2030_EMPTY)
    inv = prospective_forecast(p_empty, status="invalid", ranking=[], status_reason="no_sessions", deadline_at=CUTOFF_2030_EMPTY.isoformat())
    s3, r3 = archive_and_seal(tmp_path / "inv", inv, p_empty)
    with pytest.raises(ObservationError):
        evaluate(s3, r3, p_empty.week_id)


def test_r02_08_daily_rows_are_not_weeks_and_blocks_do_not_bridge_gaps():
    rows = [WeeklyObservation(f"2026-09-{d:02d}", f"f-{d}", CLEAN, None, True, 0.1) for d in range(7, 12)]
    with pytest.raises(ObservationError):
        block_bootstrap_mean(rows, block_length=1, n_boot=10, seed=1)
    gap = [obs("2026-W30", 0.1), obs("2026-W31", None, valid=False), obs("2026-W32", -0.1)]
    with pytest.raises(ObservationError):
        block_bootstrap_mean(gap, block_length=2, n_boot=10, seed=1)
    r = block_bootstrap_mean(gap, block_length=1, n_boot=50, seed=1)       # con bloque 1 se cuenta la inválida
    assert r.n_used == 2 and r.n_invalid_excluded == 1
    missing = [obs("2026-W30", 0.1), obs("2026-W32", -0.1)]
    with pytest.raises(ObservationError):
        block_bootstrap_mean(missing, block_length=2, n_boot=10, seed=1)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf"), True, "0.1"])
def test_r03_14_non_finite_or_non_numeric_values_are_rejected(value):
    with pytest.raises(ObservationError):
        block_bootstrap_mean([obs("2026-W37", value)], block_length=1, n_boot=10, seed=1)


def test_sta04_invalid_runs_are_counted_not_hidden():
    weeks = [obs("2026-W30", 0.01), obs("2026-W31", None, valid=False), obs("2026-W32", 0.02)]
    r = block_bootstrap_mean(weeks, block_length=1, n_boot=50, seed=1)
    assert r.n_used == 2 and r.n_invalid_excluded == 1
