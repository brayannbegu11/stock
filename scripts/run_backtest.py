"""Backtest semanal del protocolo con pronosticadores intercambiables (Q0, Q1, A1) sobre datos archivados.

Uso:
  python scripts/run_backtest.py --manifest sample --start 2024-01-01 --end 2025-12-31 --forecasters Q0,Q1,A1
  python scripts/run_backtest.py --manifest universe --weeks-back 13 --forecasters Q0,Q1,A1

``--manifest sample`` usa data/store/sample_universe.json (67 valores); ``universe`` usa
data/store/universe_history_manifest.json (todo el tablero principal). El último corte cuya salida
todavía no tiene datos se emite igualmente como ``pending_outcome`` (la lista de la semana en curso).

Salida: data/store/backtest_<label>.json y docs/informes/<informe>.md si se pasa --report.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, timedelta
from decimal import Decimal as D
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from twlab.backtest import (  # noqa: E402
    BacktestConfig, MomentumForecaster, RandomForecaster, Runner, TabularForecaster, load_market, load_market_daily, load_master_file,
    markdown_report,
)
from twlab.calendar import load_twse_reference_calendar  # noqa: E402
from twlab.store import RawStore  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", default="sample", help="sample | universe | daily (cotizaciones oficiales por fecha) | ruta a un manifiesto")
    ap.add_argument("--lookback-start", default="2024-07-01", help="daily: primera sesión cargada para historial y entrenamiento")
    ap.add_argument("--start")
    ap.add_argument("--end")
    ap.add_argument("--weeks-back", type=int, default=0, help="si se da, start = hoy - N semanas y end = hoy")
    ap.add_argument("--forecasters", default="Q0,Q1,A1")
    ap.add_argument("--label", default=None)
    ap.add_argument("--notional", type=int, default=1_000_000)
    ap.add_argument("--slots", type=int, default=5)
    ap.add_argument("--seed", type=int, default=20260909)
    ap.add_argument("--block-length", type=int, default=4)
    ap.add_argument("--commission", default="0.001425")
    ap.add_argument("--slippage-bps", type=int, default=10)
    ap.add_argument("--sizing", choices=("proportional", "fixed"), default="proportional")
    ap.add_argument("--lot-size", type=int, default=1000, help="1000 = lotes regulares; 1 = lotes sueltos (零股), precios de sesión regular como aproximación")
    ap.add_argument("--min-commission", default="0", help="comisión mínima por orden en TWD (habitual: 20)")
    ap.add_argument("--exposure-tolerance", default="0.10")
    ap.add_argument("--retrain-every", type=int, default=4)
    ap.add_argument("--min-train-weeks", type=int, default=52)
    ap.add_argument("--report", default=None, help="nombre del informe markdown en docs/informes (sin ruta)")
    args = ap.parse_args()
    today = date.today()
    if args.weeks_back:
        start, end = today - timedelta(weeks=args.weeks_back), today
    else:
        start, end = date.fromisoformat(args.start), date.fromisoformat(args.end)
    manifest = {"sample": ROOT / "data" / "store" / "sample_universe.json",
                "universe": ROOT / "data" / "store" / "universe_history_manifest.json"}.get(args.manifest, Path(args.manifest))
    label = args.label or f"{args.manifest}_{start.isoformat()}_{end.isoformat()}"
    store = RawStore(ROOT / "data" / "raw")
    calendar = load_twse_reference_calendar()
    cfg = BacktestConfig(start=start, end=end, slots=args.slots, notional=args.notional, sizing=args.sizing,
                         exposure_tolerance=D(args.exposure_tolerance), block_length=args.block_length, seed=args.seed,
                         commission_per_side=D(args.commission), slippage_bps=args.slippage_bps, label=label,
                         lot_size=args.lot_size, min_commission_twd=D(args.min_commission))
    if args.manifest == "daily":
        # universo completo desde las cotizaciones oficiales por fecha (sin derechos); historial desde --lookback-start
        master = load_master_file(sorted((ROOT / "data" / "store").glob("master_*.jsonl"))[-1])
        market = load_market_daily(store, calendar, master, as_of=today, start=date.fromisoformat(args.lookback_start), end=end,
                                   par_value=cfg.par_value)
    else:
        market = load_market(store, manifest, calendar, par_value=cfg.par_value)
    if market.warnings:
        print("avisos del mercado:", *market.warnings[:20], sep="\n  ")
    names = [n.strip() for n in args.forecasters.split(",") if n.strip()]
    forecasters = []
    for n in names:
        if n == "Q0":
            forecasters.append(MomentumForecaster())
        elif n == "A1":
            forecasters.append(RandomForecaster(args.seed))
        elif n == "Q1":
            forecasters.append(TabularForecaster(market, retrain_every_weeks=args.retrain_every, min_weeks=args.min_train_weeks, seed=args.seed))
        else:
            raise SystemExit(f"pronosticador desconocido: {n}")
    if "A1" not in names:
        forecasters.append(RandomForecaster(args.seed))
    result = Runner(store, market, cfg, forecasters).run()
    out = ROOT / "data" / "store" / f"backtest_{label}.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=1, default=str, allow_nan=False), encoding="utf-8")   # sin NaN (R12-03)
    print(json.dumps({k: v for k, v in result["summary"].items() if k != "forecasters"}, ensure_ascii=False, indent=1, default=str))
    for name, e in result["summary"]["forecasters"].items():
        print(name, json.dumps({k: v for k, v in e.items() if k not in ("final_valuation", "open_positions_at_end", "training_history")},
                               ensure_ascii=False, default=str))
    if args.report:
        path = ROOT / "docs" / "informes" / args.report
        path.write_text(markdown_report(result, title=f"Backtest {label}"), encoding="utf-8")
        print(f"informe: {path}")
    print(f"escrito {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
