"""Cálculos oficiales (secciones 11.1, 11.2 y 11.4 de la constitución).

Los saldos salen de lo asignado por los ingresos repartidos (incluido el saldo inicial) menos los
gastos. Lo anulado no llega aquí: el almacén solo entrega movimientos vigentes (RN-53). Todavía no
hay transferencias (Hito 8) ni cierres (Hito 9): el presupuesto ajustado es igual al original y
todos los meses están abiertos. Nada se guarda: todo se deriva (principio 3.3).
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
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


def consumption_available(
    entries: Iterable[AllocationEntry],
    pocket_id: int,
    month: Month,
    expenses: Iterable[ExpenseEntry] = (),
) -> int:
    """Disponible de una bolsa de consumo en un mes (11.1): asignado − gastado. Empieza en cero cada
    mes (RN-11). Sin transferencias, el presupuesto ajustado es el asignado."""
    return assigned(entries, pocket_id, month) - spent(expenses, pocket_id, month)


def accumulated_balance(
    entries: Iterable[AllocationEntry], pocket_id: int, expenses: Iterable[ExpenseEntry] = ()
) -> int:
    """Saldo de una bolsa acumulable (11.2, RN-12): todo lo asignado menos todo lo gastado."""
    return sum(e.amount for e in entries if e.pocket_id == pocket_id) - sum(
        e.amount for e in expenses if e.pocket_id == pocket_id
    )


def pocket_balance(
    pocket: Pocket,
    entries: Sequence[AllocationEntry],
    month: Month,
    expenses: Sequence[ExpenseEntry] = (),
) -> PocketBalance:
    """Acumulable: saldo histórico; consumo: disponible del mes indicado."""
    if pocket.behavior is Behavior.ACUMULABLE:
        return PocketBalance(
            pocket, accumulated_balance(entries, pocket.id, expenses), BalanceKind.BALANCE
        )
    return PocketBalance(
        pocket,
        consumption_available(entries, pocket.id, month, expenses),
        BalanceKind.MONTH_AVAILABLE,
    )


def month_income_total(entries: Iterable[AllocationEntry], month: Month) -> int:
    """Ingresos del mes para estadísticas: el saldo inicial no cuenta (RN-54)."""
    return sum(
        e.amount
        for e in entries
        if e.budget_month == month and e.income_kind is not IncomeKind.INITIAL_BALANCE
    )


def percent_used(spent_amount: int, budget: int) -> int | None:
    """% usado (11.1) como entero hacia abajo; None si el presupuesto es 0 o negativo."""
    if budget <= 0:
        return None
    return spent_amount * 100 // budget


def integrity_gap(
    distributed_income_total: int,
    expense_total: int,
    pockets: Iterable[Pocket],
    entries: Sequence[AllocationEntry],
    expenses: Sequence[ExpenseEntry] = (),
) -> int:
    """Invariante 11.4. Devuelve 0 si cuadra.

    Σ ingresos repartidos (incluye el saldo inicial) − Σ gastos
      = Σ saldos de acumulables + Σ disponibles de consumo de los meses abiertos (todos, sin cierre)
      + Σ ajustes de cierre (aún no hay)
    """
    right = 0
    for pocket in pockets:
        if pocket.behavior is Behavior.ACUMULABLE:
            right += accumulated_balance(entries, pocket.id, expenses)
        else:
            months = {e.budget_month for e in entries if e.pocket_id == pocket.id} | {
                e.month for e in expenses if e.pocket_id == pocket.id
            }
            right += sum(consumption_available(entries, pocket.id, m, expenses) for m in months)
    return (distributed_income_total - expense_total) - right
