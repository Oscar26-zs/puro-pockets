"""Metas de ahorro (sección 7; RN-19 a RN-25, RN-28, RN-29).

Una meta no tiene dinero propio (RN-23, RN-25): su avance es el saldo de su bolsa acumulable,
calculado con `accumulated_balance` (11.2), la misma función que usan `get_bolsa_status` y
`list_bolsas`. Crear o cambiar una meta no mueve ningún saldo.

`reached` es el único lugar que decide cuándo una meta activa pasa a `lograda` (RN-24): la llaman
los almacenes dentro de la transacción de cada operación que cambia el saldo de una bolsa. Una meta
lograda queda así aunque el saldo baje después.

Referencia pública: `M-<n>`. Los errores no incluyen montos ni nombres de metas.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from datetime import date
from enum import StrEnum

from puro_pockets.domain.balances import AllocationEntry, ExpenseEntry, accumulated_balance
from puro_pockets.domain.errors import DomainError
from puro_pockets.domain.money import MAX_MONEY
from puro_pockets.domain.months import Month
from puro_pockets.domain.pockets import is_plain_int

MAX_NAME = 60
PROJECTION_MONTHS = 3  # RN-28: últimos 3 meses calendario completos
_REF = re.compile(r"^\s*[Mm]\s*-\s*([0-9]{1,18})\s*$")


class GoalStatus(StrEnum):
    ACTIVE = "activa"
    ACHIEVED = "lograda"
    PAUSED = "pausada"


@dataclass(frozen=True)
class GoalRef:
    number: int

    @classmethod
    def parse(cls, text: object) -> GoalRef:
        found = _REF.match(text) if isinstance(text, str) else None
        if found is None or int(found.group(1)) < 1:
            raise DomainError(
                "La meta se indica por su referencia M-n; consúltala con get_goal_progress."
            )
        return cls(int(found.group(1)))

    def __str__(self) -> str:
        return f"M-{self.number}"


@dataclass(frozen=True)
class Goal:
    id: int  # interno; se muestra solo como M-<id>
    pocket_id: int
    name: str
    target_amount: int  # colones
    target_date: date | None
    status: GoalStatus
    achieved_on: date | None
    created_on: date
    archived: bool = False  # se archivó junto con su bolsa (sección 6.4)

    @property
    def reference(self) -> str:
        return str(GoalRef(self.id))

    @property
    def live(self) -> bool:
        """Activa y no archivada: la única que se evalúa y la que ocupa el cupo de su bolsa."""
        return self.status is GoalStatus.ACTIVE and not self.archived


def validate_goal_name(value: object) -> str:
    text = value.strip() if isinstance(value, str) else ""
    if not 1 <= len(text) <= MAX_NAME:
        raise DomainError(f"El nombre de la meta es obligatorio, hasta {MAX_NAME} caracteres.")
    return text


def validate_target_amount(value: object) -> int:
    """RN-19: monto objetivo en colones, entero positivo (sin decimales)."""
    if isinstance(value, float) or not is_plain_int(value):
        raise DomainError("El monto objetivo es en colones: un entero positivo, sin decimales.")
    if not 0 < value <= MAX_MONEY:  # type: ignore[operator]
        raise DomainError("El monto objetivo debe ser mayor que 0.")
    return int(value)  # type: ignore[call-overload]


def validate_target_date(value: date | None, today: date) -> date | None:
    """RN-20: opcional; si se indica, no puede estar en el pasado."""
    if value is not None and value < today:
        raise DomainError("La fecha objetivo no puede estar en el pasado.")
    return value


def reached(
    goals: Iterable[Goal], balance_of: Callable[[int], int], on: date
) -> list[tuple[int, date]]:
    """RN-24: metas vivas cuyo saldo ya alcanza el objetivo → (id, fecha de logro).

    La fecha es la del movimiento que lo cruzó (`on`), nunca anterior a la creación de la meta.
    """
    return [
        (goal.id, max(on, goal.created_on))
        for goal in goals
        if goal.live and balance_of(goal.pocket_id) >= goal.target_amount
    ]


def balance_function(
    entries: Sequence[AllocationEntry], expenses: Sequence[ExpenseEntry]
) -> Callable[[int], int]:
    """Saldo de una bolsa acumulable con la función oficial (11.2)."""
    return lambda pocket_id: accumulated_balance(entries, pocket_id, expenses)


@dataclass(frozen=True)
class Progress:
    balance: int
    percent: int  # tope 100, hacia abajo
    missing: int


def progress(goal: Goal, balance: int) -> Progress:
    """11.3: avance = saldo; falta = max(0, objetivo − avance); % con tope de 100."""
    percent = max(0, min(100, balance * 100 // goal.target_amount))
    return Progress(balance, percent, max(0, goal.target_amount - balance))


@dataclass(frozen=True)
class NetChange:
    months: int  # meses completos considerados (0 a 3)
    average: int | None  # promedio mensual de la variación neta; None sin meses
    projectable: bool  # RN-28: hay al menos un mes y el promedio es positivo


def net_monthly_change(
    entries: Sequence[AllocationEntry],
    expenses: Sequence[ExpenseEntry],
    pocket_id: int,
    current: Month,
) -> NetChange:
    """RN-28: promedio de la variación neta del saldo en los últimos 3 meses completos.

    Variación de un mes = asignado con ese mes presupuestario − gastado ese mes calendario (las
    mismas atribuciones que 11.1). Solo cuentan meses completos (anteriores al actual) desde el
    primero con movimientos de la bolsa. La app entrega los números; la proyección la hace Claude.
    """
    months = [e.budget_month for e in entries if e.pocket_id == pocket_id] + [
        e.month for e in expenses if e.pocket_id == pocket_id
    ]
    if not months:
        return NetChange(0, None, False)
    first = min(months)
    window = []
    month = current.previous()
    while month >= first and len(window) < PROJECTION_MONTHS:
        window.append(month)
        month = month.previous()
    if not window:
        return NetChange(0, None, False)
    total = sum(
        sum(e.amount for e in entries if e.pocket_id == pocket_id and e.budget_month == m)
        - sum(e.amount for e in expenses if e.pocket_id == pocket_id and e.month == m)
        for m in window
    )
    average = total // len(window)
    return NetChange(len(window), average, average > 0)
