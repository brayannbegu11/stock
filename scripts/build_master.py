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
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from twlab.master import ORDINARY_EQUITY, AmbiguousSymbol, SecurityMaster  # noqa: E402
from twlab.sources import finmind  # noqa: E402
from twlab.sources.twse import (  # noqa: E402
    census_rows_tpex, census_rows_twse, delisting_rows_twse, latest_capture, load_rows, resolve_delistings,
    security_versions_from_census,
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
    # las retiradas vienen por símbolo; se resuelven contra el maestro (identidad = símbolo + fecha de alta, R08-05).
    # La fila de retirada es una revisión posterior a la de alta: recorded_at estrictamente mayor (R04-12).
    resolution = resolve_delistings(delistings, master, market="TWSE",
                                    recorded_at=caps["delist_twse"].ingested_at_dt + timedelta(seconds=1),
                                    source_id=caps["delist_twse"].capture_id)
    closed = 0
    for ev in resolution.events:
        master.close_version(ev.security_id, valid_to=ev.effective, recorded_at=ev.recorded_at, source_id=ev.source_id, terminal=ev)
        closed += 1
    orphan_delistings = len(resolution.orphan)
    reused_symbols = list(resolution.prior_issuer)
    today = as_of.date()
    universe = master.universe(as_of=today)                                          # tablero principal por defecto (R08-13)
    innovation = master.universe(as_of=today, boards=("innovation",))
    # comprobaciones UNI sobre datos reales
    ambiguous = 0
    for v in universe:
        try:
            master.resolve_symbol(v.symbol, as_of=today)
        except AmbiguousSymbol:
            ambiguous += 1
    counts = {m: Counter(v.instrument_type for v in master.universe(as_of=today, markets=(m,), instrument_types=tuple({v.instrument_type for v in master._versions})))
              for m in ("TWSE", "TPEX", "ESB")}
    industries = Counter((v.market, v.board) for v in master.universe(as_of=today, boards=("main", "innovation")))
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
        f"- Universo simulable por defecto (TWSE + TPEX, acciones ordinarias, **tablero principal**, vigentes): **{len(universe)}**. "
        f"Tablero de innovación fuera del universo salvo habilitación explícita del protocolo: {len(innovation)} valores.",
        f"- Tableros (mercado, tablero) entre las acciones ordinarias vigentes: {dict(industries)}.",
        f"- Retiradas con símbolo ambiguo (varios segmentos vigentes): {len(resolution.ambiguous)}.",
        f"- Clasificación FinMind de los vigentes: {dict(fm_types)} (`absent` = no aparece en `TaiwanStockInfo`).",
        f"- Retiradas TWSE listadas: {len(delistings)}; cerradas en el maestro (existían en el censo vigente): {closed}; "
        f"sin segmento porque no están en el censo vigente ni se conoce su fecha de alta: {orphan_delistings} (pendiente: TEJ o histórico de FinMind).",
        f"- Símbolos ambiguos al resolver (UNI-03): {ambiguous}.",
        f"- Símbolos reutilizados detectados (retirada de un emisor anterior con fecha ≤ alta del vigente; UNI-03 real): {len(reused_symbols)}."
        + ("" if not reused_symbols else " Ejemplos: " + "; ".join(reused_symbols[:8])),
        f"- Filas rechazadas por el maestro (solapes/duplicados): {len(problems)}." + ("" if not problems else " Detalle: " + "; ".join(problems[:10])),
        "",
        "Exclusiones del universo simulable por defecto: ETF, ETN, DR, certificados de beneficio, filas de índice, tablero de innovación "
        "(se cataloga con `board=innovation`; `SecurityMaster.universe` lo excluye salvo `boards=(\"main\", \"innovation\")`), "
        "ESB (mercado fuera de alcance), y todo símbolo sin clasificación (`unclassified`: ausente del catálogo de FinMind o con "
        "categoría no reconocida).",
    ]
    (ROOT / "docs" / "informes" / f"10_censo_{stamp}.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    print("\n".join(report))
    print(f"\nmaestro escrito: data/store/master_{stamp}.jsonl ({len(master._versions)} segmentos, {len(master._terminal)} eventos terminales)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
