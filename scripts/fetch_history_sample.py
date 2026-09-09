"""Selecciona una muestra estratificada del censo TWSE y archiva su histórico de FinMind (2021-2025).

La muestra es **para probar el motor**, no para inferir rentabilidad: procede
del censo vigente (sesgo de supervivencia) y se completa con hasta tres
sociedades retiradas en 2024-2025 para ejercitar la retirada en el libro.

Uso: python scripts/fetch_history_sample.py [--per-industry 2] [--start 2021-01-01] [--end 2025-12-31]
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from twlab.sources import finmind  # noqa: E402
from twlab.sources.twse import census_rows_twse, delisting_rows_twse, latest_capture, load_rows  # noqa: E402
from twlab.store import RawStore  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-industry", type=int, default=2)
    ap.add_argument("--start", default="2021-01-01")
    ap.add_argument("--end", default="2025-12-31")
    ap.add_argument("--max-delisted", type=int, default=3)
    args = ap.parse_args()
    store = RawStore(ROOT / "data" / "raw")
    census = census_rows_twse(load_rows(store, latest_capture(store, "twse", "t187ap03_L")))
    info_rows = finmind.rows(store, latest_capture(store, "finmind", "TaiwanStockInfo"))
    instrument, board, market = finmind.classify_info(info_rows)
    by_industry: dict[str, list] = defaultdict(list)
    for r in census:
        if instrument.get(r.symbol, "ordinary_equity") != "ordinary_equity" or r.listing_date is None:
            continue
        if r.listing_date > date(2020, 6, 30):          # historial suficiente para 120 sesiones antes de 2021
            continue
        by_industry[r.industry_code].append(r)
    sample = []
    for code in sorted(by_industry):
        rows_ = sorted(by_industry[code], key=lambda r: r.symbol)[: args.per_industry]
        sample.extend(rows_)
    delisted = [d for d in delisting_rows_twse(load_rows(store, latest_capture(store, "twse", "suspendListing")))
                if date(2024, 1, 1) <= d.delisting_date <= date(2025, 12, 31)]
    delisted = sorted(delisted, key=lambda d: d.delisting_date)[: args.max_delisted]
    symbols = [r.symbol for r in sample] + [d.symbol for d in delisted]
    print(f"muestra: {len(sample)} cotizadas ({len(by_industry)} industrias) + {len(delisted)} retiradas 2024-2025")
    manifest = {"start": args.start, "end": args.end, "per_industry": args.per_industry,
                "listed": [{"symbol": r.symbol, "name": r.name_zh, "industry": r.industry_code, "listing_date": r.listing_date.isoformat()} for r in sample],
                "delisted": [{"symbol": d.symbol, "name": d.name_zh, "delisting_date": d.delisting_date.isoformat()} for d in delisted],
                "captures": {}}
    for i, sid in enumerate(symbols, 1):
        rec_p = finmind.fetch(store, "TaiwanStockPrice", data_id=sid, start_date=args.start, end_date=args.end)
        rec_d = finmind.fetch(store, "TaiwanStockDividend", data_id=sid, start_date="2020-01-01", end_date=args.end)
        n_p = len(finmind.rows(store, rec_p)) if rec_p.http_status == 200 else -1
        n_d = len(finmind.rows(store, rec_d)) if rec_d.http_status == 200 else -1
        manifest["captures"][sid] = {"price": rec_p.capture_id, "price_rows": n_p, "dividend": rec_d.capture_id, "dividend_rows": n_d}
        print(f"[{i}/{len(symbols)}] {sid}: {n_p} barras, {n_d} filas de dividendo")
    out = ROOT / "data" / "store"
    out.mkdir(parents=True, exist_ok=True)
    (out / "sample_universe.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    print("escrito data/store/sample_universe.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
