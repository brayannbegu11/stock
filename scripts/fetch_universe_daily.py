"""Archiva las cotizaciones diarias oficiales de TWSE y TPEx, una petición por sesión y mercado (reanudable).

Fuente por fecha (todas las acciones de cada sesión), alternativa al nivel gratuito de FinMind para el
universo completo. Sólo precios y volúmenes: no trae derechos.

Uso: python scripts/fetch_universe_daily.py --start 2024-07-01 --end 2026-09-09 [--pause 3] [--newest-first]
"""
from __future__ import annotations

import argparse
import sys
import time
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import requests  # noqa: E402

from twlab.calendar import load_twse_reference_calendar  # noqa: E402
from twlab.sources import twse_daily as td  # noqa: E402
from twlab.store import RawStore  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2024-07-01")
    ap.add_argument("--end", default=date.today().isoformat())
    ap.add_argument("--pause", type=float, default=3.0)
    ap.add_argument("--newest-first", action="store_true")
    args = ap.parse_args()
    store = RawStore(ROOT / "data" / "raw")
    cal = load_twse_reference_calendar()
    sessions = cal.sessions_between(date.fromisoformat(args.start), date.fromisoformat(args.end))
    if args.newest_first:
        sessions = list(reversed(sessions))
    have_twse = td.captured_sessions(store, "twse", td.TWSE_DATASET)
    have_tpex = td.captured_sessions(store, "tpex", td.TPEX_DATASET)
    print(f"sesiones oficiales: {len(sessions)}; ya capturadas twse={len(have_twse)} tpex={len(have_tpex)}", flush=True)
    t0 = time.time()
    n = 0
    for i, d in enumerate(sessions, 1):
        for name, have, fn in (("twse", have_twse, td.fetch_twse), ("tpex", have_tpex, td.fetch_tpex)):
            if d in have:
                continue
            for _attempt in range(5):
                try:
                    rec = fn(store, d, pause_s=args.pause)
                    if rec.http_status != 200:
                        print(f"  {name} {d}: http {rec.http_status}; espera 120 s", flush=True)
                        time.sleep(120)
                        continue
                    n += 1
                    break
                except requests.RequestException as exc:
                    print(f"  {name} {d}: red {exc}; espera 60 s", flush=True)
                    time.sleep(60)
        if i % 20 == 0 or i == len(sessions):
            print(f"[{i}/{len(sessions)}] {d} peticiones nuevas={n} t={time.time() - t0:.0f}s", flush=True)
    print("hecho", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
