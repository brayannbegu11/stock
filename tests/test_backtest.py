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
from twlab.timeutil import taipei as _taipei
from datetime import time
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


def test_r12_01_conflicting_rights_are_discarded_for_ledger_and_labels_alike(tmp_path):
    ex = date(2024, 1, 10)
    rows = dividend_rows("A", ex_date=ex, cash=2.0, pay=date(2024, 2, 1)) + dividend_rows("A", ex_date=ex, cash=10.0, pay=date(2024, 2, 1))
    store, path = make_market(tmp_path, dividends={"A": rows})
    m = load_market(store, path, CAL)
    a = m.securities[m.by_symbol["A"]]
    assert [e.ambiguous for e in a.events] == [True] and any("different values" in w and "AMBIGUOUS" in w for w in m.warnings)
    # una fila inválida (pago antes de la fecha ex) hace ambiguo el derecho aunque otra fila sea válida
    rows2 = dividend_rows("A", ex_date=ex, cash=10.0, pay=date(2024, 1, 9)) + dividend_rows("A", ex_date=ex, cash=2.0, pay=date(2024, 2, 1))
    store2, path2 = make_market(tmp_path / "b", dividends={"A": rows2})
    m2 = load_market(store2, path2, CAL)
    assert [e.ambiguous for e in m2.securities[m2.by_symbol["A"]].events] == [True] and any("pay_before_ex" in w for w in m2.warnings)
    # filas idénticas repetidas: un solo evento, con la identidad del libro, compartido por Q1 y el coordinador
    rows3 = dividend_rows("A", ex_date=ex, cash=2.0, pay=date(2024, 2, 1)) * 2
    store3, path3 = make_market(tmp_path / "c", dividends={"A": rows3})
    m3 = load_market(store3, path3, CAL)
    ev = m3.securities[m3.by_symbol["A"]].events
    assert len(ev) == 1 and ev[0].event_id.endswith(":cash:2024-01-10:2024") and ev[0].pay_date == date(2024, 2, 1)
    f = TabularForecaster(m3, min_weeks=10)
    assert f.dividends[m3.by_symbol["A"]] is ev
    # R11-01: fecha de anuncio sin hora → apertura de la sesión siguiente (política del protocolo), calidad conservative_inference
    rows4 = dividend_rows("A", ex_date=ex, cash=2.0, pay=date(2024, 2, 1))
    rows4[0]["AnnouncementTime"] = ""
    rows4[0]["AnnouncementDate"] = "2023-12-01"                                  # viernes
    store4, path4 = make_market(tmp_path / "d", dividends={"A": rows4})
    ev4 = load_market(store4, path4, CAL).securities["TWSE:A@2023-01-02"].events[0]
    assert ev4.known_at == taipei(date(2023, 12, 4), time(9, 0)) and ev4.known_quality == "conservative_inference"


def _cash_row(sid, ex, cash, pay, *, year="2024", ann_date="2023-12-01", ann_time="8:0:0"):
    return {"stock_id": sid, "year": year, "AnnouncementDate": ann_date, "AnnouncementTime": ann_time,
            "CashEarningsDistribution": cash, "CashStatutorySurplus": 0, "StockEarningsDistribution": 0, "StockStatutorySurplus": 0,
            "CashExDividendTradingDate": ex, "CashDividendPaymentDate": pay, "StockExDividendTradingDate": ""}


def test_r13_02_to_05_contradictory_rights_become_ambiguous_and_invalidate_labels_and_intervals(tmp_path):
    from twlab.backtest import validated_dividend_events
    from twlab.sources.finmind import dividends_from_rows
    from twlab.models import q1
    ex = "2024-01-10"

    def events_for(rows):
        return validated_dividend_events("TWSE:A@2023-01-02", dividends_from_rows(rows, stock_id="A"), D(10), CAL)
    # R13-02: 10 y 0 TWD para el mismo derecho: ambiguo, no «10»
    ev, pr = events_for([_cash_row("A", ex, 10.0, "2024-02-01"), _cash_row("A", ex, 0, "2024-02-01")])
    assert [e.ambiguous for e in ev] == [True] and pr and "zero and positive" in pr[0]
    # R13-03: importe infinito: ambiguo (el libro lo rechazaría)
    ev, pr = events_for([_cash_row("A", ex, "Infinity", "2024-02-01")])
    assert [e.ambiguous for e in ev] == [True] and "non_finite" in pr[0]
    # R13-04: periodo vacío frente a 2024 para el mismo derecho: un solo grupo, ambiguo (no dos derechos)
    ev, pr = events_for([_cash_row("A", ex, 10.0, "2024-02-01"), _cash_row("A", ex, 10.0, "2024-02-01", year="")])
    assert len(ev) == 1 and ev[0].ambiguous and "missing_period" in pr[0]
    # R13-05: mismo derecho con anuncios distintos (uno posterior a la fecha ex): ambiguo, nunca «sin dividendo»
    ev, pr = events_for([_cash_row("A", ex, 10.0, "2024-02-01", ann_date="2024-01-02"), _cash_row("A", ex, 10.0, "2024-02-01", ann_date="2024-02-01")])
    assert [e.ambiguous for e in ev] == [True]
    # filas idénticas repetidas: un derecho válido; sólo ceros: ningún derecho
    ev, pr = events_for([_cash_row("A", ex, 10.0, "2024-02-01")] * 3)
    assert len(ev) == 1 and not ev[0].ambiguous and pr == []
    assert events_for([_cash_row("A", ex, 0, "")]) == ([], [])
    # una etiqueta cuya semana contiene un derecho ambiguo no existe
    entry, exit_ = date(2024, 1, 8), date(2024, 1, 12)
    by = {entry: q1.BarLike(entry, D(100), D(100), D(1), taipei(entry, time(13, 30))), exit_: q1.BarLike(exit_, D(100), D(100), D(1), taipei(exit_, time(13, 30)))}
    amb = q1.DividendLike("A:cash:2024-01-10:2024", date(2024, 1, 10), "cash", ambiguous=True)
    assert q1.weekly_label(by, entry, exit_, [amb]) is None
    # y el coordinador invalida el intervalo del tenedor (cantidad incierta), sin fabricar un retorno sin dividendo
    store, path = make_market(tmp_path, dividends={"A": [_cash_row("A", ex, 10.0, "2024-02-01"), _cash_row("A", ex, 0, "2024-02-01")]})
    m = load_market(store, path, CAL)

    class OnlyA:
        name, model_id, version = "Q0", "rule:only_a", "t"

        def forecast(self, view, plan, candidates, *, slots):
            from twlab.backtest import Selection
            a = next(c for c in candidates if c.symbol == "A")
            return [Selection(a.security_id, 1.0, [a.doc_id])], {"training_manifest_id": None}
    res = Runner(store, m, BacktestConfig(start=date(2024, 1, 1), end=date(2024, 1, 12), label="t", slots=1), [OnlyA(), RandomForecaster(1)]).run()
    w = res["weeks"][0]
    assert any("ambiguous_right" in f for f in w["forecasters"]["Q0"]["stale_prices"])
    assert w["paired"]["Q0"]["paired"] is False and "ambiguous_right" in w["paired"]["Q0"]["unpaired_reason"]
    assert w.get("ambiguous_rights")


def test_r14_03_r14_05_r14_08_ambiguity_survives_liquidation_and_voids_gross_returns(tmp_path):
    def stock_row(per_share):
        return {"stock_id": "A", "year": "2024", "AnnouncementDate": "2023-12-01", "AnnouncementTime": "8:0:0", "CashEarningsDistribution": 0,
                "CashStatutorySurplus": 0, "StockEarningsDistribution": per_share, "StockStatutorySurplus": 0, "CashExDividendTradingDate": "",
                "CashDividendPaymentDate": "", "StockExDividendTradingDate": "2024-01-10"}
    store, path = make_market(tmp_path, dividends={"A": [stock_row(10.0), stock_row(0)]}, end=date(2024, 3, 29))
    m = load_market(store, path, CAL)

    class AThenB:
        name, model_id, version = "Q0", "rule:a_then_b", "t"

        def forecast(self, view, plan, candidates, *, slots):
            from twlab.backtest import Selection
            sym = "A" if plan.week_id == "2024-W02" else "B"
            c = next(c for c in candidates if c.symbol == sym)
            return [Selection(c.security_id, 1.0, [c.doc_id])], {"training_manifest_id": None}
    res = Runner(store, m, BacktestConfig(start=date(2024, 1, 1), end=date(2024, 1, 19), label="t", slots=1), [AThenB(), RandomForecaster(1)]).run()
    w2, w3 = res["weeks"][0], res["weeks"][1]
    q2, q3 = w2["forecasters"]["Q0"], w3["forecasters"]["Q0"]
    # R14-05: la selección con derecho ambiguo no tiene rentabilidad bruta ni media
    assert q2["picks"][0]["gross_return"] is None and q2["mean_gross_pick_return"] is None
    # R14-03: vendida la cantidad registrada, la incertidumbre persiste: la semana siguiente (sólo B) tampoco es medible
    assert any(f.startswith("ambiguous_right:") for f in q3["stale_prices"]) and w3["paired"]["Q0"]["paired"] is False
    s = res["summary"]["forecasters"]["Q0"]
    assert s["ambiguous_claims"] and any(f.startswith("ambiguous_right:") for f in s["final_valuation"]["flags"])
    # la media bruta publicada excluye la semana ambigua (sólo queda la selección limpia de B)
    assert s["mean_weekly_gross_pick_return"] == pytest.approx(q3["mean_gross_pick_return"])
    assert not any(w.get("action_errors") for w in res["weeks"])                # R14-08: la forma exacta se aplica sin errores del libro


def test_r14_06_r15_05_forecaster_refuses_a_market_whose_content_changed_underneath(tmp_path):
    from dataclasses import replace
    from twlab.models import q1
    store, path = make_market(tmp_path, end=date(2024, 6, 28))
    for mutate in ("capture", "bar", "event", "calendar", "ex_date"):
        m = load_market(store, path, CAL)
        f = TabularForecaster(m, min_weeks=10)
        f.maybe_train(taipei(date(2024, 3, 3), time(18, 0)))
        sec = next(iter(m.securities.values()))
        if mutate == "capture":
            sec.price_capture = archive(store, "TaiwanStockPrice", sec.symbol, price_rows(sec.symbol, date(2023, 1, 2), date(2024, 6, 28), seed=7))
        elif mutate == "bar":                                    # mismo identificador de captura, otro cierre en memoria
            b = sec.bars[-100]
            sec.bars[-100] = replace(b, close=b.close * 2)
        elif mutate == "event":                                  # un derecho que aparece o cambia sin cambiar capturas
            sec.events.append(q1.DividendLike("x:cash:2024-01-10:2024", date(2024, 1, 10), "cash", cash_per_share=D(10), known_at=taipei(date(2023, 12, 1))))
        elif mutate == "ex_date":                                # misma identidad de evento, otra fecha ex (R15-05 parcial)
            sec.events.append(q1.DividendLike("x:cash:2024-01-10:2024", date(2024, 1, 10), "cash", cash_per_share=D(10), known_at=taipei(date(2023, 12, 1))))
            f = TabularForecaster(m, min_weeks=10)
            f.maybe_train(taipei(date(2024, 3, 3), time(18, 0)))
            sec.events[-1] = replace(sec.events[-1], ex_date=date(2024, 1, 11))
        else:                                                    # otro calendario con la MISMA etiqueta de versión pero distinto contenido (R15-05)
            m.calendar = TradingCalendar(start=CAL.start, end=CAL.end, closures=[date(2024, 1, 12)], source_id=CAL.source_id, recorded_at=CAL.recorded_at, version=CAL.version)
        with pytest.raises(ValueError, match="changed"):
            f.maybe_train(taipei(date(2024, 3, 10), time(18, 0)))


def test_r15_06_r15_07_new_lots_keep_gross_returns_and_the_report_flags_uncertain_equity(tmp_path):
    from twlab.backtest import markdown_report
    def stock_row(per_share):
        return {"stock_id": "A", "year": "2024", "AnnouncementDate": "2023-12-01", "AnnouncementTime": "8:0:0", "CashEarningsDistribution": 0,
                "CashStatutorySurplus": 0, "StockEarningsDistribution": per_share, "StockStatutorySurplus": 0, "CashExDividendTradingDate": "",
                "CashDividendPaymentDate": "", "StockExDividendTradingDate": "2024-01-10"}
    store, path = make_market(tmp_path, dividends={"A": [stock_row(10.0), stock_row(0)]}, end=date(2024, 3, 29))
    m = load_market(store, path, CAL)

    class AlwaysA:
        name, model_id, version = "Q0", "rule:always_a", "t"

        def forecast(self, view, plan, candidates, *, slots):
            from twlab.backtest import Selection
            c = next(c for c in candidates if c.symbol == "A")
            return [Selection(c.security_id, 1.0, [c.doc_id])], {"training_manifest_id": None}
    res = Runner(store, m, BacktestConfig(start=date(2024, 1, 1), end=date(2024, 1, 19), label="t", slots=1), [AlwaysA(), RandomForecaster(1)]).run()
    q2, q3 = res["weeks"][0]["forecasters"]["Q0"], res["weeks"][1]["forecasters"]["Q0"]
    assert q2["picks"][0]["gross_return"] is None                              # el lote que sufrió el derecho ambiguo
    assert q3["picks"][0]["gross_return"] is not None and q3["mean_gross_pick_return"] is not None   # R15-06: el lote nuevo conserva su bruto
    assert any(f.startswith("ambiguous_right:") for f in q3["stale_prices"])    # pero el patrimonio sigue incierto
    md = markdown_report(res, title="t")
    assert "PROVISIONAL" in md and "ambiguous_right" in md                    # R15-07: el patrimonio final se publica calificado


def test_r13_06_unresolved_delisting_makes_the_interval_unmeasurable(tmp_path):
    store, path = make_market(tmp_path)
    mf = json.loads(path.read_text(encoding="utf-8"))
    mf["delisted"].append({"symbol": "A", "name": "name-A", "delisting_date": "2024-01-09"})
    path.write_text(json.dumps(mf), encoding="utf-8")
    m = load_market(store, path, CAL)

    class OnlyA:
        name, model_id, version = "Q0", "rule:only_a", "t"

        def forecast(self, view, plan, candidates, *, slots):
            from twlab.backtest import Selection
            a = next(c for c in candidates if c.symbol == "A")
            return [Selection(a.security_id, 1.0, [a.doc_id])], {"training_manifest_id": None}
    res = Runner(store, m, BacktestConfig(start=date(2024, 1, 1), end=date(2024, 1, 12), label="t", slots=1), [OnlyA(), RandomForecaster(1)]).run()
    w = res["weeks"][0]
    q0 = w["forecasters"]["Q0"]
    assert any(f.startswith("unresolved_terminal:") for f in q0["stale_prices"]) and q0["portfolio_net_return_open_close"] is None
    assert w["paired"]["Q0"]["paired"] is False and "unresolved_terminal" in w["paired"]["Q0"]["unpaired_reason"]


def test_r13_07_stock_dividend_uses_the_exact_par_ratio_end_to_end(tmp_path):
    from twlab.backtest import validated_dividend_events
    from twlab.sources.finmind import dividends_from_rows
    row = {"stock_id": "A", "year": "2024", "AnnouncementDate": "2023-12-01", "AnnouncementTime": "8:0:0", "CashEarningsDistribution": 0,
           "CashStatutorySurplus": 0, "StockEarningsDistribution": 1.0, "StockStatutorySurplus": 0, "CashExDividendTradingDate": "",
           "CashDividendPaymentDate": "", "StockExDividendTradingDate": "2024-01-10"}
    ev, _ = validated_dividend_events("TWSE:A@2023-01-02", dividends_from_rows([row], stock_id="A"), D(3), CAL)
    assert ev[0].stock_per_share == D(1) and ev[0].par_value == D(3)


def test_r12_02_valuation_after_a_right_without_a_later_price_is_flagged(tmp_path):
    closed_week = TradingCalendar(start=CAL.start, end=CAL.end, closures=[date(2024, 1, d) for d in range(15, 20)],
                                  source_id="synthetic", recorded_at=CAL.recorded_at, version="closed-W03")
    def stock_row(year, ex, per_share):
        return {"stock_id": "A", "year": year, "AnnouncementDate": "2023-11-01", "AnnouncementTime": "8:0:0",
                "CashEarningsDistribution": 0, "CashStatutorySurplus": 0, "StockEarningsDistribution": per_share, "StockStatutorySurplus": 0,
                "CashExDividendTradingDate": "", "CashDividendPaymentDate": "", "StockExDividendTradingDate": ex}
    # 5 % en acciones el 10-01 deja un lote suelto tras la salida del 12-01 (n×1.000 acciones → n×50 sueltas);
    # 1:1 el 15-01 (semana cerrada) lo duplica sin que exista precio posterior al derecho
    stock_div = [stock_row("2022", "2024-01-10", 0.5), stock_row("2023", "2024-01-15", 10.0)]
    store, path = make_market(tmp_path, dividends={"A": stock_div}, end=date(2024, 3, 29))
    m = load_market(store, path, closed_week)
    cfg = BacktestConfig(start=date(2024, 1, 1), end=date(2024, 1, 16), label="t", slots=1)

    class OnlyA:
        name, model_id, version = "Q0", "rule:only_a", "t"

        def forecast(self, view, plan, candidates, *, slots):
            from twlab.backtest import Selection
            a = next(c for c in candidates if c.symbol == "A")
            return [Selection(a.security_id, 1.0, [a.doc_id])], {"training_manifest_id": None}
    res = Runner(store, m, cfg, [OnlyA(), RandomForecaster(1)]).run()
    fv = res["summary"]["forecasters"]["Q0"]["final_valuation"]
    assert any(fl.startswith("price_predates_right:TWSE:A@2023-01-02:2024-01-15") for fl in fv["flags"]), fv["flags"]


def test_r12_03_degenerate_bootstrap_serialises_without_nan(tmp_path):
    store, path = make_market(tmp_path, end=date(2024, 3, 29))
    m = load_market(store, path, CAL)
    cfg = BacktestConfig(start=date(2024, 1, 1), end=date(2024, 1, 12), label="t", block_length=1)   # una sola semana operada
    res = Runner(store, m, cfg, [MomentumForecaster(), RandomForecaster(1)]).run()
    pe = res["summary"]["forecasters"]["Q0"]["paired_excess_vs_baseline"]
    assert pe["degenerate"] and pe["ci95"] is None and pe["n_fixed_observations"] == 1
    json.dumps(res, default=str, allow_nan=False)                                # no lanza


def test_r10_05_delisting_date_declared_in_captures_is_used(tmp_path):
    store, path = make_market(tmp_path, overrides={"A": {"delisting_date": "2024-02-15"}})
    m = load_market(store, path, CAL)
    assert m.securities[m.by_symbol["A"]].delisting_date == date(2024, 2, 15)
    mf = json.loads(path.read_text(encoding="utf-8"))
    mf["delisted"].append({"symbol": "A", "name": "A", "delisting_date": "2024-03-01"})
    path.write_text(json.dumps(mf), encoding="utf-8")
    with pytest.raises(ManifestInconsistent):
        load_market(store, path, CAL)


def test_r16_02_r16_03_daily_market_provenance_and_last_kept_capture(tmp_path):
    from twlab.backtest import load_market_daily
    from twlab.master import SecurityMaster, SecurityVersion, security_id_for
    from twlab.sources import twse_daily as td
    from tests.test_twse_daily import _put, twse_body, tpex_body, TWSE_FIELDS
    store = RawStore(tmp_path)
    master = SecurityMaster()
    for market, sym in (("TWSE", "2035"), ("TPEX", "6488")):
        sid = security_id_for(market, sym, date(2023, 1, 2))
        master.add(SecurityVersion(security_id=sid, issuer_id=sid, symbol=sym, name_zh=sym, market=market, board="main",
                                   instrument_type="ordinary_equity", valid_from=date(2023, 1, 2), valid_to=None, recorded_at=taipei(date(2024, 1, 1)), source_id="t"))
    caps = {}
    for d, price in ((date(2024, 1, 4), "100"), (date(2024, 1, 5), "--")):        # 2035: precio el 4-01, sin precio regular el 5-01
        row = ["2035", "x", "1,000", "1", "100,000", price, price, price, price, "+", "0"]
        caps[d] = _put(store, "twse", f"{td.TWSE_DATASET}/{d.isoformat()}", twse_body(d.strftime("%Y%m%d"), [row]))
        trow = ["6488", "y", "50", "+1", "50", "50", "50", "50", "1,000", "50,000", "1"] + [""] * 6
        _put(store, "tpex", f"{td.TPEX_DATASET}/{d.isoformat()}", tpex_body(d.strftime("%Y%m%d"), [trow]))
    m = load_market_daily(store, CAL, master, as_of=date(2024, 1, 10), start=date(2024, 1, 4), end=date(2024, 1, 5))
    a = m.securities[m.by_symbol["2035"]]
    assert [b.session for b in a.bars] == [date(2024, 1, 4)]
    assert a.price_capture.capture_id == caps[date(2024, 1, 4)].capture_id             # R16-03: la captura de la última barra conservada
    assert a.source_id == "twse" and a.derivation == td.TWSE_DERIVATION                # R16-02: procedencia de la fuente real
    assert a.bar_captures == {date(2024, 1, 4): caps[date(2024, 1, 4)].capture_id}
    b = m.securities[m.by_symbol["6488"]]
    assert b.source_id == "tpex" and b.derivation == td.TPEX_DERIVATION and len(b.bar_captures) == 2
    # el documento del paquete lleva esa procedencia y enumera las capturas de cada sesión
    from twlab.weekly import plan_week
    cfg = BacktestConfig(start=date(2024, 1, 1), end=date(2024, 1, 5), label="t")
    r = Runner(store, m, cfg, [MomentumForecaster(), RandomForecaster(1)])
    plan = plan_week(taipei(date(2024, 1, 7), time(18, 0)), CAL)
    packet, _, _ = r.build_week_packet(plan)
    doc = next(d for d in packet.admitted if d.security_ids == (b.security_id,))
    assert doc.source_id == "tpex" and doc.derivation == td.TPEX_DERIVATION and doc.payload["captures_doc"] == "tpex:captures:2024-W02"
    assert doc.capture_id == b.bar_captures[date(2024, 1, 5)]
    manifest = next(d for d in packet.admitted if d.doc_id == "tpex:captures:2024-W02")
    assert manifest.kind == "capture_manifest" and manifest.payload["session_captures"] == {d.isoformat(): c for d, c in b.bar_captures.items()}
    assert manifest.capture_id == b.bar_captures[date(2024, 1, 5)] and manifest.available_at <= plan.cutoff_at
    twse_manifest = next(d for d in packet.admitted if d.doc_id == "twse:captures:2024-W02")
    assert list(twse_manifest.payload["session_captures"]) == ["2024-01-04"]      # la sesión sin precio regular no respalda ninguna barra


def test_r16_07_and_user_scenario_flags_and_odd_lot_costs(tmp_path):
    from twlab.backtest import markdown_report
    result = {"summary": {"period": ["2024-01-01", "2024-01-12"], "manifest": "m", "universe_size": 2, "weeks_operated": 1, "weeks_invalid_no_sessions": 0,
                          "weeks_pending_outcome": [], "assumptions": {"baseline": "A1"}, "universe_ew": {"mean_weekly_gross_open_close": None},
                          "forecasters": {"Q0": {"model_id": "q0", "mean_weekly_net_return_open_close": None, "mean_weekly_gross_pick_return": None,
                                                 "mean_costs_over_invested": None, "weeks_positive": 0, "final_equity": 100000.0,
                                                 "final_valuation": {"flags": ["stale_price:TWSE:A@2023-01-02:2024-01-11"]}, "ambiguous_claims": []},
                                          "A1": {"model_id": "a1", "mean_weekly_net_return_open_close": None, "mean_weekly_gross_pick_return": None,
                                                 "mean_costs_over_invested": None, "weeks_positive": 0, "final_equity": 1.0, "final_valuation": {"flags": []}}}},
              "weeks": []}
    md = markdown_report(result, title="t")
    assert "PROVISIONAL" in md and "stale_price" in md                                   # R16-07
    # escenario del usuario: lotes sueltos con comisión mínima
    store, path = make_market(tmp_path, end=date(2024, 3, 29))
    m = load_market(store, path, CAL)
    cfg = BacktestConfig(start=date(2024, 1, 1), end=date(2024, 1, 19), label="t", notional=5_000, lot_size=1, min_commission_twd=D(20))
    res = Runner(store, m, cfg, [MomentumForecaster(), RandomForecaster(1)]).run()
    w = res["weeks"][0]["forecasters"]["Q0"]
    assert w["filled"] == 5 and w["failed"] == 0                                        # con lotes de 1 acción todo cabe
    # 0,1425 % de 5.000 TWD son 7 TWD, pero el mínimo de 20 se aplica por lado: la fricción de ida y vuelta supera el 1,2 %
    assert w["costs_over_invested"] > 0.012
    assert res["summary"]["assumptions"]["lot_size"] == 1 and D(str(res["summary"]["assumptions"]["costs"]["min_commission_twd"])) == D(20)
    # sin mínimo, la misma orden paga sólo el porcentaje
    cfg0 = BacktestConfig(start=date(2024, 1, 1), end=date(2024, 1, 19), label="t", notional=5_000, lot_size=1)
    res0 = Runner(store, load_market(store, path, CAL), cfg0, [MomentumForecaster(), RandomForecaster(1)]).run()
    assert res0["weeks"][0]["forecasters"]["Q0"]["costs_over_invested"] < 0.009


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
    assert "sin intervalo medible (stale_price)" in md and "→ pendiente" not in md


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


def _daily_market(tmp_path):
    """Mercado diario mínimo (dos fuentes, dos sesiones) con capturas por sesión, como en el R16-02."""
    from twlab.backtest import load_market_daily
    from twlab.master import SecurityMaster, SecurityVersion, security_id_for
    from twlab.sources import twse_daily as td
    from tests.test_twse_daily import _put, twse_body, tpex_body
    store = RawStore(tmp_path)
    master = SecurityMaster()
    for market, sym in (("TWSE", "2035"), ("TPEX", "6488")):
        sid = security_id_for(market, sym, date(2023, 1, 2))
        master.add(SecurityVersion(security_id=sid, issuer_id=sid, symbol=sym, name_zh=sym, market=market, board="main",
                                   instrument_type="ordinary_equity", valid_from=date(2023, 1, 2), valid_to=None, recorded_at=taipei(date(2024, 1, 1)), source_id="t"))
    for d in (date(2024, 1, 4), date(2024, 1, 5)):
        row = ["2035", "x", "1,000", "1", "100,000", "100", "100", "100", "100", "+", "0"]
        _put(store, "twse", f"{td.TWSE_DATASET}/{d.isoformat()}", twse_body(d.strftime("%Y%m%d"), [row]))
        trow = ["6488", "y", "50", "+1", "50", "50", "50", "50", "1,000", "50,000", "1"] + [""] * 6
        _put(store, "tpex", f"{td.TPEX_DATASET}/{d.isoformat()}", tpex_body(d.strftime("%Y%m%d"), [trow]))
    market = load_market_daily(store, CAL, master, as_of=date(2024, 1, 10), start=date(2024, 1, 4), end=date(2024, 1, 5))
    return store, market


def test_r17_02_replacing_a_session_capture_changes_data_version_and_stops_q1(tmp_path):
    from twlab.backtest import TabularForecaster
    _, market = _daily_market(tmp_path)
    sec = market.securities[market.by_symbol["6488"]]
    before = market.data_version
    f = TabularForecaster(market, min_weeks=1)
    sec.bar_captures[date(2024, 1, 4)] = sec.bar_captures[date(2024, 1, 5)]
    assert market.data_version != before
    with pytest.raises(ValueError):
        f.maybe_train(taipei(date(2024, 1, 7), time(18)))


def test_r17_03_series_with_a_session_without_capture_reference_is_not_admitted(tmp_path):
    from twlab.weekly import plan_week
    store, market = _daily_market(tmp_path)
    sec = market.securities[market.by_symbol["6488"]]
    del sec.bar_captures[date(2024, 1, 4)]
    cfg = BacktestConfig(start=date(2024, 1, 1), end=date(2024, 1, 5), label="t")
    r = Runner(store, market, cfg, [MomentumForecaster(), RandomForecaster(1)])
    packet, _, candidates = r.build_week_packet(plan_week(taipei(date(2024, 1, 7), time(18, 0)), CAL))
    assert not any(d.security_ids == (sec.security_id,) for d in packet.admitted)
    c = next(c for c in candidates if c.security_id == sec.security_id)
    assert not c.eligible and not c.scorable and c.reasons == ("provenance_incomplete:1_sessions_without_capture",)
    manifest = next(d for d in packet.admitted if d.doc_id == "tpex:captures:2024-W02")
    assert list(manifest.payload["session_captures"]) == ["2024-01-05"]
    other = market.securities[market.by_symbol["2035"]]
    assert any(d.security_ids == (other.security_id,) for d in packet.admitted)       # la serie íntegra sigue admitida


def test_r17_10_pending_week_records_the_known_entry_status_of_each_pick(tmp_path):
    from twlab.backtest import load_market
    store, path = make_market(tmp_path)
    market = load_market(store, path, CAL)
    cfg = BacktestConfig(start=date(2024, 3, 18), end=date(2024, 3, 27), label="t", notional=1_000_000, slots=5)
    r = Runner(store, market, cfg, [MomentumForecaster(), RandomForecaster(1)])
    r.run()
    pending = [w for w in r.weeks if w.get("pending_outcome")]
    assert pending, "la última semana debe quedar pendiente de desenlace"
    fr = pending[-1]["forecasters"]["Q0"]
    assert fr["picks"], "hay selecciones"
    assert all(p.get("entry_status") in ("filled", "entry_failed") for p in fr["picks"])
    assert sum(p["entry_status"] == "filled" for p in fr["picks"]) == fr["filled"]
    assert sum(p["entry_status"] == "entry_failed" for p in fr["picks"]) == fr["failed"]
    # R19-03: los costes de las compras ya ejecutadas se publican aunque la salida esté pendiente
    assert fr["costs_twd"] > 0 and fr["costs_denominator_twd"] > 0 and fr["costs_scope"] == "entries_only_pending_exit"
    assert abs(fr["costs_over_invested"] - fr["costs_twd"] / fr["costs_denominator_twd"]) < 1e-12


def test_r18_01_empty_capture_map_on_a_daily_source_is_not_a_single_capture_series(tmp_path):
    from twlab.weekly import plan_week
    store, market = _daily_market(tmp_path)
    for sec in market.securities.values():
        sec.bar_captures.clear()
    cfg = BacktestConfig(start=date(2024, 1, 1), end=date(2024, 1, 5), label="t")
    r = Runner(store, market, cfg, [MomentumForecaster(), RandomForecaster(1)])
    packet, _, candidates = r.build_week_packet(plan_week(taipei(date(2024, 1, 7), time(18, 0)), CAL))
    assert not any(d.kind == "price_bar_series" for d in packet.admitted)
    assert all(c.reasons[0].startswith("provenance_incomplete:") for c in candidates) and len(candidates) == 2


def test_r18_02_conflicting_session_captures_between_series_stop_the_packet(tmp_path):
    from twlab.backtest import ManifestInconsistent
    from twlab.weekly import plan_week
    store, market = _daily_market(tmp_path)
    import copy
    a = market.securities[market.by_symbol["2035"]]
    b = copy.deepcopy(a)
    b.bar_captures[date(2024, 1, 4)] = "twse:MI_INDEX_ALLBUT0999/2024-01-04:2024-01-05T00:00:00+00:00:other-revision"
    market.securities["TWSE:9999@2023-01-02"] = b
    cfg = BacktestConfig(start=date(2024, 1, 1), end=date(2024, 1, 5), label="t")
    r = Runner(store, market, cfg, [MomentumForecaster(), RandomForecaster(1)])
    with pytest.raises(ManifestInconsistent):
        r.build_week_packet(plan_week(taipei(date(2024, 1, 7), time(18, 0)), CAL))


def test_r18_07_summary_counts_measurable_weeks_separately(tmp_path):
    from twlab.backtest import load_market, markdown_report
    store, path = make_market(tmp_path)
    market = load_market(store, path, CAL)
    cfg = BacktestConfig(start=date(2024, 2, 5), end=date(2024, 3, 29), label="t", notional=1_000_000, slots=5)
    r = Runner(store, market, cfg, [MomentumForecaster(), RandomForecaster(1)])
    res = r.run()
    for name, e in res["summary"]["forecasters"].items():
        measured = sum(1 for w in res["weeks"] if w["status"] == "valid" and not w.get("pending_outcome")
                       and w["forecasters"][name].get("portfolio_net_return_open_close") is not None)
        assert e["weeks_measured"] == measured and e["weeks_positive"] <= e["weeks_measured"]
    report = markdown_report(res, title="t")
    assert f"{res['summary']['forecasters']['Q0']['weeks_positive']}/{res['summary']['forecasters']['Q0']['weeks_measured']}" in report


def test_weekly_rerun_reuses_identical_packets_and_forecasts_and_keeps_first_ingestion(tmp_path):
    """Ciclo semanal: una segunda corrida con la misma etiqueta de archivo no duplica paquetes ni predicciones idénticas."""
    from twlab.backtest import load_market
    store, path = make_market(tmp_path)
    market = load_market(store, path, CAL)
    cfg = BacktestConfig(start=date(2024, 3, 4), end=date(2024, 3, 15), label="run_a", archive_label="lab", notional=1_000_000, slots=5)
    Runner(store, market, cfg, [MomentumForecaster(), RandomForecaster(1)]).run()
    packets1 = store.captures(source_id="packet"); forecasts1 = store.captures(source_id="forecast")
    assert packets1 and all(r.dataset.startswith("lab/") for r in packets1)
    cfg2 = BacktestConfig(start=date(2024, 3, 4), end=date(2024, 3, 22), label="run_b", archive_label="lab", notional=1_000_000, slots=5)
    Runner(store, market, cfg2, [MomentumForecaster(), RandomForecaster(1)]).run()
    packets2 = store.captures(source_id="packet"); forecasts2 = store.captures(source_id="forecast")
    weeks1 = {r.dataset for r in packets1}
    assert {r.dataset for r in packets2 if r.dataset in weeks1} == weeks1
    assert len([r for r in packets2 if r.dataset in weeks1]) == len(packets1)      # ninguna semana repetida se volvió a archivar
    assert len(packets2) == len(packets1) + 1                                      # sólo la semana nueva
    assert len(forecasts2) == len(forecasts1) + 2
    for r in packets1:
        assert store.find(source_id="packet", dataset=r.dataset, extra_equal={"packet_hash": r.extra["packet_hash"]}).capture_id == r.capture_id


def test_r20_01_week_records_carry_the_exact_forecast_identity(tmp_path):
    from twlab.backtest import load_market
    store, path = make_market(tmp_path)
    market = load_market(store, path, CAL)
    cfg = BacktestConfig(start=date(2024, 3, 4), end=date(2024, 3, 15), label="t", archive_label="lab", notional=1_000_000, slots=5)
    r = Runner(store, market, cfg, [MomentumForecaster(), RandomForecaster(1)])
    res = r.run()
    w = res["weeks"][0]
    assert w["packet_capture"] and w["packet_hash"]
    for name, x in w["forecasters"].items():
        rec = store.get(x["forecast_capture_id"])
        assert rec.sha256 == x["forecast_sha256"] and rec.dataset == f"lab/{name}/{w['week_id']}"
        assert x["deadline_at"] and datetime.fromisoformat(x["deadline_at"]).tzinfo is not None


def test_r20_04_reused_packet_and_forecast_bytes_are_verified(tmp_path):
    from twlab.backtest import load_market, ManifestInconsistent
    store, path = make_market(tmp_path)
    market = load_market(store, path, CAL)
    cfg = BacktestConfig(start=date(2024, 3, 4), end=date(2024, 3, 15), label="a", archive_label="lab", notional=1_000_000, slots=5)
    Runner(store, market, cfg, [MomentumForecaster(), RandomForecaster(1)]).run()
    pkt = store.captures(source_id="packet")[0]
    (store.root / pkt.path).write_bytes(b'{"corrupt":true}')
    cfg2 = BacktestConfig(start=date(2024, 3, 4), end=date(2024, 3, 15), label="b", archive_label="lab", notional=1_000_000, slots=5)
    bad = Runner(store, market, cfg2, [MomentumForecaster(), RandomForecaster(1)]).run()["weeks"][0]
    # el rechazo sigue siendo deliberado (ManifestInconsistent), contenido en la semana: no se emite ni se evalúa (R26-03)
    assert bad["status"] == "invalid:archive" and bad["archive_error"].startswith("ManifestInconsistent")
    assert not any(x.get("picks") or x.get("forecast_sha256") for x in bad["forecasters"].values())
    # un forecast corrupto no se reutiliza: se vuelve a archivar con bytes íntegros
    store2, path2 = make_market(tmp_path / "b")
    market2 = load_market(store2, path2, CAL)
    Runner(store2, market2, cfg, [MomentumForecaster(), RandomForecaster(1)]).run()
    fc = store2.captures(source_id="forecast")[0]
    (store2.root / fc.path).write_bytes(b'{"corrupt":true}')
    n_before = len(store2.captures(source_id="forecast"))
    res = Runner(store2, market2, cfg2, [MomentumForecaster(), RandomForecaster(1)]).run()
    assert len(store2.captures(source_id="forecast")) == n_before + 1
    name = fc.dataset.split("/")[1]
    assert res["weeks"][0]["forecasters"][name]["forecast_capture_id"] != fc.capture_id


def test_r23_01_runner_archives_the_master_snapshot_once_and_links_every_week(tmp_path):
    """Cada semana enlaza la instantánea del maestro con la que se resolvieron símbolos y nombres; bytes idénticos se reutilizan."""
    from twlab.backtest import load_market, master_snapshot_bytes
    store, path = make_market(tmp_path)
    market = load_market(store, path, CAL)
    cfg = BacktestConfig(start=date(2024, 3, 4), end=date(2024, 3, 15), label="a", archive_label="lab", notional=1_000_000, slots=5)
    res = Runner(store, market, cfg, [MomentumForecaster(), RandomForecaster(1)]).run()
    masters = store.captures(source_id="master")
    assert len(masters) == 1 and masters[0].dataset == "lab/master"
    assert all(w["master_capture"] == masters[0].capture_id and w["master_sha256"] == masters[0].sha256 for w in res["weeks"])
    payload = store.read(masters[0])
    assert payload == master_snapshot_bytes(market.master)
    # cada predicción archivada declara el maestro con el que se resolvió, archivado antes que ella (R24-02)
    for w in res["weeks"]:
        for name, x in w["forecasters"].items():
            frec = store.get(x["forecast_capture_id"])
            assert json.loads(store.read(frec))["master_sha256"] == masters[0].sha256
            assert frec.ingested_at_dt >= masters[0].ingested_at_dt
    # la instantánea vuelve a cargarse fila a fila con las validaciones del maestro y reproduce la vista efectiva (R24-03)
    from twlab.master import SecurityMaster, SecurityVersion
    m2 = SecurityMaster()
    for r in (json.loads(l) for l in payload.decode("utf-8").splitlines()):
        r.pop("kind")
        for k in ("valid_from", "valid_to"):
            r[k] = date.fromisoformat(r[k]) if r[k] else None
        r["recorded_at"] = datetime.fromisoformat(r["recorded_at"])
        m2.add(SecurityVersion(**r))
    assert {(v.security_id, v.valid_from, v.symbol, v.valid_to) for v in m2._effective(None)} == \
           {(v.security_id, v.valid_from, v.symbol, v.valid_to) for v in market.master._effective(None)}
    rows = [json.loads(l) for l in payload.decode("utf-8").splitlines()]
    assert {r["security_id"] for r in rows} == set(market.securities) and all(r["kind"] == "segment" for r in rows)
    for r in rows:
        assert market.securities[r["security_id"]].symbol == r["symbol"]
    # segunda corrida con la misma etiqueta: misma instantánea, sin duplicar
    cfg2 = BacktestConfig(start=date(2024, 3, 4), end=date(2024, 3, 22), label="b", archive_label="lab", notional=1_000_000, slots=5)
    res2 = Runner(store, market, cfg2, [MomentumForecaster(), RandomForecaster(1)]).run()
    assert len(store.captures(source_id="master")) == 1
    assert all(w["master_capture"] == masters[0].capture_id for w in res2["weeks"])
    # instantánea corrupta: se vuelve a archivar con bytes íntegros
    (store.root / masters[0].path).write_bytes(b"corrupt")
    cfg3 = BacktestConfig(start=date(2024, 3, 4), end=date(2024, 3, 15), label="c", archive_label="lab", notional=1_000_000, slots=5)
    res3 = Runner(store, market, cfg3, [MomentumForecaster(), RandomForecaster(1)]).run()
    fresh = [m for m in store.captures(source_id="master") if m.capture_id != masters[0].capture_id]
    assert len(fresh) == 1 and store.read(fresh[0]) == payload and all(w["master_capture"] == fresh[0].capture_id for w in res3["weeks"])


def test_r25_02_master_snapshot_corrupted_between_weeks_is_rearchived_before_use(tmp_path):
    """Dentro de una misma corrida, la instantánea se verifica en cada semana: si se corrompe, se vuelve a archivar."""
    from twlab.backtest import load_market, _sundays
    store, path = make_market(tmp_path)
    market = load_market(store, path, CAL)
    cfg = BacktestConfig(start=date(2024, 3, 4), end=date(2024, 3, 22), label="a", archive_label="lab", notional=1_000_000, slots=5)
    r = Runner(store, market, cfg, [MomentumForecaster(), RandomForecaster(1)])
    sundays = list(_sundays(cfg.start, cfg.end))
    assert len(sundays) >= 2
    r.run_week(sundays[0])
    first = store.get(r.weeks[-1]["master_capture"])
    (store.root / first.path).write_bytes(b"corrupt")
    r.run_week(sundays[1])
    w = r.weeks[-1]
    fresh = store.get(w["master_capture"])
    assert fresh.capture_id != first.capture_id and fresh.sha256 == first.sha256
    store.read(fresh)                                                     # íntegra
    for name, x in w["forecasters"].items():
        assert json.loads(store.read(store.get(x["forecast_capture_id"])))["master_sha256"] == fresh.sha256
    # una copia íntegra ya existente (aunque no sea la primera) se reutiliza en la semana siguiente
    if len(sundays) >= 3:
        r.run_week(sundays[2])
        assert r.weeks[-1]["master_capture"] == fresh.capture_id


def test_r26_02_master_changes_during_a_run_are_archived_and_cited(tmp_path):
    """Si el maestro cambia entre semanas de la misma corrida, la semana siguiente cita una instantánea nueva."""
    from twlab.backtest import load_market, _sundays
    from datetime import datetime, timezone
    store, path = make_market(tmp_path)
    market = load_market(store, path, CAL)
    cfg = BacktestConfig(start=date(2024, 3, 4), end=date(2024, 3, 22), label="a", archive_label="lab", notional=1_000_000, slots=5)
    r = Runner(store, market, cfg, [MomentumForecaster(), RandomForecaster(1)])
    sundays = list(_sundays(cfg.start, cfg.end))
    r.run_week(sundays[0])
    first = store.get(r.weeks[-1]["master_capture"])
    sid = market.by_symbol["A"]
    seen = market.master.current_segment(sid).recorded_at + timedelta(seconds=1)      # una revisión se registra después de la fila previa
    market.master.close_version(sid, valid_to=sundays[1], recorded_at=seen, source_id="fixture")
    r.run_week(sundays[1])
    w = r.weeks[-1]
    second = store.get(w["master_capture"])
    assert second.capture_id != first.capture_id and second.sha256 != first.sha256
    rows = [json.loads(l) for l in store.read(second).decode("utf-8").splitlines()]
    assert any(row["security_id"] == sid and row["valid_to"] == sundays[1].isoformat() for row in rows)
    for name, x in w["forecasters"].items():
        assert json.loads(store.read(store.get(x["forecast_capture_id"])))["master_sha256"] == second.sha256


def test_r26_03_missing_master_copy_falls_back_to_another_intact_copy(tmp_path):
    from twlab.backtest import load_market, _sundays, master_snapshot_bytes
    store, path = make_market(tmp_path)
    market = load_market(store, path, CAL)
    cfg = BacktestConfig(start=date(2024, 3, 4), end=date(2024, 3, 22), label="a", archive_label="lab", notional=1_000_000, slots=5)
    r = Runner(store, market, cfg, [MomentumForecaster(), RandomForecaster(1)])
    sundays = list(_sundays(cfg.start, cfg.end))
    r.run_week(sundays[0])
    first = store.get(r.weeks[-1]["master_capture"])
    second = store.put(source_id="master", dataset="lab/master", payload=master_snapshot_bytes(market.master), url="u")
    (store.root / first.path).unlink()
    r.run_week(sundays[1])
    assert r.weeks[-1]["master_capture"] == second.capture_id and r.weeks[-1]["status"] == "valid"


def test_r26_03_missing_forecast_copy_is_rearchived(tmp_path):
    from twlab.backtest import load_market
    store, path = make_market(tmp_path)
    market = load_market(store, path, CAL)
    cfg = BacktestConfig(start=date(2024, 3, 4), end=date(2024, 3, 15), label="a", archive_label="lab", notional=1_000_000, slots=5)
    res = Runner(store, market, cfg, [MomentumForecaster(), RandomForecaster(1)]).run()
    x = res["weeks"][0]["forecasters"]["Q0"]
    (store.root / store.get(x["forecast_capture_id"]).path).unlink()
    cfg2 = BacktestConfig(start=date(2024, 3, 4), end=date(2024, 3, 15), label="b", archive_label="lab", notional=1_000_000, slots=5)
    res2 = Runner(store, market, cfg2, [MomentumForecaster(), RandomForecaster(1)]).run()
    y = res2["weeks"][0]["forecasters"]["Q0"]
    assert y["forecast_sha256"] == x["forecast_sha256"] and y["forecast_capture_id"] != x["forecast_capture_id"]
    store.read(store.get(y["forecast_capture_id"]))


@pytest.mark.parametrize("target,bad", [("manifest", "invalid_json"), ("manifest", "non_object"), ("packet", "missing"), ("packet", "corrupt")])
def test_r26_03_archive_failures_are_contained_per_week(tmp_path, target, bad):
    """Un índice corrupto o un paquete archivado ilegible dejan la semana registrada como invalid:archive; no escapa ninguna excepción."""
    from twlab.backtest import load_market
    from twlab.store import ManifestCorrupt
    store, path = make_market(tmp_path)
    market = load_market(store, path, CAL)
    cfg = BacktestConfig(start=date(2024, 3, 4), end=date(2024, 3, 15), label="a", archive_label="lab", notional=1_000_000, slots=5)
    res = Runner(store, market, cfg, [MomentumForecaster(), RandomForecaster(1)]).run()
    if target == "manifest":
        (store.root / "manifest.jsonl").write_bytes(b"{bad" if bad == "invalid_json" else b"[]")
        with pytest.raises(ManifestCorrupt):
            store.captures()
    else:
        p = store.root / store.get(res["weeks"][0]["packet_capture"]).path
        if bad == "missing":
            p.unlink()
        else:
            p.write_bytes(b'{"corrupt":true}')
    cfg2 = BacktestConfig(start=date(2024, 3, 4), end=date(2024, 3, 15), label="b", archive_label="lab", notional=1_000_000, slots=5)
    res2 = Runner(store, market, cfg2, [MomentumForecaster(), RandomForecaster(1)]).run()
    w = res2["weeks"][0]
    assert w["status"] == "invalid:archive" and w["archive_error"]
    assert not any(x.get("picks") or x.get("forecast_sha256") for x in w["forecasters"].values())     # sin listas; libro gestionado
    assert res2["summary"]["weeks_invalid_archive"] == [w["week_id"]] and res2["summary"]["weeks_operated"] == 0
    from twlab.backtest import markdown_report
    assert "invalid:archive" in markdown_report(res2, title="t")


_ROOT = Path(__file__).resolve().parents[1]

def _run_with_failure(tmp_path, *, failure="packet", start=date(2024, 2, 5), end=date(2024, 3, 15), fail_last=True):
    """Corrida con un fallo del archivo inyectado en la última semana (paquete o predicción); devuelve store, market, result."""
    from twlab.backtest import load_market, _sundays
    from twlab.weekly import plan_week
    from twlab.timeutil import taipei
    store, path = make_market(tmp_path)
    market = load_market(store, path, CAL)
    cfg = BacktestConfig(start=start, end=end, label="a", archive_label="lab", notional=1_000_000, slots=5)
    sundays = list(_sundays(start, end))
    target = plan_week(taipei(sundays[-1] if fail_last else sundays[0], time(18, 0)), CAL).week_id
    original = store.find
    def fail(**kwargs):
        if kwargs["source_id"] == failure and kwargs["dataset"].endswith(target):
            raise OSError("injected disk read failure")
        return original(**kwargs)
    store.find = fail
    q1 = MomentumForecaster(); q1.name = "Q1"
    res = Runner(store, market, cfg, [MomentumForecaster(), q1, RandomForecaster(1)]).run()
    store.find = original
    return store, market, res, target


def test_r27_03_master_changed_between_snapshot_and_emission_fails_the_week(tmp_path):
    from twlab.backtest import load_market, _sundays
    store, path = make_market(tmp_path)
    market = load_market(store, path, CAL)
    cfg = BacktestConfig(start=date(2024, 3, 4), end=date(2024, 3, 15), label="a", archive_label="lab", notional=1_000_000, slots=5)
    r = Runner(store, market, cfg, [MomentumForecaster(), RandomForecaster(1)])
    sid = market.by_symbol["A"]
    original = r.master_record
    def archive_then_close():
        rec = original()
        seen = market.master.current_segment(sid).recorded_at + timedelta(seconds=1)
        market.master.close_version(sid, valid_to=date(2024, 3, 9), recorded_at=seen, source_id="fixture")
        return rec
    r.master_record = archive_then_close
    r.run_week(list(_sundays(cfg.start, cfg.end))[0])
    w = r.weeks[-1]
    assert w["status"] == "invalid:archive" and "master changed during emission" in w["archive_error"]
    assert w["forecasters"] and all("forecast_sha256" in x for x in w["forecasters"].values())     # traza conservada


def test_r27_05_a_failed_week_still_manages_inherited_baskets(tmp_path):
    """Una salida bloqueada la semana anterior se reintenta en el último cierre de la semana fallida."""
    from twlab.backtest import load_market, _sundays
    from twlab.weekly import plan_week
    from twlab.timeutil import taipei
    store, path = make_market(tmp_path)
    market = load_market(store, path, CAL)
    cfg = BacktestConfig(start=date(2024, 2, 26), end=date(2024, 3, 22), label="a", archive_label="lab", notional=1_000_000, slots=5)
    sundays = list(_sundays(cfg.start, cfg.end))
    assert len(sundays) >= 3
    p1 = plan_week(taipei(sundays[0], time(18, 0)), CAL)
    exit1 = p1.exit_at.date()
    for sid in list(market.by_session):                       # sin cierre el viernes de la primera semana: salidas bloqueadas
        market.by_session[sid].pop(exit1, None)
        market.securities[sid].bars = [b for b in market.securities[sid].bars if b.session != exit1]
    r = Runner(store, market, cfg, [MomentumForecaster(), RandomForecaster(1)])
    r.run_week(sundays[0])
    blocked = [s for _, ss in r.open_slots["Q0"] for s in ss if s.status == "exit_blocked"]
    assert blocked
    p2 = plan_week(taipei(sundays[1], time(18, 0)), CAL)
    original = store.find
    def fail(**kwargs):
        if kwargs["source_id"] == "packet" and kwargs["dataset"].endswith(p2.week_id):
            raise OSError("injected disk read failure")
        return original(**kwargs)
    store.find = fail
    r.run_week(sundays[1])
    store.find = original
    w2 = r.weeks[-1]
    assert w2["status"] == "invalid:archive" and w2["pending_outcome"] is False
    assert all(x.get("equity_end") is not None for x in w2["forecasters"].values())
    for s in blocked:                                          # vendida en el último cierre de la semana fallida, no después
        assert s.status == "exited" and s.exit is not None and s.exit.at.date() == p2.exit_at.date()
    assert not any(s.status == "exit_blocked" for _, ss in r.open_slots["Q0"] for s in ss)


@pytest.mark.parametrize("field,value", [("capture_id", []), ("capture_id", {}), ("extra", []), ("ingested_at", "not-a-time")])
def test_r27_06_malformed_index_records_are_contained_in_the_week(tmp_path, field, value):
    from twlab.backtest import load_market
    store, path = make_market(tmp_path)
    market = load_market(store, path, CAL)
    cfg = BacktestConfig(start=date(2024, 3, 4), end=date(2024, 3, 15), label="a", archive_label="lab", notional=1_000_000, slots=5)
    res = Runner(store, market, cfg, [MomentumForecaster(), RandomForecaster(1)]).run()
    cid = res["weeks"][0]["packet_capture"]
    rows = [json.loads(l) for l in (store.root / "manifest.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    for row in rows:
        if row["capture_id"] == cid:
            row[field] = value
    (store.root / "manifest.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    cfg2 = BacktestConfig(start=date(2024, 3, 4), end=date(2024, 3, 15), label="b", archive_label="lab", notional=1_000_000, slots=5)
    w = Runner(store, market, cfg2, [MomentumForecaster(), RandomForecaster(1)]).run()["weeks"][0]
    assert w["status"] == "invalid:archive" and w["archive_error"].startswith("ManifestCorrupt")


@pytest.mark.parametrize("failure", ["packet", "forecast"])
def test_r27_07_report_headers_support_a_failed_current_week(tmp_path, failure):
    import importlib.util
    store, market, res, target = _run_with_failure(tmp_path, failure=failure)
    assert res["weeks"][-1]["status"] == "invalid:archive" and res["weeks"][-1]["week_id"] == target
    spec = importlib.util.spec_from_file_location("assemble_backtest_reports", _ROOT / "scripts" / "assemble_backtest_reports.py")
    asm = importlib.util.module_from_spec(spec); spec.loader.exec_module(asm)
    for name in ("header_15", "header_15b", "header_15c"):
        fn = getattr(asm, name)
        text = fn(res) if name == "header_15" else fn(res, res)
        assert "invalid:archive" in text and target in text, name


@pytest.mark.parametrize("failure", ["packet", "forecast"])
def test_r27_08_exporter_and_site_show_the_failed_week(tmp_path, monkeypatch, failure):
    import importlib.util, shutil, subprocess, sys
    store, market, res, target = _run_with_failure(tmp_path, failure=failure)
    spec = importlib.util.spec_from_file_location("export_site_data", _ROOT / "scripts" / "export_site_data.py")
    ex = importlib.util.module_from_spec(spec); spec.loader.exec_module(ex)
    monkeypatch.setattr(ex, "RAW", store.root); monkeypatch.setattr(ex, "STORE", tmp_path)
    monkeypatch.setattr(ex, "SCENARIOS", [("standard", "a", "fixture.md")])
    for name, value in [("export_rounds", []), ("export_docs", []), ("count_tests", 0), ("raw_coverage", {}), ("master_stats", {})]:
        monkeypatch.setattr(ex, name, lambda v=value: v)
    (tmp_path / "backtest_a.json").write_text(json.dumps(res, default=str), encoding="utf-8")
    out = ex.build()
    sc = out["scenarios"][0]
    w = [x for x in sc["weeks"] if x["week_id"] == target][0]
    assert w["status"] == "invalid:archive" and w["archive_error"] and w["prospective"] is False and "invalid:archive" in w["forecast_reasons"]
    assert sc["current_week"]["week_id"] == target and sc["current_week"]["status"] == "invalid:archive"
    assert sc["weeks_invalid_archive"] == [target]
    if failure == "forecast":                                  # la traza de lo archivado antes del fallo se conserva
        assert w["forecasters"]
    node = shutil.which("node")
    if not node:
        pytest.skip("node no disponible")
    site = tmp_path / "site.json"; site.write_text(json.dumps(out), encoding="utf-8")
    r = subprocess.run([node, str(_ROOT / "tests" / "site_render.cjs"), str(site)], capture_output=True, text=True, encoding="utf-8", cwd=str(_ROOT))
    assert r.returncode == 0, r.stderr[-800:]
    rendered = json.loads(r.stdout)
    expected = {"es": "semana no emitida: fallo del archivo", "en": "week not issued: archive failure", "zh": "該週未發布：存檔故障"}
    reason = {"es": "semana no emitida: fallo del archivo", "en": "week not issued: archive failure", "zh": "該週未發布：存檔故障"}
    for lang in ("es", "en", "zh"):
        assert expected[lang] in rendered[lang]["week"] and "injected disk read failure" in rendered[lang]["week"], lang
        assert reason[lang] in rendered[lang]["table"], lang


@pytest.mark.parametrize("value", [None, [], {}])
def test_r27_06_market_without_a_security_master_is_contained(tmp_path, value):
    from twlab.backtest import load_market, _sundays
    store, path = make_market(tmp_path)
    market = load_market(store, path, CAL)
    cfg = BacktestConfig(start=date(2024, 3, 4), end=date(2024, 3, 15), label="a", archive_label="lab", notional=1_000_000, slots=5)
    market.master = value
    r = Runner(store, market, cfg, [MomentumForecaster(), RandomForecaster(1)])
    r.run_week(list(_sundays(cfg.start, cfg.end))[0])
    assert r.weeks[-1]["status"] == "invalid:archive" and "security master unavailable" in r.weeks[-1]["archive_error"]
