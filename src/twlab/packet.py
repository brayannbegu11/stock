"""Paquete de información por fecha de corte y aislamiento del predictor.

El constructor de paquetes es el único filtro entre el archivo y el
predictor. Reglas (PRUEBAS_ACEPTACION.md, bloque PIT) y correcciones de las
rondas 1-3 de Astra:

- ``available_at`` debe ser <= corte (PIT-01, PIT-02, PIT-08, PIT-09).
- ``availability_quality == unknown`` nunca entra al paquete principal.
- ``published_at`` no puede ser posterior a ``available_at`` (R01-02).
- Comparaciones sobre instantes UTC (R01-03).
- ``Document`` es inmutable y su hash cubre todo el contenido; ``doc_id``
  repetidos son un error (R01-04, R02-02).
- **Procedencia en modo prospectivo** (R01-02, R02-01, R03-01): cada
  documento debe enlazar una captura real (reloj del sistema) de la misma
  fuente, anterior al corte, con el sha256 que declara; además debe declarar
  el extractor (``derivation``) registrado que, aplicado a los bytes
  archivados, reproduce exactamente su ``payload``. Sin extractor registrado
  no hay documento prospectivo.
- El plazo de emisión se **deriva** del calendario y del protocolo
  (``weekly.plan_week``); no es un argumento libre (R02-06, R03-02). Una
  semana sin sesiones produce un paquete con ``week_status = invalid:no_sessions``.
- Toda referencia documental de una predicción debe apuntar a un documento
  admitido (TXT-05). El predictor recibe un objeto sin resultados (PIT-11, R01-05).
"""
from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass, field, replace
from datetime import date, datetime
from enum import Enum
from types import MappingProxyType
from typing import Any, Callable, Iterable, Mapping, Optional, Sequence

from .calendar import TradingCalendar
from .store import CaptureRecord, RawStore
from .timeutil import UTC, AvailabilityQuality, ensure_aware, is_after, to_utc
from .weekly import STATUS_VALID, plan_week

MODE_HISTORICAL = "historical"
MODE_PROSPECTIVE = "prospective"
EVIDENCE_PROSPECTIVE = "prospective_registered"

R_AVAILABLE_AFTER_CUTOFF = "available_after_cutoff"
R_UNKNOWN_AVAILABILITY = "unknown_availability"
R_NOT_RECEIVED_BEFORE_CUTOFF = "not_received_before_cutoff"
R_INCONSISTENT_METADATA = "inconsistent_metadata"
R_NO_CAPTURE_EVIDENCE = "no_capture_evidence"
R_SYNTHETIC_CAPTURE = "synthetic_capture_not_prospective"
R_PROVENANCE_MISMATCH = "provenance_mismatch"
R_DERIVATION_MISMATCH = "derivation_mismatch"

Extractor = Callable[[bytes], Mapping[str, Any]]   # devuelve {"payload": Mapping, "security_ids": Sequence[str]}


def _freeze(obj: Any) -> Any:
    if isinstance(obj, Mapping):
        return MappingProxyType({k: _freeze(v) for k, v in obj.items()})
    if isinstance(obj, (list, tuple)):
        return tuple(_freeze(v) for v in obj)
    if isinstance(obj, (set, frozenset)):
        return tuple(sorted(_freeze(v) for v in obj))
    return obj


def _thaw(obj: Any) -> Any:
    if isinstance(obj, Mapping):
        return {k: _thaw(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_thaw(v) for v in obj]
    return obj


def _jsonable(obj: Any) -> Any:
    if isinstance(obj, MappingProxyType):
        return dict(obj)
    if isinstance(obj, datetime):
        return to_utc(obj).isoformat()
    if isinstance(obj, date):
        return obj.isoformat()
    if isinstance(obj, Enum):
        return obj.value
    if isinstance(obj, (set, frozenset)):
        return sorted(obj)
    raise TypeError(f"not serialisable: {type(obj).__name__}")


def canonical_bytes(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=_jsonable).encode("utf-8")


@dataclass(frozen=True)
class Document:
    doc_id: str
    kind: str                      # news | filing | calendar_event | price_bar | flow | ...
    source_id: str
    security_ids: tuple[str, ...]
    available_at: datetime         # derivado por política ANTES de llegar aquí
    availability_quality: AvailabilityQuality
    published_at: Optional[datetime] = None
    first_seen_at: Optional[datetime] = None
    version: int = 1
    supersedes: Optional[str] = None
    period_end: Optional[date] = None
    scheduled_for: Optional[datetime] = None
    capture_id: Optional[str] = None       # CaptureRecord del RawStore del que procede
    source_sha256: Optional[str] = None    # sha256 de los bytes capturados de los que se derivó
    derivation: Optional[str] = None       # identificador del extractor registrado que produjo payload
    payload: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        ensure_aware(self.available_at, f"{self.doc_id}.available_at")
        for name in ("published_at", "first_seen_at", "scheduled_for"):
            v = getattr(self, name)
            if v is not None:
                ensure_aware(v, f"{self.doc_id}.{name}")
        object.__setattr__(self, "security_ids", tuple(self.security_ids))
        object.__setattr__(self, "payload", _freeze(copy.deepcopy(_thaw(self.payload))))

    def canonical(self) -> dict[str, Any]:
        return {
            "doc_id": self.doc_id, "kind": self.kind, "source_id": self.source_id,
            "security_ids": list(self.security_ids), "available_at": self.available_at,
            "availability_quality": self.availability_quality, "published_at": self.published_at,
            "first_seen_at": self.first_seen_at, "version": self.version, "supersedes": self.supersedes,
            "period_end": self.period_end, "scheduled_for": self.scheduled_for, "capture_id": self.capture_id,
            "source_sha256": self.source_sha256, "derivation": self.derivation, "payload": self.payload,
        }

    def content_hash(self) -> str:
        return hashlib.sha256(canonical_bytes(self.canonical())).hexdigest()


@dataclass(frozen=True)
class Rejection:
    doc_id: str
    reason: str
    detail: str


@dataclass(frozen=True)
class Packet:
    packet_id: str
    cutoff_at: datetime
    mode: str
    evidence_class: str
    admitted: tuple[Document, ...]
    rejected: tuple[Rejection, ...]
    created_at: datetime
    week_id: Optional[str] = None
    week_status: Optional[str] = None        # valid | invalid:no_sessions
    deadline_at: Optional[datetime] = None   # plazo de emisión derivado del protocolo y del calendario
    registration_deadline_at: Optional[datetime] = None   # último instante para archivar/acreditar el registro
    entry_at: Optional[datetime] = None
    exit_at: Optional[datetime] = None
    calendar_version: Optional[str] = None

    def admitted_ids(self) -> set[str]:
        return {d.doc_id for d in self.admitted}

    @property
    def manifest(self) -> list[tuple[str, str]]:
        return [(d.doc_id, d.content_hash()) for d in self.admitted]

    def packet_hash(self) -> str:
        """Cubre todo lo que el predictor puede ver: admitidos, rechazados con sus motivos y el plan (R05-04).
        ``created_at`` queda fuera a propósito: es un metadato de construcción, no contenido."""
        body = canonical_bytes({
            "packet_id": self.packet_id, "cutoff_at": self.cutoff_at, "mode": self.mode,
            "evidence_class": self.evidence_class, "week_id": self.week_id, "week_status": self.week_status,
            "deadline_at": self.deadline_at, "registration_deadline_at": self.registration_deadline_at,
            "entry_at": self.entry_at, "exit_at": self.exit_at,
            "calendar_version": self.calendar_version, "manifest": self.manifest,
            "rejected": [[r.doc_id, r.reason, r.detail] for r in self.rejected],
        })
        return hashlib.sha256(body).hexdigest()


def build_packet(
    *,
    packet_id: str,
    cutoff_at: datetime,
    documents: Iterable[Document],
    mode: str,
    evidence_class: str,
    calendar: Optional[TradingCalendar] = None,
    captures: Optional[Mapping[str, CaptureRecord]] = None,
    read_bytes: Optional[Callable[[CaptureRecord], bytes]] = None,
    extractors: Optional[Mapping[str, Extractor]] = None,
    allow_injected_clock: bool = False,
    now: Optional[datetime] = None,
) -> Packet:
    if mode not in (MODE_HISTORICAL, MODE_PROSPECTIVE):
        raise ValueError(f"unknown mode {mode!r}")
    ensure_aware(cutoff_at, "cutoff_at")
    if mode == MODE_PROSPECTIVE and (captures is None or read_bytes is None or extractors is None):
        raise ValueError("prospective packets require the capture registry, a byte reader and the extractor registry")
    if allow_injected_clock and evidence_class == EVIDENCE_PROSPECTIVE:
        raise ValueError("synthetic (injected clock) captures can never be prospective_registered")
    if evidence_class == EVIDENCE_PROSPECTIVE and mode != MODE_PROSPECTIVE:
        raise ValueError("prospective_registered evidence requires prospective mode")
    docs = list(documents)
    ids = [d.doc_id for d in docs]
    if len(set(ids)) != len(ids):
        dupes = sorted({i for i in ids if ids.count(i) > 1})
        raise ValueError(f"duplicate doc_id in packet input: {dupes}")
    admitted: list[Document] = []
    rejected: list[Rejection] = []
    for d in docs:
        if d.availability_quality == AvailabilityQuality.UNKNOWN:
            rejected.append(Rejection(d.doc_id, R_UNKNOWN_AVAILABILITY, "availability could not be established"))
            continue
        if d.published_at is not None and is_after(d.published_at, d.available_at):
            rejected.append(Rejection(d.doc_id, R_INCONSISTENT_METADATA,
                                      f"published_at={to_utc(d.published_at).isoformat()} later than available_at={to_utc(d.available_at).isoformat()}"))
            continue
        if is_after(d.available_at, cutoff_at):
            rejected.append(Rejection(d.doc_id, R_AVAILABLE_AFTER_CUTOFF,
                                      f"available_at={to_utc(d.available_at).isoformat()} > cutoff={to_utc(cutoff_at).isoformat()}"))
            continue
        if mode == MODE_PROSPECTIVE:
            if d.capture_id is None or d.capture_id not in captures:  # type: ignore[operator]
                rejected.append(Rejection(d.doc_id, R_NO_CAPTURE_EVIDENCE, "document is not linked to a RawStore capture"))
                continue
            rec = captures[d.capture_id]  # type: ignore[index]
            if rec.clock_source != "system" and not allow_injected_clock:
                rejected.append(Rejection(d.doc_id, R_SYNTHETIC_CAPTURE, f"capture clock_source={rec.clock_source}"))
                continue
            if rec.source_id != d.source_id or d.source_sha256 is None or d.source_sha256 != rec.sha256:
                rejected.append(Rejection(d.doc_id, R_PROVENANCE_MISMATCH,
                                          f"document source={d.source_id} sha={str(d.source_sha256)[:12]} vs capture source={rec.source_id} sha={rec.sha256[:12]}"))
                continue
            extractor = extractors.get(d.derivation) if d.derivation else None  # type: ignore[union-attr]
            if extractor is None:
                rejected.append(Rejection(d.doc_id, R_DERIVATION_MISMATCH, f"derivation={d.derivation!r} is not a registered extractor"))
                continue
            try:
                raw = read_bytes(rec)  # type: ignore[misc]
                if hashlib.sha256(raw).hexdigest() != rec.sha256:
                    raise ValueError("archived bytes do not match capture sha256")
                extraction = extractor(raw)
                if not isinstance(extraction, Mapping) or "payload" not in extraction or "security_ids" not in extraction:
                    raise ValueError("extractor must return a mapping with 'payload' and 'security_ids'")
                derived_payload = canonical_bytes(_thaw(extraction["payload"]))
                derived_ids = tuple(str(s) for s in extraction["security_ids"])
            except Exception as exc:                      # sólo la clase: el mensaje podría transportar contenido (R09-03)
                rejected.append(Rejection(d.doc_id, R_DERIVATION_MISMATCH, f"extractor {d.derivation} failed: {type(exc).__name__}"))
                continue
            # identidad JSON exacta (true ≠ 1) y entidades derivadas, no declaradas (R04-07, R04-14)
            if derived_payload != canonical_bytes(_thaw(d.payload)):
                rejected.append(Rejection(d.doc_id, R_DERIVATION_MISMATCH,
                                          f"payload does not equal extractor({d.derivation}) applied to the archived bytes"))
                continue
            if derived_ids != d.security_ids:
                rejected.append(Rejection(d.doc_id, R_DERIVATION_MISMATCH,
                                          f"security_ids {d.security_ids} do not equal extracted {derived_ids}"))
                continue
            ingested = rec.ingested_at_dt
            if is_after(ingested, cutoff_at):
                rejected.append(Rejection(d.doc_id, R_NOT_RECEIVED_BEFORE_CUTOFF,
                                          f"ingested_at={ingested.isoformat()} > cutoff={to_utc(cutoff_at).isoformat()}"))
                continue
            if d.first_seen_at is not None and to_utc(d.first_seen_at) != to_utc(ingested):
                rejected.append(Rejection(d.doc_id, R_INCONSISTENT_METADATA,
                                          f"first_seen_at={to_utc(d.first_seen_at).isoformat()} != capture ingested_at={ingested.isoformat()}"))
                continue
            d = replace(d, first_seen_at=ingested)
        admitted.append(d)
    admitted.sort(key=lambda x: (to_utc(x.available_at), x.doc_id))
    week = plan_week(cutoff_at, calendar) if calendar is not None else None
    return Packet(
        packet_id=packet_id,
        cutoff_at=cutoff_at,
        mode=mode,
        evidence_class=evidence_class,
        admitted=tuple(admitted),
        rejected=tuple(rejected),
        created_at=ensure_aware(now) if now else datetime.now(UTC),
        week_id=week.week_id if week else None,
        week_status=week.status if week else None,
        deadline_at=week.deadline_at if week else None,
        registration_deadline_at=week.registration_deadline_at if week else None,
        entry_at=week.entry_at if week else None,
        exit_at=week.exit_at if week else None,
        calendar_version=f"{calendar.source_id}@{calendar.version}" if calendar is not None else None,
    )


KNOWN_REJECTION_REASONS = frozenset({
    R_AVAILABLE_AFTER_CUTOFF, R_UNKNOWN_AVAILABILITY, R_NOT_RECEIVED_BEFORE_CUTOFF, R_INCONSISTENT_METADATA,
    R_NO_CAPTURE_EVIDENCE, R_SYNTHETIC_CAPTURE, R_PROVENANCE_MISMATCH, R_DERIVATION_MISMATCH,
})


def readmission_problems(
    packet: Packet,
    *,
    store: Optional[RawStore] = None,
    extractors: Optional[Mapping[str, Extractor]] = None,
    read_bytes: Optional[Callable[[CaptureRecord], bytes]] = None,
) -> list[str]:
    """Vuelve a aplicar el filtro de admisión a un paquete recuperado de un registro (R08-01, R09-01..03).

    El hash acredita bytes, no admisibilidad: un paquete construido a mano puede contener documentos
    que ``build_packet`` habría rechazado. Por documento admitido se comprueban disponibilidad
    conocida, coherencia de fechas y disponibilidad no posterior al corte. En modo prospectivo el
    archivo es **obligatorio** (sin él la readmisión falla cerrada): captura existente, procedencia,
    reloj del sistema, ingestión no posterior al corte, integridad de los bytes archivados y
    re-derivación del *payload* con el extractor registrado (sin registro, el documento no se readmite).
    Los rechazos recuperados deben ser únicos, con motivo del catálogo y sin colisión con los admitidos.
    """
    problems: list[str] = []
    if packet.mode == MODE_PROSPECTIVE and store is None:
        problems.append("archive_required_for_prospective_readmission (R09-02)")
    seen: set[str] = set()
    for d in packet.admitted:
        if d.doc_id in seen:
            problems.append(f"{d.doc_id}: duplicate doc_id")
        seen.add(d.doc_id)
        if d.availability_quality == AvailabilityQuality.UNKNOWN:
            problems.append(f"{d.doc_id}: {R_UNKNOWN_AVAILABILITY}")
        if d.published_at is not None and is_after(d.published_at, d.available_at):
            problems.append(f"{d.doc_id}: {R_INCONSISTENT_METADATA}")
        if is_after(d.available_at, packet.cutoff_at):
            problems.append(f"{d.doc_id}: {R_AVAILABLE_AFTER_CUTOFF}")
        if packet.mode != MODE_PROSPECTIVE:
            continue
        if d.capture_id is None or d.source_sha256 is None or d.derivation is None:
            problems.append(f"{d.doc_id}: {R_NO_CAPTURE_EVIDENCE}")
            continue
        if d.first_seen_at is None or is_after(d.first_seen_at, packet.cutoff_at):
            problems.append(f"{d.doc_id}: {R_NOT_RECEIVED_BEFORE_CUTOFF}")
        if store is None:
            continue
        try:
            rec = store.get(d.capture_id)
        except KeyError:
            problems.append(f"{d.doc_id}: {R_NO_CAPTURE_EVIDENCE} (capture {d.capture_id} not in archive)")
            continue
        if rec.source_id != d.source_id or rec.sha256 != d.source_sha256:
            problems.append(f"{d.doc_id}: {R_PROVENANCE_MISMATCH}")
        if rec.clock_source != "system":
            problems.append(f"{d.doc_id}: {R_SYNTHETIC_CAPTURE}")
        if is_after(rec.ingested_at_dt, packet.cutoff_at) or (d.first_seen_at is not None and to_utc(d.first_seen_at) != to_utc(rec.ingested_at_dt)):
            problems.append(f"{d.doc_id}: {R_NOT_RECEIVED_BEFORE_CUTOFF}")
        try:                                                    # integridad real de los bytes archivados (R09-01)
            raw = (read_bytes or store.read)(rec)
            if hashlib.sha256(raw).hexdigest() != rec.sha256:
                raise ValueError("archived bytes do not match capture sha256")
        except Exception as exc:
            problems.append(f"{d.doc_id}: archived bytes fail integrity: {exc}")
            continue
        extractor = (extractors or {}).get(d.derivation)
        if extractor is None:
            problems.append(f"{d.doc_id}: {R_DERIVATION_MISMATCH} (extractor {d.derivation!r} not registered; payload cannot be re-derived)")
            continue
        try:
            extraction = extractor(raw)
            if not isinstance(extraction, Mapping) or "payload" not in extraction or "security_ids" not in extraction:
                raise ValueError("extractor must return a mapping with 'payload' and 'security_ids'")
            if canonical_bytes(_thaw(extraction["payload"])) != canonical_bytes(_thaw(d.payload)):
                raise ValueError("payload does not equal extractor output on the archived bytes")
            if tuple(str(s) for s in extraction["security_ids"]) != d.security_ids:
                raise ValueError("security_ids do not equal extracted identities")
        except Exception as exc:
            problems.append(f"{d.doc_id}: {R_DERIVATION_MISMATCH} ({exc})")
    rejected_ids: set[str] = set()
    for r in packet.rejected:
        if r.doc_id in seen:
            problems.append(f"{r.doc_id}: document is both admitted and rejected")
        if r.doc_id in rejected_ids:
            problems.append(f"{r.doc_id}: duplicate rejection")
        rejected_ids.add(r.doc_id)
        if r.reason not in KNOWN_REJECTION_REASONS:
            problems.append(f"{r.doc_id}: rejection reason {r.reason!r} is not in the admission catalog (R09-03)")
        elif not rejection_detail_is_canonical(r.reason, r.detail):
            problems.append(f"{r.doc_id}: rejection detail is not one of the templates build_packet emits for {r.reason!r} (R09-03)")
    return problems


_ISO = r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9:.+\-]+"
_ID = r"[A-Za-z0-9_:.@/\-]+"
_REJECTION_DETAIL_TEMPLATES: dict[str, tuple[str, ...]] = {
    R_UNKNOWN_AVAILABILITY: (r"availability could not be established",),
    R_INCONSISTENT_METADATA: (rf"published_at={_ISO} later than available_at={_ISO}", rf"first_seen_at={_ISO} != capture ingested_at={_ISO}"),
    R_AVAILABLE_AFTER_CUTOFF: (rf"available_at={_ISO} > cutoff={_ISO}",),
    R_NO_CAPTURE_EVIDENCE: (r"document is not linked to a RawStore capture",),
    R_SYNTHETIC_CAPTURE: (rf"capture clock_source={_ID}",),
    R_PROVENANCE_MISMATCH: (rf"document source={_ID} sha=[0-9a-fA-F]{{0,12}}(None)? vs capture source={_ID} sha=[0-9a-f]{{12}}",),
    R_DERIVATION_MISMATCH: (rf"derivation='?{_ID}'? is not a registered extractor", r"derivation=None is not a registered extractor",
                            rf"extractor {_ID} failed: [A-Za-z_][A-Za-z0-9_]*",
                            rf"payload does not equal extractor\({_ID}\) applied to the archived bytes",
                            r"security_ids \([^)]*\) do not equal extracted \([^)]*\)"),
    R_NOT_RECEIVED_BEFORE_CUTOFF: (rf"ingested_at={_ISO} > cutoff={_ISO}",),
}


def rejection_detail_is_canonical(reason: str, detail: str) -> bool:
    """El detalle de un rechazo sólo puede ser una de las plantillas de ``build_packet``: sin texto libre que el
    predictor pueda leer (R09-03). Las excepciones de extractores se reducen a su clase, nunca a su mensaje."""
    import re
    return any(re.fullmatch(p, str(detail)) is not None for p in _REJECTION_DETAIL_TEMPLATES.get(reason, ()))


def packet_to_json(packet: Packet) -> bytes:
    """Serialización canónica del paquete para archivarlo junto a su hash (registro de paquetes acreditados)."""
    return canonical_bytes({
        "packet_id": packet.packet_id, "cutoff_at": packet.cutoff_at, "mode": packet.mode,
        "evidence_class": packet.evidence_class, "created_at": packet.created_at, "week_id": packet.week_id,
        "week_status": packet.week_status, "deadline_at": packet.deadline_at,
        "registration_deadline_at": packet.registration_deadline_at, "entry_at": packet.entry_at,
        "exit_at": packet.exit_at, "calendar_version": packet.calendar_version,
        "admitted": [d.canonical() for d in packet.admitted],
        "rejected": [[r.doc_id, r.reason, r.detail] for r in packet.rejected],
        "packet_hash": packet.packet_hash(),
    })


def _dt(v: Optional[str]) -> Optional[datetime]:
    return datetime.fromisoformat(v) if isinstance(v, str) else None


def packet_from_json(raw: bytes) -> Packet:
    """Reconstruye un paquete archivado y comprueba que su hash coincide con el declarado."""
    body = json.loads(raw.decode("utf-8"))
    docs = []
    for c in body["admitted"]:
        docs.append(Document(
            doc_id=c["doc_id"], kind=c["kind"], source_id=c["source_id"], security_ids=tuple(c["security_ids"]),
            available_at=_dt(c["available_at"]), availability_quality=AvailabilityQuality(c["availability_quality"]),
            published_at=_dt(c.get("published_at")), first_seen_at=_dt(c.get("first_seen_at")),
            version=c.get("version", 1), supersedes=c.get("supersedes"),
            period_end=date.fromisoformat(c["period_end"]) if c.get("period_end") else None,
            scheduled_for=_dt(c.get("scheduled_for")), capture_id=c.get("capture_id"),
            source_sha256=c.get("source_sha256"), derivation=c.get("derivation"), payload=c.get("payload") or {},
        ))
    packet = Packet(
        packet_id=body["packet_id"], cutoff_at=_dt(body["cutoff_at"]), mode=body["mode"],
        evidence_class=body["evidence_class"], admitted=tuple(docs),
        rejected=tuple(Rejection(*r) for r in body["rejected"]), created_at=_dt(body["created_at"]),
        week_id=body.get("week_id"), week_status=body.get("week_status"), deadline_at=_dt(body.get("deadline_at")),
        registration_deadline_at=_dt(body.get("registration_deadline_at")), entry_at=_dt(body.get("entry_at")),
        exit_at=_dt(body.get("exit_at")), calendar_version=body.get("calendar_version"),
    )
    if packet.packet_hash() != body.get("packet_hash"):
        raise ValueError("archived packet hash does not match its content")
    return packet


def validate_document_references(document_ids: Sequence[str], packet: Packet) -> list[str]:
    """TXT-05: devuelve los identificadores citados que NO están en el paquete."""
    allowed = packet.admitted_ids()
    return [d for d in document_ids if d not in allowed]


# -- aislamiento del predictor (PIT-11, R01-05) -----------------------------
class AccessDenied(PermissionError):
    pass


@dataclass(frozen=True)
class SecurityEvent:
    at: datetime
    role: str
    action: str
    detail: str


class PredictorView:
    """Lo único que ve un proceso predictor. No contiene resultados: no hay nada que filtrar."""

    __slots__ = ("_packet", "security_log")

    def __init__(self, packet: Packet) -> None:
        self._packet = packet
        self.security_log: list[SecurityEvent] = []

    @property
    def role(self) -> str:
        return "predictor"

    def packet(self) -> Packet:
        return self._packet

    def outcomes(self) -> Any:
        ev = SecurityEvent(datetime.now(UTC), "predictor", "read_outcomes",
                           "blocked: predictor attempted to access outcome store")
        self.security_log.append(ev)
        raise AccessDenied(ev.detail)


class EvaluatorView:
    __slots__ = ("_outcomes",)

    def __init__(self, outcomes: Any) -> None:
        self._outcomes = outcomes

    @property
    def role(self) -> str:
        return "evaluator"

    def outcomes(self) -> Any:
        return self._outcomes


def open_workspace(*, role: str, packet: Optional[Packet] = None, outcomes: Any = None):
    """Fábrica: el objeto del predictor se construye sin recibir jamás los resultados."""
    if role == "predictor":
        if outcomes is not None:
            raise ValueError("a predictor workspace must not be constructed with outcomes")
        if packet is None:
            raise ValueError("predictor workspace requires a packet")
        return PredictorView(packet)
    if role == "evaluator":
        return EvaluatorView(outcomes)
    raise ValueError(f"unknown role {role!r}")


__all__ = ["STATUS_VALID"]
