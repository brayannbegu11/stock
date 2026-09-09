"""Demostración completa del motor con la regla transparente Q0 (momentum de 20 sesiones).

Desde la ronda 9 es un envoltorio fino de ``twlab.backtest`` (el mismo recorrido semanal que
``scripts/run_backtest.py``) con los pronosticadores Q0 y A1 sobre la muestra archivada por
``fetch_history_sample.py``. Reproduce las cifras del informe 11.

**Qué demuestra:** que la cadena datos → paquete → predicción → libro → evaluación funciona
de extremo a extremo sin LLM y con control temporal. **Qué NO demuestra:** rentabilidad.

Uso: python scripts/run_q0_demo.py --start 2024-01-01 --end 2025-12-31
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from decimal import Decimal as D
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from twlab.backtest import BacktestConfig, MomentumForecaster, RandomForecaster, Runner, load_market  # noqa: E402
from twlab.calendar import load_twse_reference_calendar  # noqa: E402
from twlab.store import RawStore  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2024-01-01")
    ap.add_argument("--end", default="2025-12-31")
    ap.add_argument("--notional", type=int, default=1_000_000)
    ap.add_argument("--slots", type=int, default=5)
    ap.add_argument("--seed", type=int, default=20260909)
    ap.add_argument("--block-length", type=int, default=4)
    ap.add_argument("--slippage-bps", type=int, default=10)
    ap.add_argument("--sizing", choices=("proportional", "fixed"), default="proportional")
    ap.add_argument("--exposure-tolerance", default="0.10")
    args = ap.parse_args()
    store = RawStore(ROOT / "data" / "raw")
    market = load_market(store, ROOT / "data" / "store" / "sample_universe.json", load_twse_reference_calendar())
    cfg = BacktestConfig(start=date.fromisoformat(args.start), end=date.fromisoformat(args.end), slots=args.slots, notional=args.notional,
                         sizing=args.sizing, exposure_tolerance=D(args.exposure_tolerance), block_length=args.block_length,
                         seed=args.seed, slippage_bps=args.slippage_bps, label="Q0")
    result = Runner(store, market, cfg, [MomentumForecaster(), RandomForecaster(args.seed)]).run()
    out_path = ROOT / "data" / "store" / f"q0_demo_{args.start}_{args.end}.json"
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=1, default=str, allow_nan=False), encoding="utf-8")   # sin NaN (R12-03)
    s = result["summary"]
    print(json.dumps({k: v for k, v in s.items() if k != "forecasters"}, ensure_ascii=False, indent=1, default=str))
    for name, e in s["forecasters"].items():
        print(name, json.dumps({k: v for k, v in e.items() if k not in ("final_valuation", "open_positions_at_end")}, ensure_ascii=False, default=str))
    print(f"\nescrito {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
