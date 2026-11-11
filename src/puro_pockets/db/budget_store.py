"""Almacén SQL del presupuesto (SQLAlchemy Core). Tablas de las migraciones 0003 a 0006.

Las lecturas de movimientos ignoran lo anulado (RN-53). Las escrituras del Hito 5 (ingresos base,
gastos, anulaciones) están en `ledger_store.py`.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date

from sqlalchemy import (
    CHAR,
    BigInteger,
    Boolean,
    Column,
    Connection,
    Date,
    DateTime,
    Engine,
    Integer,
    MetaData,
    Table,
    Text,
    delete,
    func,
    insert,
    select,
    update,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.exc import IntegrityError

from puro_pockets.domain.balances import AllocationEntry, ExpenseEntry, IncomeKind
from puro_pockets.domain.errors import InitialBalanceAlreadyLoaded
from puro_pockets.domain.goals import Goal, GoalStatus, balance_function, reached
from puro_pockets.domain.money import Currency
from puro_pockets.domain.months import Month
from puro_pockets.domain.pockets import Behavior, Pocket
from puro_pockets.services.budget import AllocationLine

metadata = MetaData()

pockets = Table(
    "pockets",
    metadata,
    Column("id", BigInteger, primary_key=True),
    Column("name", Text, nullable=False),
    Column("behavior", Text, nullable=False),
    Column("group_name", Text),
    Column("surplus_target_pocket_id", BigInteger),
    Column("active", Boolean, nullable=False),
    Column("archived_at", DateTime(timezone=True)),
)

savings_goals = Table(
    "savings_goals",
    metadata,
    Column("id", BigInteger, primary_key=True),
    Column("pocket_id", BigInteger, nullable=False),
    Column("name", Text, nullable=False),
    Column("target_amount", BigInteger, nullable=False),
    Column("target_date", Date),
    Column("status", Text, nullable=False),
    Column("achieved_on", Date),
    Column("created_on", Date, nullable=False),
    Column("archived_at", DateTime(timezone=True)),
)

categories = Table(
    "categories",
    metadata,
    Column("id", BigInteger, primary_key=True),
    Column("name", Text, nullable=False),
    Column("pocket_id", BigInteger, nullable=False),
    Column("active", Boolean, nullable=False),
)

budget_month_allocations = Table(
    "budget_month_allocations",
    metadata,
    Column("month", CHAR(7), primary_key=True),
    Column("pocket_id", BigInteger, primary_key=True),
    Column("percentage", Integer, nullable=False),
)

incomes = Table(
    "incomes",
    metadata,
    Column("id", BigInteger, primary_key=True),
    Column("income_date", Date, nullable=False),
    Column("kind", Text, nullable=False),
    Column("source", Text),
    Column("budget_month", CHAR(7), nullable=False),
    Column("amount", BigInteger, nullable=False),
    Column("allocation_status", Text, nullable=False),
    Column("note", Text),
    Column("currency", Text, nullable=False),
    Column("original_amount", BigInteger, nullable=False),
    Column("exchange_rate", BigInteger),
    Column("voided", Boolean, nullable=False),
    Column("voided_at", DateTime(timezone=True)),
    Column("void_reason", Text),
)

income_allocations = Table(
    "income_allocations",
    metadata,
    Column("id", BigInteger, primary_key=True),
    Column("income_id", BigInteger, nullable=False),
    Column("pocket_id", BigInteger, nullable=False),
    Column("percentage", Integer),
    Column("amount", BigInteger, nullable=False),
)

expenses = Table(
    "expenses",
    metadata,
    Column("id", BigInteger, primary_key=True),
    Column("expense_date", Date, nullable=False),
    Column("month", CHAR(7), nullable=False),
    Column("pocket_id", BigInteger, nullable=False),
    Column("category_id", BigInteger),
    Column("description", Text),
    Column("currency", Text, nullable=False),
    Column("original_amount", BigInteger, nullable=False),
    Column("exchange_rate", BigInteger),
    Column("amount", BigInteger, nullable=False),
    Column("voided", Boolean, nullable=False),
    Column("voided_at", DateTime(timezone=True)),
    Column("void_reason", Text),
    Column("recurring_id", BigInteger),
)

recurring_expenses = Table(
    "recurring_expenses",
    metadata,
    Column("id", BigInteger, primary_key=True),
    Column("name", Text, nullable=False),
    Column("currency", Text, nullable=False),
    Column("day_of_month", Integer, nullable=False),
    Column("pocket_id", BigInteger, nullable=False),
    Column("category_id", BigInteger),
    Column("start_month", CHAR(7), nullable=False),
    Column("active", Boolean, nullable=False),
    Column("deactivated_at", DateTime(timezone=True)),
)

recurring_expense_amounts = Table(
    "recurring_expense_amounts",
    metadata,
    Column("recurring_id", BigInteger, primary_key=True),
    Column("from_month", CHAR(7), primary_key=True),
    Column("original_amount", BigInteger, nullable=False),
)

idempotency_keys = Table(
    "idempotency_keys",
    metadata,
    Column("operation_id", Text, primary_key=True),
    Column("tool", Text, nullable=False),
    Column("fingerprint", CHAR(64), nullable=False),
    Column("response", JSONB, nullable=False),
)

INITIAL_BALANCE_INDEX = "ux_incomes_single_initial_balance"
LIVE_INCOME = (incomes.c.allocation_status == "repartido") & incomes.c.voided.is_(False)
LIVE_EXPENSE = expenses.c.voided.is_(False)


def constraint_name(exc: IntegrityError) -> str | None:
    return getattr(getattr(exc.orig, "diag", None), "constraint_name", None)


class SqlBudgetStore:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def list_pockets(self) -> list[Pocket]:
        with self._engine.connect() as conn:
            rows = conn.execute(
                select(pockets.c.id, pockets.c.name, pockets.c.behavior, pockets.c.active).order_by(
                    pockets.c.id
                )
            ).all()
        return [Pocket(r.id, r.name, Behavior(r.behavior), r.active) for r in rows]

    def allocation_months(self, up_to: Month) -> list[Month]:
        with self._engine.connect() as conn:
            rows = conn.execute(
                select(budget_month_allocations.c.month)
                .where(budget_month_allocations.c.month <= str(up_to))
                .distinct()
                .order_by(budget_month_allocations.c.month)
            ).scalars()
            return [Month.parse(m) for m in rows]

    def allocation_rows(self, month: Month) -> dict[int, int]:
        with self._engine.connect() as conn:
            rows = conn.execute(
                select(
                    budget_month_allocations.c.pocket_id, budget_month_allocations.c.percentage
                ).where(budget_month_allocations.c.month == str(month))
            ).all()
        return {r.pocket_id: r.percentage for r in rows}

    def replace_allocation(self, month: Month, rows: Mapping[int, int]) -> None:
        """Reemplaza solo las filas de ese mes, en una transacción (RN-02)."""
        with self._engine.begin() as conn:
            conn.execute(
                delete(budget_month_allocations).where(
                    budget_month_allocations.c.month == str(month)
                )
            )
            conn.execute(
                insert(budget_month_allocations),
                [
                    {"month": str(month), "pocket_id": pid, "percentage": pct}
                    for pid, pct in rows.items()
                ],
            )

    def has_initial_balance(self) -> bool:
        with self._engine.connect() as conn:
            return bool(
                conn.execute(
                    select(func.count())
                    .select_from(incomes)
                    .where(
                        (incomes.c.kind == IncomeKind.INITIAL_BALANCE.value)
                        & incomes.c.voided.is_(False)
                    )
                ).scalar()
            )

    def record_distributed_income(
        self,
        kind: IncomeKind,
        income_date: date,
        budget_month: Month,
        lines: Sequence[AllocationLine],
    ) -> int:
        """Ingreso en colones ya repartido (saldo inicial) y sus repartos, en una transacción."""
        total = sum(line.amount for line in lines)
        try:
            with self._engine.begin() as conn:
                income_id = conn.execute(
                    insert(incomes)
                    .values(
                        income_date=income_date,
                        kind=kind.value,
                        budget_month=str(budget_month),
                        amount=total,
                        currency=Currency.CRC.value,
                        original_amount=total,
                        allocation_status="repartido",
                    )
                    .returning(incomes.c.id)
                ).scalar_one()
                insert_lines(conn, income_id, lines)
                self._settle_goals(conn, income_date)
        except IntegrityError as exc:
            if constraint_name(exc) == INITIAL_BALANCE_INDEX:
                raise InitialBalanceAlreadyLoaded() from None
            raise
        return income_id

    def allocation_entries(self) -> list[AllocationEntry]:
        with self._engine.connect() as conn:
            rows = conn.execute(
                select(
                    income_allocations.c.pocket_id,
                    incomes.c.budget_month,
                    income_allocations.c.amount,
                    incomes.c.kind,
                )
                .select_from(
                    income_allocations.join(incomes, incomes.c.id == income_allocations.c.income_id)
                )
                .where(LIVE_INCOME)
            ).all()
        return [
            AllocationEntry(r.pocket_id, Month.parse(r.budget_month), r.amount, IncomeKind(r.kind))
            for r in rows
        ]

    def distributed_income_total(self) -> int:
        """Lado izquierdo del invariante, consultado directamente sobre `incomes`."""
        with self._engine.connect() as conn:
            return int(
                conn.execute(
                    select(func.coalesce(func.sum(incomes.c.amount), 0)).where(LIVE_INCOME)
                ).scalar_one()
            )

    def expense_entries(self) -> list[ExpenseEntry]:
        with self._engine.connect() as conn:
            rows = conn.execute(
                select(expenses.c.pocket_id, expenses.c.month, expenses.c.amount).where(
                    LIVE_EXPENSE
                )
            ).all()
        return [ExpenseEntry(r.pocket_id, Month.parse(r.month), r.amount) for r in rows]

    def expense_total(self) -> int:
        """Σ gastos vigentes, consultado directamente sobre `expenses` (invariante)."""
        with self._engine.connect() as conn:
            return int(
                conn.execute(
                    select(func.coalesce(func.sum(expenses.c.amount), 0)).where(LIVE_EXPENSE)
                ).scalar_one()
            )

    # --- Metas: lectura y evaluación de "lograda" (RN-24), dentro de la transacción ---

    @staticmethod
    def _read_goals(conn: Connection) -> list[Goal]:
        rows = conn.execute(select(savings_goals).order_by(savings_goals.c.id)).all()
        return [
            Goal(
                r.id,
                r.pocket_id,
                r.name,
                r.target_amount,
                r.target_date,
                GoalStatus(r.status),
                r.achieved_on,
                r.created_on,
                r.archived_at is not None,
            )
            for r in rows
        ]

    def _settle_goals(self, conn: Connection, on: date) -> list[int]:
        """Pasa a lograda las metas vivas cuyo saldo ya alcanza el objetivo (decide `reached`, con
        el saldo oficial de 11.2). Se llama en la transacción de cada operación que sube un saldo.
        """
        goals = [g for g in self._read_goals(conn) if g.live]
        if not goals:
            return []
        ids = sorted({g.pocket_id for g in goals})
        entries = [
            AllocationEntry(r.pocket_id, Month.parse(r.budget_month), r.amount, IncomeKind(r.kind))
            for r in conn.execute(
                select(
                    income_allocations.c.pocket_id,
                    incomes.c.budget_month,
                    income_allocations.c.amount,
                    incomes.c.kind,
                )
                .select_from(
                    income_allocations.join(incomes, incomes.c.id == income_allocations.c.income_id)
                )
                .where(LIVE_INCOME & income_allocations.c.pocket_id.in_(ids))
            ).all()
        ]
        spent = [
            ExpenseEntry(r.pocket_id, Month.parse(r.month), r.amount)
            for r in conn.execute(
                select(expenses.c.pocket_id, expenses.c.month, expenses.c.amount).where(
                    LIVE_EXPENSE & expenses.c.pocket_id.in_(ids)
                )
            ).all()
        ]
        done = []
        for goal_id, day in reached(goals, balance_function(entries, spent), on):
            conn.execute(
                update(savings_goals)
                .where((savings_goals.c.id == goal_id) & (savings_goals.c.status == "activa"))
                .values(status=GoalStatus.ACHIEVED.value, achieved_on=day)
            )
            done.append(goal_id)
        return done


def insert_lines(conn, income_id: int, lines: Sequence[AllocationLine]) -> None:
    conn.execute(
        insert(income_allocations),
        [
            {
                "income_id": income_id,
                "pocket_id": line.pocket_id,
                "percentage": line.percentage,
                "amount": line.amount,
            }
            for line in lines
        ],
    )
