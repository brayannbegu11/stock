"""Construye el maestro de valores y el informe de censo desde las capturas archivadas.

Fuentes: censo TWSE (``t187ap03_L``), TPEx (``mopsfin_t187ap03_O``), ESB (``mopsfin_t187ap03_R``),
retiradas TWSE (``company/suspendListingCsvAndHtml``), catálogo FinMind (``TaiwanStockInfo``, para
tipo de instrumento y tablero) y retiradas FinMind (``TaiwanStockDelisting``).

Salida: ``data/store/master_<fecha>.jsonl`` (segmentos + eventos terminales) y
``docs/informes/10_censo_<fecha>.md``. Todo referido a la fecha de la captura; no es un
maestro histórico completo (las retiradas anteriores al censo vigente carecen de fecha de alta).
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from dataclasses import asdict
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from twlab.master import ORDINARY_EQUITY, AmbiguousSymbol, SecurityMaster  # noqa: E402
from twlab.sources import finmind  # noqa: E402
from twlab.sources.twse import (  # noqa: E402
    census_rows_tpex, census_rows_twse, delisting_rows_twse, latest_capture, load_rows, security_versions_from_census,
    terminal_events_from_delistings,
)
from twlab.store import RawStore  # noqa: E402


def main() -> int:
    store = RawStore(ROOT / "data" / "raw")
    caps = {name: latest_capture(store, src, ds) for name, (src, ds) in {
        "twse": ("twse", "t187ap03_L"), "tpex": ("tpex", "t187ap03_O"), "esb": ("tpex", "t187ap03_R"),
        "delist_twse": ("twse", "suspendListing"), "info": ("finmind", "TaiwanStockInfo"), "delist_fm": ("finmind", "TaiwanStockDelisting"),
    }.items()}
    as_of = max(c.ingested_at_dt for c in caps.values())
    info_rows = finmind.rows(store, caps["info"])
    instrument, board, fm_market = finmind.classify_info(info_rows)
    census = {
        "TWSE": census_rows_twse(load_rows(store, caps["twse"])),
        "TPEX": census_rows_tpex(load_rows(store, caps["tpex"])),
        "ESB": census_rows_tpex(load_rows(store, caps["esb"])),
    }
    master = SecurityMaster()
    problems: list[str] = []
    for market, rows in census.items():
        versions = security_versions_from_census(rows, market=market, instrument_types=instrument, boards=board,
                                                 recorded_at=caps["twse" if market == "TWSE" else ("tpex" if market == "TPEX" else "esb")].ingested_at_dt,
                                                 source_id=caps["twse" if market == "TWSE" else ("tpex" if market == "TPEX" else "esb")].capture_id)
        for v in versions:
            try:
                master.add(v)
            except Exception as exc:  # solapes o duplicados: se informan, no se ocultan
                problems.append(f"{market}:{v.symbol}: {exc}")
    delistings = delisting_rows_twse(load_rows(store, caps["delist_twse"]))
    terminal = terminal_events_from_delistings(delistings, market="TWSE", recorded_at=caps["delist_twse"].ingested_at_dt,
                                               source_id=caps["delist_twse"].capture_id)
    closed = 0
    orphan_delistings = 0
    reused_symbols: list[str] = []
    for ev in terminal:
        seg = master.current_segment(ev.security_id)
        if seg is None:
            orphan_delistings += 1
        elif ev.effective <= seg.valid_from:
            # UNI-03 en datos reales: la retirada es de un emisor anterior que usó el mismo símbolo; el segmento
            # vigente pertenece a otro emisor y no se cierra. El emisor anterior queda pendiente de fecha de alta.
            reused_symbols.append(f"{ev.security_id} (retirada {ev.effective.isoformat()} ≤ alta vigente {seg.valid_from.isoformat()})")
        else:
            master.close_version(ev.security_id, valid_to=ev.effective, recorded_at=ev.recorded_at, source_id=ev.source_id, terminal=ev)
            closed += 1
    today = as_of.date()
    universe = master.universe(as_of=today)
    # comprobaciones UNI sobre datos reales
    ambiguous = 0
    for v in universe:
        try:
            master.resolve_symbol(v.symbol, as_of=today)
        except AmbiguousSymbol:
            ambiguous += 1
    counts = {m: Counter(v.instrument_type for v in master.universe(as_of=today, markets=(m,), instrument_types=tuple({v.instrument_type for v in master._versions})))
              for m in ("TWSE", "TPEX", "ESB")}
    industries = Counter((v.market, v.board) for v in universe)
    out_dir = ROOT / "data" / "store"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = today.isoformat()
    with (out_dir / f"master_{stamp}.jsonl").open("w", encoding="utf-8") as fh:
        for v in master._versions:
            fh.write(json.dumps({"kind": "segment", **asdict(v)}, ensure_ascii=False, default=str) + "\n")
        for ev in master._terminal:
            fh.write(json.dumps({"kind": "terminal", **asdict(ev)}, ensure_ascii=False, default=str) + "\n")
    fm_types = Counter(fm_market.get(v.symbol, "absent") for v in universe)
    report = [
        f"# Censo del maestro al {stamp}",
        "",
        f"Construido desde las capturas archivadas (`data/raw`, capturas más recientes al {as_of.isoformat()}). "
        "Sólo cubre el censo vigente más las retiradas listadas por TWSE; no es un maestro histórico completo.",
        "",
        "| Mercado | Filas de censo | Segmentos en el maestro | Acciones ordinarias vigentes | Otros instrumentos / sin clasificar |",
        "|---|---|---|---|---|",
    ]
    for m in ("TWSE", "TPEX", "ESB"):
        segs = [v for v in master._versions if v.market == m]
        eq = len(master.universe(as_of=today, markets=(m,)))
        others = counts[m].total() - eq
        report.append(f"| {m} | {len(census[m])} | {len(segs)} | {eq} | {others} |")
    report += [
        "",
        f"- Universo simulable por defecto (TWSE + TPEX, acciones ordinarias, vigentes): **{len(universe)}**.",
        f"- Tableros (mercado, tablero): {dict(industries)}.",
        f"- Clasificación FinMind de los vigentes: {dict(fm_types)} (`absent` = no aparece en `TaiwanStockInfo`).",
        f"- Retiradas TWSE listadas: {len(delistings)}; cerradas en el maestro (existían en el censo vigente): {closed}; "
        f"sin segmento porque no están en el censo vigente ni se conoce su fecha de alta: {orphan_delistings} (pendiente: TEJ o histórico de FinMind).",
        f"- Símbolos ambiguos al resolver (UNI-03): {ambiguous}.",
        f"- Símbolos reutilizados detectados (retirada de un emisor anterior con fecha ≤ alta del vigente; UNI-03 real): {len(reused_symbols)}."
        + ("" if not reused_symbols else " Ejemplos: " + "; ".join(reused_symbols[:8])),
        f"- Filas rechazadas por el maestro (solapes/duplicados): {len(problems)}." + ("" if not problems else " Detalle: " + "; ".join(problems[:10])),
        "",
        "Exclusiones del universo simulable: ETF, ETN, DR, certificados de beneficio, filas de índice, tablero de innovación "
        "(se cataloga con `board=innovation` y queda dentro del universo sólo si el protocolo lo admite), ESB (mercado fuera de alcance), "
        "y todo símbolo sin clasificación (`unclassified`).",
    ]
    (ROOT / "docs" / "informes" / f"10_censo_{stamp}.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    print("\n".join(report))
    print(f"\nmaestro escrito: data/store/master_{stamp}.jsonl ({len(master._versions)} segmentos, {len(master._terminal)} eventos terminales)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
