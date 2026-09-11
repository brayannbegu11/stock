"""Archivo original versionado, sólo anexado.

- ``ingested_at`` lo pone el reloj del sistema en el momento real de la
  captura. No existe parámetro para fijarlo a mano (PIT-04).
- Un reloj inyectado (pruebas, datos sintéticos) marca el registro con
  ``clock_source="injected"``; esos registros nunca pueden declararse
  capturas prospectivas (R01-20).
- Un hash prueba integridad relativa, no fecha de existencia (PIT-12). El
  estado «sellado» **no se almacena ni se lee de un campo** (R02-07): se
  recalcula en ``RawStore.is_sealed`` ejecutando el verificador registrado
  para la autoridad del recibo, comprobando además que los bytes archivados
  siguen intactos (R03-05) y que tanto el instante acreditado como la propia
  captura son anteriores al plazo (R03-06).
- Sólo las autoridades de producción (OpenTimestamps, TSA RFC 3161) producen
  sellos utilizables por el protocolo; un verificador de prueba se marca como
  tal y ``seals()`` lo excluye salvo petición explícita (bloqueo pedido por
  Astra en P2 hasta completar la cadena criptográfica).
- El manifiesto es compatible hacia atrás (R02-11).
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field, fields
from datetime import datetime
from pathlib import Path
from typing import Callable, Mapping, Optional

from .timeutil import UTC, ensure_aware, is_after

from .seals import PRODUCTION_AUTHORITIES, is_production_authority, production_verifier

RECEIPT_PENDING = "pending"
RECEIPT_VERIFIED = "verified"
RECEIPT_INVALID = "invalid"

Verifier = Callable[["CaptureRecord", "Receipt"], bool]


class UntrustedVerifier(ValueError):
    pass


class ManifestCorrupt(ValueError):
    """El índice del archivo (``manifest.jsonl``) tiene una línea que no es un registro válido: nada de lo que
    contiene puede usarse como evidencia hasta que se repare (R26-03)."""


class MissingCapture(KeyError):
    """Identificador de captura ausente del índice del archivo (R26-03)."""


class IntegrityError(RuntimeError):
    pass


@dataclass(frozen=True)
class Receipt:
    receipt_id: str
    authority: str            # opentimestamps | rfc3161 | <test authority>
    digest: str               # sha256 que el recibo acredita
    status: str               # pending | verified | invalid  (resultado de la última verificación; informativo)
    attested_at: Optional[str] = None      # instante acreditado por la autoridad (ISO 8601 con zona)
    verification_method: Optional[str] = None
    verified_at: Optional[str] = None

    def attested_at_dt(self) -> Optional[datetime]:
        if not self.attested_at:
            return None
        try:
            dt = datetime.fromisoformat(self.attested_at)
        except ValueError:
            return None
        return dt if dt.tzinfo is not None else None


@dataclass(frozen=True)
class SealInfo:
    """Lo que un sello acredita: un digest concreto, en un instante, para una captura concreta."""
    receipt_id: str
    authority: str
    capture_id: str
    digest: str
    attested_at: datetime
    ingested_at: datetime
    production: bool
    capture_extra: Mapping[str, object]


_RECORD_FIELDS: Optional[set[str]] = None


@dataclass(frozen=True)
class CaptureRecord:
    capture_id: str
    source_id: str
    dataset: str
    path: str
    sha256: str
    bytes: int
    ingested_at: str          # ISO-8601 UTC
    url: str
    http_status: Optional[int]
    content_type: Optional[str]
    clock_source: str         # system | injected
    extra: dict = field(default_factory=dict)
    receipt: Optional[dict] = None

    @property
    def ingested_at_dt(self) -> datetime:
        return datetime.fromisoformat(self.ingested_at)

    @property
    def receipt_obj(self) -> Optional[Receipt]:
        return Receipt(**self.receipt) if self.receipt else None

    @classmethod
    def from_manifest_line(cls, raw: dict) -> "CaptureRecord":
        global _RECORD_FIELDS
        if _RECORD_FIELDS is None:
            _RECORD_FIELDS = {f.name for f in fields(cls)}
        data = {k: v for k, v in raw.items() if k in _RECORD_FIELDS}
        legacy_receipt = raw.get("receipt_id")
        if legacy_receipt and data.get("receipt") is None:
            data["extra"] = {**dict(data.get("extra") or {}), "legacy_receipt_note": f"{legacy_receipt}@{raw.get('receipt_authority')}"}
        return cls(**data)


class RawStore:
    MANIFEST = "manifest.jsonl"

    def __init__(self, root: Path, clock: Optional[Callable[[], datetime]] = None,
                 verifiers: Optional[Mapping[str, Verifier]] = None) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._clock = clock
        self._clock_source = "injected" if clock is not None else "system"
        self._verifiers: dict[str, Verifier] = {}
        for authority, verifier in (verifiers or {}).items():
            self.register_verifier(authority, verifier)

    def _now(self) -> datetime:
        now = self._clock() if self._clock else datetime.now(UTC)
        return ensure_aware(now, "clock").astimezone(UTC)

    def put(
        self,
        *,
        source_id: str,
        dataset: str,
        payload: bytes,
        url: str,
        http_status: Optional[int] = None,
        content_type: Optional[str] = None,
        extra: Optional[dict] = None,
    ) -> CaptureRecord:
        ingested_at = self._now()
        sha = hashlib.sha256(payload).hexdigest()
        ext = ".json" if (content_type or "").startswith("application/json") else ".bin"
        rel = Path(source_id) / dataset / f"{ingested_at.strftime('%Y%m%dT%H%M%S%fZ')}__{sha[:12]}{ext}"
        abs_path = self.root / rel
        abs_path.parent.mkdir(parents=True, exist_ok=True)
        abs_path.write_bytes(payload)
        rec = CaptureRecord(
            capture_id=f"{source_id}:{dataset}:{ingested_at.isoformat()}:{sha[:12]}",
            source_id=source_id,
            dataset=dataset,
            path=str(rel).replace("\\", "/"),
            sha256=sha,
            bytes=len(payload),
            ingested_at=ingested_at.isoformat(),
            url=url,
            http_status=http_status,
            content_type=content_type,
            clock_source=self._clock_source,
            extra=dict(extra or {}),
        )
        self._append(rec)
        return rec

    def _append(self, rec: CaptureRecord) -> None:
        with (self.root / self.MANIFEST).open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(asdict(rec), ensure_ascii=False) + "\n")

    def _read_manifest(self) -> list[CaptureRecord]:
        p = self.root / self.MANIFEST
        if not p.exists():
            return []
        latest: dict[str, CaptureRecord] = {}
        for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            try:
                raw = json.loads(line)
                if not isinstance(raw, dict):
                    raise ValueError("manifest line is not an object")
                r = CaptureRecord.from_manifest_line(raw)
            except (ValueError, TypeError, AttributeError) as exc:   # json.JSONDecodeError es ValueError
                raise ManifestCorrupt(f"{p.name} line {n}: {exc}") from exc
            latest[r.capture_id] = r          # los recibos se anexan; la última línea gana
        return list(latest.values())

    def get(self, capture_id: str) -> CaptureRecord:
        recs = {r.capture_id: r for r in self._read_manifest()}
        if capture_id not in recs:
            raise MissingCapture(capture_id)
        return recs[capture_id]

    def find(self, *, source_id: str, dataset: str, sha256: Optional[str] = None,
             extra_equal: Optional[Mapping[str, object]] = None) -> Optional[CaptureRecord]:
        """Primera captura (la más antigua por ``ingested_at``) de ``dataset`` con el mismo contenido.

        Sirve para no volver a archivar bytes idénticos en corridas repetidas: el registro devuelto conserva la hora
        real de la primera ingestión, que es la que cuenta como evidencia. La igualdad se declara por ``sha256`` de los
        bytes o por claves de ``extra`` (p. ej. ``packet_hash``, que excluye metadatos de construcción). No escribe nada.
        """
        if sha256 is None and not extra_equal:
            raise ValueError("find() needs sha256 or extra_equal")
        best: Optional[CaptureRecord] = None
        for r in self._read_manifest():
            if r.source_id != source_id or r.dataset != dataset:
                continue
            if sha256 is not None and r.sha256 != sha256:
                continue
            if extra_equal and any(r.extra.get(k) != v for k, v in extra_equal.items()):
                continue
            if best is None or r.ingested_at < best.ingested_at:
                best = r
        return best

    def captures(
        self,
        *,
        source_id: Optional[str] = None,
        dataset: Optional[str] = None,
        known_at: Optional[datetime] = None,
    ) -> list[CaptureRecord]:
        recs = self._read_manifest()
        if source_id:
            recs = [r for r in recs if r.source_id == source_id]
        if dataset:
            recs = [r for r in recs if r.dataset == dataset]
        if known_at is not None:
            ka = ensure_aware(known_at, "known_at").astimezone(UTC)
            recs = [r for r in recs if r.ingested_at_dt <= ka]
        return sorted(recs, key=lambda r: r.ingested_at)

    def read(self, rec: CaptureRecord) -> bytes:
        data = (self.root / rec.path).read_bytes()
        if hashlib.sha256(data).hexdigest() != rec.sha256:
            raise IntegrityError(rec.capture_id)
        return data

    def intact(self, rec: CaptureRecord) -> bool:
        p = self.root / rec.path
        return p.exists() and hashlib.sha256(p.read_bytes()).hexdigest() == rec.sha256

    # -- sellos temporales -------------------------------------------------
    def register_verifier(self, authority: str, verifier: Verifier) -> None:
        """Sólo autoridades de prueba. Las de producción se resuelven en ``twlab.seals`` (R05-01)."""
        if is_production_authority(authority):
            raise UntrustedVerifier(
                f"{authority!r} is a production authority; its verifier is fixed in twlab.seals and cannot be injected"
            )
        self._verifiers[authority] = verifier

    def _verifier_for(self, authority: str) -> Optional[Verifier]:
        if is_production_authority(authority):
            return production_verifier(authority)
        return self._verifiers.get(authority)

    def attach_receipt(self, capture_id: str, *, receipt_id: str, authority: str, digest: str,
                       attested_at: Optional[str] = None) -> CaptureRecord:
        """Anexa un recibo en estado ``pending``. El digest debe ser el sha256 del registro."""
        rec = self.get(capture_id)
        if digest != rec.sha256:
            raise ValueError(f"receipt digest {digest[:12]} does not match capture sha256 {rec.sha256[:12]}")
        receipt = Receipt(receipt_id=receipt_id, authority=authority, digest=digest,
                          status=RECEIPT_PENDING, attested_at=attested_at)
        new = CaptureRecord(**{**asdict(rec), "receipt": asdict(receipt)})
        self._append(new)
        return new

    def verify_receipt(self, capture_id: str, *, method: str) -> CaptureRecord:
        """Ejecuta el verificador registrado y anexa el resultado (informativo; el sello se recalcula siempre)."""
        rec = self.get(capture_id)
        receipt = rec.receipt_obj
        if receipt is None:
            raise ValueError("no receipt attached")
        ok = self.is_sealed(rec)
        updated = Receipt(**{**asdict(receipt), "status": RECEIPT_VERIFIED if ok else RECEIPT_INVALID,
                             "verification_method": method, "verified_at": datetime.now(UTC).isoformat()})
        new = CaptureRecord(**{**asdict(rec), "receipt": asdict(updated)})
        self._append(new)
        return new

    def seal_info(self, rec: CaptureRecord, *, not_after: Optional[datetime] = None) -> Optional[SealInfo]:
        """Sello prospectivo completo, recalculado; ``None`` si cualquier condición falla.

        Condiciones: reloj del sistema; bytes archivados intactos; recibo con
        digest igual al sha256; instante acreditado válido; captura e instante
        acreditado no posteriores a ``not_after``; verificador registrado para
        la autoridad que acepte el recibo.
        """
        if rec.clock_source != "system":
            return None
        receipt = rec.receipt_obj
        if receipt is None or receipt.digest != rec.sha256:
            return None
        if not self.intact(rec):
            return None
        attested = receipt.attested_at_dt()
        if attested is None:
            return None
        ingested = rec.ingested_at_dt
        if not_after is not None and (is_after(attested, not_after) or is_after(ingested, not_after)):
            return None
        verifier = self._verifier_for(receipt.authority)
        if verifier is None:
            return None
        try:
            if not verifier(rec, receipt):
                return None
        except Exception:
            return None
        return SealInfo(receipt.receipt_id, receipt.authority, rec.capture_id, rec.sha256, attested, ingested,
                        is_production_authority(receipt.authority), dict(rec.extra))

    def is_sealed(self, rec: CaptureRecord, *, not_after: Optional[datetime] = None) -> bool:
        return self.seal_info(rec, not_after=not_after) is not None

    def seals(self, *, not_after: Optional[datetime] = None, allow_test_authorities: bool = False) -> dict[str, SealInfo]:
        """Sellos verificados por identificador de recibo. Sólo autoridades de producción salvo petición explícita."""
        out: dict[str, SealInfo] = {}
        for r in self._read_manifest():
            info = self.seal_info(r, not_after=not_after)
            if info is not None and (info.production or allow_test_authorities):
                out[info.receipt_id] = info
        return out

    def verify(self) -> list[str]:
        problems: list[str] = []
        for r in self._read_manifest():
            p = self.root / r.path
            if not p.exists():
                problems.append(f"missing:{r.capture_id}")
                continue
            if hashlib.sha256(p.read_bytes()).hexdigest() != r.sha256:
                problems.append(f"hash_mismatch:{r.capture_id}")
        return problems
