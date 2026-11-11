"""Almacén SQL de movimientos (Hito 5): salario, gastos, anulación, categorías y clave de operación.

Cada escritura guarda el movimiento y su clave de operación en una sola transacción (principio 3.6).
Si otra llamada simultánea guardó la misma clave primero, la PK de `idempotency_keys` lo detecta: se
revierte todo y se lanza `OperationTaken` para que el servicio devuelva el resultado guardado.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import datetime

from sqlalchemy import Connection, func, insert, select, update
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
)
from puro_pockets.domain.balances import IncomeKind
from puro_pockets.domain.categories import Category
from puro_pockets.domain.errors import AlreadyVoided, CategoryAlreadyExists, MovementNotFound
from puro_pockets.domain.ledger import MovementKind, MovementRef
from puro_pockets.domain.money import Currency
from puro_pockets.domain.months import Month
from puro_pockets.services.budget import AllocationLine
from puro_pockets.services.ledger import (
    ExpenseRow,
    IncomeRow,
    NewExpense,
    NewIncome,
    Operation,
    OperationTaken,
    StoredOperation,
)

OPERATION_PK = "idempotency_keys_pkey"
CATEGORY_NAME_INDEX = "ux_categories_name_ci"


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
)


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

    # --- Escrituras ---

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
                    allocation_status="repartido",
                )
                .returning(incomes.c.id)
            ).scalar_one()
            insert_lines(conn, income_id, lines)
            return respond(income_id)

        return self._write(operation, work)

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
                )
                .returning(expenses.c.id)
            ).scalar_one()
            return respond(expense_id)

        return self._write(operation, work)

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
