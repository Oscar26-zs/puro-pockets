"""Cálculos oficiales del Hito 4 (secciones 11.1, 11.2 y 11.4 de la constitución).

Todavía no hay gastos, transferencias ni cierres: los saldos salen solo de lo asignado por los
ingresos repartidos (incluido el saldo inicial). Nada se guarda: todo se deriva (principio 3.3).
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
    """Lo asignado a una bolsa por un ingreso repartido."""

    pocket_id: int
    budget_month: Month
    amount: int
    income_kind: IncomeKind = IncomeKind.BASE


@dataclass(frozen=True)
class PocketBalance:
    pocket: Pocket
    balance: int
    kind: BalanceKind


def assigned(entries: Iterable[AllocationEntry], pocket_id: int, month: Month) -> int:
    """Σ lo asignado a la bolsa por los ingresos del mes presupuestario (11.1)."""
    return sum(e.amount for e in entries if e.pocket_id == pocket_id and e.budget_month == month)


def consumption_available(entries: Iterable[AllocationEntry], pocket_id: int, month: Month) -> int:
    """Disponible de una bolsa de consumo en un mes (11.1). Empieza en cero cada mes (RN-11)."""
    return assigned(entries, pocket_id, month)


def accumulated_balance(entries: Iterable[AllocationEntry], pocket_id: int) -> int:
    """Saldo de una bolsa acumulable: todo lo asignado, de todos los meses (11.2, RN-12)."""
    return sum(e.amount for e in entries if e.pocket_id == pocket_id)


def pocket_balance(
    pocket: Pocket, entries: Sequence[AllocationEntry], current: Month
) -> PocketBalance:
    if pocket.behavior is Behavior.ACUMULABLE:
        return PocketBalance(pocket, accumulated_balance(entries, pocket.id), BalanceKind.BALANCE)
    return PocketBalance(
        pocket, consumption_available(entries, pocket.id, current), BalanceKind.MONTH_AVAILABLE
    )


def month_income_total(entries: Iterable[AllocationEntry], month: Month) -> int:
    """Ingresos del mes para estadísticas: el saldo inicial no cuenta (RN-54)."""
    return sum(
        e.amount
        for e in entries
        if e.budget_month == month and e.income_kind is not IncomeKind.INITIAL_BALANCE
    )


def integrity_gap(
    distributed_income_total: int, pockets: Iterable[Pocket], entries: Sequence[AllocationEntry]
) -> int:
    """Invariante 11.4. Devuelve 0 si cuadra.

    Σ ingresos repartidos (incluye el saldo inicial) − Σ gastos (aún no hay)
      = Σ saldos de acumulables + Σ disponibles de consumo de los meses abiertos (todos, sin cierre)
      + Σ ajustes de cierre (aún no hay)
    """
    right = 0
    for pocket in pockets:
        if pocket.behavior is Behavior.ACUMULABLE:
            right += accumulated_balance(entries, pocket.id)
        else:
            months = {e.budget_month for e in entries if e.pocket_id == pocket.id}
            right += sum(consumption_available(entries, pocket.id, m) for m in months)
    return distributed_income_total - right
