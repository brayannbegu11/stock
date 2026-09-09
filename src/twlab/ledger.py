"""Libro de cartera simulada, determinista e independiente de los LLM.

Invariantes contables (CONTRATOS_DATOS.md §5) y correcciones de las rondas
1-4 de Astra. Desde la ronda 4 el libro contabiliza por **lotes con
propietario** (R04-09/10/11): cada compra crea un lote etiquetado (p. ej. la
cesta y el puesto que lo compró); las acciones corporativas escalan cada
lote; las ventas consumen sólo los lotes del propietario indicado; los
dividendos se declaran lote a lote. Así una cesta nunca vende ni se
atribuye lo que compró otra, y su rentabilidad bruta puede incluir sus
dividendos.

- Sólo precios nominales (SIM-02). Validación de dominios (R01-16).
- Orden cronológico estricto; derechos para quien tenía el lote en la fecha
  efectiva (R01-12). Un cobro cuya fecha de pago se conoce tarde se abona en
  el instante en que se conoce, no retroactivamente (R04-08).
- Comisión e impuesto sobre el importe ejecutado, redondeo declarado,
  efectivo = suma de componentes (R01-13/14). Lotes de 1.000 (SIM-06, R01-17).
- Acciones corporativas exactamente una vez; id consumido sólo al aplicarse
  (R01-11). Pago sin fecha → cobro no disponible (R02-05). Fracciones se
  conservan (R02-13/14).
- ``valuation`` es pura y no acepta instantes anteriores al reloj (R02-15, R03-09).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Mapping, Optional, Union

from .timeutil import ensure_aware, to_utc

D = Decimal
ZERO = D("0")
TWD = D("1")
DEFAULT_OWNER = "unassigned"


def q_twd(x: Decimal) -> Decimal:
    """Redondeo comercial a TWD entero (HALF_UP)."""
    return x.quantize(TWD, rounding=ROUND_HALF_UP)


def floor_twd(x: Decimal) -> Decimal:
    """Truncado a TWD entero; práctica habitual de comisiones e impuesto en Taiwán, a confirmar por contrato."""
    return x.quantize(TWD, rounding=ROUND_DOWN)


class LedgerError(ValueError):
    pass


class OutOfOrderEvent(LedgerError):
    pass


class DuplicateCorporateAction(LedgerError):
    pass


class MissingPrice(KeyError):
    pass


@dataclass(frozen=True)
class CostModel:
    commission_per_side: Decimal          # p. ej. D("0.001425") (ilustrativa, no contratada)
    sell_tax: Decimal = D("0.003")        # impuesto de transacción sobre venta de acciones ordinarias
    slippage_bps_per_side: int = 0
    rounding: str = "floor"               # floor | half_up; política declarada, a confirmar con el bróker
    label: str = "illustrative_not_contracted"

    def __post_init__(self) -> None:
        for name in ("commission_per_side", "sell_tax"):
            v = getattr(self, name)
            if not isinstance(v, Decimal) or not v.is_finite() or v < 0 or v >= 1:
                raise LedgerError(f"{name} must be a finite Decimal in [0, 1)")
        if not isinstance(self.slippage_bps_per_side, int) or self.slippage_bps_per_side < 0 or self.slippage_bps_per_side >= 10_000:
            raise LedgerError("slippage_bps_per_side out of range")
        if self.rounding not in ("floor", "half_up"):
            raise LedgerError("rounding must be floor or half_up")

    @property
    def slippage(self) -> Decimal:
        return D(self.slippage_bps_per_side) / D(10_000)

    def round(self, x: Decimal) -> Decimal:
        return floor_twd(x) if self.rounding == "floor" else q_twd(x)


@dataclass(frozen=True)
class Fill:
    security_id: str
    side: str
    shares: int
    price: Decimal            # precio de referencia (apertura/cierre usado)
    gross: Decimal            # price * shares, redondeado a TWD
    slippage_cost: Decimal    # coste del deslizamiento, redondeado
    executed: Decimal         # importe realmente ejecutado: gross ± slippage_cost
    commission: Decimal
    tax: Decimal
    cash_delta: Decimal       # == -(executed + commission) en compra; executed - commission - tax en venta
    realized_pnl: Decimal     # sólo ventas: neto - base de coste vendida
    at: datetime
    event_id: str
    owner: str = DEFAULT_OWNER


@dataclass(frozen=True)
class Rejection:
    security_id: str
    side: str
    reason: str
    detail: str
    at: datetime
    event_id: str


Result = Union[Fill, Rejection]


@dataclass
class Lot:
    owner: str
    quantity: Decimal          # puede tener fracción tras acciones corporativas
    cost_twd: Decimal
    opened_at: datetime


@dataclass
class Position:
    security_id: str
    opened_at: datetime
    lots: list[Lot] = field(default_factory=list)
    status: str = "open"                  # open | suspended | delisted_unresolved | delisted_settled
    last_price: Optional[Decimal] = None  # sólo lo cambian las ejecuciones (y los splits)
    lot_size: int = 1000
    terminal_price: Optional[Decimal] = None
    notes: list[str] = field(default_factory=list)

    @property
    def total_quantity(self) -> Decimal:
        return sum((lot.quantity for lot in self.lots), ZERO)

    @property
    def shares(self) -> int:
        return int(self.total_quantity.to_integral_value(rounding=ROUND_DOWN))

    @property
    def unresolved_fraction(self) -> Decimal:
        """Suma de las fracciones de cada lote: las fracciones de distintos propietarios no se cancelan (R05-07)."""
        return sum((lot.quantity - int(lot.quantity.to_integral_value(rounding=ROUND_DOWN)) for lot in self.lots), ZERO)

    @property
    def cost_twd(self) -> Decimal:
        return sum((lot.cost_twd for lot in self.lots), ZERO)

    def owner_quantity(self, owner: str) -> Decimal:
        return sum((lot.quantity for lot in self.lots if lot.owner == owner), ZERO)


@dataclass(frozen=True)
class LedgerEvent:
    seq: int
    kind: str
    at: datetime
    security_id: Optional[str]
    cash_delta: Decimal
    detail: str
    event_id: str
    owner: Optional[str] = None


@dataclass
class Receivable:
    security_id: str
    amount: Decimal
    pay_at: Optional[datetime]     # None → fecha de pago desconocida: nunca disponible hasta fijarla
    event_id: str
    owner: str


@dataclass(frozen=True)
class CorporateAction:
    event_id: str
    security_id: str
    kind: str                     # cash_dividend | stock_dividend | split | delisting
    effective_at: datetime        # fecha de derechos (ex-date) o fecha efectiva
    per_share_cash: Optional[Decimal] = None
    pay_at: Optional[datetime] = None            # fecha de pago; None → cobro pendiente sin fecha (no disponible)
    stock_ratio: Optional[Decimal] = None        # acciones nuevas por acción antigua (配股): 0.1 → +100 por 1.000
    split_ratio: Optional[Decimal] = None        # nuevas/antiguas: 2 en un 2:1, 0.5 en un contrasplit 1:2
    terminal_price: Optional[Decimal] = None     # None → no resuelto
    stock_per_share: Optional[Decimal] = None    # TWD de valor nominal distribuidos por acción (forma exacta del dividendo en acciones)
    par_value: Optional[Decimal] = None          # valor nominal: cantidad nueva = cantidad × (par + per_share) / par, sin redondear el cociente (R13-07)


@dataclass(frozen=True)
class Valuation:
    at: datetime
    cash: Decimal                 # efectivo contable + cobros cuya fecha de pago ya llegó a ``at``
    receivables: Decimal          # cobros con fecha de pago posterior a ``at`` o sin fecha
    positions_value: Decimal
    total: Decimal
    unresolved: tuple[str, ...]
    flags: tuple[str, ...]


def _positive_decimal(value: Decimal, name: str) -> Decimal:
    try:
        v = D(value)
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise LedgerError(f"{name} is not a number: {value!r}") from exc
    if not v.is_finite() or v <= 0:
        raise LedgerError(f"{name} must be a positive finite number, got {value!r}")
    return v


def _positive_int(value: int, name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise LedgerError(f"{name} must be a positive integer, got {value!r}")
    return value


class PaperLedger:
    def __init__(
        self,
        *,
        ledger_id: str,
        initial_cash: Decimal,
        cost_model: CostModel,
        price_series_kind: str = "nominal",
        lot_size: int = 1000,
    ) -> None:
        if price_series_kind != "nominal":
            raise LedgerError(
                "ledger requires nominal prices; adjusted series would double-count corporate actions (SIM-02)"
            )
        self.ledger_id = ledger_id
        self.cash = q_twd(_positive_decimal(initial_cash, "initial_cash"))
        self.initial_cash = self.cash
        self.costs = cost_model
        self.lot_size = _positive_int(lot_size, "lot_size")
        self.positions: dict[str, Position] = {}
        self.closed: list[Position] = []
        self.events: list[LedgerEvent] = []
        self.receivables: list[Receivable] = []
        self._applied_actions: set[str] = set()
        self._seq = 0
        self._last_at: Optional[datetime] = None
        self._declared_dividends: dict[tuple[str, str], Decimal] = {}
        self._owner_sale_gross: dict[tuple[str, str], Decimal] = {}
        self.owners_seen: set[str] = set()

    # -- reloj y cobros ------------------------------------------------------
    @property
    def clock(self) -> Optional[datetime]:
        return self._last_at

    def _touch(self, at: datetime) -> datetime:
        ensure_aware(at, "at")
        if self._last_at is not None and to_utc(at) < to_utc(self._last_at):
            raise OutOfOrderEvent(f"event at {to_utc(at).isoformat()} precedes last event {to_utc(self._last_at).isoformat()}")
        self._settle(at)
        self._last_at = at
        return at

    def _settle(self, at: datetime) -> None:
        """Abona, en orden de fecha de pago, los cobros vencidos. El asiento se fecha en ``at`` si el
        vencimiento se conoció tarde (R04-08); la fecha contractual queda en el detalle."""
        due = sorted((r for r in self.receivables if r.pay_at is not None and to_utc(r.pay_at) <= to_utc(at)),
                     key=lambda r: to_utc(r.pay_at))  # type: ignore[arg-type]
        for r in due:
            self.cash += r.amount
            self.receivables.remove(r)
            settle_at = r.pay_at if (self._last_at is None or to_utc(r.pay_at) >= to_utc(self._last_at)) else at  # type: ignore[arg-type]
            self._log("receivable_settled", settle_at, r.security_id, r.amount,
                      f"dividend paid (contractual pay_at={to_utc(r.pay_at).isoformat()})", r.event_id, r.owner)  # type: ignore[arg-type]

    def advance_to(self, at: datetime) -> None:
        """Avanza el reloj del libro sin operar (semanas sin negociación): procesa pagos vencidos."""
        self._touch(at)

    def set_payment_date(self, event_id: str, *, pay_at: datetime, at: datetime) -> None:
        """Fija la fecha de pago de un cobro declarado sin ella; ``at`` es cuándo se conoció (R03-08)."""
        ensure_aware(pay_at, "pay_at")
        targets = [r for r in self.receivables if r.event_id == event_id and r.pay_at is None]
        if not targets:
            raise LedgerError(f"no receivable without payment date for {event_id}")
        declared = next(e.at for e in self.events if e.event_id == event_id)
        if to_utc(pay_at) < to_utc(declared):
            raise LedgerError("pay_at cannot precede the declaration date")
        self._touch(at)
        for r in targets:
            r.pay_at = pay_at
        self._log("payment_date_set", at, targets[0].security_id, ZERO, f"pay_at={to_utc(pay_at).isoformat()}", event_id)
        self._settle(at)

    def _log(self, kind: str, at: datetime, security_id: Optional[str], cash_delta: Decimal,
             detail: str, event_id: str, owner: Optional[str] = None) -> None:
        self._seq += 1
        self.events.append(LedgerEvent(self._seq, kind, ensure_aware(at), security_id, cash_delta, detail, event_id, owner))

    def _reject(self, security_id: str, side: str, reason: str, detail: str, at: datetime, event_id: str) -> Rejection:
        r = Rejection(security_id, side, reason, detail, at, event_id)
        self._log(f"{side}_rejected", at, security_id, ZERO, reason, event_id)
        return r

    def available_cash(self) -> Decimal:
        """Efectivo disponible. Ni posiciones inmovilizadas ni cobros pendientes cuentan (SIM-05)."""
        return self.cash

    def declared_dividends(self, security_id: str, owner: str) -> Decimal:
        """Dividendos declarados (derechos adquiridos) para los lotes de un propietario, valor de referencia sin redondear."""
        return self._declared_dividends.get((security_id, owner), ZERO)

    def reserve_owner(self, owner: str) -> None:
        """Reserva la identidad de una cesta aunque no llegue a comprar nada (R06-06)."""
        if owner in self.owners_seen:
            raise LedgerError(f"owner {owner!r} already used in this ledger")
        self.owners_seen.add(owner)

    def owner_sale_gross(self, security_id: str, owner: str) -> Decimal:
        """Importe bruto acumulado (precio × acciones) de todas las ventas de un propietario (R05-06)."""
        return self._owner_sale_gross.get((security_id, owner), ZERO)

    # -- operaciones ------------------------------------------------------
    def buy(self, *, security_id: str, price: Decimal, shares: int, at: datetime, event_id: str,
            owner: str = DEFAULT_OWNER) -> Result:
        price = _positive_decimal(price, "price")
        _positive_int(shares, "shares")
        self._touch(at)
        if shares % self.lot_size != 0:
            return self._reject(security_id, "buy", "not_round_lot", f"shares={shares} lot={self.lot_size}", at, event_id)
        pos = self.positions.get(security_id)
        if pos is not None and pos.status != "open":
            return self._reject(security_id, "buy", f"position_{pos.status}", "cannot add to non-open position", at, event_id)
        gross = q_twd(price * shares)
        slip = self.costs.round(gross * self.costs.slippage)
        executed = gross + slip
        commission = self.costs.round(executed * self.costs.commission_per_side)
        total = executed + commission
        if total > self.cash:
            return self._reject(security_id, "buy", "insufficient_cash", f"need={total} cash={self.cash}", at, event_id)
        self.cash -= total
        if pos is None:
            pos = Position(security_id, at, lot_size=self.lot_size)
            self.positions[security_id] = pos
        pos.lots.append(Lot(owner, D(shares), total, at))
        pos.last_price = price
        self.owners_seen.add(owner)
        fill = Fill(security_id, "buy", shares, price, gross, slip, executed, commission, ZERO, -total, ZERO, at, event_id, owner)
        self._log("buy", at, security_id, -total, f"{shares}@{price}", event_id, owner)
        return fill

    def sell(self, *, security_id: str, price: Decimal, shares: int, at: datetime, event_id: str,
             owner: Optional[str] = None) -> Result:
        """Vende ``shares`` acciones; si se indica ``owner`` sólo consume sus lotes (R04-09)."""
        price = _positive_decimal(price, "price")
        _positive_int(shares, "shares")
        self._touch(at)
        pos = self.positions.get(security_id)
        if pos is None:
            return self._reject(security_id, "sell", "no_position", "", at, event_id)
        if pos.status != "open":
            return self._reject(security_id, "sell", f"exit_blocked_{pos.status}", "position remains in ledger", at, event_id)
        lots = [lot for lot in pos.lots if owner is None or lot.owner == owner]
        # sólo se venden acciones enteras de cada lote: las fracciones son derechos pendientes, no se consumen (R07-09)
        available = sum((D(int(lot.quantity.to_integral_value(rounding=ROUND_DOWN))) for lot in lots), ZERO)
        if D(shares) > available:
            return self._reject(security_id, "sell", "invalid_quantity",
                                f"shares={shares} whole_held={available} owner={owner or 'any'}", at, event_id)
        if shares % self.lot_size != 0:
            return self._reject(security_id, "sell", "odd_lot_requires_separate_mechanism",
                                f"shares={shares} lot={self.lot_size}; regular-session price not applicable (SIM-06)", at, event_id)
        gross = q_twd(price * shares)
        slip = self.costs.round(gross * self.costs.slippage)
        executed = gross - slip
        commission = self.costs.round(executed * self.costs.commission_per_side)
        tax = self.costs.round(executed * self.costs.sell_tax)
        net = executed - commission - tax
        remaining = D(shares)
        basis_sold = ZERO
        for lot in lots:                                   # FIFO dentro del propietario (o global si owner=None)
            if remaining <= 0:
                break
            take = min(D(int(lot.quantity.to_integral_value(rounding=ROUND_DOWN))), remaining)
            if take <= 0:
                continue
            part = q_twd(lot.cost_twd * take / lot.quantity) if lot.quantity else ZERO
            lot.quantity -= take
            lot.cost_twd -= part
            basis_sold += part
            remaining -= take
            # el ingreso de referencia (sin redondear) se atribuye al propietario de cada lote consumido (R06-07)
            key = (security_id, lot.owner)
            self._owner_sale_gross[key] = self._owner_sale_gross.get(key, ZERO) + price * take
        pos.lots = [lot for lot in pos.lots if lot.quantity > 0]
        self.cash += net
        pos.last_price = price
        if not pos.lots:
            self.closed.append(self.positions.pop(security_id))
        elif pos.shares == 0:
            pos.notes.append("whole_shares_sold_fraction_pending")
        fill = Fill(security_id, "sell", shares, price, gross, slip, executed, commission, tax, net, net - basis_sold,
                    at, event_id, owner or DEFAULT_OWNER)
        self._log("sell", at, security_id, net, f"{shares}@{price} realized={net - basis_sold}", event_id, owner)
        return fill

    # -- estados ----------------------------------------------------------
    def mark_suspended(self, security_id: str, *, at: datetime, detail: str = "") -> None:
        self._touch(at)
        pos = self.positions[security_id]
        if pos.status == "open":
            pos.status = "suspended"
            pos.notes.append(f"suspended@{to_utc(at).isoformat()} {detail}")
            self._log("suspended", at, security_id, ZERO, detail, f"susp:{security_id}:{to_utc(at).isoformat()}")

    def mark_resumed(self, security_id: str, *, at: datetime) -> None:
        self._touch(at)
        pos = self.positions[security_id]
        if pos.status == "suspended":
            pos.status = "open"
            self._log("resumed", at, security_id, ZERO, "", f"res:{security_id}:{to_utc(at).isoformat()}")

    def apply_corporate_action(self, action: CorporateAction) -> None:
        if action.event_id in self._applied_actions:
            raise DuplicateCorporateAction(action.event_id)
        ensure_aware(action.effective_at, "effective_at")
        # validar antes de tocar el estado o consumir el identificador (R01-11)
        if action.kind == "cash_dividend":
            if action.per_share_cash is None:
                raise LedgerError("cash_dividend requires per_share_cash")
            per_share = D(action.per_share_cash)
            if not per_share.is_finite() or per_share < 0:
                raise LedgerError("per_share_cash must be a non-negative finite number")
            if action.pay_at is not None and to_utc(ensure_aware(action.pay_at)) < to_utc(action.effective_at):
                raise LedgerError("pay_at cannot precede effective_at")
        elif action.kind == "stock_dividend":
            if action.stock_ratio is None and action.stock_per_share is None:
                raise LedgerError("stock_dividend requires stock_ratio or stock_per_share with par_value")
            if action.stock_ratio is not None:
                _positive_decimal(action.stock_ratio, "stock_ratio")
            if action.stock_per_share is not None:
                _positive_decimal(action.stock_per_share, "stock_per_share")
                if action.par_value is None:
                    raise LedgerError("stock_per_share requires par_value")
                _positive_decimal(action.par_value, "par_value")
        elif action.kind == "split":
            if action.split_ratio is None:
                raise LedgerError("split requires split_ratio")
            _positive_decimal(action.split_ratio, "split_ratio")
        elif action.kind == "delisting":
            if action.terminal_price is not None:
                _positive_decimal(action.terminal_price, "terminal_price")
        else:
            raise LedgerError(f"unsupported corporate action kind {action.kind!r}; block the affected simulation")
        pos = self.positions.get(action.security_id)
        if pos is not None and any(to_utc(action.effective_at) < to_utc(lot.opened_at) for lot in pos.lots):
            raise LedgerError(
                f"{action.security_id}: a lot was opened after action effective {to_utc(action.effective_at).isoformat()}; "
                "rights belong to the holder at the effective date"
            )
        self._touch(action.effective_at)
        self._applied_actions.add(action.event_id)
        if pos is None:
            self._log("corporate_action_ignored", action.effective_at, action.security_id, ZERO,
                      f"{action.kind}: no position", action.event_id)
            return
        if action.kind == "cash_dividend":
            # importe por propietario (no por lote de adquisición): fragmentar la compra no cambia el cobro (R05-08)
            by_owner: dict[str, Decimal] = {}
            for lot in pos.lots:
                by_owner[lot.owner] = by_owner.get(lot.owner, ZERO) + lot.quantity
            for owner, qty in by_owner.items():
                amount = self.costs.round(D(action.per_share_cash) * qty)
                key = (action.security_id, owner)
                # atribución de referencia sin redondear; el efectivo cobrado sí se redondea (R06-10)
                self._declared_dividends[key] = self._declared_dividends.get(key, ZERO) + D(action.per_share_cash) * qty
                self.receivables.append(Receivable(action.security_id, amount, action.pay_at, action.event_id, owner))
                when = to_utc(action.pay_at).isoformat() if action.pay_at else "UNKNOWN (not spendable until set_payment_date)"
                self._log("cash_dividend_declared", action.effective_at, action.security_id, ZERO,
                          f"{qty}x{action.per_share_cash} payable {when}", action.event_id, owner)
            self._settle(action.effective_at)   # pagadero en este mismo instante: se abona ahora (R03-15)
        elif action.kind in ("stock_dividend", "split"):
            if action.kind == "stock_dividend" and action.stock_per_share is not None:
                # forma exacta: multiplicar antes de dividir evita inmovilizar lotes por un cociente periódico (R13-07)
                par, per = D(action.par_value), D(action.stock_per_share)
                factor = (par + per) / par
                for lot in pos.lots:
                    lot.quantity = lot.quantity * (par + per) / par
            else:
                factor = (1 + D(action.stock_ratio)) if action.kind == "stock_dividend" else D(action.split_ratio)
                for lot in pos.lots:
                    lot.quantity = lot.quantity * factor
            if action.kind == "split" and pos.last_price is not None:
                pos.last_price = pos.last_price / D(action.split_ratio)
            if pos.unresolved_fraction > 0:
                pos.notes.append(f"fractional_shares_unresolved:{pos.unresolved_fraction}")
            self._log(action.kind, action.effective_at, action.security_id, ZERO,
                      f"factor={factor} total={pos.total_quantity} shares={pos.shares} fraction={pos.unresolved_fraction}",
                      action.event_id)
        elif action.kind == "delisting":
            pos.terminal_price = action.terminal_price
            pos.status = "delisted_settled" if action.terminal_price is not None else "delisted_unresolved"
            self._log("delisting", action.effective_at, action.security_id, ZERO,
                      f"terminal_price={action.terminal_price}", action.event_id)

    # -- valoración (pura) ----------------------------------------------------
    def valuation(self, *, prices: Mapping[str, Decimal], at: datetime,
                  unresolved_policy: str = "zero_flagged") -> Valuation:
        ensure_aware(at, "at")
        if unresolved_policy not in ("zero_flagged", "raise"):
            raise LedgerError(unresolved_policy)
        if self._last_at is not None and to_utc(at) < to_utc(self._last_at):
            raise LedgerError(
                f"valuation at {to_utc(at).isoformat()} precedes the ledger clock {to_utc(self._last_at).isoformat()}; "
                "a historical valuation requires replaying the ledger up to that instant (R03-09)"
            )
        value = ZERO
        unresolved: list[str] = []
        flags: list[str] = []
        for sid, pos in self.positions.items():
            if pos.unresolved_fraction > 0:
                flags.append(f"{sid}:fractional_shares_unresolved")
            if pos.status == "delisted_settled":
                value += D(pos.terminal_price) * pos.total_quantity
                flags.append(f"{sid}:terminal_price")
            elif pos.status == "delisted_unresolved":
                unresolved.append(sid)
                if unresolved_policy == "raise":
                    raise MissingPrice(f"{sid} delisted without terminal price")
                flags.append(f"{sid}:unresolved_valued_at_zero")
            elif pos.status == "suspended":
                price = prices.get(sid, pos.last_price)
                if price is None:
                    raise MissingPrice(f"{sid} suspended without any known price")
                value += _positive_decimal(price, f"price[{sid}]") * pos.total_quantity
                flags.append(f"{sid}:suspended" + ("" if sid in prices else "_stale_price"))
            elif sid in prices:
                value += _positive_decimal(prices[sid], f"price[{sid}]") * pos.total_quantity
            elif pos.shares == 0 and pos.unresolved_fraction > 0 and pos.last_price is not None:
                value += pos.last_price * pos.unresolved_fraction
                flags.append(f"{sid}:fraction_valued_at_last_fill_price")
            else:
                raise MissingPrice(f"no price for open position {sid} at {to_utc(at).isoformat()}; absence is not a zero return")
        value = q_twd(value)
        due = sum((r.amount for r in self.receivables if r.pay_at is not None and to_utc(r.pay_at) <= to_utc(at)), ZERO)
        pending = sum((r.amount for r in self.receivables), ZERO) - due
        if any(r.pay_at is None for r in self.receivables):
            flags.append("receivables_without_payment_date")
        if pending:
            flags.append("receivables_pending")
        cash = self.cash + due
        return Valuation(at, cash, pending, value, cash + pending + value, tuple(unresolved), tuple(flags))
