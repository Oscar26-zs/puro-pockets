"""Registros que intercambian el servicio de movimientos y su almacén (Hitos 5 y 6).

`services/ledger.py` los reexporta, así que los almacenes y las pruebas pueden importarlos desde
cualquiera de los dos módulos.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from typing import Protocol

from puro_pockets.domain.balances import IncomeKind
from puro_pockets.domain.categories import Category
from puro_pockets.domain.goals import Goal, GoalStatus
from puro_pockets.domain.ledger import MovementRef
from puro_pockets.domain.money import Converted, Currency
from puro_pockets.domain.months import Month
from puro_pockets.domain.pockets import Behavior
from puro_pockets.domain.recurring import RecurringTemplate
from puro_pockets.services.budget import AllocationLine, BudgetStore


@dataclass(frozen=True)
class Operation:
    operation_id: str
    tool: str
    fingerprint: str


@dataclass(frozen=True)
class StoredOperation:
    tool: str
    fingerprint: str
    response: dict


@dataclass(frozen=True)
class NewIncome:
    kind: IncomeKind
    income_date: date
    budget_month: Month
    money: Converted
    pending: bool = False  # extra recién registrado (RN-06): sin repartos
    source: str | None = None  # origen del extra (texto corto opcional)


@dataclass(frozen=True)
class NewExpense:
    expense_date: date
    month: Month
    pocket_id: int
    category_id: int | None
    description: str | None
    money: Converted
    recurring_id: int | None = None  # pago de un gasto fijo (Hito 6)


@dataclass(frozen=True)
class IncomeRow:
    id: int
    kind: IncomeKind
    income_date: date
    budget_month: Month
    currency: Currency
    original_amount: int
    exchange_rate: int | None
    amount: int
    voided: bool
    void_reason: str | None
    pending: bool = False
    source: str | None = None


@dataclass(frozen=True)
class ExpenseRow:
    id: int
    expense_date: date
    month: Month
    pocket_id: int
    category_id: int | None
    description: str | None
    currency: Currency
    original_amount: int
    exchange_rate: int | None
    amount: int
    voided: bool
    void_reason: str | None
    recurring_id: int | None = None


@dataclass(frozen=True)
class NewRecurring:
    name: str
    currency: Currency
    original_amount: int
    day_of_month: int
    pocket_id: int
    category_id: int | None
    start_month: Month


@dataclass(frozen=True)
class RecurringChange:
    """Cambios de una plantilla; None = sin cambio. El monto vale desde `amount[0]`."""

    recurring_id: int
    name: str | None = None
    amount: tuple[Month, int] | None = None
    day_of_month: int | None = None
    pocket_id: int | None = None
    category_id: int | None = None


@dataclass(frozen=True)
class NewPocket:
    name: str
    behavior: Behavior
    group: str | None
    month: Month  # mes desde el que aplican los porcentajes nuevos (RN-15)
    existing: dict[int, int]  # porcentajes nuevos de las bolsas existentes en ese mes
    share: int  # porcentaje de la bolsa nueva


@dataclass(frozen=True)
class NewGoal:
    pocket_id: int
    name: str
    target_amount: int
    target_date: date | None
    created_on: date


@dataclass(frozen=True)
class GoalChange:
    """Cambios de una meta; None = sin cambio."""

    goal_id: int
    target_amount: int | None = None
    target_date: date | None = None
    clear_target_date: bool = False
    status: GoalStatus | None = None


class OperationTaken(Exception):  # noqa: N818 - señal interna, no un error de negocio
    """Otra llamada simultánea guardó la misma clave de operación primero."""


class LedgerStore(BudgetStore, Protocol):
    """Almacén de movimientos. Las escrituras guardan el cambio y la clave en una transacción;
    si la clave ya existe (carrera), revierten y lanzan `OperationTaken`."""

    def list_categories(self) -> list[Category]: ...

    def create_category(self, name: str, pocket_id: int) -> Category: ...

    def get_operation(self, operation_id: str) -> StoredOperation | None: ...

    def record_income(
        self,
        income: NewIncome,
        lines: Sequence[AllocationLine],
        operation: Operation,
        respond: Callable[[int], dict],
    ) -> dict:
        """Ingreso y sus repartos. Un extra pendiente (`income.pending`) no lleva repartos. En la
        misma transacción evalúa las metas (RN-24) con la fecha del ingreso."""
        ...

    def distribute_extra(
        self,
        income_id: int,
        lines: Sequence[AllocationLine],
        operation: Operation,
        respond: Callable[[], dict],
        on: date | None = None,
    ) -> dict:
        """Pasa un extra de pendiente a repartido y guarda sus repartos, atómico, y evalúa las metas
        (RN-24) con la fecha `on`. Si ya no está pendiente (otra llamada lo repartió) lanza
        `ExtraAlreadyDistributed`; si está anulado, `MovementVoided`."""
        ...

    def record_expense(
        self, expense: NewExpense, operation: Operation, respond: Callable[[int], dict]
    ) -> dict:
        """Si es el pago de un fijo que ya tiene pago vigente en el mes: `RecurringAlreadyPaid`."""
        ...

    def void_movement(
        self,
        ref: MovementRef,
        reason: str,
        voided_at: datetime,
        operation: Operation,
        response: dict,
        on: date | None = None,
    ) -> None:
        """Marca la anulación solo si no estaba anulado; si ya lo estaba, `AlreadyVoided`. Anular
        un gasto sube un saldo: evalúa las metas (RN-24) con la fecha `on`."""
        ...

    def get_income(self, income_id: int) -> IncomeRow | None: ...

    def get_expense(self, expense_id: int) -> ExpenseRow | None: ...

    def income_lines(self, income_id: int) -> list[AllocationLine]: ...

    def recent_incomes(
        self, month: Month | None, include_voided: bool, limit: int
    ) -> list[IncomeRow]: ...

    def recent_expenses(
        self, month: Month | None, pocket_id: int | None, include_voided: bool, limit: int
    ) -> list[ExpenseRow]: ...

    def expenses_in_month(self, month: Month) -> list[ExpenseRow]:
        """Gastos vigentes del mes."""
        ...

    def base_income_total(self, month: Month) -> int:
        """Σ ingresos base vigentes del mes presupuestario (sin saldo inicial, RN-54)."""
        ...

    def extra_income_total(self, month: Month) -> int:
        """Σ extras repartidos y vigentes del mes presupuestario (los pendientes no cuentan)."""
        ...

    def pending_extras(self) -> list[IncomeRow]:
        """Extras vigentes en estado pendiente (RN-06), de cualquier mes."""
        ...

    def distributed_extras(self, limit: int) -> list[IncomeRow]:
        """Últimos extras repartidos y vigentes, los más recientes primero."""
        ...

    # --- Gastos fijos (Hito 6) ---

    def list_recurring(self) -> list[RecurringTemplate]: ...

    def create_recurring(
        self, new: NewRecurring, operation: Operation, respond: Callable[[int], dict]
    ) -> dict:
        """Si ya hay una plantilla activa con ese nombre: `RecurringNameTaken`."""
        ...

    def update_recurring(
        self, change: RecurringChange, operation: Operation, respond: Callable[[], dict]
    ) -> dict: ...

    def deactivate_recurring(
        self,
        recurring_id: int,
        at: datetime,
        operation: Operation,
        respond: Callable[[], dict],
    ) -> dict: ...

    def recurring_payments(self, month: Month) -> dict[int, int]:
        """{id de plantilla: id del gasto} de los pagos vigentes del mes."""
        ...

    # --- Bolsas flexibles y metas (Hito 7) ---

    def future_allocation_months(self, after: Month) -> list[Month]:
        """Meses posteriores a `after` con porcentajes propios."""
        ...

    def create_pocket(
        self, new: NewPocket, operation: Operation, respond: Callable[[int], dict]
    ) -> dict:
        """Crea la bolsa y escribe el conjunto completo de porcentajes del mes, atómico (RN-13).
        Nombre repetido sin distinguir mayúsculas: `PocketAlreadyExists`."""
        ...

    def archive_pocket(
        self,
        pocket_id: int,
        at: datetime,
        months: dict[Month, dict[int, int]],
        operation: Operation,
        respond: Callable[[], dict],
    ) -> dict:
        """Archiva la bolsa (RN-16), archiva sus metas y reescribe los porcentajes de cada mes
        indicado sin ella (RN-17), todo en una transacción."""
        ...

    def list_goals(self) -> list[Goal]: ...

    def create_goal(
        self, new: NewGoal, operation: Operation, respond: Callable[[int], dict], on: date
    ) -> dict:
        """Inserta la meta y la evalúa (RN-24). Otra activa en la bolsa: `GoalAlreadyActive`."""
        ...

    def update_goal(
        self, change: GoalChange, operation: Operation, respond: Callable[[], dict], on: date
    ) -> dict: ...
