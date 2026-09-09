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


def test_ridge_recovers_a_linear_signal():
    import random
    rng = random.Random(0)
    X = [[rng.gauss(0, 1) for _ in range(3)] for _ in range(400)]
    y = [2 * x[0] - x[1] + 0.1 * rng.gauss(0, 1) for x in X]
    m = q1.RidgeRank(alpha=0.1).fit(X, y)
    pred = m.predict(X)
    corr = sum((p - sum(pred) / len(pred)) * (t - sum(y) / len(y)) for p, t in zip(pred, y))
    assert corr > 0 and abs(m.w[0] / m.w[1] + 2) < 0.2
