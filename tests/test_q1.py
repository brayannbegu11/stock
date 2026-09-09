"""Q1: contrato temporal de características y etiquetas, y funcionamiento del modelo con datos sintéticos."""
from datetime import date, datetime, time, timedelta
from decimal import Decimal as D

import pytest

from twlab.calendar import TradingCalendar
from twlab.models import q1
from twlab.timeutil import taipei

CAL = TradingCalendar(start=date(2023, 1, 1), end=date(2026, 12, 31), closures=[], source_id="synthetic", recorded_at=taipei(date(2023, 1, 1)))


def synthetic_bars(start: date, n: int, *, seed: int, drift: float = 0.0, lag_hours: int = 24) -> list[q1.BarLike]:
    import random
    rng = random.Random(seed)
    out, price, d = [], 100.0, start
    while len(out) < n:
        if CAL.is_session(d):
            price *= 1 + drift + rng.gauss(0, 0.02)
            close_at = taipei(d, time(13, 30))
            out.append(q1.BarLike(d, D(f"{price * 0.999:.2f}"), D(f"{price:.2f}"), D(1_000_000 + rng.randrange(500_000)),
                                  close_at + timedelta(hours=lag_hours)))
        d += timedelta(days=1)
    return out


def test_features_use_only_bars_available_at_the_cutoff():
    bars = synthetic_bars(date(2024, 1, 2), 200, seed=1)
    cutoff = taipei(date(2024, 9, 8), time(18, 0))                     # domingo
    f = q1.features_from_bars(bars, cutoff)
    assert f is not None and set(f) == set(q1.FEATURE_NAMES)
    # la barra del viernes 6-09 está disponible el sábado 7-09 13:30 (política 24 h): entra. La del lunes 9-09 no.
    known = [b for b in bars if b.available_at <= cutoff]
    assert known[-1].session == date(2024, 9, 6)
    # una barra futura plantada con precio absurdo no cambia nada porque no está disponible
    spiked = bars + [q1.BarLike(date(2024, 9, 9), D(1), D(99999), D(1), taipei(date(2024, 9, 10), time(13, 30)))]
    assert q1.features_from_bars(spiked, cutoff) == f
    # con menos de 121 barras no hay características
    assert q1.features_from_bars(bars[:100], cutoff) is None


def test_training_rows_only_carry_labels_known_at_the_current_cutoff():
    bars = {"SEC-A": synthetic_bars(date(2023, 1, 2), 600, seed=2), "SEC-B": synthetic_bars(date(2023, 1, 2), 600, seed=3)}
    cutoffs = []
    d = date(2023, 1, 1)
    while d < date(2025, 6, 1):
        cutoffs.append(taipei(d, time(18, 0)))
        d += timedelta(days=7)
    now = taipei(date(2024, 6, 2), time(18, 0))
    rows = q1.build_training_rows(bars, cutoffs, now_cutoff=now, calendar=CAL)
    assert rows
    assert all(r.cutoff_at < now for r in rows)
    assert all(r.label_known_at <= now for r in rows)
    # la semana cuyo corte es el domingo anterior (26-05) termina el viernes 31-05: su barra está disponible el sábado 1-06 → entra
    assert any(r.cutoff_at.date() == date(2024, 5, 26) for r in rows)
    # la semana del corte 2-06 (la actual) no tiene etiqueta conocida: no entra
    assert not any(r.cutoff_at.date() == date(2024, 6, 2) for r in rows)
    # coherencia de la etiqueta: apertura del lunes → cierre del viernes de ESA semana
    r0 = next(r for r in rows if r.cutoff_at.date() == date(2024, 5, 26) and r.security_id == "SEC-A")
    by = {b.session: b for b in bars["SEC-A"]}
    assert r0.label == pytest.approx(float(by[date(2024, 5, 31)].close) / float(by[date(2024, 5, 27)].open) - 1)


def test_q1_fits_and_ranks_and_refuses_with_too_little_history():
    bars = {f"SEC-{i}": synthetic_bars(date(2023, 1, 2), 500, seed=10 + i, drift=0.0005 * (i % 3)) for i in range(6)}
    cutoffs = [taipei(date(2023, 1, 1) + timedelta(days=7 * k), time(18, 0)) for k in range(120)]
    now = taipei(date(2025, 3, 2), time(18, 0))
    rows = q1.build_training_rows(bars, cutoffs, now_cutoff=now, calendar=CAL)
    assert q1.fit_q1(rows, trained_at=now, min_weeks=10_000) is None
    model = q1.fit_q1(rows, trained_at=now, min_weeks=20)
    assert model is not None and model.n_weeks >= 20 and model.training_manifest_id.startswith(q1.MODEL_ID)
    feats = [q1.features_from_bars(b, now) for b in bars.values()]
    scores = model.predict([f for f in feats if f is not None])
    assert len(scores) == 6 and all(0.0 <= s <= 1.0 for s in scores)
    assert sorted(scores) != scores or len(set(scores)) > 1


def test_r10_01_label_is_known_only_when_open_and_close_are_both_available():
    entry, exit_ = date(2024, 1, 8), date(2024, 1, 12)
    open_bar = q1.BarLike(entry, D(50), D(51), D(1), taipei(date(2024, 1, 20), time(13, 30)))     # apertura publicada tarde
    close_bar = q1.BarLike(exit_, D(99), D(100), D(1), taipei(date(2024, 1, 13), time(13, 30)))
    lab = q1.weekly_label({entry: open_bar, exit_: close_bar}, entry, exit_)
    assert lab is not None and lab[0] == pytest.approx(1.0) and lab[1] == open_bar.available_at
    bars = {"SEC-A": synthetic_bars(date(2023, 1, 2), 300, seed=4)}
    # sustituimos la apertura del 8-01-2024 por una disponible el 20-01: al corte del 14-01 la etiqueta no está madura
    late = [q1.BarLike(b.session, b.open, b.close, b.value_twd, taipei(date(2024, 1, 20), time(13, 30))) if b.session == entry else b
            for b in bars["SEC-A"]]
    cutoffs = [taipei(date(2024, 1, 7), time(18, 0))]
    assert q1.build_training_rows({"SEC-A": late}, cutoffs, now_cutoff=taipei(date(2024, 1, 14), time(18, 0)), calendar=CAL) == []
    assert len(q1.build_training_rows({"SEC-A": late}, cutoffs, now_cutoff=taipei(date(2024, 1, 21), time(18, 0)), calendar=CAL)) == 1


def test_r10_03_cache_retries_missing_outcomes_and_is_keyed_by_data_version():
    full = synthetic_bars(date(2023, 1, 2), 300, seed=5)
    cutoff = taipei(date(2024, 1, 7), time(18, 0))
    partial = [b for b in full if b.session <= date(2024, 1, 10)]          # aún sin el viernes 12-01
    cache: dict = {}
    assert q1.build_training_rows({"A": partial}, [cutoff], now_cutoff=taipei(date(2024, 1, 14), time(18, 0)), calendar=CAL, cache=cache) == []
    assert cache == {}                                                       # nada incompleto se guarda
    rows = q1.build_training_rows({"A": full}, [cutoff], now_cutoff=taipei(date(2024, 1, 14), time(18, 0)), calendar=CAL, cache=cache, data_version="v2")
    assert len(rows) == 1 and any(k[:3] == (cutoff, "A", "v2") for k in cache)
    assert q1.build_training_rows({"A": full}, [cutoff], now_cutoff=taipei(date(2024, 1, 14), time(18, 0)), calendar=CAL, cache=cache, data_version="v3")
    assert {k[2] for k in cache} == {"v2", "v3"}                            # otra versión de datos no reutiliza la anterior


def test_r10_04_ties_get_average_ranks_so_a_flat_component_cannot_cancel_signal():
    assert q1._rank01([1.0, 1.0, 1.0]) == [0.5, 0.5, 0.5]
    assert q1._rank01([3.0, 1.0, 2.0]) == [1.0, 0.0, 0.5]
    assert q1._rank01([2.0, 1.0, 2.0]) == [0.75, 0.0, 0.75]
    ridge = q1.RidgeRank(alpha=1.0)
    ridge.mu, ridge.sd, ridge.w, ridge.b = [0.0] * len(q1.FEATURE_NAMES), [1.0] * len(q1.FEATURE_NAMES), [1.0] + [0.0] * (len(q1.FEATURE_NAMES) - 1), 0.0

    class Flat:
        def predict(self, X):
            return [0.0] * len(X)
    model = q1.Q1Model(trained_at=taipei(date(2024, 1, 7)), n_rows=0, n_weeks=0, first_label_week="", last_label_week="", ridge=ridge, lgbm=Flat())
    feats = [{k: 0.0 for k in q1.FEATURE_NAMES} | {"ret_5": v} for v in (3.0, 1.0, 2.0)]
    scores = model.predict(feats)
    assert scores[0] > scores[2] > scores[1]                                 # el componente plano no borra el orden del informativo


def test_r10_08_r10_09_training_manifest_identifies_rows_and_config_and_label_is_total_return():
    bars = {f"SEC-{i}": synthetic_bars(date(2023, 1, 2), 500, seed=20 + i, drift=0.0004 * (i % 3)) for i in range(6)}
    cutoffs = [taipei(date(2023, 1, 1) + timedelta(days=7 * k), time(18, 0)) for k in range(120)]
    now = taipei(date(2025, 3, 2), time(18, 0))
    rows = q1.build_training_rows(bars, cutoffs, now_cutoff=now, calendar=CAL)
    m1 = q1.fit_q1(rows, trained_at=now, min_weeks=20, seed=1)
    m2 = q1.fit_q1(rows, trained_at=now, min_weeks=20, seed=2)                  # otra semilla → otra configuración
    flipped = [q1.TrainingRow(r.cutoff_at, r.security_id, r.features, -r.label, r.label_known_at) for r in rows]
    m3 = q1.fit_q1(flipped, trained_at=now, min_weeks=20, seed=1)              # otras etiquetas → otros datos
    ids = {m.training_manifest_id for m in (m1, m2, m3)}
    assert len(ids) == 3 and all("|data=" in i and "|cfg=" in i for i in ids)
    assert m1.first_label_week == q1.label_week_id(rows[0].cutoff_at) and q1.label_week_id(taipei(date(2024, 1, 7), time(18, 0))) == "2024-W02"
    # R10-08 (ronda 11): el hash de datos no redondea; diferencias diminutas que cambian los rangos cambian el identificador
    tiny = [q1.TrainingRow(r.cutoff_at, r.security_id, r.features, 1e-12 * (i % 3), r.label_known_at) for i, r in enumerate(rows)]
    tiny2 = [q1.TrainingRow(r.cutoff_at, r.security_id, r.features, 1e-12 * (2 - i % 3), r.label_known_at) for i, r in enumerate(rows)]
    assert q1.fit_q1(tiny, trained_at=now, min_weeks=20, seed=1).training_manifest_id != q1.fit_q1(tiny2, trained_at=now, min_weeks=20, seed=1).training_manifest_id
    # etiqueta de retorno total: apertura 100, cierre 50 tras dividendo en acciones 1:1 dentro de la semana → 0 %
    entry, exit_ = date(2024, 1, 8), date(2024, 1, 12)
    by = {entry: q1.BarLike(entry, D(100), D(100), D(1), taipei(entry, time(13, 30))), exit_: q1.BarLike(exit_, D(50), D(50), D(1), taipei(exit_, time(13, 30)))}
    known = taipei(date(2023, 12, 1))
    stock = q1.DividendLike("A:stock:2024-01-10:2023", date(2024, 1, 10), "stock", stock_ratio=D(1), known_at=known)
    cash = q1.DividendLike("A:cash:2024-01-10:2023", date(2024, 1, 10), "cash", cash_per_share=D(10), known_at=known)
    assert q1.weekly_label(by, entry, exit_)[0] == pytest.approx(-0.5)
    assert q1.weekly_label(by, entry, exit_, [stock])[0] == pytest.approx(0.0)
    assert q1.weekly_label(by, entry, exit_, [cash])[0] == pytest.approx(-0.4)
    # un derecho con fecha ex el propio día de entrada no pertenece al comprador; uno posterior a la salida tampoco
    outside = [q1.DividendLike("A:cash:2024-01-08:2023", entry, "cash", cash_per_share=D(10), known_at=known),
               q1.DividendLike("A:cash:2024-01-15:2023", date(2024, 1, 15), "cash", cash_per_share=D(10), known_at=known)]
    assert q1.weekly_label(by, entry, exit_, outside)[0] == pytest.approx(-0.5)


def test_r10_09_r11_01_r11_02_chained_rights_duplicates_and_announcement_availability():
    entry, exit_ = date(2024, 1, 8), date(2024, 1, 12)
    by = {entry: q1.BarLike(entry, D(100), D(100), D(1), taipei(entry, time(13, 30))), exit_: q1.BarLike(exit_, D(50), D(50), D(1), taipei(exit_, time(13, 30)))}
    known = taipei(date(2023, 12, 1))
    stock = q1.DividendLike("A:stock:2024-01-09:2023", date(2024, 1, 9), "stock", stock_ratio=D(1), known_at=known)
    cash = q1.DividendLike("A:cash:2024-01-11:2023", date(2024, 1, 11), "cash", cash_per_share=D(10), known_at=known)
    # R10-09: acciones 1:1 el 9-01 y 10 TWD por acción el 11-01 → 2×50 + 2×10 = 120 por acción inicial: +20 %
    assert q1.weekly_label(by, entry, exit_, [cash, stock])[0] == pytest.approx(0.20)
    # efectivo y acciones el mismo día: efectivo primero sobre la cantidad previa, como el libro
    same_day_cash = q1.DividendLike("A:cash:2024-01-09:2023", date(2024, 1, 9), "cash", cash_per_share=D(10), known_at=known)
    assert q1.weekly_label(by, entry, exit_, [stock, same_day_cash])[0] == pytest.approx((2 * 50 + 10) / 100 - 1)
    # R11-02: el mismo evento repetido cuenta una vez
    assert q1.weekly_label(by, entry, exit_, [stock, stock])[0] == pytest.approx(0.0)
    # R11-01: un derecho anunciado después del corte de entrenamiento no madura; sin instante conocido no hay etiqueta
    late = q1.DividendLike("A:cash:2024-01-10:2023", date(2024, 1, 10), "cash", cash_per_share=D(100), known_at=taipei(date(2024, 2, 1), time(8, 0)))
    lab = q1.weekly_label(by, entry, exit_, [late])
    assert lab is not None and lab[1] == late.known_at
    assert q1.weekly_label(by, entry, exit_, [q1.DividendLike("x", date(2024, 1, 10), "cash", cash_per_share=D(1))]) is None
    bars = {"A": synthetic_bars(date(2023, 1, 2), 300, seed=6)}
    cutoff = taipei(date(2024, 1, 7), time(18, 0))
    rows = q1.build_training_rows(bars, [cutoff], now_cutoff=taipei(date(2024, 1, 14), time(18, 0)), calendar=CAL, dividends_by_security={"A": [late]})
    assert rows == []                                                       # la etiqueta existe pero no está madura el 14-01
    rows = q1.build_training_rows(bars, [cutoff], now_cutoff=taipei(date(2024, 2, 4), time(18, 0)), calendar=CAL, dividends_by_security={"A": [late]})
    assert len(rows) == 1


def test_r10_03_cache_is_keyed_by_calendar_version_too():
    bars = {"A": synthetic_bars(date(2023, 1, 2), 300, seed=7)}
    cutoff = taipei(date(2024, 1, 7), time(18, 0))
    cache: dict = {}
    r1 = q1.build_training_rows(bars, [cutoff], now_cutoff=taipei(date(2024, 1, 21), time(18, 0)), calendar=CAL, cache=cache)
    closed_friday = TradingCalendar(start=CAL.start, end=CAL.end, closures=[date(2024, 1, 12)], source_id="synthetic", recorded_at=CAL.recorded_at, version="2")
    r2 = q1.build_training_rows(bars, [cutoff], now_cutoff=taipei(date(2024, 1, 21), time(18, 0)), calendar=closed_friday, cache=cache)
    assert len(cache) == 2 and r1[0].label != r2[0].label                   # otra versión del calendario: otra etiqueta, otra clave


def test_ridge_recovers_a_linear_signal():
    import random
    rng = random.Random(0)
    X = [[rng.gauss(0, 1) for _ in range(3)] for _ in range(400)]
    y = [2 * x[0] - x[1] + 0.1 * rng.gauss(0, 1) for x in X]
    m = q1.RidgeRank(alpha=0.1).fit(X, y)
    pred = m.predict(X)
    corr = sum((p - sum(pred) / len(pred)) * (t - sum(y) / len(y)) for p, t in zip(pred, y))
    assert corr > 0 and abs(m.w[0] / m.w[1] + 2) < 0.2
