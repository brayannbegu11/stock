"""Cesta semanal de hasta cinco puestos de igual peso (PROTOCOLO.yaml weekly_experiment).

Cada puesto es **propietario** de los lotes que compró (``owner =
"<week_id>:<rank>"``). Reglas (rondas 4-6 de Astra):

- Una cesta se entra una sola vez por libro; la identidad se reserva aunque
  el puesto quede vacío o falle (R05-05, R06-06).
- La salida vende sólo los lotes del propietario; la cantidad atribuible es
  la del propietario; la rentabilidad bruta usa todas las ventas del
  propietario (también las parciales y las FIFO que consumieron sus lotes),
  el residuo valorado al precio de salida y los dividendos declarados sin
  redondear (R04-09/10/11, R05-06, R06-07, R06-10).
- Una liquidación completa previa del propietario cuenta como salida
  realizada (R06-08); un residuo que más tarde se convierte en lote entero
  puede venderse en un reintento (R06-09).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import ROUND_DOWN, Decimal
from typing import Mapping, Optional, Sequence

from .ledger import Fill, PaperLedger, Rejection

D = Decimal
_Q = D("1E-12")


def slot_owner(week_id: str, rank: int) -> str:
    return f"{week_id}:{rank}"


@dataclass
class Slot:
    rank: int
    security_id: Optional[str]
    status: str                      # filled | entry_failed | empty | exited | exit_blocked
    reason: str = ""
    owner: Optional[str] = None
    entry: Optional[Fill] = None
    exit: Optional[Fill] = None
    exit_price: Optional[Decimal] = None       # último precio de salida usado para valorar el residuo
    exit_attributed_quantity: Decimal = D(0)   # cantidad del propietario justo antes de la última venta
    exit_residual_quantity: Decimal = D(0)     # cantidad del propietario que sigue en el libro
    dividends_declared: Decimal = D(0)         # dividendos declarados sobre los lotes del propietario (sin redondear)
    sale_gross_total: Decimal = D(0)           # ventas brutas de referencia del propietario (todas)
    liquidated: bool = False                   # el propietario ya no tiene cantidad en el libro
    notes: list[str] = field(default_factory=list)

    @property
    def gross_pick_return(self) -> Optional[Decimal]:
        """(ventas brutas del propietario + residuo × último precio de salida + dividendos) / importe de entrada − 1."""
        if self.entry is None or not self.entry.shares or self.status not in ("exited",):
            return None
        residual_value = self.exit_residual_quantity * (self.exit_price or D(0))
        value = self.sale_gross_total + residual_value + self.dividends_declared
        return (value / (self.entry.price * self.entry.shares) - 1).quantize(_Q)


def enter_basket(
    ledger: PaperLedger,
    *,
    picks: Sequence[str],
    slots: int,
    notional_per_slot: Decimal,
    open_prices: Mapping[str, Decimal],
    at: datetime,
    week_id: str,
    eligibility: Optional[Mapping[str, tuple[bool, str]]] = None,
) -> list[Slot]:
    """Entra en cada selección con importe nocional fijo por puesto.

    Un puesto fallido conserva su efectivo (SIM-09); no se redistribuye a los
    demás. Los puestos sin selección quedan en efectivo
    (``fill_unavailable_slots_with_cash``). La identidad de cada puesto queda
    reservada en el libro pase lo que pase (R06-06).
    """
    if len(picks) > slots:
        raise ValueError(f"{len(picks)} picks exceed {slots} slots")
    if len(set(picks)) != len(picks):
        raise ValueError(f"duplicate selections are not allowed: {list(picks)}")
    owners = [slot_owner(week_id, r) for r in range(1, slots + 1)]
    already = [o for o in owners if o in ledger.owners_seen]
    if already:
        raise ValueError(f"basket {week_id} already entered in this ledger (owners {already}); a basket is entered once (R05-05)")
    for o in owners:
        ledger.reserve_owner(o)
    out: list[Slot] = []
    for rank in range(1, slots + 1):
        owner = owners[rank - 1]
        if rank > len(picks):
            out.append(Slot(rank, None, "empty", "no_selection", owner=owner))
            continue
        sid = picks[rank - 1]
        if eligibility is not None:
            ok, why = eligibility.get(sid, (False, "not_in_eligibility_table"))
            if not ok:
                out.append(Slot(rank, sid, "entry_failed", f"ineligible:{why}", owner=owner))
                continue
        price = open_prices.get(sid)
        if price is None:
            out.append(Slot(rank, sid, "entry_failed", "no_open_price", owner=owner))
            continue
        price = D(price)
        unit_cost = price * (1 + ledger.costs.slippage) * (1 + ledger.costs.commission_per_side)
        lots = int((D(notional_per_slot) / (unit_cost * ledger.lot_size)).to_integral_value(rounding=ROUND_DOWN))
        shares = lots * ledger.lot_size
        if shares <= 0:
            out.append(Slot(rank, sid, "entry_failed", "notional_below_one_lot", owner=owner))
            continue
        existing = ledger.positions.get(sid)
        pre_qty = existing.total_quantity if existing is not None else D(0)
        res = ledger.buy(security_id=sid, price=price, shares=shares, at=at, event_id=f"{owner}:entry:{sid}", owner=owner)
        if isinstance(res, Rejection):
            out.append(Slot(rank, sid, "entry_failed", res.reason, owner=owner))
        else:
            slot = Slot(rank, sid, "filled", owner=owner, entry=res)
            if pre_qty:
                slot.notes.append(f"pre_existing_quantity_in_ledger_not_attributed:{pre_qty}")
            out.append(slot)
    return out


def _refresh(s: Slot, ledger: PaperLedger, price: Optional[Decimal]) -> None:
    pos = ledger.positions.get(s.security_id or "")
    s.exit_residual_quantity = pos.owner_quantity(s.owner) if (pos is not None and s.owner) else D(0)
    s.dividends_declared = ledger.declared_dividends(s.security_id or "", s.owner or "")
    s.sale_gross_total = ledger.owner_sale_gross(s.security_id or "", s.owner or "")
    s.liquidated = s.exit_residual_quantity == 0
    if price is not None:
        s.exit_price = price


def exit_basket(
    ledger: PaperLedger,
    slots: Sequence[Slot],
    *,
    close_prices: Mapping[str, Decimal],
    at: datetime,
    week_id: str,
) -> list[Slot]:
    for s in slots:
        if s.entry is None or s.security_id is None or s.owner is None:
            continue
        if s.status not in ("filled", "exit_blocked", "exited"):
            continue
        if s.status == "exited" and s.liquidated:
            continue                                        # nada que vender ni valorar
        pos = ledger.positions.get(s.security_id)
        owned = pos.owner_quantity(s.owner) if pos is not None else D(0)
        price = close_prices.get(s.security_id)
        if owned == 0:
            # liquidación completa previa del propietario (R06-08): la salida está realizada
            s.status = "exited"
            _refresh(s, ledger, D(price) if price is not None else s.exit_price)
            s.notes.append(f"already_liquidated_before_exit@{at.isoformat()}")
            continue
        if price is None:
            if s.status != "exited":
                s.status = "exit_blocked"
                s.reason = "no_close_price"
            s.notes.append(f"exit_attempt_blocked:no_close_price@{at.isoformat()}")
            continue
        price = D(price)
        sellable = (int(owned.to_integral_value(rounding=ROUND_DOWN)) // ledger.lot_size) * ledger.lot_size
        if sellable <= 0:
            if s.status != "exited":
                s.status = "exit_blocked"
                s.reason = "odd_lot_remainder_only"
            _refresh(s, ledger, price)
            s.notes.append(f"exit_attempt_blocked:odd_lot_remainder_only@{at.isoformat()}")
            continue
        attempt = sum(1 for n in s.notes if n.startswith("exit_attempt"))
        res = ledger.sell(security_id=s.security_id, price=price, shares=sellable, at=at,
                          event_id=f"{s.owner}:exit:{s.security_id}:attempt{attempt}", owner=s.owner)
        if isinstance(res, Rejection):
            if s.status != "exited":
                s.status = "exit_blocked"
                s.reason = res.reason
            s.notes.append(f"exit_attempt_blocked:{res.reason}@{at.isoformat()}")
        else:
            s.status = "exited"
            s.reason = ""
            s.exit = res
            s.exit_attributed_quantity = owned
            _refresh(s, ledger, price)
            s.notes.append(f"exit_attempt_sold:{sellable}@{at.isoformat()}")
            if s.exit_residual_quantity:
                s.notes.append(f"residual_quantity_in_ledger:{s.exit_residual_quantity}")
    return list(slots)


@dataclass(frozen=True)
class BasketReport:
    week_id: str
    filled_slots: int
    empty_slots: int
    failed_slots: int
    exit_blocked_slots: int
    mean_gross_pick_return: Optional[Decimal]   # media de selecciones ejecutadas, bruta, con dividendos declarados
    portfolio_net_return: Decimal               # (patrimonio_fin - patrimonio_ini)/patrimonio_ini


def basket_report(week_id: str, slots: Sequence[Slot], *, equity_start: Decimal, equity_end: Decimal) -> BasketReport:
    """SIM-11: la media de las selecciones no es la rentabilidad de la cartera."""
    rets = [s.gross_pick_return for s in slots if s.gross_pick_return is not None]
    mean = (sum(rets, D(0)) / len(rets)) if rets else None
    return BasketReport(
        week_id=week_id,
        filled_slots=sum(1 for s in slots if s.status in ("filled", "exited", "exit_blocked")),
        empty_slots=sum(1 for s in slots if s.status == "empty"),
        failed_slots=sum(1 for s in slots if s.status == "entry_failed"),
        exit_blocked_slots=sum(1 for s in slots if s.status == "exit_blocked"),
        mean_gross_pick_return=mean,
        portfolio_net_return=(D(equity_end) - D(equity_start)) / D(equity_start),
    )
