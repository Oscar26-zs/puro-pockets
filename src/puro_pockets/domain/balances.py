"""Cálculos oficiales (secciones 9.1, 11.1, 11.2 y 11.4 de la constitución).

Los saldos salen de lo asignado por los ingresos repartidos (incluido el saldo inicial), más las
transferencias recibidas, menos las enviadas y los gastos (Hito 8). Lo anulado no llega aquí: el
almacén solo entrega movimientos vigentes (RN-53); las transferencias nunca se anulan (RN-43).
Con el cierre de mes (Hito 9), el disponible de un mes cerrado queda en la tabla de ajustes y el
invariante suma solo los meses abiertos. Nada se guarda: todo se deriva (principio 3.3).
`pocket_figures` es la única función que arma las cifras de una bolsa.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from enum import StrEnum

from puro_pockets.domain.months import Month
from puro_pockets.domain.pockets import Behavior, Pocket


class IncomeKind(StrEnum):
    BASE = "base"
    EXTRA = "extra"
    INITIAL_BALANCE = "saldo_inicial"


class BalanceKind(StrEnum):
    BALANCE = "saldo"  # acumulable (11.2)
    MONTH_AVAILABLE = "disponible_del_mes"  # consumo (11.1)


@dataclass(frozen=True)
class AllocationEntry:
    """Lo asignado a una bolsa por un ingreso repartido y vigente."""

    pocket_id: int
    budget_month: Month
    amount: int
    income_kind: IncomeKind = IncomeKind.BASE


@dataclass(frozen=True)
class ExpenseEntry:
    """Un gasto vigente, en colones, en el mes calendario de su fecha (RN-32)."""

    pocket_id: int
    month: Month
    amount: int


@dataclass(frozen=True)
class TransferEntry:
    """Una transferencia entre bolsas, en colones, en el mes presupuestario de su fecha (RN-40).
    Las transferencias no se anulan (RN-43): todas cuentan."""

    from_pocket_id: int
    to_pocket_id: int
    month: Month
    amount: int


@dataclass(frozen=True)
class PocketBalance:
    pocket: Pocket
    balance: int
    kind: BalanceKind


def assigned(entries: Iterable[AllocationEntry], pocket_id: int, month: Month) -> int:
    """Σ lo asignado a la bolsa por los ingresos del mes presupuestario (11.1)."""
    return sum(e.amount for e in entries if e.pocket_id == pocket_id and e.budget_month == month)


def spent(expenses: Iterable[ExpenseEntry], pocket_id: int, month: Month) -> int:
    """Σ gastos del mes de la bolsa."""
    return sum(e.amount for e in expenses if e.pocket_id == pocket_id and e.month == month)


def received(transfers: Iterable[TransferEntry], pocket_id: int, month: Month | None) -> int:
    """Σ transferencias recibidas por la bolsa (en el mes indicado, o en todo el historial)."""
    return sum(
        t.amount
        for t in transfers
        if t.to_pocket_id == pocket_id and (month is None or t.month == month)
    )


def sent(transfers: Iterable[TransferEntry], pocket_id: int, month: Month | None) -> int:
    """Σ transferencias enviadas por la bolsa (en el mes indicado, o en todo el historial)."""
    return sum(
        t.amount
        for t in transfers
        if t.from_pocket_id == pocket_id and (month is None or t.month == month)
    )


def consumption_available(
    entries: Iterable[AllocationEntry],
    pocket_id: int,
    month: Month,
    expenses: Iterable[ExpenseEntry] = (),
    transfers: Sequence[TransferEntry] = (),
) -> int:
    """Disponible de una bolsa de consumo en un mes (11.1, 9.1): presupuesto ajustado − gastado,
    con presupuesto ajustado = asignado + recibidas del mes − enviadas del mes. Empieza en cero cada
    mes (RN-11)."""
    return (
        assigned(entries, pocket_id, month)
        + received(transfers, pocket_id, month)
        - sent(transfers, pocket_id, month)
        - spent(expenses, pocket_id, month)
    )


def accumulated_balance(
    entries: Iterable[AllocationEntry],
    pocket_id: int,
    expenses: Iterable[ExpenseEntry] = (),
    transfers: Sequence[TransferEntry] = (),
) -> int:
    """Saldo de una bolsa acumulable (11.2, RN-12): todo lo asignado + recibidas − enviadas − todo
    lo gastado."""
    return (
        sum(e.amount for e in entries if e.pocket_id == pocket_id)
        + received(transfers, pocket_id, None)
        - sent(transfers, pocket_id, None)
        - sum(e.amount for e in expenses if e.pocket_id == pocket_id)
    )


def percent_used(spent_amount: int, budget: int) -> int | None:
    """% usado (11.1) como entero hacia abajo; None si el presupuesto es 0 o negativo."""
    if budget <= 0:
        return None
    return spent_amount * 100 // budget


@dataclass(frozen=True)
class PocketFigures:
    """Las cifras oficiales de una bolsa en un mes (9.1, 11.1 y 11.2), de una sola función.

    `assigned` es el presupuesto original del mes; `adjusted_budget` = asignado + recibidas −
    enviadas del mes. Consumo: `available` (disponible del mes) y el % usado sobre el ajustado,
    con el % sobre el original como referencia. Acumulable: `balance` (saldo histórico, que ya
    incluye todas las transferencias).
    """

    pocket: Pocket
    month: Month
    assigned: int
    transfers_in: int
    transfers_out: int
    adjusted_budget: int
    spent: int
    available: int | None
    balance: int | None
    percent_used: int | None
    percent_used_original: int | None

    @property
    def amount(self) -> int:
        """Lo que la bolsa tiene: saldo (acumulable) o disponible del mes (consumo)."""
        if self.balance is not None:
            return self.balance
        return self.available or 0

    @property
    def kind(self) -> BalanceKind:
        if self.balance is not None:
            return BalanceKind.BALANCE
        return BalanceKind.MONTH_AVAILABLE

    @property
    def negative(self) -> bool:
        return self.amount < 0


def pocket_figures(
    pocket: Pocket,
    month: Month,
    entries: Sequence[AllocationEntry],
    expenses: Sequence[ExpenseEntry] = (),
    transfers: Sequence[TransferEntry] = (),
) -> PocketFigures:
    """Única función que calcula presupuesto original, transferencias, ajustado, gastado y
    disponible o saldo. `get_bolsa_status`, `get_summary`, `get_allocation_context`, las vistas
    previas y las validaciones (RN-18, RN-37, RN-42) la usan; nadie repite estos cálculos."""
    got = assigned(entries, pocket.id, month)
    incoming = received(transfers, pocket.id, month)
    outgoing = sent(transfers, pocket.id, month)
    adjusted = got + incoming - outgoing
    used = spent(expenses, pocket.id, month)
    if pocket.behavior is Behavior.ACUMULABLE:
        balance = accumulated_balance(entries, pocket.id, expenses, transfers)
        return PocketFigures(
            pocket, month, got, incoming, outgoing, adjusted, used, None, balance, None, None
        )
    return PocketFigures(
        pocket,
        month,
        got,
        incoming,
        outgoing,
        adjusted,
        used,
        adjusted - used,
        None,
        percent_used(used, adjusted),
        percent_used(used, got),
    )


def pocket_balance(
    pocket: Pocket,
    entries: Sequence[AllocationEntry],
    month: Month,
    expenses: Sequence[ExpenseEntry] = (),
    transfers: Sequence[TransferEntry] = (),
) -> PocketBalance:
    """Acumulable: saldo histórico; consumo: disponible del mes indicado."""
    figures = pocket_figures(pocket, month, entries, expenses, transfers)
    return PocketBalance(pocket, figures.amount, figures.kind)


def month_income_total(entries: Iterable[AllocationEntry], month: Month) -> int:
    """Ingresos del mes para estadísticas: el saldo inicial no cuenta (RN-54)."""
    return sum(
        e.amount
        for e in entries
        if e.budget_month == month and e.income_kind is not IncomeKind.INITIAL_BALANCE
    )


def integrity_gap(
    distributed_income_total: int,
    expense_total: int,
    pockets: Iterable[Pocket],
    entries: Sequence[AllocationEntry],
    expenses: Sequence[ExpenseEntry] = (),
    transfers: Sequence[TransferEntry] = (),
    is_month_closed: Callable[[Month], bool] = lambda _month: False,
    adjustment_total: int = 0,
) -> int:
    """Invariante 11.4. Devuelve 0 si cuadra.

    Σ ingresos repartidos (incluye el saldo inicial) − Σ gastos
      = Σ saldos de acumulables + Σ disponibles de consumo de los meses abiertos
      + Σ ajustes de cierre (sobrante no destinado suma; sobregasto no cubierto resta)

    `is_month_closed` es `domain.closures.is_closed` aplicada a los cierres guardados (Hito 9).

    Las transferencias no aparecen a la izquierda: no crean ni destruyen dinero, solo lo mueven
    entre bolsas del lado derecho.
    """
    right = 0
    for pocket in pockets:
        if pocket.behavior is Behavior.ACUMULABLE:
            right += accumulated_balance(entries, pocket.id, expenses, transfers)
        else:
            months = (
                {e.budget_month for e in entries if e.pocket_id == pocket.id}
                | {e.month for e in expenses if e.pocket_id == pocket.id}
                | {t.month for t in transfers if pocket.id in (t.from_pocket_id, t.to_pocket_id)}
            )
            right += sum(
                consumption_available(entries, pocket.id, m, expenses, transfers)
                for m in months
                if not is_month_closed(m)
            )
    return (distributed_income_total - expense_total) - (right + adjustment_total)
