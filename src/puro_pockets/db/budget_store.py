"""Almacén SQL del presupuesto (SQLAlchemy Core). Tablas de la migración 0003_budget."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date

from sqlalchemy import (
    CHAR,
    BigInteger,
    Boolean,
    Column,
    Date,
    Engine,
    Integer,
    MetaData,
    Table,
    Text,
    delete,
    func,
    insert,
    select,
)
from sqlalchemy.exc import IntegrityError

from puro_pockets.domain.balances import AllocationEntry, IncomeKind
from puro_pockets.domain.errors import InitialBalanceAlreadyLoaded
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

INITIAL_BALANCE_INDEX = "ux_incomes_single_initial_balance"


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
                    .where(incomes.c.kind == IncomeKind.INITIAL_BALANCE.value)
                ).scalar()
            )

    def record_distributed_income(
        self,
        kind: IncomeKind,
        income_date: date,
        budget_month: Month,
        lines: Sequence[AllocationLine],
    ) -> int:
        try:
            with self._engine.begin() as conn:
                income_id = conn.execute(
                    insert(incomes)
                    .values(
                        income_date=income_date,
                        kind=kind.value,
                        budget_month=str(budget_month),
                        amount=sum(line.amount for line in lines),
                        allocation_status="repartido",
                    )
                    .returning(incomes.c.id)
                ).scalar_one()
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
        except IntegrityError as exc:
            constraint = getattr(getattr(exc.orig, "diag", None), "constraint_name", None)
            if constraint == INITIAL_BALANCE_INDEX:
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
                .where(incomes.c.allocation_status == "repartido")
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
                    select(func.coalesce(func.sum(incomes.c.amount), 0)).where(
                        incomes.c.allocation_status == "repartido"
                    )
                ).scalar_one()
            )
