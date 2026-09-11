"""Recorrido semanal del protocolo sobre datos archivados, con pronosticadores intercambiables.

Generaliza la demo Q0 (informe 11): por cada corte dominical construye el paquete con las barras
disponibles según la política declarada, pide a cada pronosticador su selección **viendo sólo el
paquete**, valida y archiva la predicción, simula la cesta de cinco puestos en un libro propio,
procesa acciones corporativas sin huecos, mide el intervalo apertura→cierre sobre el patrimonio
contable y empareja cada pronosticador con el comparador aleatorio de la misma semana.

Nada aquí mide rentabilidad futura: los costes son ilustrativos, el universo histórico procede del
censo vigente y varios valores del protocolo siguen sin congelar (informe 11 §4). Si el corte más
reciente aún no tiene desenlace, la selección se emite y archiva igualmente (``pending_outcome``).
"""
from __future__ import annotations

import hashlib

import collections
import json
import random
import statistics
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal as D
from pathlib import Path
from typing import Callable, Mapping, Optional, Protocol, Sequence

from .calendar import TradingCalendar
from .evaluation import IntervalMismatch, IntervalReturn, WeeklyObservation, block_bootstrap_mean, paired_excess
from .ledger import CorporateAction, CostModel, LedgerError, MissingPrice, PaperLedger
from .master import SecurityMaster, SecurityVersion, TerminalEvent, UnknownSymbol, classify_coverage, security_id_for
from .models import q1 as q1mod
from .packet import Document, Packet, PredictorView, build_packet, canonical_bytes, packet_to_json, packet_from_json
from .schemas import validate_prediction
from .simulation import basket_report, enter_basket, exit_basket
from .sources import finmind
from .sources.finmind import SourceIdentityMismatch
from .store import CaptureRecord, RawStore, IntegrityError, ManifestCorrupt, MissingCapture
from .timeutil import TAIPEI, AvailabilityQuality, derive_available_at, taipei
from .weekly import WeekPlan, plan_week

EVIDENCE = "historical_numeric_temporally_controlled"
PRE_OPEN = time(8, 59)


@dataclass
class BacktestConfig:
    start: date
    end: date
    slots: int = 5
    notional: int = 1_000_000
    sizing: str = "proportional"              # proportional | fixed
    exposure_tolerance: D = D("0.10")
    block_length: int = 4
    n_boot: int = 2000
    seed: int = 20260909
    commission_per_side: D = D("0.001425")
    sell_tax: D = D("0.003")
    slippage_bps: int = 10
    lot_size: int = 1000                       # 1000 = lote regular; 1 = lotes sueltos (零股, precios de sesión regular como aproximación declarada)
    min_commission_twd: D = D(0)               # comisión mínima por orden (los brókers suelen aplicar 20 TWD)
    min_history_sessions: int = 120
    liquidity_multiple: int = 20               # mediana(importe 20 sesiones) ≥ multiple × nocional
    par_value: D = D(10)
    baseline: str = "A1"
    label: str = "backtest"
    archive_label: Optional[str] = None        # dataset del archivo (paquetes y predicciones); estable entre corridas semanales


@dataclass
class Security:
    symbol: str
    security_id: str
    market: str
    name: str
    listing_date: date
    delisting_date: Optional[date]
    bars: list[finmind.Bar]
    dividends: list[finmind.DividendRow]
    price_capture: object
    dividend_capture: object = None
    events: list = field(default_factory=list)          # derechos validados (q1.DividendLike): libro y etiquetas usan esta lista
    source_id: str = "finmind"                          # procedencia de las barras (finmind | twse | tpex)
    derivation: str = "finmind_price_bars_v1"           # extractor declarado para el documento de barras
    bar_captures: dict = field(default_factory=dict)    # sesión → capture_id que respalda esa barra (fuentes por fecha, R16-02)


@dataclass
class MarketData:
    securities: dict[str, Security]            # por security_id
    by_symbol: dict[str, str]                  # símbolo → security_id
    master: SecurityMaster
    calendar: TradingCalendar
    by_session: dict[str, dict[date, finmind.Bar]]
    traded_days: set[date]
    dropped_no_regular_price: int
    source_manifest: str
    bars_before_listing_dropped: int = 0
    warnings: list[str] = field(default_factory=list)
    par_value: D = D(10)                       # valor nominal con el que se convirtieron los dividendos en acciones (R11-03)

    @property
    def data_version(self) -> str:
        """Huella del **contenido** que consume el pronosticador (R10-03, R15-05): capturas, barras (sesión, apertura,
        cierre, importe, disponibilidad), derechos validados y versión del calendario. Cambiar cualquiera de ellos en
        memoria, aunque conserve identificadores, cambia la versión."""
        import hashlib
        h = hashlib.sha256()
        cal = self.calendar
        # contenido del calendario, no sólo su etiqueta (R15-05, ronda 16): rango y cierres efectivos
        h.update(f"{cal.source_id}@{cal.version}|{cal.start}|{cal.end}|{','.join(sorted(d.isoformat() for d in cal.closures))}\n".encode("utf-8"))
        for sec_id in sorted(self.securities):
            s = self.securities[sec_id]
            caps = ",".join(f"{d.isoformat()}={c}" for d, c in sorted(s.bar_captures.items())) if s.bar_captures else ""
            # la procedencia por sesión también es contenido (R17-02): sustituir la captura de una sesión cambia la versión
            h.update(f"{sec_id}|{s.price_capture.capture_id}|{getattr(s.dividend_capture, 'capture_id', '')}|{s.listing_date}|{s.delisting_date}|{caps}\n".encode("utf-8"))
            for b in s.bars:
                h.update(f"{b.session}:{b.open}:{b.close}:{b.value_twd}:{b.available_at.timestamp()}\n".encode("utf-8"))
            for e in s.events:
                h.update(f"{e.event_id}:{e.kind}:{e.ex_date}:{e.cash_per_share}:{e.stock_per_share}:{e.par_value}:{e.stock_ratio}:{e.pay_date}:"
                         f"{e.known_at.timestamp() if e.known_at else None}:{e.ambiguous}\n".encode("utf-8"))
        return h.hexdigest()[:16]


class ManifestInconsistent(ValueError):
    pass


# Fuentes por fecha: cada sesión de una serie debe estar respaldada por su propia captura (R18-01)
SESSION_CAPTURE_SOURCES = ("twse", "tpex")


def load_market(store: RawStore, manifest_path: Path, calendar: TradingCalendar, *, default_market: str = "TWSE",
                par_value: D = D(10)) -> MarketData:
    """Carga barras y dividendos desde las capturas listadas en un manifiesto (muestra o universo).

    Comprueba identidad y coherencia (R08-06, R10-05, R10-06): la captura de precios y la de dividendos
    deben ser de FinMind y del símbolo; un ``security_id`` o una fecha de alta declarados en el manifiesto
    deben coincidir con lo reconstruido; las barras anteriores a la fecha de alta se descartan (pertenecen a
    otro emisor o a otra fuente); los dividendos se leen siempre que exista captura, y el recuento del
    manifiesto, si existe, debe coincidir con las filas leídas.
    """
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    listing: dict[str, date] = {}
    delisting: dict[str, date] = {}
    names: dict[str, str] = {}
    declared: dict[str, dict] = {}              # símbolo → campos declarados en listed/delisted (security_id, market, listing_date)
    for row in manifest.get("listed", []):
        sid = row["symbol"]
        if sid in listing:
            raise ManifestInconsistent(f"{sid}: repeated in listed")
        listing[sid] = date.fromisoformat(row["listing_date"])
        names[sid] = row.get("name", "")
        declared[sid] = {k: row[k] for k in ("security_id", "market") if k in row}
    for row in manifest.get("delisted", []):
        sid = row["symbol"]
        if sid in delisting:
            raise ManifestInconsistent(f"{sid}: repeated in delisted")
        delisting[sid] = date.fromisoformat(row["delisting_date"])
        names.setdefault(sid, row.get("name", ""))
        if row.get("listing_date"):
            if sid in listing and date.fromisoformat(row["listing_date"]) != listing[sid]:
                raise ManifestInconsistent(f"{sid}: listing_date in delisted != listed")
            listing.setdefault(sid, date.fromisoformat(row["listing_date"]))
        d = declared.setdefault(sid, {})
        for k in ("security_id", "market"):
            if k in row:
                if k in d and d[k] != row[k]:
                    raise ManifestInconsistent(f"{sid}: {k} in delisted != listed")
                d[k] = row[k]
    master = SecurityMaster()
    securities: dict[str, Security] = {}
    by_symbol: dict[str, str] = {}
    by_session: dict[str, dict[date, finmind.Bar]] = {}
    dropped = 0
    dropped_before_listing = 0
    warnings: list[str] = []
    for sid, caps in manifest["captures"].items():
        if caps.get("price_rows", 0) <= 0:
            continue
        rec = store.get(caps["price"])
        if rec.source_id != "finmind" or rec.dataset != f"TaiwanStockPrice/{sid}":
            raise SourceIdentityMismatch(f"{sid}: manifest points to capture {rec.capture_id} ({rec.source_id}/{rec.dataset})")
        raw_bars = finmind.bars_from_rows(finmind.rows(store, rec), stock_id=sid)
        if "price_rows" in caps and caps["price_rows"] != len(raw_bars):
            raise ManifestInconsistent(f"{sid}: manifest declares {caps['price_rows']} price rows, capture has {len(raw_bars)}")
        dec = declared.get(sid, {})
        market = caps.get("market") or dec.get("market") or default_market
        if caps.get("market") and dec.get("market") and caps["market"] != dec["market"]:
            raise ManifestInconsistent(f"{sid}: market in captures != listed/delisted")
        if caps.get("listing_date") and sid in listing and date.fromisoformat(caps["listing_date"]) != listing[sid]:
            raise ManifestInconsistent(f"{sid}: listing_date {caps['listing_date']} in captures != {listing[sid].isoformat()} in listed")
        vf = date.fromisoformat(caps["listing_date"]) if caps.get("listing_date") else listing.get(sid, raw_bars[0].session if raw_bars else None)
        if vf is None:
            continue
        sec_id = security_id_for(market, sid, vf)
        for where, declared_id in (("captures", caps.get("security_id")), ("listed/delisted", dec.get("security_id"))):
            if declared_id and declared_id != sec_id:
                raise ManifestInconsistent(f"{sid}: security_id {declared_id!r} in {where} != reconstructed {sec_id!r}")
        if caps.get("dividend_rows", 0) > 0 and not caps.get("dividend"):
            raise ManifestInconsistent(f"{sid}: manifest declares {caps['dividend_rows']} dividend rows but no dividend capture (R10-06)")
        usable = [b for b in raw_bars if b.has_regular_price]
        dropped += len(raw_bars) - len(usable)
        bars = [b for b in usable if b.session >= vf]
        dropped_before_listing += len(usable) - len(bars)
        if not bars:
            continue
        divs: list[finmind.DividendRow] = []
        drec = None
        if caps.get("dividend"):
            drec = store.get(caps["dividend"])
            if drec.source_id != "finmind" or drec.dataset != f"TaiwanStockDividend/{sid}":
                raise SourceIdentityMismatch(f"{sid}: manifest points to dividend capture {drec.capture_id} ({drec.source_id}/{drec.dataset})")
            try:
                divs = finmind.dividends_from_rows(finmind.rows(store, drec), stock_id=sid)
            except ValueError as exc:
                if caps.get("dividend_rows", 0) >= 0:
                    raise ManifestInconsistent(f"{sid}: dividend capture unreadable but manifest does not declare failure: {exc}") from exc
                warnings.append(f"{sid}: dividend capture failed ({exc}); no dividends loaded")
            if caps.get("dividend_rows", len(divs)) >= 0 and caps.get("dividend_rows", len(divs)) != len(divs):
                raise ManifestInconsistent(f"{sid}: manifest declares {caps['dividend_rows']} dividend rows, capture has {len(divs)}")
        name = caps.get("name", names.get(sid, ""))
        # el segmento se conoció cuando se ingirió la captura de precios que lo declara (no con la hora de esta carga):
        # es la fecha de registro que decide qué identidades eran conocidas al corte de cada semana (R24-01)
        known = rec.ingested_at_dt
        sv = SecurityVersion(security_id=sec_id, issuer_id=sec_id, symbol=sid, name_zh=name, market=market, board="main",
                             instrument_type="ordinary_equity", valid_from=vf, valid_to=None, recorded_at=known, source_id=manifest_path.name)
        master.add(sv)
        dl = delisting.get(sid)
        if caps.get("delisting_date"):                        # una retirada declarada en captures cuenta, y no puede contradecir delisted (R10-05)
            cdl = date.fromisoformat(caps["delisting_date"])
            if dl and cdl != dl:
                raise ManifestInconsistent(f"{sid}: delisting_date in captures != delisted")
            dl = cdl
        if dl:
            later = known + timedelta(seconds=1)
            master.close_version(sec_id, valid_to=dl, recorded_at=later, source_id="twse:suspendListing",
                                 terminal=TerminalEvent(sec_id, "delisting", dl, later, "twse:suspendListing"))
        events, problems = validated_dividend_events(sec_id, divs, par_value, calendar)
        warnings.extend(problems)
        securities[sec_id] = Security(sid, sec_id, market, name, vf, dl, bars, divs, rec, drec, events)
        by_symbol[sid] = sec_id
        by_session[sec_id] = {b.session: b for b in bars}
    traded: set[date] = set().union(*[set(m) for m in by_session.values()]) if by_session else set()
    return MarketData(securities, by_symbol, master, calendar, by_session, traded, dropped, manifest_path.name,
                      dropped_before_listing, warnings, par_value)


def load_master_file(path: Path) -> SecurityMaster:
    """Maestro escrito por ``scripts/build_master.py`` (``data/store/master_<fecha>.jsonl``)."""
    master = SecurityMaster()
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            row = json.loads(line)
            if row.pop("kind") != "segment":
                continue
            for k in ("valid_from", "valid_to"):
                row[k] = date.fromisoformat(row[k]) if row[k] else None
            row["recorded_at"] = datetime.fromisoformat(row["recorded_at"])
            master.add(SecurityVersion(**row))
    return master


def master_snapshot_bytes(master: SecurityMaster) -> bytes:
    """Instantánea determinista del maestro (todas las filas registradas, JSONL ``kind == "segment"``) para archivarla
    junto a los paquetes y predicciones de una corrida: la identidad de cada valor seleccionado (código y símbolo) se
    contrasta después con esta instantánea, no con el JSON de resultados (R23-01)."""
    rows = []
    for v in master._versions:  # noqa: SLF001 - serialización fiel de lo registrado (nada se borra en el maestro)
        rows.append({"kind": "segment", "security_id": v.security_id, "issuer_id": v.issuer_id, "symbol": v.symbol,
                     "name_zh": v.name_zh, "name_en": v.name_en, "market": v.market, "board": v.board,
                     "instrument_type": v.instrument_type, "currency": v.currency,
                     "valid_from": v.valid_from.isoformat(), "valid_to": v.valid_to.isoformat() if v.valid_to else None,
                     "recorded_at": v.recorded_at.isoformat(), "source_id": v.source_id})
    # orden cronológico de registro: al volver a cargar la instantánea fila a fila con ``SecurityMaster.add`` se reproduce
    # exactamente la historia (sustituciones y cierres validados por el propio maestro, R24-03)
    rows.sort(key=lambda r: (datetime.fromisoformat(r["recorded_at"]).astimezone(timezone.utc), r["security_id"], r["valid_from"]))
    return ("\n".join(json.dumps(r, ensure_ascii=False, sort_keys=True) for r in rows) + "\n").encode("utf-8")


def load_market_daily(store: RawStore, calendar: TradingCalendar, master: SecurityMaster, *, as_of: date, start: date, end: date,
                      par_value: D = D(10)) -> MarketData:
    """Mercado construido desde las cotizaciones diarias oficiales por fecha (TWSE ``MI_INDEX``, TPEx ``dailyQuotes``).

    Universo y fechas de alta del maestro; una barra por símbolo y sesión desde las capturas por fecha; barras
    anteriores al alta descartadas; **sin derechos** (la fuente no los trae: se declara en ``warnings`` y en el
    resumen). Cada documento de barras referencia la captura de su última sesión.
    """
    from .sources import twse_daily as td
    universe = master.universe(as_of=as_of)
    wanted = {(v.market, v.symbol): v for v in universe}
    have = {"TWSE": td.captured_sessions(store, "twse", td.TWSE_DATASET), "TPEX": td.captured_sessions(store, "tpex", td.TPEX_DATASET)}
    readers = {"TWSE": (td.twse_rows, td.bars_twse), "TPEX": (td.tpex_rows, td.bars_tpex)}
    bars: dict[tuple[str, str], list] = {k: [] for k in wanted}
    captures_by_session: dict[tuple[str, str], dict[date, object]] = {k: {} for k in wanted}
    missing: list[str] = []
    closed_sessions: list[str] = []
    for s in calendar.sessions_between(start, end):
        for market in ("TWSE", "TPEX"):
            rec = have[market].get(s)
            if rec is None:
                missing.append(f"{market}:{s.isoformat()}")
                continue
            reader, parser = readers[market]
            rows = reader(store, rec)
            if rows is None:
                closed_sessions.append(f"{market}:{s.isoformat()}")
                continue
            for sid, bar in parser(s, rows).items():
                key = (market, sid)
                if key in wanted:
                    bars[key].append(bar)
                    captures_by_session[key][s] = rec
    dropped = 0
    dropped_before_listing = 0
    securities: dict[str, Security] = {}
    by_symbol: dict[str, str] = {}
    by_session: dict[str, dict[date, finmind.Bar]] = {}
    sources = {"TWSE": ("twse", td.TWSE_DERIVATION), "TPEX": ("tpex", td.TPEX_DERIVATION)}
    for key, v in wanted.items():
        allb = sorted(bars[key], key=lambda b: b.session)
        usable = [b for b in allb if b.has_regular_price]
        dropped += len(allb) - len(usable)
        kept = [b for b in usable if b.session >= v.valid_from]
        dropped_before_listing += len(usable) - len(kept)
        if not kept:
            continue
        caps = {b.session: captures_by_session[key][b.session] for b in kept}     # una captura por barra conservada (R16-02)
        last_rec = caps[kept[-1].session]                                          # la de la última barra conservada (R16-03)
        src, deriv = sources[v.market]
        securities[v.security_id] = Security(v.symbol, v.security_id, v.market, v.name_zh, v.valid_from, v.valid_to, kept, [], last_rec, None, [],
                                             src, deriv, {d: r.capture_id for d, r in caps.items()})
        by_symbol[v.symbol] = v.security_id
        by_session[v.security_id] = {b.session: b for b in kept}
    traded: set[date] = set().union(*[set(m) for m in by_session.values()]) if by_session else set()
    warnings = ["sin derechos: la fuente oficial por fecha no trae dividendos; libro y etiquetas operan sin ellos"]
    if missing:
        warnings.append(f"sesiones oficiales sin captura: {len(missing)} (p. ej. {', '.join(missing[:3])})")
    if closed_sessions:
        warnings.append(f"sesiones oficiales sin datos (cierres sobrevenidos u otros): {len(closed_sessions)} (p. ej. {', '.join(closed_sessions[:3])})")
    return MarketData(securities, by_symbol, master, calendar, by_session, traded, dropped,
                      f"official_daily_quotes:{start.isoformat()}..{end.isoformat()}", dropped_before_listing, warnings, par_value)


# ---------------------------------------------------------------------------------------------------
# Pronosticadores: sólo ven el paquete (PredictorView) y la lista de candidatos derivada de él.
# ---------------------------------------------------------------------------------------------------

@dataclass
class Candidate:
    security_id: str
    symbol: str
    doc_id: str
    sessions: list                 # [[fecha, apertura, cierre, volumen, importe], ...] del documento
    scorable: bool
    eligible: bool
    reasons: tuple[str, ...]


@dataclass
class Selection:
    security_id: str
    score: float
    doc_ids: list[str]
    feature_ids: list[str] = field(default_factory=list)


class Forecaster(Protocol):
    name: str
    model_id: str
    version: str

    def forecast(self, view: PredictorView, plan: WeekPlan, candidates: Sequence[Candidate], *, slots: int) -> tuple[list[Selection], dict]:
        """Devuelve selecciones ordenadas (como máximo ``slots``) y metadatos (training_manifest_id, limitaciones)."""


class MomentumForecaster:
    """Q0: rentabilidad de 20 sesiones sobre las barras nominales del paquete. Control transparente."""
    name, model_id, version = "Q0", "rule:momentum_20_sessions_v1", "q0_v1"

    def forecast(self, view, plan, candidates, *, slots):
        scored = []
        for c in candidates:
            if not (c.scorable and c.eligible) or len(c.sessions) < 21:
                continue
            closes = [D(s[2]) for s in c.sessions]
            scored.append(Selection(c.security_id, float(closes[-1] / closes[-21] - 1), [c.doc_id], ["ret_20s", "median_value_20s"]))
        return sorted(scored, key=lambda s: s.score, reverse=True)[:slots], {"training_manifest_id": None}


class RandomForecaster:
    """A1: cinco valores al azar entre los elegibles de la semana, con semilla declarada."""
    name, model_id, version = "A1", "rule:random_eligible_v1", "a1_v1"

    def __init__(self, seed: int) -> None:
        self.rng = random.Random(seed)

    def forecast(self, view, plan, candidates, *, slots):
        eligible = [c for c in candidates if c.eligible]
        picks = self.rng.sample(eligible, min(slots, len(eligible))) if eligible else []
        return [Selection(c.security_id, 0.0, [c.doc_id], []) for c in picks], {"training_manifest_id": None}


def dividend_known_at(dv: finmind.DividendRow, calendar: TradingCalendar) -> tuple[Optional[datetime], str]:
    """Instante en que el derecho era público, con la política del protocolo (R11-01, ronda 12).

    Hora de anuncio publicada → ese instante (``verified_original`` en cuanto a anuncio; FinMind no acredita
    versiones posteriores de importes o fechas, y así se declara). Sólo fecha → apertura de la primera sesión
    posterior (``derive_available_at``, ``conservative_inference``). Sin anuncio → desconocido.
    """
    if dv.announced_at is not None:
        return dv.announced_at, AvailabilityQuality.VERIFIED_ORIGINAL.value
    if dv.announced_date is not None:
        try:
            av = derive_available_at(dv.announced_date, calendar=calendar)
        except Exception:
            return None, AvailabilityQuality.UNKNOWN.value
        return av.available_at, av.quality.value
    return None, AvailabilityQuality.UNKNOWN.value


def _finite_nonneg(x) -> bool:
    return isinstance(x, D) and x.is_finite() and x >= 0


def validated_dividend_events(sec_id: str, rows: Sequence[finmind.DividendRow], par_value: D,
                              calendar: TradingCalendar) -> tuple[list[q1mod.DividendLike], list[str]]:
    """La **única** lista de derechos que consumen el libro y las etiquetas de Q1 (R12-01, R13-02..05).

    Las filas se agrupan por (tipo, fecha ex) **antes** de filtrar importes: un mismo derecho con filas
    contradictorias (importes distintos, cero junto a positivo, periodos distintos, anuncios distintos), con
    una fila inválida (importe no finito o negativo, periodo vacío, pago anterior a la fecha ex) no se
    descarta en silencio: produce un derecho **ambiguo** que invalida las etiquetas y los intervalos de las
    posiciones afectadas. Las filas idénticas repetidas cuentan una vez; sólo ceros = ningún derecho.
    """
    groups: dict[tuple[str, date], list[dict]] = {}
    for dv in rows:
        known_at, quality = dividend_known_at(dv, calendar)
        if dv.cash_ex_date is not None:
            groups.setdefault(("cash", dv.cash_ex_date), []).append(
                {"amount": dv.cash_per_share, "pay": dv.cash_pay_date, "period": str(dv.period or "").strip(), "known_at": known_at, "quality": quality})
        if dv.stock_ex_date is not None:
            groups.setdefault(("stock", dv.stock_ex_date), []).append(
                {"amount": dv.stock_per_share, "pay": None, "period": str(dv.period or "").strip(), "known_at": known_at, "quality": quality})
    events: list[q1mod.DividendLike] = []
    problems: list[str] = []
    for (kind, exd), members in groups.items():
        invalid: list[str] = []
        for m in members:
            if not _finite_nonneg(m["amount"]):
                invalid.append("non_finite_or_negative_amount")
            if not m["period"] and (isinstance(m["amount"], D) and m["amount"] != 0):
                invalid.append("missing_period")
            if kind == "cash" and m["pay"] and m["pay"] < exd:
                invalid.append("pay_before_ex")
        positive = [m for m in members if _finite_nonneg(m["amount"]) and m["amount"] > 0]
        zero = [m for m in members if _finite_nonneg(m["amount"]) and m["amount"] == 0]
        distinct = {(m["amount"], m["pay"], m["period"], m["known_at"]) for m in positive}
        period = positive[0]["period"] if positive else ""
        eid = f"{sec_id}:{kind}:{exd.isoformat()}:{period}"
        if invalid or len(distinct) > 1 or (positive and zero):
            why = "invalid member (" + ", ".join(sorted(set(invalid))) + ")" if invalid else ("zero and positive rows" if (positive and zero) else "different values")
            problems.append(f"{eid}: {len(members)} rows with {why}; right marked AMBIGUOUS: labels and intervals of holders are invalid (R13-02..05)")
            events.append(q1mod.DividendLike(eid, exd, kind, known_at=None, ambiguous=True))
            continue
        if not positive:
            continue                                        # sólo ceros: no hay derecho
        m = positive[0]
        if kind == "cash":
            events.append(q1mod.DividendLike(eid, exd, "cash", cash_per_share=m["amount"], known_at=m["known_at"], pay_date=m["pay"],
                                             known_quality=m["quality"]))
        else:
            events.append(q1mod.DividendLike(eid, exd, "stock", stock_ratio=m["amount"] / par_value, known_at=m["known_at"], pay_date=None,
                                             known_quality=m["quality"], stock_per_share=m["amount"], par_value=par_value))
    return sorted(events, key=lambda e: (e.ex_date, 0 if e.kind == "cash" else 1)), problems


class TabularForecaster:
    """Q1: características de precio/volumen del paquete y modelo entrenado sólo con etiquetas conocidas al corte."""
    name, model_id, version = "Q1", q1mod.MODEL_ID, "q1_v1"

    def __init__(self, market: MarketData, *, retrain_every_weeks: int = 4, min_weeks: int = 52, seed: int = 20260909) -> None:
        self.market = market
        self.retrain_every = retrain_every_weeks
        self.min_weeks = min_weeks
        self.seed = seed
        self.par_value = market.par_value
        self.model: Optional[q1mod.Q1Model] = None
        self.trained_for: Optional[datetime] = None
        self.last_cutoff: Optional[datetime] = None
        self.weeks_since_train = 0
        self.cache: dict = {}
        self.history: list[str] = []
        self.data_version = market.data_version
        # la misma lista validada de derechos que aplica el libro (R12-01): identidad, importes, instante de conocimiento
        self.dividends = {sec_id: s.events for sec_id, s in market.securities.items()}

    def maybe_train(self, cutoff_at: datetime) -> None:
        if self.market.data_version != self.data_version:
            raise ValueError("MarketData changed after this forecaster was built (data_version differs); build a new forecaster (R14-06)")
        if self.last_cutoff is not None and cutoff_at < self.last_cutoff:
            raise ValueError(f"cutoffs must be non-decreasing ({cutoff_at.isoformat()} < {self.last_cutoff.isoformat()}); "
                             "a TabularForecaster serves one chronological run (R10-02)")
        self.last_cutoff = cutoff_at
        if self.model is not None and self.weeks_since_train < self.retrain_every:
            self.weeks_since_train += 1
            return
        first = min(b.session for s in self.market.securities.values() for b in s.bars[:1])
        cutoffs = []
        d = first + timedelta(days=(6 - first.weekday()) % 7)
        while d < cutoff_at.date():
            cutoffs.append(taipei(d, time(18, 0)))
            d += timedelta(days=7)
        bars = {sec_id: s.bars for sec_id, s in self.market.securities.items()}
        rows = q1mod.build_training_rows(bars, cutoffs, now_cutoff=cutoff_at, calendar=self.market.calendar,
                                         dividends_by_security=self.dividends, cache=self.cache, data_version=self.data_version)
        self.model = q1mod.fit_q1(rows, trained_at=cutoff_at, min_weeks=self.min_weeks, seed=self.seed)
        self.trained_for = cutoff_at
        self.weeks_since_train = 1
        self.history.append(f"{cutoff_at.date().isoformat()}: {self.model.training_manifest_id if self.model else 'insufficient_history'}")

    def forecast(self, view, plan, candidates, *, slots):
        self.maybe_train(plan.cutoff_at)
        meta = {"training_manifest_id": self.model.training_manifest_id if self.model else None}
        if self.model is None:
            return [], {**meta, "status_reason": "insufficient_training_history"}
        feats, elig = [], []
        for c in candidates:
            if not (c.scorable and c.eligible):
                continue
            bars = [q1mod.BarLike(date.fromisoformat(s[0]), D(s[1]), D(s[2]), D(s[4]), plan.cutoff_at) for s in c.sessions]
            f = q1mod.features_from_bars(bars, plan.cutoff_at)
            if f is not None:
                feats.append(f)
                elig.append(c)
        if not feats:
            return [], {**meta, "status_reason": "no_eligible_securities"}
        scores = self.model.predict(feats)
        ranked = sorted(zip(elig, scores), key=lambda t: t[1], reverse=True)[:slots]
        return [Selection(c.security_id, float(s), [c.doc_id], list(q1mod.FEATURE_NAMES)) for c, s in ranked], meta


# ---------------------------------------------------------------------------------------------------

def _week_costs(slots) -> D:
    total = D(0)
    for s_ in slots:
        for f in (s_.entry, s_.exit):
            if f is not None:
                total += f.commission + f.tax + f.slippage_cost
    return total


def _sundays(start: date, end: date):
    d = start + timedelta(days=(6 - start.weekday()) % 7)
    while d <= end:
        yield d
        d += timedelta(days=7)


# fallos del archivo que impiden emitir o evaluar una semana; la semana queda registrada como ``invalid:archive`` y la
# corrida continúa (R26-03). Los paquetes archivados corruptos siguen siendo un rechazo deliberado (ManifestInconsistent, R20-04).
ARCHIVE_ERRORS = (ManifestInconsistent, IntegrityError, ManifestCorrupt, MissingCapture, OSError)


class Runner:
    def __init__(self, store: RawStore, market: MarketData, cfg: BacktestConfig, forecasters: Sequence[Forecaster]) -> None:
        self.store, self.market, self.cfg = store, market, cfg
        self._master_rec: Optional[CaptureRecord] = None
        self.forecasters = {f.name: f for f in forecasters}
        if cfg.baseline not in self.forecasters:
            raise ValueError(f"baseline {cfg.baseline!r} is not among the forecasters")
        for f in forecasters:
            # un pronosticador ligado a un mercado sirve sólo a ese mercado (R11-04) y convierte los derechos con el mismo
            # valor nominal que el libro (R11-03)
            if getattr(f, "market", None) is not None and getattr(f, "market") is not market:
                raise ValueError(f"forecaster {f.name} is bound to a different MarketData; build one per run (R11-04)")
            if getattr(f, "par_value", None) is not None and getattr(f, "par_value") != cfg.par_value:
                raise ValueError(f"forecaster {f.name} converts stock dividends with par_value={getattr(f, 'par_value')} "
                                 f"but the ledger uses {cfg.par_value} (R11-03)")
        if market.par_value != cfg.par_value:
            raise ValueError(f"market events were validated with par_value={market.par_value} but the ledger uses {cfg.par_value} (R11-03)")
        costs = CostModel(commission_per_side=cfg.commission_per_side, sell_tax=cfg.sell_tax, slippage_bps_per_side=cfg.slippage_bps,
                          min_commission_twd=cfg.min_commission_twd)
        self.costs = costs
        self.initial = D(cfg.notional * cfg.slots)
        self.ledgers = {n: PaperLedger(ledger_id=n, initial_cash=self.initial, cost_model=costs, lot_size=cfg.lot_size) for n in self.forecasters}
        self.open_slots: dict[str, list] = {n: [] for n in self.forecasters}
        self.ambiguous_positions: dict[str, set[str]] = {n: set() for n in self.forecasters}
        self.ambiguous_claims: dict[str, set[str]] = {n: set() for n in self.forecasters}     # derechos no aplicados: incertidumbre permanente
        self.ambiguous_hits: dict[str, list[tuple[str, date]]] = {n: [] for n in self.forecasters}   # (valor, fecha ex) de cada derecho ambiguo sufrido
        self.prev_equity = {n: self.initial for n in self.forecasters}
        self.cursor = {n: cfg.start - timedelta(days=1) for n in self.forecasters}
        self.weeks: list[dict] = []
        self.last_data_day = max(market.traded_days) if market.traded_days else cfg.start

    # -- precios y eventos --------------------------------------------------------------------------
    def marks(self, session: date, ledger: PaperLedger, kind: str, *, valued_at: Optional[date] = None) -> tuple[dict[str, D], list[str]]:
        """Precios para valorar en ``valued_at`` (por defecto la propia sesión) usando la sesión ``session``.

        Si un valor no tiene precio regular en ``session`` se usa su último cierre con marca ``stale_price``; y si
        entre la sesión del precio usado y ``valued_at`` hay un derecho aplicado, el precio es anterior al derecho
        y se marca ``price_predates_right`` (R12-02): esa valoración no es un precio de mercado posterior al evento.
        """
        out, stale = {}, []
        valued_at = valued_at or session
        # un derecho ambiguo no aplicado hace incierto el patrimonio para siempre, con o sin la posición (R13-05, R14-03)
        stale.extend(f"ambiguous_right:{eid}" for eid in sorted(self.ambiguous_claims.get(ledger.ledger_id, ())))
        for sec, pos in ledger.positions.items():
            if pos.status.startswith("delisted"):
                if pos.terminal_price is None:
                    stale.append(f"unresolved_terminal:{sec}")   # valor terminal no resuelto: el cero contable no es un precio (R13-06)
                continue
            b = self.market.by_session.get(sec, {}).get(session)
            if b is None:
                prev = [x for x in self.market.securities[sec].bars if x.session <= session]
                if not prev:
                    continue
                out[sec] = prev[-1].close
                price_session = prev[-1].session
                stale.append(f"stale_price:{sec}:{price_session.isoformat()}")
            else:
                out[sec] = b.open if kind == "open" else b.close
                price_session = session
            for e in self.market.securities[sec].events:
                if price_session < e.ex_date <= valued_at:
                    stale.append(f"price_predates_right:{sec}:{e.ex_date.isoformat()}")
        return out, stale

    def apply_actions(self, name: str, upto: date) -> int:
        ledger = self.ledgers[name]
        since = self.cursor[name]
        if upto <= since:
            return 0
        events = []
        for sec in list(ledger.positions):
            s = self.market.securities[sec]
            for e in s.events:                               # la lista validada, la misma que usan las etiquetas (R12-01)
                if since < e.ex_date <= upto:
                    events.append((e.ex_date, e.kind, sec, e))
            if s.delisting_date and since < s.delisting_date <= upto:
                events.append((s.delisting_date, "delisting", sec, None))
        n = 0
        for exd, kind, sec, e in sorted(events, key=lambda ev: (ev[0], ev[1])):
            at = taipei(exd, PRE_OPEN)
            if e is not None and e.ambiguous:
                # el derecho no puede aplicarse: desde aquí el patrimonio del libro es incierto (cantidad o efectivo no
                # registrados) y lo sigue siendo aunque la posición se venda (R13-05, R14-03). La fecha se conserva para
                # invalidar sólo los lotes que la tenían en cartera (R15-06).
                self.ambiguous_positions[name].add(sec)
                self.ambiguous_claims[name].add(e.event_id)
                self.ambiguous_hits[name].append((sec, exd))
                self.weeks[-1].setdefault("ambiguous_rights", []).append(f"{name}:{e.event_id}")
                continue
            try:
                if kind == "cash":
                    pay = taipei(e.pay_date, time(9, 0)) if e.pay_date else None
                    ledger.apply_corporate_action(CorporateAction(e.event_id, sec, "cash_dividend", at, per_share_cash=e.cash_per_share, pay_at=pay))
                elif kind == "stock":
                    exact = e.par_value > 0
                    ledger.apply_corporate_action(CorporateAction(e.event_id, sec, "stock_dividend", at,
                                                                  stock_ratio=None if exact else e.stock_ratio,
                                                                  stock_per_share=e.stock_per_share if exact else None,
                                                                  par_value=e.par_value if exact else None))
                elif kind == "delisting":
                    ledger.apply_corporate_action(CorporateAction(f"{sec}:delisting:{exd}", sec, "delisting", at, terminal_price=None))
                else:
                    continue
                n += 1
            except LedgerError as exc:
                self.weeks[-1].setdefault("action_errors", []).append(f"{name}:{sec}:{kind}:{exd}:{exc}")
        self.cursor[name] = upto
        return n

    # -- paquete y candidatos ------------------------------------------------------------------------
    def build_week_packet(self, plan: WeekPlan) -> tuple[Packet, object, list[Candidate]]:
        cutoff = plan.cutoff_at
        docs = []
        # Procedencia de fuentes por fecha (R16-02): un documento «capture_manifest» por fuente enumera, sesión a sesión,
        # la captura que respalda las barras de esa fuente conocidas al corte; cada serie lo referencia (captures_doc) y
        # lleva como capture_id/source_sha256 los de su última barra conocida. Así la lista completa queda archivada una
        # vez por paquete y no 1.937 veces.
        manifests: dict[str, dict[str, str]] = {}
        manifest_caps: dict[str, dict] = {}
        for s in self.market.securities.values():
            if not s.bar_captures:
                continue
            m = manifests.setdefault(s.source_id, {})
            for d, cap in s.bar_captures.items():
                if taipei(d).replace(hour=13, minute=30) + finmind.PRICE_AVAILABILITY_LAG <= cutoff:
                    key = d.isoformat()
                    if key in m and m[key] != cap:
                        # dos series de la misma fuente no pueden referenciar capturas distintas de una misma sesión (R18-02):
                        # el manifiesto común no sobrescribe; el conflicto detiene la construcción del paquete
                        raise ManifestInconsistent(f"conflicting session captures for {s.source_id} {key}: {m[key]} vs {cap} ({s.symbol})")
                    m[key] = cap
        for src, entries in manifests.items():
            if not entries:
                continue
            last_session = max(entries)
            last_cap = self.store.get(entries[last_session])
            manifest_caps[src] = last_cap
            docs.append(Document(
                doc_id=f"{src}:captures:{plan.week_id}", kind="capture_manifest", source_id=src, security_ids=(),
                available_at=taipei(date.fromisoformat(last_session)).replace(hour=13, minute=30) + finmind.PRICE_AVAILABILITY_LAG,
                availability_quality=AvailabilityQuality.CONSERVATIVE_INFERENCE, capture_id=last_cap.capture_id, source_sha256=last_cap.sha256,
                derivation="capture_manifest_v1", payload={"session_captures": dict(sorted(entries.items()))},
            ))
        provenance_rejected: list[tuple[str, str, int]] = []
        for sec_id, s in self.market.securities.items():
            known = [b for b in s.bars if b.available_at <= cutoff]
            if not known:
                continue
            window = known[-130:]
            if s.bar_captures or s.source_id in SESSION_CAPTURE_SOURCES:
                # toda sesión de la serie debe estar respaldada por una captura enumerada (R17-03); un mapa vacío en una
                # fuente por fecha no convierte la serie en una de captura única (R18-01): tampoco se admite
                missing = [b.session for b in window if b.session not in s.bar_captures]
                if missing:
                    provenance_rejected.append((sec_id, s.symbol, len(missing)))
                    continue
            last_cap = self.store.get(s.bar_captures[known[-1].session]) if s.bar_captures else s.price_capture
            payload = {"history_sessions": len(known), "last_session": known[-1].session.isoformat(), "name": s.name,
                       "sessions": [[b.session.isoformat(), str(b.open), str(b.close), b.volume_shares, str(b.value_twd)] for b in window]}
            if s.bar_captures:
                payload["captures_doc"] = f"{s.source_id}:captures:{plan.week_id}"
            docs.append(Document(
                doc_id=f"{s.symbol}:bars:{plan.week_id}", kind="price_bar_series", source_id=s.source_id, security_ids=(sec_id,),
                available_at=known[-1].available_at, availability_quality=AvailabilityQuality.CONSERVATIVE_INFERENCE,
                capture_id=last_cap.capture_id, source_sha256=last_cap.sha256, derivation=s.derivation, payload=payload,
            ))
        alabel = self.cfg.archive_label or self.cfg.label
        packet = build_packet(packet_id=f"pkt-{alabel}-{plan.week_id}", cutoff_at=cutoff, documents=docs, mode="historical",
                              evidence_class=EVIDENCE, calendar=self.market.calendar)
        # un paquete idéntico (mismo packet_hash, que excluye created_at) ya archivado se reutiliza: conserva la hora
        # real de su primera ingestión y evita duplicar ~13 MB por semana y corrida (ciclo semanal)
        rec = self.store.find(source_id="packet", dataset=f"{alabel}/{plan.week_id}", extra_equal={"packet_hash": packet.packet_hash()})
        if rec is not None:
            # los metadatos no bastan (R20-04): se leen los bytes (integridad sha256) y se re-deriva el hash de contenido
            try:
                archived = packet_from_json(self.store.read(rec))
            except (IntegrityError, OSError, ValueError, KeyError, TypeError) as exc:
                raise ManifestInconsistent(f"archived packet {rec.capture_id} is unreadable or corrupt: {exc}") from exc
            if archived.packet_hash() != packet.packet_hash():
                raise ManifestInconsistent(f"archived packet {rec.capture_id} does not re-derive to packet_hash {packet.packet_hash()}")
        if rec is None:
            rec = self.store.put(source_id="packet", dataset=f"{alabel}/{plan.week_id}", payload=packet_to_json(packet),
                                 url="local://backtest", content_type="application/json",
                                 extra={"packet_hash": packet.packet_hash(), "evidence_class": EVIDENCE})
        last_session = self.market.calendar.prev_session(before=cutoff.date())
        candidates: list[Candidate] = []
        for doc in packet.admitted:
            if doc.kind != "price_bar_series":
                continue
            sec_id = doc.security_ids[0]
            s = self.market.securities[sec_id]
            sessions = list(doc.payload["sessions"])
            values = [D(x[4]) for x in sessions[-20:]]
            try:
                sv = self.market.master.resolve_symbol(s.symbol, as_of=last_session)
            except UnknownSymbol:
                candidates.append(Candidate(sec_id, s.symbol, doc.doc_id, sessions, False, False, ("not_in_catalog_as_of_last_session",)))
                continue
            median_value = statistics.median(values) if values else D(0)
            status_ok = doc.payload["last_session"] == last_session.isoformat()
            cov = classify_coverage(sv, price_history_sessions=int(doc.payload["history_sessions"]),
                                    min_history_sessions=self.cfg.min_history_sessions,
                                    trading_status="normal" if status_ok else "no_bar_on_last_session",
                                    liquidity_ok=median_value >= D(self.cfg.liquidity_multiple * self.cfg.notional))
            candidates.append(Candidate(sv.security_id, s.symbol, doc.doc_id, sessions, cov.numerically_scorable, cov.simulation_eligible, cov.reasons))
        for sec_id, symbol, n_missing in provenance_rejected:
            candidates.append(Candidate(sec_id, symbol, "", [], False, False, (f"provenance_incomplete:{n_missing}_sessions_without_capture",)))
        return packet, rec, candidates

    def make_forecast(self, f: Forecaster, plan: WeekPlan, packet: Packet, selections: list[Selection], meta: dict, candidates) -> dict:
        eligible = [c for c in candidates if c.eligible]
        scorable = [c for c in candidates if c.scorable]
        obj = {
            "schema_version": "2.0", "forecast_id": f"{f.name}-{plan.week_id}", "experiment_id": f.name, "protocol_version": "2.0-draft-backtest",
            "packet_id": packet.packet_id, "cutoff_at": plan.cutoff_at.isoformat(), "issued_at": (plan.cutoff_at + timedelta(minutes=5)).isoformat(),
            "deadline_at": plan.deadline_at.isoformat(), "timezone": "Asia/Taipei", "evidence_class": EVIDENCE,
            "model": {"requested_id": f.model_id, "returned_id": f.model_id, "revision_id": None,
                      "prompt_or_feature_version": f.version, "training_manifest_id": meta.get("training_manifest_id")},
            "coverage": {"catalog_count": len(self.market.securities), "scored_count": len(scorable), "deep_review_count": 0,
                         "eligible_count": len(eligible), "missing_critical_sources": []},
            "status": "selected" if selections else "abstained",
            "ranking": [{"security_id": s.security_id, "ticker_as_of": self.market.securities[s.security_id].symbol, "market": self.market.securities[s.security_id].market,
                         "rank": i + 1, "score": s.score, "score_definition": f"{f.model_id} sobre barras nominales del paquete",
                         "document_ids": s.doc_ids, "feature_ids": s.feature_ids, "impact_hypothesis": None, "counterargument": None,
                         "calibrated_probability": None, "calibration_model_id": None} for i, s in enumerate(selections)],
            "limitations": ["universo del censo vigente (sesgo de supervivencia)", "disponibilidad de barras por política de 24 h, no verificada",
                            "costes ilustrativos; deslizamiento central no congelado", "regla de liquidez provisional, no del protocolo"],
        }
        if not selections:
            obj["status_reason"] = meta.get("status_reason", "no_eligible_securities")
        return obj

    # -- una semana ------------------------------------------------------------------------------------
    def run_week(self, sunday: date) -> None:
        cfg = self.cfg
        cutoff = taipei(sunday, time(18, 0))
        try:
            self._check_market()                                        # antes de planificar: sin calendario no hay plan (R28-04)
        except ManifestInconsistent as exc:
            iso = (sunday + timedelta(days=1)).isocalendar()
            self.weeks.append({"week_id": f"{iso[0]}-W{iso[1]:02d}", "cutoff_at": cutoff.isoformat(), "status": "invalid:archive",
                               "forecasters": {}, "pending_outcome": False, "archive_error": f"{type(exc).__name__}: {exc}"[:300],
                               "note": f"invalid:archive ({type(exc).__name__}): mercado inutilizable; semana no planificada"})
            return
        plan = plan_week(cutoff, self.market.calendar)
        record: dict = {"week_id": plan.week_id, "cutoff_at": cutoff.isoformat(), "status": plan.status, "forecasters": {}}
        self.weeks.append(record)
        bound = min(cfg.end, self.last_data_day)
        if not plan.is_valid:
            week_end = plan.target_monday + timedelta(days=6)
            if plan.target_monday > bound:                  # semana sin sesiones más allá del límite: sólo se registra (R10-07)
                record["note"] = "invalid:no_sessions (registrado; fuera del límite de simulación)"
                record["pending_outcome"] = True
                return
            upto = min(week_end, bound)                     # nunca se procesa ni se valora más allá del límite
            last_close = self.market.calendar.prev_session(before=upto + timedelta(days=1))
            for name, lg in self.ledgers.items():
                self.apply_actions(name, upto)
                lg.advance_to(taipei(upto, time(23, 59)))
                prices, stale = self.marks(last_close, lg, "close", valued_at=upto)
                try:
                    v = lg.valuation(prices=prices, at=taipei(upto, time(23, 59)))
                    record["forecasters"][name] = {"equity_end": float(v.total), "flags": list(v.flags)[:6] + stale}
                    self.prev_equity[name] = v.total
                except MissingPrice as exc:
                    record["forecasters"][name] = {"equity_end": None, "flags": [f"missing_price:{exc}"] + stale}
            record["note"] = "invalid:no_sessions (registrado, sin operaciones; eventos procesados hasta el límite)"
            return
        try:
            emitted = self._emit_week(plan, record, bound)
        except ARCHIVE_ERRORS as exc:
            # el archivo no permite emitir con garantías: la semana queda registrada como fallida (con la traza de lo
            # que llegó a archivarse antes del fallo), sin evaluación, y la corrida continúa con la siguiente (R26-03);
            # el libro sigue vivo: derechos, reintento de salidas heredadas y valoración (R27-05)
            record["status"] = "invalid:archive"
            record["archive_error"] = f"{type(exc).__name__}: {exc}"[:300]
            record["note"] = f"invalid:archive ({type(exc).__name__}): semana no emitida ni evaluada; posiciones heredadas gestionadas"
            self._carry_inherited(plan, record, bound)
            return
        # la evaluación queda fuera de la contención: un fallo en ella no es del archivo y no debe intentar
        # retroceder libros ya operados (R28-05); se propaga tal cual
        self._evaluate_week(plan, record, bound, *emitted)

    def _check_market(self) -> None:
        """El mercado en memoria debe tener la forma que la emisión presupone; si no, no se emite nada (R28-04)."""
        m = self.market
        if not isinstance(m.master, SecurityMaster):
            raise ManifestInconsistent("security master unavailable: the market does not carry a SecurityMaster")
        if not all(isinstance(v, SecurityVersion) for v in m.master._versions):  # noqa: SLF001
            raise ManifestInconsistent("security master contains rows that are not SecurityVersion")
        if not isinstance(m.calendar, TradingCalendar):
            raise ManifestInconsistent("market calendar unavailable")
        if not isinstance(m.securities, dict) or not isinstance(m.by_session, dict) or not isinstance(m.by_symbol, dict):
            raise ManifestInconsistent("market structures unavailable (securities, by_session, by_symbol)")

    def _carry_inherited(self, plan: WeekPlan, record: dict, bound: date) -> None:
        """Semana sin emisión: se aplican los derechos, se reintentan las salidas de las cestas heredadas en el último
        cierre de la semana y se valora el libro, exactamente como en una semana válida pero sin cesta nueva (R27-05)."""
        entry_s, exit_s = plan.entry_at.date(), plan.exit_at.date()
        if entry_s > bound:
            record["pending_outcome"] = True
            return
        pending_exit = exit_s > bound
        record["pending_outcome"] = pending_exit
        close_prices = {} if pending_exit else {sec: m[exit_s].close for sec, m in self.market.by_session.items() if exit_s in m}
        for name, lg in self.ledgers.items():
            self.apply_actions(name, entry_s)
            lg.advance_to(plan.entry_at)
            fr = record["forecasters"].setdefault(name, {})
            if pending_exit:
                fr["note"] = "semana no emitida; salida heredada pendiente"
                continue
            self.apply_actions(name, exit_s)
            for wid, ss in self.open_slots[name]:
                exit_basket(lg, ss, close_prices=close_prices, at=plan.exit_at, week_id=wid)
            self.open_slots[name] = [(wid, ss) for wid, ss in self.open_slots[name]
                                     if any(s.status in ("filled", "exit_blocked") or (s.status == "exited" and not s.liquidated) for s in ss)]
            lg.advance_to(plan.exit_at)                        # el reloj del libro llega al cierre aunque no haya cestas (R28-02)
            close_marks, stale = self.marks(exit_s, lg, "close")
            try:
                v = lg.valuation(prices=close_marks, at=plan.exit_at)
                fr.update({"equity_end": float(v.total), "flags": list(v.flags)[:6] + stale, "baskets_in_follow_up": len(self.open_slots[name]),
                           "note": "semana no emitida; cestas heredadas gestionadas"})
                self.prev_equity[name] = v.total
            except MissingPrice as exc:
                fr.update({"equity_end": None, "flags": [f"missing_price:{exc}"] + stale, "note": "semana no emitida; cestas heredadas gestionadas"})

    def _emit_week(self, plan: WeekPlan, record: dict, bound: date):
        """Emisión de la semana: paquete, maestro y predicciones archivadas. Devuelve lo que la evaluación necesita."""
        cfg = self.cfg
        self._check_market()                                            # (R27-06, R28-04)
        packet, pkt_rec, candidates = self.build_week_packet(plan)
        mrec = self.master_record()             # el maestro se archiva antes que cualquier predicción que lo cite (R24-02)
        view = PredictorView(packet)
        entry_s, exit_s = plan.entry_at.date(), plan.exit_at.date()
        # Límite de simulación (R09-06, R10-07): nunca más allá del final del periodo pedido ni del último dato.
        # La entrada se ejecuta si su sesión está dentro del límite; la salida sólo si también lo está. Lo que
        # queda fuera no se intenta (ni se marca bloqueado) ni se consulta: queda pendiente para una corrida posterior.
        pending_entry, pending_exit = entry_s > bound, exit_s > bound
        record.update(eligible=sum(1 for c in candidates if c.eligible), scored=sum(1 for c in candidates if c.scorable),
                      coverage_reasons=dict(collections.Counter(r.split(":")[0] for c in candidates for r in c.reasons)),
                      pending_outcome=pending_exit)
        picks: dict[str, list[str]] = {}
        for name, f in self.forecasters.items():
            try:
                selections, meta = f.forecast(view, plan, candidates, slots=cfg.slots)
                meta = meta if isinstance(meta, dict) else {}
                obj = self.make_forecast(f, plan, packet, selections, meta, candidates)
                if not isinstance(obj, dict):
                    raise TypeError(f"make_forecast returned {type(obj).__name__}, not a dict")
                problems = validate_prediction(obj, packet, calendar=self.market.calendar, experiment_ids=list(self.forecasters))
            except Exception as exc:  # noqa: BLE001 - un pronosticador roto no aborta la semana: queda como predicción inválida (R28-04)
                selections, meta = [], {}
                problems = [f"forecast_error:{type(exc).__name__}:{str(exc)[:120]}"]
                obj = self._invalid_forecast(f, plan, packet, problems[0])
            if any(not isinstance(obj.get(k), str) for k in ("cutoff_at", "deadline_at", "status")) or not isinstance(obj.get("ranking"), list):
                selections, problems = [], ["forecast_error:missing_or_mistyped_fields"]           # contrato mínimo del archivo (R28-04)
                obj = self._invalid_forecast(f, plan, packet, problems[0])
            if problems:
                obj["status"], obj["ranking"], obj["status_reason"] = "invalid", [], "; ".join(problems[:3])
            # la predicción archivada fija los bytes del paquete (hash lógico) y del maestro (sha256) con los que se resolvió
            fpayload = canonical_bytes({"forecast": obj, "packet_hash": packet.packet_hash(), "master_sha256": mrec.sha256})
            fsha = hashlib.sha256(fpayload).hexdigest()
            fdataset = f"{cfg.archive_label or cfg.label}/{name}/{plan.week_id}"
            frec = self.store.find(source_id="forecast", dataset=fdataset, sha256=fsha)
            if frec is not None:
                try:
                    self.store.read(frec)                        # integridad de los bytes reutilizados (R20-04)
                except (IntegrityError, OSError):                # corrupta o ausente: se vuelve a archivar (R26-03)
                    frec = None
            if frec is None:
                # bytes idénticos ya archivados e íntegros: se conserva la primera ingestión (la única que vale como fecha de emisión)
                frec = self.store.put(source_id="forecast", dataset=fdataset, payload=fpayload, url="local://backtest",
                                      content_type="application/json", extra={"packet_hash": packet.packet_hash(), "packet_capture": pkt_rec.capture_id,
                                                                              "master_capture": mrec.capture_id})
            picks[name] = [s.security_id for s in selections] if obj["status"] == "selected" else []
            record["forecasters"][name] = {"picks": [{"security_id": p, "symbol": self.market.securities[p].symbol,
                                                      "name": self.market.securities[p].name} for p in picks[name]],
                                           "forecast_status": obj["status"], "status_reason": obj.get("status_reason"),
                                           "training_manifest_id": meta.get("training_manifest_id"), "validation_problems": problems,
                                           # identidad exacta de la predicción evaluada (R20-01): la clasificación temporal se resuelve por estos bytes
                                           "forecast_sha256": fsha, "forecast_capture_id": frec.capture_id, "deadline_at": obj["deadline_at"]}
        record["packet_capture"] = pkt_rec.capture_id
        record["packet_hash"] = packet.packet_hash()
        # el maestro citado debe ser el vigente durante toda la emisión: si cambió entre la instantánea y las
        # predicciones, la semana no puede darse por emitida con garantías (R27-03)
        if hashlib.sha256(master_snapshot_bytes(self.market.master)).hexdigest() != mrec.sha256:
            raise ManifestInconsistent(f"{plan.week_id}: the security master changed during emission; predictions cite {mrec.sha256[:12]}")
        record["master_capture"] = mrec.capture_id                          # identidad de los valores (R23-01)
        record["master_sha256"] = mrec.sha256
        return picks, candidates, entry_s, exit_s, pending_entry, pending_exit

    def _invalid_forecast(self, f: Forecaster, plan: WeekPlan, packet: Packet, reason: str) -> dict:
        """Predicción inválida mínima (contrato del laboratorio) cuando el pronosticador falla al construir la suya (R28-04)."""
        return {"schema_version": "2.0", "forecast_id": f"{f.name}-{plan.week_id}", "experiment_id": f.name,
                "protocol_version": "2.0-draft-backtest", "packet_id": packet.packet_id, "cutoff_at": plan.cutoff_at.isoformat(),
                "issued_at": (plan.cutoff_at + timedelta(minutes=5)).isoformat(), "deadline_at": plan.deadline_at.isoformat(),
                "timezone": "Asia/Taipei", "evidence_class": EVIDENCE, "status": "invalid", "ranking": [], "status_reason": reason}

    def _evaluate_week(self, plan: WeekPlan, record: dict, bound: date, picks, candidates, entry_s, exit_s, pending_entry, pending_exit) -> None:
        """Evaluación de la semana (libro, cestas, retornos); fuera de la contención de fallos del archivo (R28-05)."""
        cfg = self.cfg
        if pending_entry:
            record["note"] = f"pending_outcome: entrada prevista {entry_s.isoformat()} posterior al límite {bound.isoformat()}"
            return
        open_prices = {sec: m[entry_s].open for sec, m in self.market.by_session.items() if entry_s in m}
        close_prices = {} if pending_exit else {sec: m[exit_s].close for sec, m in self.market.by_session.items() if exit_s in m}
        intervals: dict[str, IntervalReturn] = {}
        for name, lg in self.ledgers.items():
            self.apply_actions(name, entry_s)
            lg.advance_to(plan.entry_at)
            open_marks, stale0 = self.marks(entry_s, lg, "open")
            try:
                equity_start = lg.valuation(prices=open_marks, at=plan.entry_at).total
            except MissingPrice as exc:
                equity_start = None
                stale0.append(f"missing_open_price:{exc}")
            notional = (lg.cash / cfg.slots).to_integral_value(rounding="ROUND_DOWN") if cfg.sizing == "proportional" else D(cfg.notional)
            slots = enter_basket(lg, picks=picks[name], slots=cfg.slots, notional_per_slot=notional, open_prices=open_prices,
                                 at=plan.entry_at, week_id=plan.week_id)
            self.open_slots[name].append((plan.week_id, slots))
            open_marks_after, _ = self.marks(entry_s, lg, "open")
            try:
                positions_value_open = lg.valuation(prices=open_marks_after, at=plan.entry_at).positions_value
            except MissingPrice:
                positions_value_open = None
            exposure = (positions_value_open / equity_start) if (equity_start and positions_value_open is not None) else D(0)
            if pending_exit:
                fr = record["forecasters"][name]
                slot_by_sec = {s.security_id: s for s in slots if s.security_id}
                for p in fr["picks"]:                                     # la ejecución del lunes ya se conoce (R17-10)
                    slot = slot_by_sec.get(p["security_id"])
                    if slot is not None:
                        p["entry_status"] = slot.status                  # filled | entry_failed
                        p["entry_reason"] = slot.reason or None
                invested0 = sum((s.entry.gross for s in slots if s.entry is not None), D(0))
                costs0 = _week_costs(slots)                                  # costes ya conocidos de las compras (R19-03)
                fr.update({"notional_per_slot": float(notional), "filled": sum(1 for s in slots if s.status == "filled"),
                           "failed": sum(1 for s in slots if s.status == "entry_failed"),
                           "fail_reasons": [s.reason for s in slots if s.status == "entry_failed"],
                           "equity_open": float(equity_start) if equity_start is not None else None, "exposure_at_open": float(exposure),
                           "costs_twd": float(costs0), "costs_denominator_twd": float(invested0),
                           "costs_over_invested": float(costs0 / invested0) if invested0 else None, "costs_scope": "entries_only_pending_exit",
                           "stale_prices": stale0, "note": "entrada ejecutada; salida pendiente"})
                continue
            self.apply_actions(name, exit_s)
            prior = [(wid, ss) for wid, ss in self.open_slots[name] if wid != plan.week_id]
            for wid, ss in self.open_slots[name]:
                exit_basket(lg, ss, close_prices=close_prices, at=plan.exit_at, week_id=wid)
            inherited_fills = [s.exit for _, ss in prior for s in ss if s.exit is not None and s.exit.at == plan.exit_at]
            self.open_slots[name] = [(wid, ss) for wid, ss in self.open_slots[name]
                                     if any(s.status in ("filled", "exit_blocked") or (s.status == "exited" and not s.liquidated) for s in ss)]
            lg.advance_to(plan.exit_at)                        # reloj del libro en el cierre también sin cestas (R28-02)
            close_marks, stale1 = self.marks(exit_s, lg, "close")
            try:
                val = lg.valuation(prices=close_marks, at=plan.exit_at)
                equity_end, flags = val.total, list(val.flags) + stale0 + stale1
            except MissingPrice as exc:
                equity_end, flags = None, [f"missing_price:{exc}"] + stale0 + stale1
            measurable = (equity_start is not None and equity_end is not None and equity_start > 0
                          and positions_value_open is not None and not stale0 and not stale1)
            rep = basket_report(plan.week_id, slots, equity_start=equity_start if measurable else self.prev_equity[name],
                                equity_end=equity_end if measurable else self.prev_equity[name])
            interval_return = (equity_end / equity_start - 1) if measurable else None
            chain_return = (equity_end / self.prev_equity[name] - 1) if equity_end is not None and self.prev_equity[name] else None
            invested = sum((s.entry.gross for s in slots if s.entry is not None), D(0))
            # costes de la semana: cesta nueva + ventas heredadas ejecutadas esta semana (R18-05); el denominador es el
            # importe bruto comprado más el vendido de cestas anteriores, para que una semana sin compras no quede sin tasa
            inherited_costs = sum((f.commission + f.tax + f.slippage_cost for f in inherited_fills), D(0))
            inherited_sales_gross = sum((f.gross for f in inherited_fills), D(0))
            costs_twd = _week_costs(slots) + inherited_costs
            costs_denominator = invested + inherited_sales_gross
            # una selección sólo pierde su rentabilidad bruta si sufrió un derecho ambiguo mientras la tenía (R14-05, R15-06):
            # un lote nuevo del mismo valor, comprado después de la fecha ex, conserva su retorno bruto
            def _hit(slot) -> bool:
                if slot.entry is None or slot.security_id is None:
                    return False
                return any(sec == slot.security_id and slot.entry.at.date() < exd <= exit_s for sec, exd in self.ambiguous_hits[name])
            pick_returns = {s.security_id: (float(s.gross_pick_return) if s.gross_pick_return is not None and not _hit(s) else None)
                            for s in slots if s.security_id}
            basket_ambiguous = any(_hit(s) for s in slots)
            fr = record["forecasters"][name]
            slot_by_sec = {s.security_id: s for s in slots if s.security_id}
            for p in fr["picks"]:
                p["gross_return"] = pick_returns.get(p["security_id"])
                slot = slot_by_sec.get(p["security_id"])
                if slot is not None:
                    p["entry_status"] = slot.status                      # filled | exited | entry_failed | exit_blocked
                    p["entry_reason"] = slot.reason or None
            fr.update({"notional_per_slot": float(notional), "filled": rep.filled_slots, "failed": rep.failed_slots,
                       "exit_blocked": rep.exit_blocked_slots, "fail_reasons": [s.reason for s in slots if s.status == "entry_failed"],
                       "mean_gross_pick_return": (float(rep.mean_gross_pick_return) if rep.mean_gross_pick_return is not None and not basket_ambiguous else None),
                       "portfolio_net_return_open_close": float(interval_return) if interval_return is not None else None,
                       "portfolio_net_return_week_over_week": float(chain_return) if chain_return is not None else None,
                       "exposure_at_open": float(exposure), "costs_twd": float(costs_twd),
                       "inherited_exit_costs_twd": float(inherited_costs), "costs_denominator_twd": float(costs_denominator),
                       "costs_over_invested": float(costs_twd / costs_denominator) if costs_denominator else None,
                       "equity_open": float(equity_start) if equity_start is not None else None,
                       "equity_end": float(equity_end) if equity_end is not None else None, "flags": list(dict.fromkeys(flags))[:8],
                       "stale_prices": list(dict.fromkeys(stale0 + stale1)), "baskets_in_follow_up": len(self.open_slots[name])})
            if measurable and rep.filled_slots > 0:
                intervals[name] = IntervalReturn(label=name, start_at=plan.entry_at, end_at=plan.exit_at, start_price_kind="open",
                                                 end_price_kind="close", value=interval_return.quantize(D("0.0000001")),
                                                 exposure=exposure.quantize(D("0.0001")), week_id=plan.week_id)
            if equity_end is not None:
                self.prev_equity[name] = equity_end
        if pending_exit:
            record["note"] = f"pending_outcome: salida prevista {exit_s.isoformat()} posterior al límite {bound.isoformat()}; entradas ejecutadas"
            return
        eligible_ids = [c.security_id for c in candidates if c.eligible]
        ew = [float(self.market.by_session[s][exit_s].close / self.market.by_session[s][entry_s].open - 1) for s in eligible_ids
              if entry_s in self.market.by_session[s] and exit_s in self.market.by_session[s]]
        record["universe_ew_gross_open_close"] = statistics.fmean(ew) if ew else None
        closure = entry_s not in self.market.traded_days or exit_s not in self.market.traded_days
        if closure:
            closed = entry_s if entry_s not in self.market.traded_days else exit_s
            record["note"] = f"extraordinary_closure_unhandled:{closed.isoformat()}"
        base = cfg.baseline
        record["paired"] = {}
        for name in self.forecasters:
            if name == base:
                continue
            entry = {"paired": False, "excess_net_vs_baseline": None, "unpaired_reason": None}
            if closure:
                entry["unpaired_reason"] = "extraordinary_closure_unhandled"
            elif record["forecasters"][name]["stale_prices"] or record["forecasters"][base]["stale_prices"]:
                first = (record["forecasters"][name]["stale_prices"] or record["forecasters"][base]["stale_prices"])[0]
                entry["unpaired_reason"] = f"non_market_valuation_in_interval:{first}"
            elif name in intervals and base in intervals:
                try:
                    entry["excess_net_vs_baseline"] = float(paired_excess(intervals[name], intervals[base], exposure_tolerance=cfg.exposure_tolerance))
                    entry["paired"] = True
                except IntervalMismatch as exc:
                    entry["unpaired_reason"] = f"interval_mismatch:{exc}"
            else:
                entry["unpaired_reason"] = "missing_interval:" + ",".join(n for n in (name, base) if n not in intervals)
            record["paired"][name] = entry

    # -- todo el periodo -------------------------------------------------------------------------------
    def master_record(self) -> CaptureRecord:
        """Instantánea del maestro con la que se resuelven símbolos y nombres, archivada antes que cualquier predicción
        que la cite. Se serializa de nuevo en **cada** llamada, de modo que un maestro que cambia durante la corrida
        (cierres, revisiones) produce una instantánea nueva citada por las semanas siguientes (R26-02). Bytes idénticos
        ya archivados e íntegros se reutilizan (la primera copia íntegra por instante), como los paquetes y las
        predicciones (R23-01); la integridad se comprueba en cada llamada y una copia corrompida o ausente se sustituye
        por otra íntegra o se vuelve a archivar antes de emitir (R25-02, R26-03)."""
        payload = master_snapshot_bytes(self.market.master)
        sha = hashlib.sha256(payload).hexdigest()
        dataset = f"{self.cfg.archive_label or self.cfg.label}/master"
        rec = self._master_rec if (self._master_rec is not None and self._master_rec.sha256 == sha) else None
        if rec is not None:
            try:
                self.store.read(rec)
            except (IntegrityError, OSError):
                rec = None
        if rec is None:
            for cand in sorted((r for r in self.store.captures(source_id="master", dataset=dataset) if r.sha256 == sha),
                               key=lambda r: r.ingested_at_dt):
                try:
                    self.store.read(cand)
                except (IntegrityError, OSError):
                    continue
                rec = cand
                break
        if rec is None:
            rec = self.store.put(source_id="master", dataset=dataset, payload=payload, url="local://backtest",
                                 content_type="application/x-ndjson", extra={"rows": len(self.market.master._versions)})  # noqa: SLF001
        self._master_rec = rec
        return rec

    def run(self) -> dict:
        cfg = self.cfg
        for sunday in _sundays(cfg.start, cfg.end):
            self.run_week(sunday)
        bound = min(cfg.end, self.last_data_day)
        end_at = taipei(bound, time(23, 59))
        last_close = self.market.calendar.prev_session(before=bound + timedelta(days=1))
        final: dict[str, dict] = {}
        for name, lg in self.ledgers.items():
            self.apply_actions(name, bound)
            lg.advance_to(end_at)
            prices, stale = self.marks(last_close, lg, "close", valued_at=bound)
            try:
                v = lg.valuation(prices=prices, at=end_at)
                final[name] = {"equity": float(v.total), "cash": float(v.cash), "receivables": float(v.receivables),
                               "positions_value": float(v.positions_value), "unresolved": list(v.unresolved), "flags": list(v.flags) + stale,
                               "valued_at": end_at.isoformat(), "prices_session": last_close.isoformat(),
                               "events_processed_through": self.cursor[name].isoformat()}
            except MissingPrice as exc:
                final[name] = {"equity": None, "error": str(exc), "flags": stale, "valued_at": end_at.isoformat()}
        operated = [w for w in self.weeks if w["status"] == "valid" and not w.get("pending_outcome")]
        summary: dict = {
            "label": cfg.label, "period": [cfg.start.isoformat(), cfg.end.isoformat()], "manifest": self.market.source_manifest,
            "universe_size": len(self.market.securities), "weeks_total": len(self.weeks), "weeks_operated": len(operated),
            "weeks_invalid_no_sessions": sum(1 for w in self.weeks if w["status"] == "invalid:no_sessions"),
            "weeks_invalid_archive": [w["week_id"] for w in self.weeks if w["status"] == "invalid:archive"],
            "weeks_pending_outcome": [w["week_id"] for w in self.weeks if w.get("pending_outcome")],
            "weeks_extraordinary_closure_unhandled": [w["week_id"] for w in self.weeks if str(w.get("note", "")).startswith("extraordinary")],
            "bars_without_regular_price_dropped": self.market.dropped_no_regular_price,
            "bars_before_listing_dropped": self.market.bars_before_listing_dropped, "market_warnings": list(self.market.warnings),
            "simulation_bound": min(cfg.end, self.last_data_day).isoformat(),
            "universe_ew": {"mean_weekly_gross_open_close": self._mean(operated, lambda w: w["universe_ew_gross_open_close"])},
            "assumptions": {**{k: (str(v) if isinstance(v, D) else (v.isoformat() if isinstance(v, date) else v)) for k, v in asdict(cfg).items()},
                            "costs": asdict(self.costs), "price_availability_lag_hours": 24,
                            "liquidity_rule": f"mediana(importe 20 sesiones) >= {cfg.liquidity_multiple} x nocional",
                            "planning_calendar": f"{self.market.calendar.source_id}@{self.market.calendar.version}"},
            "forecasters": {},
        }
        for name, f in self.forecasters.items():
            fw = [w["forecasters"][name] for w in operated]
            entry = {
                "model_id": f.model_id, "mean_weekly_net_return_open_close": self._mean(fw, lambda r: r.get("portfolio_net_return_open_close")),
                "mean_weekly_net_return_week_over_week": self._mean(fw, lambda r: r.get("portfolio_net_return_week_over_week")),
                "mean_weekly_gross_pick_return": self._mean(fw, lambda r: r.get("mean_gross_pick_return")),
                "mean_costs_over_invested": self._mean(fw, lambda r: r.get("costs_over_invested")),
                "weeks_positive": sum(1 for r in fw if (r.get("portfolio_net_return_open_close") or 0) > 0),
                "weeks_measured": sum(1 for r in fw if r.get("portfolio_net_return_open_close") is not None),   # denominador (R18-07)
                "weeks_selected": sum(1 for r in fw if r.get("forecast_status") == "selected"),
                "entry_failures": sum(r.get("failed", 0) for r in fw), "exit_blocked": sum(r.get("exit_blocked", 0) for r in fw),
                "final_equity": final[name]["equity"],
                "total_net_return": (final[name]["equity"] / float(self.initial) - 1) if final[name]["equity"] is not None else None,
                "final_valuation": final[name],
                "open_positions_at_end": [{"security_id": sec, "status": pos.status, "quantity": str(pos.total_quantity),
                                           "unresolved_fraction": str(pos.unresolved_fraction)} for sec, pos in sorted(self.ledgers[name].positions.items())],
                "baskets_in_follow_up_at_end": [wid for wid, _ in self.open_slots[name]],
                "ambiguous_claims": sorted(self.ambiguous_claims[name]),       # derechos no aplicados: el patrimonio es incierto desde entonces
            }
            if hasattr(f, "history"):
                entry["training_history"] = list(getattr(f, "history"))
            if name != cfg.baseline:
                obs = [WeeklyObservation(w["week_id"], f"{name}-{w['week_id']}", EVIDENCE, None, bool(w["paired"][name]["paired"]),
                                         w["paired"][name]["excess_net_vs_baseline"]) for w in self.weeks if w["status"] == "valid" and not w.get("pending_outcome")]
                try:
                    boot = block_bootstrap_mean(obs, block_length=cfg.block_length, n_boot=cfg.n_boot, seed=cfg.seed)
                    entry["paired_excess_vs_baseline"] = {"baseline": cfg.baseline, "mean": boot.mean,
                                                          "ci95": None if boot.degenerate else [boot.ci_low, boot.ci_high],   # sin NaN en JSON (R12-03)
                                                          "n_used": boot.n_used, "n_excluded": boot.n_invalid_excluded,
                                                          "block_length": boot.block_length, "n_segments": boot.n_segments,
                                                          "resample_mean": boot.resample_mean,
                                                          "n_fixed_observations": boot.n_fixed_observations,
                                                          "variability_limited": boot.variability_limited, "degenerate": boot.degenerate}
                except Exception as exc:
                    entry["paired_excess_vs_baseline"] = {"baseline": cfg.baseline, "error": str(exc)}
                entry["unpaired_reasons"] = dict(collections.Counter((w["paired"][name]["unpaired_reason"] or "").split(":")[0]
                                                                     for w in operated if not w["paired"][name]["paired"]))
            summary["forecasters"][name] = entry
        return {"summary": summary, "weeks": self.weeks}

    @staticmethod
    def _mean(rows, getter) -> Optional[float]:
        xs = [getter(r) for r in rows]
        xs = [x for x in xs if x is not None]
        return statistics.fmean(xs) if xs else None


def markdown_report(result: dict, *, title: str) -> str:
    s = result["summary"]
    lines = [f"# {title}", "",
             f"Periodo {s['period'][0]} → {s['period'][1]} · universo {s['universe_size']} valores ({s['manifest']}) · "
             f"{s['weeks_operated']} semanas operadas, {s['weeks_invalid_no_sessions']} sin sesiones, "
             f"{len(s['weeks_pending_outcome'])} pendientes de desenlace.", "",
             "Costes ilustrativos (no contratados); universo del censo vigente; disponibilidad de barras por política de 24 h. "
             "Nada de esto es una estimación de rendimiento futuro.", "",
             "| Pronosticador | Media semanal neta apertura→cierre | Media bruta de las selecciones | Costes/semana sobre compras brutas + ventas brutas heredadas | Semanas > 0 (de las medibles) | Patrimonio final | Exceso neto vs " + s["assumptions"]["baseline"] + " (IC 95 %) |",
             "|---|---|---|---|---|---|---|"]
    fmt = lambda x: "—" if x is None else f"{x*100:+.2f} %"
    for name, e in s["forecasters"].items():
        pe = e.get("paired_excess_vs_baseline")
        if pe and pe.get("degenerate"):
            pe_txt = f"{pe['mean']*100:+.2f} % (incertidumbre no estimable: remuestreo degenerado, n={pe['n_used']})"
        elif pe and "ci95" in pe:
            pe_txt = f"{pe['mean']*100:+.2f} % [{pe['ci95'][0]*100:+.2f} %, {pe['ci95'][1]*100:+.2f} %] n={pe['n_used']}"
            if pe.get("n_fixed_observations"):
                pe_txt += f" (variabilidad limitada: {pe['n_fixed_observations']} semanas fijas)"
        elif pe and "error" in pe:
            pe_txt = f"no estimable: {pe['error']}"
        else:
            pe_txt = "—"
        fflags = [str(f) for f in e.get("final_valuation", {}).get("flags", [])]
        if e.get("final_equity") is None:
            equity_txt = "desconocido: " + str(e.get("final_valuation", {}).get("error", ""))
        elif e.get("ambiguous_claims") or fflags:
            # cualquier marca de la valoración final (derecho ambiguo, terminal no resuelto, precio anterior a derecho,
            # precio obsoleto, fracción pendiente…) la convierte en provisional (R15-07, R16-07)
            kinds = sorted({f.split(":")[0] if not f.startswith("TWSE") and not f.startswith("TPEX") else f.rsplit(":", 1)[-1] for f in fflags})
            equity_txt = f"≈ {e['final_equity']:,.0f} TWD (contable, PROVISIONAL: {', '.join(kinds) or 'derechos ambiguos'})"
        else:
            equity_txt = f"{e['final_equity']:,.0f} TWD"
        lines.append(f"| {name} (`{e['model_id']}`) | {fmt(e['mean_weekly_net_return_open_close'])} | {fmt(e['mean_weekly_gross_pick_return'])} | "
                     f"{fmt(e['mean_costs_over_invested'])} | {e['weeks_positive']}/{e.get('weeks_measured', s['weeks_operated'])} | {equity_txt} | {pe_txt} |")
    ew = s["universe_ew"]["mean_weekly_gross_open_close"]
    lines += ["", f"Referencia equiponderada del universo elegible (bruta, apertura→cierre): {ew*100:+.2f} % semanal." if ew is not None else "", ""]
    warns = s.get("market_warnings", [])
    ambiguous = [w for w in warns if "AMBIGUOUS" in w]
    lines += ["## Límites", "",
              "- Universo del censo vigente (sesgo de supervivencia); costes ilustrativos; disponibilidad de barras por política de 24 h, no verificada.",
              "- Derechos (dividendos) según FinMind: la fecha y hora de anuncio acreditan el anuncio, no las revisiones posteriores de importes o "
              "fechas; no hay versiones históricas archivadas. Las etiquetas y la contabilidad que dependen de derechos son inferencia conservadora.",
              f"- Derechos ambiguos o inválidos detectados en la carga: {len(ambiguous)} (etiquetas e intervalos de sus tenedores invalidados); "
              f"avisos de carga en total: {len(warns)}." + (" Ejemplos: " + "; ".join(w[:120] for w in warns[:3]) if warns else ""),
              "- Un bootstrap con observaciones fijas o degenerado se declara como tal en la tabla; nunca como un IC ordinario.", ""]
    lines += ["## Selecciones semana a semana", ""]
    names = list(s["forecasters"])
    lines.append("| Semana | " + " | ".join(names) + " |")
    lines.append("|---|" + "---|" * len(names))
    for w in result["weeks"]:
        if w["status"] != "valid":
            why = w.get("note", w["status"]) + (f" — {w['archive_error']}" if w.get("archive_error") else "")   # causa concreta (R28-08)
            lines.append(f"| {w['week_id']} | " + " | ".join([why] + [""] * (len(names) - 1)) + " |")
            continue
        cells = []
        for n in names:
            fr = w["forecasters"].get(n, {})
            picks = fr.get("picks", [])
            if not picks:
                net0 = fr.get("portfolio_net_return_open_close")
                tail0 = f" → neto del libro {net0*100:+.2f} % (posiciones heredadas)" if net0 is not None else ""
                cells.append(f"({fr.get('forecast_status', '—')}: {fr.get('status_reason') or ''}){tail0}".strip())
                continue
            def _pick(p):
                s = f"{p['symbol']} {p['name']}"
                if p.get("gross_return") is not None:
                    return s + f" {p['gross_return']*100:+.1f} %"
                if p.get("entry_status") == "entry_failed":
                    return s + f" (sin ejecutar: {p.get('entry_reason')})"
                if p.get("entry_status") in ("exit_blocked",):
                    return s + " (salida bloqueada)"
                return s
            txt = ", ".join(_pick(p) for p in picks)
            net = fr.get("portfolio_net_return_open_close")
            if net is not None:
                tail = f" → neto {net*100:+.2f} %"
            elif w.get("pending_outcome"):
                tail = " → pendiente"
            elif fr.get("stale_prices"):
                tail = f" → sin intervalo medible ({fr['stale_prices'][0].split(':')[0]})"
            else:
                tail = " → sin intervalo medible"
            cells.append(txt + tail)
        lines.append(f"| {w['week_id']} | " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n"
