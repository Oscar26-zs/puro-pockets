"""Presupuesto (Hito 4): bolsas, categorías, porcentajes por mes, ingresos y repartos.

Solo colones: moneda, monto original, tipo de cambio y anulación llegan en el Hito 5 con su propia
migración. Datos iniciales: las bolsas Necesidades, Ahorro y Gustos (editables; sin porcentajes).

El downgrade borra datos financieros: se niega a correr si hay datos, salvo con
ALLOW_DESTRUCTIVE_DOWNGRADE=true (ver README).

Revision ID: 0003_budget
Revises: 0002_oauth
Create Date: 2026-11-10
"""

import os
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_budget"
down_revision: str | None = "0002_oauth"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

MONTH_CHECK = "~ '^[0-9]{4}-(0[1-9]|1[0-2])$'"
SEED_POCKETS = (("Necesidades", "consumo"), ("Ahorro", "acumulable"), ("Gustos", "consumo"))
ALLOW_ENV = "ALLOW_DESTRUCTIVE_DOWNGRADE"


def _id() -> sa.Column:
    return sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True)


def upgrade() -> None:
    op.create_table(
        "pockets",
        _id(),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("behavior", sa.Text(), nullable=False),
        sa.Column("group_name", sa.Text(), nullable=True),
        sa.Column(
            "surplus_target_pocket_id", sa.BigInteger(), sa.ForeignKey("pockets.id"), nullable=True
        ),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint("behavior IN ('consumo','acumulable')", name="ck_pockets_behavior"),
    )
    # Nombre único sin distinguir mayúsculas
    op.create_index("ux_pockets_name_ci", "pockets", [sa.text("lower(name)")], unique=True)

    op.create_table(
        "categories",
        _id(),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("pocket_id", sa.BigInteger(), sa.ForeignKey("pockets.id"), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.create_index("ux_categories_name_ci", "categories", [sa.text("lower(name)")], unique=True)

    op.create_table(
        "budget_month_allocations",
        sa.Column("month", sa.CHAR(7), primary_key=True),
        sa.Column("pocket_id", sa.BigInteger(), sa.ForeignKey("pockets.id"), primary_key=True),
        sa.Column("percentage", sa.Integer(), nullable=False),
        sa.CheckConstraint(f"month {MONTH_CHECK}", name="ck_bma_month"),
        sa.CheckConstraint("percentage BETWEEN 0 AND 100", name="ck_bma_percentage"),
    )

    op.create_table(
        "incomes",
        _id(),
        sa.Column("income_date", sa.Date(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("source", sa.Text(), nullable=True),
        sa.Column("budget_month", sa.CHAR(7), nullable=False),
        sa.Column("amount", sa.BigInteger(), nullable=False),
        sa.Column("allocation_status", sa.Text(), nullable=False, server_default="pendiente"),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint("kind IN ('base','extra','saldo_inicial')", name="ck_incomes_kind"),
        sa.CheckConstraint(f"budget_month {MONTH_CHECK}", name="ck_incomes_budget_month"),
        sa.CheckConstraint("amount > 0", name="ck_incomes_amount"),
        sa.CheckConstraint(
            "allocation_status IN ('pendiente','repartido')", name="ck_incomes_allocation_status"
        ),
    )
    # Un solo saldo inicial (RN-54). El Hito 5 lo recrea con "AND NOT voided" para permitir una
    # nueva carga tras anular el saldo inicial.
    op.create_index(
        "ux_incomes_single_initial_balance",
        "incomes",
        ["kind"],
        unique=True,
        postgresql_where=sa.text("kind = 'saldo_inicial'"),
    )

    op.create_table(
        "income_allocations",
        _id(),
        sa.Column("income_id", sa.BigInteger(), sa.ForeignKey("incomes.id"), nullable=False),
        sa.Column("pocket_id", sa.BigInteger(), sa.ForeignKey("pockets.id"), nullable=False),
        sa.Column("percentage", sa.Integer(), nullable=True),
        sa.Column("amount", sa.BigInteger(), nullable=False),
        sa.CheckConstraint(
            "percentage IS NULL OR percentage BETWEEN 0 AND 100", name="ck_ia_percentage"
        ),
        sa.CheckConstraint("amount >= 0", name="ck_ia_amount"),
        sa.UniqueConstraint("income_id", "pocket_id", name="uq_ia_income_pocket"),
    )

    pockets = sa.table("pockets", sa.column("name", sa.Text), sa.column("behavior", sa.Text))
    op.bulk_insert(pockets, [{"name": n, "behavior": b} for n, b in SEED_POCKETS])


def _has_data(connection: sa.Connection) -> bool:
    """Hay datos si alguna tabla del hito tiene filas o las bolsas difieren de las iniciales."""
    for table in ("categories", "budget_month_allocations", "incomes", "income_allocations"):
        if connection.execute(sa.text(f"SELECT EXISTS (SELECT 1 FROM {table})")).scalar():
            return True
    rows = connection.execute(
        sa.text("SELECT name, behavior, active, group_name, surplus_target_pocket_id FROM pockets")
    ).all()
    expected = {(n, b, True, None, None) for n, b in SEED_POCKETS}
    return len(rows) != len(SEED_POCKETS) or {tuple(r) for r in rows} != expected


def downgrade() -> None:
    if os.environ.get(ALLOW_ENV, "").strip().lower() != "true" and _has_data(op.get_bind()):
        raise RuntimeError(
            "Downgrade de 0003_budget cancelado: las tablas del presupuesto tienen datos y se "
            "borrarían. Haz un respaldo (README) y, solo si estás seguro, repite con "
            f"{ALLOW_ENV}=true."
        )
    op.drop_table("income_allocations")
    op.drop_index("ux_incomes_single_initial_balance", table_name="incomes")
    op.drop_table("incomes")
    op.drop_table("budget_month_allocations")
    op.drop_index("ux_categories_name_ci", table_name="categories")
    op.drop_table("categories")
    op.drop_index("ux_pockets_name_ci", table_name="pockets")
    op.drop_table("pockets")
