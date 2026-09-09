"""Q1: modelo tabular compartido (lineal regularizado + gradient boosting) sobre barras nominales.

Contrato temporal (PIT):
- Las características de un valor en un corte T se calculan sólo con barras cuya ``available_at`` ≤ T.
- Las etiquetas de entrenamiento son rentabilidades **totales** apertura→cierre (dividendos en efectivo y
  en acciones con fecha ex dentro de la semana, según el protocolo) de semanas cuya apertura y cierre
  tienen ``available_at`` ≤ T. Una semana cuya apertura o cierre aún no está disponible en T no se etiqueta.
- El modelo se reentrena con cadencia declarada y sólo con filas anteriores al corte; el identificador del
  entrenamiento incluye el hash de las filas y de la configuración.

El objetivo es el **rango** cruzado de la rentabilidad semanal (0..1 dentro de cada semana, empates con
rango medio), no el nivel: reduce el peso de valores extremos y es lo que la cesta de cinco puestos
necesita (ordenar, no estimar). Sin fundamentales ni noticias todavía: modelo de precios/volumen modesto.
"""
from __future__ import annotations

import hashlib
import json
import math
import statistics
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Iterable, Mapping, Optional, Sequence

from ..calendar import TradingCalendar
from ..timeutil import to_utc
from ..weekly import plan_week

FEATURE_NAMES = (
    "ret_5", "ret_20", "ret_60", "ret_120", "vol_20", "vol_60", "log_value_20", "value_ratio_5_60",
    "dist_high_120", "missing_20", "ret_5_lag_20",
)
MODEL_ID = "q1:tabular_ridge_lgbm_rank_v2"
LGBM_PARAMS = dict(n_estimators=200, learning_rate=0.03, num_leaves=15, min_child_samples=50, subsample=0.8, subsample_freq=1,
                   colsample_bytree=0.8, reg_lambda=5.0, verbose=-1)


@dataclass(frozen=True)
class BarLike:
    """Subconjunto de una barra que Q1 necesita (compatible con ``sources.finmind.Bar``)."""
    session: date
    open: Decimal
    close: Decimal
    value_twd: Decimal
    available_at: datetime


@dataclass(frozen=True)
class DividendLike:
    """Derecho con fecha ex: efectivo por acción y/o acciones nuevas por acción (para la etiqueta de retorno total)."""
    ex_date: date
    cash_per_share: Decimal = Decimal(0)
    stock_ratio: Decimal = Decimal(0)


def features_from_bars(bars: Sequence[BarLike], cutoff_at: datetime, *, sessions_expected_20: int = 20) -> Optional[dict[str, float]]:
    """Características de un valor en el corte; ``None`` si no hay historial suficiente (121 barras)."""
    known = [b for b in bars if to_utc(b.available_at) <= to_utc(cutoff_at) and b.close > 0 and b.open > 0]
    if len(known) < 121:
        return None
    closes = [float(b.close) for b in known]
    values = [float(b.value_twd) for b in known]
    c = closes[-1]
    rets = [math.log(closes[i] / closes[i - 1]) for i in range(1, len(closes)) if closes[i - 1] > 0]
    return {
        "ret_5": math.log(c / closes[-6]), "ret_20": math.log(c / closes[-21]), "ret_60": math.log(c / closes[-61]),
        "ret_120": math.log(c / closes[-121]),
        "vol_20": statistics.pstdev(rets[-20:]) if len(rets) >= 20 else 0.0,
        "vol_60": statistics.pstdev(rets[-60:]) if len(rets) >= 60 else 0.0,
        "log_value_20": math.log(max(statistics.median(values[-20:]), 1.0)),
        "value_ratio_5_60": (statistics.fmean(values[-5:]) / max(statistics.fmean(values[-60:]), 1.0)),
        "dist_high_120": c / max(closes[-120:]) - 1.0,
        "missing_20": float(sessions_expected_20 - min(20, sum(1 for b in known[-20:] if (cutoff_at.date() - b.session).days <= 35))),
        "ret_5_lag_20": math.log(closes[-21] / closes[-26]),
    }


@dataclass
class TrainingRow:
    cutoff_at: datetime
    security_id: str
    features: dict[str, float]
    label: float                 # rentabilidad total apertura→cierre de la semana siguiente al corte
    label_known_at: datetime     # available_at más tardío de las barras usadas para la etiqueta (apertura y cierre)


def weekly_label(bars_by_session: Mapping[date, BarLike], entry_s: date, exit_s: date,
                 dividends: Iterable[DividendLike] = ()) -> Optional[tuple[float, datetime]]:
    """Retorno total apertura(entrada)→cierre(salida): derechos con fecha ex en (entrada, salida] (R10-09).

    El instante en que la etiqueta se conoce es el ``available_at`` más tardío de las dos barras (R10-01).
    """
    a, b = bars_by_session.get(entry_s), bars_by_session.get(exit_s)
    if a is None or b is None or a.open <= 0 or b.close <= 0:
        return None
    cash, factor = 0.0, 1.0
    for d in dividends:
        if entry_s < d.ex_date <= exit_s:
            cash += float(d.cash_per_share)
            factor *= 1.0 + float(d.stock_ratio)
    total = (float(b.close) * factor + cash) / float(a.open) - 1.0
    known_at = max(a.available_at, b.available_at, key=to_utc)
    return total, known_at


def _rank01(values: Sequence[float]) -> list[float]:
    """Rango en [0, 1]; los empates reciben el rango medio (R10-04): una señal constante vale 0,5 para todos."""
    n = len(values)
    if n <= 1:
        return [0.5] * n
    order = sorted(range(n), key=lambda i: values[i])
    out = [0.0] * n
    i = 0
    while i < n:
        j = i
        while j + 1 < n and values[order[j + 1]] == values[order[i]]:
            j += 1
        avg = (i + j) / 2 / (n - 1)
        for k in range(i, j + 1):
            out[order[k]] = avg
        i = j + 1
    return out


class RidgeRank:
    """Regresión ridge cerrada sobre características estandarizadas (sin dependencias)."""

    def __init__(self, alpha: float = 1.0) -> None:
        self.alpha = alpha
        self.mu: list[float] = []
        self.sd: list[float] = []
        self.w: list[float] = []
        self.b = 0.0

    def fit(self, X: Sequence[Sequence[float]], y: Sequence[float]) -> "RidgeRank":
        n, p = len(X), len(X[0])
        self.mu = [statistics.fmean(col) for col in zip(*X)]
        self.sd = [max(statistics.pstdev(col), 1e-9) for col in zip(*X)]
        Z = [[(row[j] - self.mu[j]) / self.sd[j] for j in range(p)] for row in X]
        ym = statistics.fmean(y)
        yc = [v - ym for v in y]
        A = [[sum(Z[i][j] * Z[i][k] for i in range(n)) + (self.alpha if j == k else 0.0) for k in range(p)] for j in range(p)]
        rhs = [sum(Z[i][j] * yc[i] for i in range(n)) for j in range(p)]
        for j in range(p):
            piv = max(range(j, p), key=lambda r: abs(A[r][j]))
            A[j], A[piv] = A[piv], A[j]
            rhs[j], rhs[piv] = rhs[piv], rhs[j]
            for r in range(j + 1, p):
                f = A[r][j] / A[j][j]
                for k in range(j, p):
                    A[r][k] -= f * A[j][k]
                rhs[r] -= f * rhs[j]
        w = [0.0] * p
        for j in range(p - 1, -1, -1):
            w[j] = (rhs[j] - sum(A[j][k] * w[k] for k in range(j + 1, p))) / A[j][j]
        self.w, self.b = w, ym
        return self

    def predict(self, X: Sequence[Sequence[float]]) -> list[float]:
        return [self.b + sum(self.w[j] * (row[j] - self.mu[j]) / self.sd[j] for j in range(len(self.w))) for row in X]


@dataclass
class Q1Model:
    trained_at: datetime
    n_rows: int
    n_weeks: int
    first_label_week: str
    last_label_week: str
    ridge: RidgeRank
    lgbm: object = None
    training_manifest_id: str = ""

    def predict(self, feats: Sequence[dict[str, float]]) -> list[float]:
        X = [[f[k] for k in FEATURE_NAMES] for f in feats]
        r = _rank01(self.ridge.predict(X))
        if self.lgbm is not None:
            g = _rank01(list(self.lgbm.predict(X)))
            return [(a + b) / 2 for a, b in zip(r, g)]
        return r


def build_training_rows(
    bars_by_security: Mapping[str, Sequence[BarLike]],
    cutoffs: Iterable[datetime],
    *,
    now_cutoff: datetime,
    calendar: TradingCalendar,
    dividends_by_security: Optional[Mapping[str, Sequence[DividendLike]]] = None,
    cache: Optional[dict] = None,
    data_version: str = "",
) -> list[TrainingRow]:
    """Filas (corte anterior, valor) con etiqueta conocida en ``now_cutoff``; nunca usa barras posteriores.

    La caché sólo guarda filas completas y su clave incluye ``data_version`` (R10-03): una fila sin
    desenlace se vuelve a intentar en cada llamada, y otra versión de los datos no reutiliza nada.
    """
    rows: list[TrainingRow] = []
    cache = cache if cache is not None else {}
    divs = dividends_by_security or {}
    for cutoff in cutoffs:
        if to_utc(cutoff) >= to_utc(now_cutoff):
            continue
        plan = plan_week(cutoff, calendar)
        if not plan.is_valid:
            continue
        entry_s, exit_s = plan.entry_at.date(), plan.exit_at.date()
        for sec, bars in bars_by_security.items():
            key = (cutoff, sec, data_version)
            row = cache.get(key)
            if row is None:
                feats = features_from_bars(bars, cutoff)
                lab = weekly_label({b.session: b for b in bars}, entry_s, exit_s, divs.get(sec, ())) if feats else None
                if feats and lab:
                    row = TrainingRow(cutoff, sec, feats, lab[0], lab[1])
                    cache[key] = row
            if row is not None and to_utc(row.label_known_at) <= to_utc(now_cutoff):
                rows.append(row)
    return rows


def label_week_id(cutoff_at: datetime) -> str:
    monday = cutoff_at.date() + timedelta(days=1)
    iso = monday.isocalendar()
    return f"{iso[0]}-W{iso[1]:02d}"


def fit_q1(rows: Sequence[TrainingRow], *, trained_at: datetime, min_weeks: int = 52, seed: int = 20260909) -> Optional[Q1Model]:
    by_week: dict[datetime, list[TrainingRow]] = {}
    for r in rows:
        by_week.setdefault(r.cutoff_at, []).append(r)
    if len(by_week) < min_weeks:
        return None
    X: list[list[float]] = []
    y: list[float] = []
    digest = hashlib.sha256()
    for cutoff, wrows in sorted(by_week.items()):
        wrows = sorted(wrows, key=lambda r: r.security_id)
        ranks = _rank01([r.label for r in wrows])
        for r, rk in zip(wrows, ranks):
            X.append([r.features[k] for k in FEATURE_NAMES])
            y.append(rk)
            digest.update(json.dumps([cutoff.isoformat(), r.security_id, [round(r.features[k], 10) for k in FEATURE_NAMES],
                                      round(r.label, 10)]).encode("utf-8"))
    alpha = float(len(X)) * 0.01
    ridge = RidgeRank(alpha=alpha).fit(X, y)
    lgbm = None
    try:
        import lightgbm as lgb
        lgbm = lgb.LGBMRegressor(random_state=seed, **LGBM_PARAMS)
        lgbm.fit(X, y)
    except Exception:
        lgbm = None
    weeks = sorted(by_week)
    cfg = {"model_id": MODEL_ID, "features": FEATURE_NAMES, "ridge_alpha": alpha, "lgbm": LGBM_PARAMS if lgbm is not None else None,
           "seed": seed, "target": "rank01(total_return_open_close_next_week)", "min_weeks": min_weeks}
    cfg_hash = hashlib.sha256(json.dumps(cfg, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:12]
    manifest = (f"{MODEL_ID}|rows={len(X)}|weeks={len(weeks)}|labels={label_week_id(weeks[0])}..{label_week_id(weeks[-1])}"
                f"|lgbm={'yes' if lgbm else 'no'}|data={digest.hexdigest()[:12]}|cfg={cfg_hash}")
    return Q1Model(trained_at=trained_at, n_rows=len(X), n_weeks=len(weeks), first_label_week=label_week_id(weeks[0]),
                   last_label_week=label_week_id(weeks[-1]), ridge=ridge, lgbm=lgbm, training_manifest_id=manifest)
