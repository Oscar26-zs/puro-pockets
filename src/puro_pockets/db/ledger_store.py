"""Almacén SQL de movimientos: salario, gastos, anulación, categorías y clave de operación (Hito 5);
extras pendientes y su reparto, gastos fijos y sus pagos (Hito 6).

Cada escritura guarda el cambio y su clave de operación en una sola transacción (principio 3.6). Si
otra llamada simultánea guardó la misma clave primero, la PK de `idempotency_keys` lo detecta: se
revierte todo y se lanza `OperationTaken` para que el servicio devuelva el resultado guardado.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import datetime

from sqlalchemy import Connection, func, insert, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError

from puro_pockets.db.budget_store import (
    LIVE_EXPENSE,
    SqlBudgetStore,
    categories,
    constraint_name,
    expenses,
    idempotency_keys,
    income_allocations,
    incomes,
    insert_lines,
    recurring_expense_amounts,
    recurring_expenses,
)
from puro_pockets.domain.balances import IncomeKind
from puro_pockets.domain.categories import Category
from puro_pockets.domain.errors import (
    AlreadyVoided,
    CategoryAlreadyExists,
    ExtraAlreadyDistributed,
    MovementNotFound,
    MovementVoided,
    RecurringAlreadyPaid,
    RecurringNameTaken,
)
from puro_pockets.domain.ledger import MovementKind, MovementRef
from puro_pockets.domain.money import Currency
from puro_pockets.domain.months import Month
from puro_pockets.domain.recurring import RecurringRef, RecurringTemplate
from puro_pockets.services.budget import AllocationLine
from puro_pockets.services.records import (
    ExpenseRow,
    IncomeRow,
    NewExpense,
    NewIncome,
    NewRecurring,
    Operation,
    OperationTaken,
    RecurringChange,
    StoredOperation,
)

OPERATION_PK = "idempotency_keys_pkey"
CATEGORY_NAME_INDEX = "ux_categories_name_ci"
PAYMENT_INDEX = "ux_expenses_recurring_month"
RECURRING_NAME_INDEX = "ux_recurring_expenses_name_active"


def _income_row(r) -> IncomeRow:
    return IncomeRow(
        r.id,
        IncomeKind(r.kind),
        r.income_date,
        Month.parse(r.budget_month),
        Currency(r.currency),
        r.original_amount,
        r.exchange_rate,
        r.amount,
        r.voided,
        r.void_reason,
        r.allocation_status == "pendiente",
        r.source,
    )


def _expense_row(r) -> ExpenseRow:
    return ExpenseRow(
        r.id,
        r.expense_date,
        Month.parse(r.month),
        r.pocket_id,
        r.category_id,
        r.description,
        Currency(r.currency),
        r.original_amount,
        r.exchange_rate,
        r.amount,
        r.voided,
        r.void_reason,
        r.recurring_id,
    )


INCOME_COLUMNS = (
    incomes.c.id,
    incomes.c.kind,
    incomes.c.income_date,
    incomes.c.budget_month,
    incomes.c.currency,
    incomes.c.original_amount,
    incomes.c.exchange_rate,
    incomes.c.amount,
    incomes.c.voided,
    incomes.c.void_reason,
    incomes.c.allocation_status,
    incomes.c.source,
)
EXPENSE_COLUMNS = (
    expenses.c.id,
    expenses.c.expense_date,
    expenses.c.month,
    expenses.c.pocket_id,
    expenses.c.category_id,
    expenses.c.description,
    expenses.c.currency,
    expenses.c.original_amount,
    expenses.c.exchange_rate,
    expenses.c.amount,
    expenses.c.voided,
    expenses.c.void_reason,
    expenses.c.recurring_id,
)
LIVE_EXTRA = (incomes.c.kind == IncomeKind.EXTRA.value) & incomes.c.voided.is_(False)


class SqlLedgerStore(SqlBudgetStore):
    # --- Idempotencia ---

    def get_operation(self, operation_id: str) -> StoredOperation | None:
        with self._engine.connect() as conn:
            row = conn.execute(
                select(
                    idempotency_keys.c.tool,
                    idempotency_keys.c.fingerprint,
                    idempotency_keys.c.response,
                ).where(idempotency_keys.c.operation_id == operation_id)
            ).first()
        return None if row is None else StoredOperation(row.tool, row.fingerprint, row.response)

    def _write(self, operation: Operation, work: Callable[[Connection], dict]) -> dict:
        """Ejecuta `work` y guarda la clave con su respuesta, todo en una transacción."""
        try:
            with self._engine.begin() as conn:
                response = work(conn)
                conn.execute(
                    insert(idempotency_keys).values(
                        operation_id=operation.operation_id,
                        tool=operation.tool,
                        fingerprint=operation.fingerprint,
                        response=response,
                    )
                )
        except IntegrityError as exc:
            if constraint_name(exc) == OPERATION_PK:
                raise OperationTaken() from None
            raise
        return response

    # --- Ingresos ---

    def record_income(
        self,
        income: NewIncome,
        lines: Sequence[AllocationLine],
        operation: Operation,
        respond: Callable[[int], dict],
    ) -> dict:
        def work(conn: Connection) -> dict:
            money = income.money
            income_id = conn.execute(
                insert(incomes)
                .values(
                    income_date=income.income_date,
                    kind=income.kind.value,
                    budget_month=str(income.budget_month),
                    amount=money.amount_crc,
                    currency=money.currency.value,
                    original_amount=money.original_amount,
                    exchange_rate=money.exchange_rate,
                    allocation_status="pendiente" if income.pending else "repartido",
                    source=income.source,
                )
                .returning(incomes.c.id)
            ).scalar_one()
            if lines:
                insert_lines(conn, income_id, lines)
            return respond(income_id)

        return self._write(operation, work)

    def distribute_extra(
        self,
        income_id: int,
        lines: Sequence[AllocationLine],
        operation: Operation,
        respond: Callable[[], dict],
    ) -> dict:
        ref = str(MovementRef(MovementKind.INCOME, income_id))

        def work(conn: Connection) -> dict:
            # Pasa de pendiente a repartido una sola vez: dos confirmaciones simultáneas con claves
            # distintas no reparten dos veces (la segunda ya no encuentra la fila pendiente)
            changed = conn.execute(
                update(incomes)
                .where(
                    (incomes.c.id == income_id)
                    & (incomes.c.kind == IncomeKind.EXTRA.value)
                    & (incomes.c.allocation_status == "pendiente")
                    & incomes.c.voided.is_(False)
                )
                .values(allocation_status="repartido")
            ).rowcount
            if changed == 0:
                voided = conn.execute(
                    select(incomes.c.voided).where(incomes.c.id == income_id)
                ).scalar()
                raise MovementVoided(ref) if voided else ExtraAlreadyDistributed(ref)
            insert_lines(conn, income_id, lines)
            return respond()

        return self._write(operation, work)

    # --- Gastos y anulación ---

    def record_expense(
        self, expense: NewExpense, operation: Operation, respond: Callable[[int], dict]
    ) -> dict:
        def work(conn: Connection) -> dict:
            money = expense.money
            expense_id = conn.execute(
                insert(expenses)
                .values(
                    expense_date=expense.expense_date,
                    month=str(expense.month),
                    pocket_id=expense.pocket_id,
                    category_id=expense.category_id,
                    description=expense.description,
                    currency=money.currency.value,
                    original_amount=money.original_amount,
                    exchange_rate=money.exchange_rate,
                    amount=money.amount_crc,
                    recurring_id=expense.recurring_id,
                )
                .returning(expenses.c.id)
            ).scalar_one()
            return respond(expense_id)

        try:
            return self._write(operation, work)
        except IntegrityError as exc:
            if constraint_name(exc) == PAYMENT_INDEX and expense.recurring_id is not None:
                raise RecurringAlreadyPaid(
                    str(RecurringRef(expense.recurring_id)), str(expense.month)
                ) from None
            raise

    def void_movement(
        self,
        ref: MovementRef,
        reason: str,
        voided_at: datetime,
        operation: Operation,
        response: dict,
    ) -> None:
        table = incomes if ref.kind is MovementKind.INCOME else expenses

        def work(conn: Connection) -> dict:
            changed = conn.execute(
                update(table)
                .where((table.c.id == ref.number) & table.c.voided.is_(False))
                .values(voided=True, voided_at=voided_at, void_reason=reason)
            ).rowcount
            if changed == 0:
                exists = conn.execute(select(table.c.id).where(table.c.id == ref.number)).first()
                raise AlreadyVoided(str(ref)) if exists else MovementNotFound(str(ref))
            return response

        self._write(operation, work)

    # --- Categorías ---

    def list_categories(self) -> list[Category]:
        with self._engine.connect() as conn:
            rows = conn.execute(
                select(
                    categories.c.id, categories.c.name, categories.c.pocket_id, categories.c.active
                ).order_by(categories.c.id)
            ).all()
        return [Category(r.id, r.name, r.pocket_id, r.active) for r in rows]

    def create_category(self, name: str, pocket_id: int) -> Category:
        try:
            with self._engine.begin() as conn:
                category_id = conn.execute(
                    insert(categories)
                    .values(name=name, pocket_id=pocket_id)
                    .returning(categories.c.id)
                ).scalar_one()
        except IntegrityError as exc:
            if constraint_name(exc) == CATEGORY_NAME_INDEX:
                raise CategoryAlreadyExists(name) from None
            raise
        return Category(category_id, name, pocket_id)

    # --- Lecturas ---

    def get_income(self, income_id: int) -> IncomeRow | None:
        with self._engine.connect() as conn:
            row = conn.execute(select(*INCOME_COLUMNS).where(incomes.c.id == income_id)).first()
        return None if row is None else _income_row(row)

    def get_expense(self, expense_id: int) -> ExpenseRow | None:
        with self._engine.connect() as conn:
            row = conn.execute(select(*EXPENSE_COLUMNS).where(expenses.c.id == expense_id)).first()
        return None if row is None else _expense_row(row)

    def income_lines(self, income_id: int) -> list[AllocationLine]:
        with self._engine.connect() as conn:
            rows = conn.execute(
                select(
                    income_allocations.c.pocket_id,
                    income_allocations.c.percentage,
                    income_allocations.c.amount,
                )
                .where(income_allocations.c.income_id == income_id)
                .order_by(income_allocations.c.pocket_id)
            ).all()
        return [AllocationLine(r.pocket_id, r.percentage, r.amount) for r in rows]

    def recent_incomes(
        self, month: Month | None, include_voided: bool, limit: int
    ) -> list[IncomeRow]:
        query = select(*INCOME_COLUMNS)
        if month is not None:
            query = query.where(incomes.c.budget_month == str(month))
        if not include_voided:
            query = query.where(incomes.c.voided.is_(False))
        query = query.order_by(incomes.c.income_date.desc(), incomes.c.id.desc()).limit(limit)
        with self._engine.connect() as conn:
            return [_income_row(r) for r in conn.execute(query).all()]

    def recent_expenses(
        self, month: Month | None, pocket_id: int | None, include_voided: bool, limit: int
    ) -> list[ExpenseRow]:
        query = select(*EXPENSE_COLUMNS)
        if month is not None:
            query = query.where(expenses.c.month == str(month))
        if pocket_id is not None:
            query = query.where(expenses.c.pocket_id == pocket_id)
        if not include_voided:
            query = query.where(LIVE_EXPENSE)
        query = query.order_by(expenses.c.expense_date.desc(), expenses.c.id.desc()).limit(limit)
        with self._engine.connect() as conn:
            return [_expense_row(r) for r in conn.execute(query).all()]

    def expenses_in_month(self, month: Month) -> list[ExpenseRow]:
        with self._engine.connect() as conn:
            rows = conn.execute(
                select(*EXPENSE_COLUMNS).where((expenses.c.month == str(month)) & LIVE_EXPENSE)
            ).all()
        return [_expense_row(r) for r in rows]

    def base_income_total(self, month: Month) -> int:
        with self._engine.connect() as conn:
            return int(
                conn.execute(
                    select(func.coalesce(func.sum(incomes.c.amount), 0)).where(
                        (incomes.c.kind == IncomeKind.BASE.value)
                        & (incomes.c.budget_month == str(month))
                        & incomes.c.voided.is_(False)
                    )
                ).scalar_one()
            )

    def extra_income_total(self, month: Month) -> int:
        with self._engine.connect() as conn:
            return int(
                conn.execute(
                    select(func.coalesce(func.sum(incomes.c.amount), 0)).where(
                        LIVE_EXTRA
                        & (incomes.c.allocation_status == "repartido")
                        & (incomes.c.budget_month == str(month))
                    )
                ).scalar_one()
            )

    def pending_extras(self) -> list[IncomeRow]:
        query = (
            select(*INCOME_COLUMNS)
            .where(LIVE_EXTRA & (incomes.c.allocation_status == "pendiente"))
            .order_by(incomes.c.id)
        )
        with self._engine.connect() as conn:
            return [_income_row(r) for r in conn.execute(query).all()]

    def distributed_extras(self, limit: int) -> list[IncomeRow]:
        query = (
            select(*INCOME_COLUMNS)
            .where(LIVE_EXTRA & (incomes.c.allocation_status == "repartido"))
            .order_by(incomes.c.income_date.desc(), incomes.c.id.desc())
            .limit(limit)
        )
        with self._engine.connect() as conn:
            return [_income_row(r) for r in conn.execute(query).all()]

    # --- Gastos fijos (Hito 6) ---

    def list_recurring(self) -> list[RecurringTemplate]:
        with self._engine.connect() as conn:
            rows = conn.execute(select(recurring_expenses).order_by(recurring_expenses.c.id)).all()
            amounts: dict[int, list[tuple[Month, int]]] = {}
            for a in conn.execute(
                select(recurring_expense_amounts).order_by(
                    recurring_expense_amounts.c.recurring_id,
                    recurring_expense_amounts.c.from_month,
                )
            ).all():
                amounts.setdefault(a.recurring_id, []).append(
                    (Month.parse(a.from_month), a.original_amount)
                )
        return [
            RecurringTemplate(
                r.id,
                r.name,
                Currency(r.currency),
                r.day_of_month,
                r.pocket_id,
                r.category_id,
                Month.parse(r.start_month),
                r.active,
                tuple(amounts.get(r.id, ())),
            )
            for r in rows
        ]

    def _recurring_write(self, operation: Operation, work: Callable[[Connection], dict]) -> dict:
        try:
            return self._write(operation, work)
        except IntegrityError as exc:
            if constraint_name(exc) == RECURRING_NAME_INDEX:
                raise RecurringNameTaken() from None
            raise

    def create_recurring(
        self, new: NewRecurring, operation: Operation, respond: Callable[[int], dict]
    ) -> dict:
        def work(conn: Connection) -> dict:
            recurring_id = conn.execute(
                insert(recurring_expenses)
                .values(
                    name=new.name,
                    currency=new.currency.value,
                    day_of_month=new.day_of_month,
                    pocket_id=new.pocket_id,
                    category_id=new.category_id,
                    start_month=str(new.start_month),
                )
                .returning(recurring_expenses.c.id)
            ).scalar_one()
            conn.execute(
                insert(recurring_expense_amounts).values(
                    recurring_id=recurring_id,
                    from_month=str(new.start_month),
                    original_amount=new.original_amount,
                )
            )
            return respond(recurring_id)

        return self._recurring_write(operation, work)

    def update_recurring(
        self, change: RecurringChange, operation: Operation, respond: Callable[[], dict]
    ) -> dict:
        def work(conn: Connection) -> dict:
            values = {
                key: value
                for key, value in (
                    ("name", change.name),
                    ("day_of_month", change.day_of_month),
                    ("pocket_id", change.pocket_id),
                    ("category_id", change.category_id),
                )
                if value is not None
            }
            if values:
                conn.execute(
                    update(recurring_expenses)
                    .where(recurring_expenses.c.id == change.recurring_id)
                    .values(**values)
                )
            if change.amount is not None:
                since, amount = change.amount
                statement = pg_insert(recurring_expense_amounts).values(
                    recurring_id=change.recurring_id,
                    from_month=str(since),
                    original_amount=amount,
                )
                conn.execute(
                    statement.on_conflict_do_update(
                        index_elements=["recurring_id", "from_month"],
                        set_={"original_amount": statement.excluded.original_amount},
                    )
                )
            return respond()

        return self._recurring_write(operation, work)

    def deactivate_recurring(
        self,
        recurring_id: int,
        at: datetime,
        operation: Operation,
        respond: Callable[[], dict],
    ) -> dict:
        def work(conn: Connection) -> dict:
            conn.execute(
                update(recurring_expenses)
                .where((recurring_expenses.c.id == recurring_id) & recurring_expenses.c.active)
                .values(active=False, deactivated_at=at)
            )
            return respond()

        return self._write(operation, work)

    def recurring_payments(self, month: Month) -> dict[int, int]:
        with self._engine.connect() as conn:
            rows = conn.execute(
                select(expenses.c.recurring_id, expenses.c.id).where(
                    expenses.c.recurring_id.is_not(None)
                    & (expenses.c.month == str(month))
                    & LIVE_EXPENSE
                )
            ).all()
        return {r.recurring_id: r.id for r in rows}
