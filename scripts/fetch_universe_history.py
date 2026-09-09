"""Archiva en ``data/raw`` el histórico de FinMind (barras nominales y dividendos) de todo el universo simulable.

Universo: acciones ordinarias vigentes del tablero principal de TWSE y TPEx según el
maestro más reciente (``scripts/build_master.py``). Una petición por valor y conjunto de
datos (el nivel gratuito de FinMind no permite descargar todo el mercado por fecha).

Reanudable: un valor cuya captura más reciente cubra ``--end`` se omite. Ante un límite de
cuota (HTTP 402/429 o mensaje de nivel) espera y reintenta; nunca reescribe ``ingested_at``.

Uso: python scripts/fetch_universe_history.py [--start 2021-01-01] [--end 2026-09-09] [--pause 1.2]
Salida: data/store/universe_history_manifest.json (símbolo → capturas y recuentos).
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import date
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from twlab.master import SecurityMaster, SecurityVersion  # noqa: E402
from twlab.sources import finmind  # noqa: E402
from twlab.store import RawStore  # noqa: E402

RATE_LIMIT_SLEEP_S = 600


def load_master(path: Path) -> SecurityMaster:
    master = SecurityMaster()
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            row = json.loads(line)
            if row.pop("kind") != "segment":
                continue
            for k in ("valid_from", "valid_to"):
                row[k] = date.fromisoformat(row[k]) if row[k] else None
            from datetime import datetime
            row["recorded_at"] = datetime.fromisoformat(row["recorded_at"])
            master.add(SecurityVersion(**row))
    return master


def already_covered(store: RawStore, dataset: str, sid: str, end: str) -> tuple[str, int] | None:
    recs = store.captures(source_id="finmind", dataset=f"{dataset}/{sid}")
    for rec in reversed(recs):
        if rec.http_status == 200 and (rec.extra or {}).get("end_date", "") >= end:
            try:
                return rec.capture_id, len(finmind.rows(store, rec))
            except ValueError:
                continue
    return None


def fetch_with_backoff(store: RawStore, dataset: str, sid: str, start: str, end: str, pause: float):
    while True:
        try:
            rec = finmind.fetch(store, dataset, data_id=sid, start_date=start, end_date=end, pause_s=pause)
        except requests.RequestException as exc:
            print(f"  red: {exc}; reintento en 60 s", flush=True)
            time.sleep(60)
            continue
        if rec.http_status == 200:
            try:
                return rec, len(finmind.rows(store, rec))
            except ValueError as exc:                     # cuerpo con status != 200 (p. ej. límite de cuota)
                body = str(exc)
        else:
            body = f"http {rec.http_status}"
        print(f"  {sid}/{dataset}: {body[:120]} → espera {RATE_LIMIT_SLEEP_S} s", flush=True)
        time.sleep(RATE_LIMIT_SLEEP_S)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2021-01-01")
    ap.add_argument("--end", default=date.today().isoformat())
    ap.add_argument("--pause", type=float, default=1.2)
    ap.add_argument("--markets", default="TWSE,TPEX")
    ap.add_argument("--limit", type=int, default=0, help="sólo los N primeros valores (pruebas)")
    args = ap.parse_args()
    store = RawStore(ROOT / "data" / "raw")
    masters = sorted((ROOT / "data" / "store").glob("master_*.jsonl"))
    if not masters:
        raise SystemExit("no hay maestro: ejecuta scripts/build_master.py")
    master = load_master(masters[-1])
    universe = master.universe(as_of=date.today(), markets=tuple(args.markets.split(",")))
    if args.limit:
        universe = universe[: args.limit]
    out_path = ROOT / "data" / "store" / "universe_history_manifest.json"
    manifest = json.loads(out_path.read_text(encoding="utf-8")) if out_path.exists() else {"start": args.start, "end": args.end, "captures": {}}
    manifest.update(start=args.start, end=args.end, master=masters[-1].name)
    print(f"universo: {len(universe)} valores ({args.markets}); periodo {args.start}..{args.end}", flush=True)
    t0 = time.time()
    done = 0
    for i, v in enumerate(universe, 1):
        entry = manifest["captures"].get(v.symbol, {})
        entry.update(security_id=v.security_id, market=v.market, listing_date=v.valid_from.isoformat(), name=v.name_zh)
        for dataset, key, start in (("TaiwanStockPrice", "price", args.start), ("TaiwanStockDividend", "dividend", "2020-01-01")):
            covered = already_covered(store, dataset, v.symbol, args.end)
            if covered:
                entry[key], entry[f"{key}_rows"] = covered
                continue
            rec, n = fetch_with_backoff(store, dataset, v.symbol, start, args.end, args.pause)
            entry[key], entry[f"{key}_rows"] = rec.capture_id, n
            done += 1
        manifest["captures"][v.symbol] = entry
        if i % 25 == 0 or i == len(universe):
            out_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
            print(f"[{i}/{len(universe)}] {v.market}:{v.symbol} barras={entry.get('price_rows')} div={entry.get('dividend_rows')} "
                  f"peticiones nuevas={done} t={time.time() - t0:.0f}s", flush=True)
    out_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"escrito {out_path}; peticiones nuevas: {done}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
