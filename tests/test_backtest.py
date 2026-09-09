"""Backtest con mercado sintético archivado en un RawStore temporal: coherencia del manifiesto, límites temporales,
pronosticadores y emparejamiento (contraejemplos R09-06, R10-02, R10-05, R10-06, R10-07)."""
import json
import random
from datetime import date, datetime, time, timedelta
from decimal import Decimal as D
from pathlib import Path

import pytest

from twlab.backtest import (
    BacktestConfig, ManifestInconsistent, MomentumForecaster, RandomForecaster, Runner, TabularForecaster, load_market,
)
from twlab.calendar import TradingCalendar
from twlab.ledger import OutOfOrderEvent
from twlab.sources.finmind import SourceIdentityMismatch
from twlab.store import RawStore
from twlab.timeutil import taipei

CAL = TradingCalendar(start=date(2023, 1, 1), end=date(2026, 12, 31), closures=[], source_id="synthetic", recorded_at=taipei(date(2023, 1, 1)))


def price_rows(sid: str, start: date, end: date, *, seed: int, first_price: float = 100.0):
    rng = random.Random(seed)
    rows, price, d = [], first_price, start
    while d <= end:
        if CAL.is_session(d):
            price *= 1 + rng.gauss(0.0005, 0.015)
            rows.append({"date": d.isoformat(), "stock_id": sid, "Trading_Volume": 2_000_000, "Trading_money": int(price * 2_000_000),
                         "open": round(price * 0.998, 2), "max": round(price * 1.01, 2), "min": round(price * 0.99, 2),
                         "close": round(price, 2), "spread": 0.0, "Trading_turnover": 1500})
        d += timedelta(days=1)
    return rows


def dividend_rows(sid: str, *, ex_date: date, cash: float, pay: date):
    return [{"stock_id": sid, "year": str(ex_date.year), "AnnouncementDate": (ex_date - timedelta(days=40)).isoformat(), "AnnouncementTime": "8:0:0",
             "CashEarningsDistribution": cash, "CashStatutorySurplus": 0, "StockEarningsDistribution": 0, "StockStatutorySurplus": 0,
             "CashExDividendTradingDate": ex_date.isoformat(), "CashDividendPaymentDate": pay.isoformat(), "StockExDividendTradingDate": ""}]


def archive(store: RawStore, dataset: str, sid: str, rows, *, source_id: str = "finmind"):
    body = json.dumps({"msg": "success", "status": 200, "data": rows}).encode("utf-8")
    return store.put(source_id=source_id, dataset=f"{dataset}/{sid}", payload=body, url="u", http_status=200, content_type="application/json")


def make_market(tmp_path: Path, *, symbols=("A", "B", "C", "D", "E", "F"), start=date(2023, 1, 2), end=date(2024, 3, 29),
                listing=None, dividends=None, overrides=None):
    store = RawStore(tmp_path / "raw")
    manifest = {"listed": [], "delisted": [], "captures": {}}
    for i, sid in enumerate(symbols):
        rows = price_rows(sid, start, end, seed=100 + i)
        rec = archive(store, "TaiwanStockPrice", sid, rows)
        entry = {"price": rec.capture_id, "price_rows": len(rows)}
        drows = (dividends or {}).get(sid, [])
        if drows:
            drec = archive(store, "TaiwanStockDividend", sid, drows)
            entry.update(dividend=drec.capture_id, dividend_rows=len(drows))
        entry.update((overrides or {}).get(sid, {}))
        manifest["captures"][sid] = entry
        manifest["listed"].append({"symbol": sid, "name": f"name-{sid}", "listing_date": ((listing or {}).get(sid) or start).isoformat()})
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return store, path


def test_r10_05_manifest_identity_and_listing_are_enforced_and_pre_listing_bars_dropped(tmp_path):
    store, path = make_market(tmp_path, overrides={"A": {"security_id": "TPEX:B@2020-01-01"}})
    with pytest.raises(ManifestInconsistent):
        load_market(store, path, CAL)
    store, path = make_market(tmp_path / "b", overrides={"A": {"listing_date": "2023-06-01"}})
    with pytest.raises(ManifestInconsistent):
        load_market(store, path, CAL)                        # listed dice 2023-01-02, captures dice 2023-06-01
    store, path = make_market(tmp_path / "c", listing={"A": date(2024, 1, 1)})
    m = load_market(store, path, CAL)
    a = m.securities[m.by_symbol["A"]]
    assert a.listing_date == date(2024, 1, 1) and min(b.session for b in a.bars) >= date(2024, 1, 1)
    assert m.bars_before_listing_dropped > 200 and a.security_id == "TWSE:A@2024-01-01"
    # con sólo unas sesiones desde el alta, A no es puntuable en el primer corte de 2024
    cfg = BacktestConfig(start=date(2024, 1, 1), end=date(2024, 1, 14), label="t")
    runner = Runner(store, m, cfg, [MomentumForecaster(), RandomForecaster(1)])
    res = runner.run()
    week = next(w for w in res["weeks"] if w["week_id"] == "2024-W02")
    assert week["coverage_reasons"].get("insufficient_history", 0) >= 1


def test_r10_05_listed_and_delisted_declarations_are_checked_too(tmp_path):
    store, path = make_market(tmp_path)
    m = json.loads(path.read_text(encoding="utf-8"))
    m["listed"][0]["security_id"] = "TPEX:B@1990-01-01"
    path.write_text(json.dumps(m), encoding="utf-8")
    with pytest.raises(ManifestInconsistent):
        load_market(store, path, CAL)
    m = json.loads(path.read_text(encoding="utf-8"))
    del m["listed"][0]["security_id"]
    m["listed"].append({"symbol": "A", "name": "otra", "listing_date": "2024-01-01"})
    path.write_text(json.dumps(m), encoding="utf-8")
    with pytest.raises(ManifestInconsistent):
        load_market(store, path, CAL)                        # símbolo repetido en listed
    m = json.loads(path.read_text(encoding="utf-8"))
    m["listed"].pop()
    m["delisted"].append({"symbol": "A", "name": "A", "delisting_date": "2024-03-01", "listing_date": "2000-01-01"})
    path.write_text(json.dumps(m), encoding="utf-8")
    with pytest.raises(ManifestInconsistent):
        load_market(store, path, CAL)                        # alta declarada en delisted distinta de listed


def test_r10_06_dividend_captures_are_always_read_and_checked(tmp_path):
    divs = {"A": dividend_rows("A", ex_date=date(2024, 1, 10), cash=2.0, pay=date(2024, 2, 1))}
    store, path = make_market(tmp_path, dividends=divs, overrides={"A": {"dividend_rows": 0}})
    with pytest.raises(ManifestInconsistent):
        load_market(store, path, CAL)                        # el contador no puede ocultar un dividendo archivado
    store, path = make_market(tmp_path / "b", dividends=divs)
    m = load_market(store, path, CAL)
    assert len(m.securities[m.by_symbol["A"]].dividends) == 1
    # captura de dividendos de otra fuente
    store3 = RawStore(tmp_path / "c" / "raw")
    rows = price_rows("A", date(2023, 1, 2), date(2024, 3, 29), seed=1)
    prec = archive(store3, "TaiwanStockPrice", "A", rows)
    drec = archive(store3, "TaiwanStockDividend", "A", divs["A"], source_id="untrusted")
    p3 = tmp_path / "c" / "manifest.json"
    p3.write_text(json.dumps({"listed": [{"symbol": "A", "name": "A", "listing_date": "2023-01-02"}], "delisted": [],
                              "captures": {"A": {"price": prec.capture_id, "price_rows": len(rows), "dividend": drec.capture_id, "dividend_rows": 1}}}), encoding="utf-8")
    with pytest.raises(SourceIdentityMismatch):
        load_market(store3, p3, CAL)
    # recuento positivo sin captura de dividendos: error, no silencio (ronda 11)
    store4, path4 = make_market(tmp_path / "d", overrides={"A": {"dividend_rows": 1}})
    with pytest.raises(ManifestInconsistent):
        load_market(store4, path4, CAL)


def test_r10_07_invalid_week_beyond_the_bound_is_not_processed(tmp_path):
    closed_week = TradingCalendar(start=CAL.start, end=CAL.end, closures=[date(2024, 1, d) for d in range(15, 20)],
                                  source_id="synthetic", recorded_at=CAL.recorded_at, version="closed-W03")
    divs = {"A": dividend_rows("A", ex_date=date(2024, 1, 18), cash=2.0, pay=date(2024, 2, 1))}
    store, path = make_market(tmp_path, dividends=divs, end=date(2024, 3, 29))
    m = load_market(store, path, closed_week)
    cfg = BacktestConfig(start=date(2024, 1, 1), end=date(2024, 1, 16), label="t")
    res = Runner(store, m, cfg, [MomentumForecaster(), RandomForecaster(1)]).run()      # antes: OutOfOrderEvent
    s = res["summary"]
    assert s["simulation_bound"] == "2024-01-16"
    w3 = next(w for w in res["weeks"] if w["week_id"] == "2024-W03")
    assert w3["status"] == "invalid:no_sessions" and "hasta el límite" in w3["note"]
    for name in ("Q0", "A1"):
        assert s["forecasters"][name]["final_valuation"]["events_processed_through"] == "2024-01-16"
        assert s["forecasters"][name]["final_valuation"]["receivables"] == 0.0                # el dividendo del 18-01 no se reconoce


def test_r11_03_r11_04_forecasters_must_share_market_and_par_value_with_the_runner(tmp_path):
    store, path = make_market(tmp_path, end=date(2024, 6, 28))
    m = load_market(store, path, CAL)
    cfg = BacktestConfig(start=date(2024, 1, 1), end=date(2024, 3, 29), label="t", par_value=D(5))
    with pytest.raises(ValueError, match="par_value"):
        Runner(store, m, cfg, [TabularForecaster(m, min_weeks=10), RandomForecaster(1)])
    other = load_market(store, path, CAL)
    with pytest.raises(ValueError, match="different MarketData"):
        Runner(store, m, BacktestConfig(start=date(2024, 1, 1), end=date(2024, 3, 29), label="t"), [TabularForecaster(other, min_weeks=10), RandomForecaster(1)])


def test_r11_05_markdown_report_keeps_uncertainty_states():
    from twlab.backtest import markdown_report
    result = {"summary": {"period": ["2024-01-01", "2024-01-12"], "manifest": "m", "universe_size": 2, "weeks_operated": 1, "weeks_invalid_no_sessions": 0,
                          "weeks_pending_outcome": [], "assumptions": {"baseline": "A1"}, "universe_ew": {"mean_weekly_gross_open_close": None},
                          "forecasters": {"Q0": {"model_id": "q0", "mean_weekly_net_return_open_close": None, "mean_weekly_gross_pick_return": None,
                                                 "mean_costs_over_invested": None, "weeks_positive": 0, "final_equity": None,
                                                 "final_valuation": {"error": "missing price"},
                                                 "paired_excess_vs_baseline": {"baseline": "A1", "error": "degenerate resampling"}},
                                          "A1": {"model_id": "a1", "mean_weekly_net_return_open_close": None, "mean_weekly_gross_pick_return": None,
                                                 "mean_costs_over_invested": None, "weeks_positive": 0, "final_equity": 1.0, "final_valuation": {}}}},
              "weeks": [{"week_id": "2024-W02", "status": "valid", "pending_outcome": False,
                         "forecasters": {"Q0": {"picks": [{"symbol": "A", "name": "A"}], "stale_prices": ["stale_price:A:2024-01-11"]},
                                         "A1": {"picks": [{"symbol": "B", "name": "B"}], "stale_prices": []}}}]}
    md = markdown_report(result, title="t")
    assert "desconocido: missing price" in md and "no estimable: degenerate resampling" in md
    assert "sin intervalo medible (precio obsoleto)" in md and "→ pendiente" not in md


def test_r10_07_r09_06_period_end_is_respected_and_entries_before_the_bound_are_executed(tmp_path):
    store, path = make_market(tmp_path)                          # datos hasta el viernes 29-03-2024
    m = load_market(store, path, CAL)
    # fin del periodo un miércoles: la entrada del lunes 8-01 se ejecuta, la salida del viernes 12-01 queda pendiente
    cfg = BacktestConfig(start=date(2024, 1, 1), end=date(2024, 1, 10), label="t")
    res = Runner(store, m, cfg, [MomentumForecaster(), RandomForecaster(1)]).run()
    s = res["summary"]
    assert s["simulation_bound"] == "2024-01-10" and s["weeks_pending_outcome"] == ["2024-W02"]
    w = next(w for w in res["weeks"] if w["week_id"] == "2024-W02")
    assert w["forecasters"]["Q0"]["filled"] == 5 and w["forecasters"]["Q0"].get("portfolio_net_return_open_close") is None
    assert s["forecasters"]["Q0"]["final_valuation"]["valued_at"].startswith("2024-01-10")
    assert s["forecasters"]["Q0"]["final_valuation"]["positions_value"] > 0          # las posiciones siguen abiertas
    assert s["forecasters"]["Q0"]["baskets_in_follow_up_at_end"] == ["2024-W02"]
    # y con más datos archivados que el periodo pedido no se consulta nada posterior: mismo resultado
    store2, path2 = make_market(tmp_path / "longer", end=date(2024, 6, 28))
    res2 = Runner(store2, load_market(store2, path2, CAL), cfg, [MomentumForecaster(), RandomForecaster(1)]).run()
    assert res2["summary"]["simulation_bound"] == "2024-01-10" and res2["summary"]["weeks_pending_outcome"] == ["2024-W02"]
    # periodo que termina el domingo del corte: el lunes cae después del límite y sólo se emite la selección
    cfg3 = BacktestConfig(start=date(2024, 1, 1), end=date(2024, 1, 7), label="t")
    res3 = Runner(store, m, cfg3, [MomentumForecaster(), RandomForecaster(1)]).run()
    w3 = res3["weeks"][0]
    assert w3["pending_outcome"] and "filled" not in w3["forecasters"]["Q0"] and w3["forecasters"]["Q0"]["picks"]


def test_r10_02_tabular_forecaster_rejects_non_increasing_cutoffs(tmp_path):
    store, path = make_market(tmp_path, end=date(2024, 6, 28))
    m = load_market(store, path, CAL)
    f = TabularForecaster(m, min_weeks=10)
    f.maybe_train(taipei(date(2024, 3, 3), time(18, 0)))
    with pytest.raises(ValueError, match="non-decreasing"):
        f.maybe_train(taipei(date(2024, 2, 4), time(18, 0)))
    f.maybe_train(taipei(date(2024, 3, 10), time(18, 0)))          # avanzar sí


def test_end_to_end_synthetic_run_pairs_forecasters_and_reproduces_with_the_same_seed(tmp_path):
    store, path = make_market(tmp_path, end=date(2024, 6, 28))
    cfg = BacktestConfig(start=date(2024, 1, 1), end=date(2024, 6, 28), label="t", block_length=2, n_boot=200)
    m = load_market(store, path, CAL)
    res = Runner(store, m, cfg, [MomentumForecaster(), TabularForecaster(m, min_weeks=10), RandomForecaster(cfg.seed)]).run()
    s = res["summary"]
    assert s["weeks_operated"] >= 20 and set(s["forecasters"]) == {"Q0", "Q1", "A1"}
    assert s["forecasters"]["Q0"]["paired_excess_vs_baseline"]["n_used"] >= 15
    assert s["forecasters"]["Q1"]["weeks_selected"] >= 15 and any("q1:" in h for h in s["forecasters"]["Q1"]["training_history"])
    # la selección de A1 no depende de qué otros pronosticadores participen
    m2 = load_market(store, path, CAL)
    res2 = Runner(store, m2, cfg, [MomentumForecaster(), RandomForecaster(cfg.seed)]).run()
    for w1, w2 in zip(res["weeks"], res2["weeks"]):
        if w1["status"] == "valid":
            assert w1["forecasters"]["A1"]["picks"] == w2["forecasters"]["A1"]["picks"]
