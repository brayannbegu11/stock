"""Captura diaria de los endpoints del catálogo a ``data/raw`` con ``ingested_at`` real.

Uso:
    python scripts/capture_daily.py            # todos los endpoints
    python scripts/capture_daily.py twse       # sólo una fuente

Cada respuesta se guarda tal cual (bytes), con sha256, código HTTP, tipo de
contenido y hora de ingestión UTC del reloj del sistema. No se transforma
nada aquí: la normalización ocurre después, sobre el archivo.
"""
from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from twlab.sources.catalog import ENDPOINTS, by_source  # noqa: E402
from twlab.store import RawStore  # noqa: E402

HEADERS = {"User-Agent": "taiwan-ia-lab/0.1 (private research; contact via repo)", "Accept": "application/json"}


def main(argv: list[str]) -> int:
    endpoints = list(ENDPOINTS) if len(argv) < 2 else by_source(argv[1])
    store = RawStore(ROOT / "data" / "raw")
    run_started = datetime.now(timezone.utc)
    summary = []
    for ep in endpoints:
        t0 = time.monotonic()
        try:
            r = requests.get(ep.url, headers=HEADERS, timeout=90)
            payload, status, ctype = r.content, r.status_code, r.headers.get("Content-Type")
            err = None
        except Exception as exc:  # la caída de una fuente se registra, no se oculta (OPS-01)
            payload, status, ctype, err = b"", None, None, repr(exc)
        elapsed = round(time.monotonic() - t0, 3)
        rows = None
        if payload and (ctype or "").startswith("application/json"):
            try:
                parsed = json.loads(payload.decode("utf-8"))
                rows = len(parsed) if isinstance(parsed, list) else len(parsed.get("data", [])) if isinstance(parsed, dict) else None
            except Exception:
                rows = None
        rec = store.put(
            source_id=ep.source_id, dataset=ep.dataset, payload=payload, url=ep.url,
            http_status=status, content_type=ctype,
            extra={"purpose": ep.purpose, "session_field": ep.session_field, "date_format": ep.date_format,
                   "units": ep.units, "rows": rows, "elapsed_s": elapsed, "error": err,
                   "run_started": run_started.isoformat()},
        )
        summary.append((ep.source_id, ep.dataset, status, rows, len(payload), elapsed, err))
        print(f"{ep.source_id:8s} {ep.dataset:20s} http={status} rows={rows} bytes={len(payload)} t={elapsed}s {err or ''}")
        time.sleep(0.5)
    failures = [s for s in summary if s[2] != 200]
    print(f"\ncaptured {len(summary)} endpoints, {len(failures)} failures, store={store.root}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
