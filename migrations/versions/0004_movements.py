"""Movimientos (Hito 5): monedas y anulación en ingresos, gastos y claves de operación.

Conserva los datos del Hito 4: los ingresos existentes (por ejemplo el saldo inicial) quedan en CRC,
con monto original = monto y sin tipo de cambio. El índice del saldo inicial se recrea ignorando los
anulados, para permitir una nueva carga tras anular (RN-54). Disparadores protegen el libro mayor:
nada se borra y un movimiento solo cambia para anularse (principio 3.4, RN-53).

El downgrade borra datos: se niega si hay gastos, claves de operación, ingresos en USD o anulados,
salvo con ALLOW_DESTRUCTIVE_DOWNGRADE=true (ver README).

Revision ID: 0004_movements
Revises: 0003_budget
Create Date: 2026-11-10
"""

import os
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004_movements"
down_revision: str | None = "0003_budget"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

MONTH_CHECK = "~ '^[0-9]{4}-(0[1-9]|1[0-2])$'"
ALLOW_ENV = "ALLOW_DESTRUCTIVE_DOWNGRADE"
INITIAL_INDEX = "ux_incomes_single_initial_balance"
CURRENCY_CHECK = (
    "(currency = 'CRC' AND exchange_rate IS NULL AND original_amount = amount) "
    "OR (currency = 'USD' AND exchange_rate IS NOT NULL AND exchange_rate > 0)"
)
VOID_CHECK = (
    "(NOT voided AND voided_at IS NULL AND void_reason IS NULL) "
    "OR (voided AND voided_at IS NOT NULL AND void_reason IS NOT NULL "
    "AND char_length(void_reason) BETWEEN 3 AND 200)"
)

LEDGER_FUNCTIONS = """
CREATE FUNCTION pp_ledger_no_delete() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'Libro mayor inmutable: no se borran filas de %; se anula el movimiento (RN-53).',
    TG_TABLE_NAME USING ERRCODE = 'restrict_violation';
END $$;

CREATE FUNCTION pp_ledger_no_update() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'Libro mayor inmutable: % no admite cambios.', TG_TABLE_NAME
    USING ERRCODE = 'restrict_violation';
END $$;

CREATE FUNCTION pp_ledger_movement_update() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
  mutable text[] := ARRAY['voided', 'voided_at', 'void_reason', 'allocation_status'];
BEGIN
  IF OLD.voided AND (NOT NEW.voided OR NEW.voided_at IS DISTINCT FROM OLD.voided_at
                     OR NEW.void_reason IS DISTINCT FROM OLD.void_reason) THEN
    RAISE EXCEPTION 'Una anulación no se deshace ni se modifica (RN-53).'
      USING ERRCODE = 'restrict_violation';
  END IF;
  IF (to_jsonb(NEW) - mutable) IS DISTINCT FROM (to_jsonb(OLD) - mutable) THEN
    RAISE EXCEPTION 'Un movimiento no se edita: se anula y se registra uno nuevo (RN-53).'
      USING ERRCODE = 'restrict_violation';
  END IF;
  RETURN NEW;
END $$;
"""

TRIGGERS = (
    ("trg_incomes_no_delete", "DELETE", "incomes", "pp_ledger_no_delete"),
    ("trg_income_allocations_no_delete", "DELETE", "income_allocations", "pp_ledger_no_delete"),
    ("trg_expenses_no_delete", "DELETE", "expenses", "pp_ledger_no_delete"),
    ("trg_income_allocations_no_update", "UPDATE", "income_allocations", "pp_ledger_no_update"),
    ("trg_incomes_update", "UPDATE", "incomes", "pp_ledger_movement_update"),
    ("trg_expenses_update", "UPDATE", "expenses", "pp_ledger_movement_update"),
)


def _id() -> sa.Column:
    return sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True)


def _void_columns() -> list[sa.Column]:
    return [
        sa.Column("voided", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("voided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("void_reason", sa.Text(), nullable=True),
    ]


def upgrade() -> None:
    # --- incomes: moneda, monto original, tipo de cambio y anulación (conserva los datos) ---
    op.add_column("incomes", sa.Column("currency", sa.Text(), nullable=False, server_default="CRC"))
    op.add_column("incomes", sa.Column("original_amount", sa.BigInteger(), nullable=True))
    op.add_column("incomes", sa.Column("exchange_rate", sa.BigInteger(), nullable=True))
    for column in _void_columns():
        op.add_column("incomes", column)
    op.execute("UPDATE incomes SET original_amount = amount")
    op.alter_column("incomes", "original_amount", nullable=False)
    op.create_check_constraint("ck_incomes_currency", "incomes", "currency IN ('CRC','USD')")
    op.create_check_constraint("ck_incomes_original_amount", "incomes", "original_amount > 0")
    op.create_check_constraint("ck_incomes_exchange_rate", "incomes", CURRENCY_CHECK)
    op.create_check_constraint("ck_incomes_void", "incomes", VOID_CHECK)
    op.drop_index(INITIAL_INDEX, table_name="incomes")
    op.create_index(
        INITIAL_INDEX,
        "incomes",
        ["kind"],
        unique=True,
        postgresql_where=sa.text("kind = 'saldo_inicial' AND NOT voided"),
    )

    # --- expenses ---
    op.create_table(
        "expenses",
        _id(),
        sa.Column("expense_date", sa.Date(), nullable=False),
        sa.Column("month", sa.CHAR(7), nullable=False),
        sa.Column("pocket_id", sa.BigInteger(), sa.ForeignKey("pockets.id"), nullable=False),
        sa.Column("category_id", sa.BigInteger(), sa.ForeignKey("categories.id"), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("currency", sa.Text(), nullable=False, server_default="CRC"),
        sa.Column("original_amount", sa.BigInteger(), nullable=False),
        sa.Column("exchange_rate", sa.BigInteger(), nullable=True),
        sa.Column("amount", sa.BigInteger(), nullable=False),
        *_void_columns(),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(f"month {MONTH_CHECK}", name="ck_expenses_month"),
        sa.CheckConstraint(
            "description IS NULL OR char_length(description) <= 120", name="ck_expenses_description"
        ),
        sa.CheckConstraint("currency IN ('CRC','USD')", name="ck_expenses_currency"),
        sa.CheckConstraint("original_amount > 0", name="ck_expenses_original_amount"),
        sa.CheckConstraint("amount > 0", name="ck_expenses_amount"),
        sa.CheckConstraint(CURRENCY_CHECK, name="ck_expenses_exchange_rate"),
        sa.CheckConstraint(VOID_CHECK, name="ck_expenses_void"),
    )
    op.create_index("ix_expenses_month", "expenses", ["month"])
    op.create_index("ix_expenses_pocket_month", "expenses", ["pocket_id", "month"])

    # --- idempotency_keys ---
    op.create_table(
        "idempotency_keys",
        sa.Column("operation_id", sa.Text(), primary_key=True),
        sa.Column("tool", sa.Text(), nullable=False),
        sa.Column("fingerprint", sa.CHAR(64), nullable=False),
        sa.Column("response", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "char_length(operation_id) BETWEEN 8 AND 100", name="ck_idempotency_operation_id"
        ),
    )

    # --- Libro mayor inmutable (después de rellenar original_amount) ---
    op.execute(LEDGER_FUNCTIONS)
    for name, event, table, function in TRIGGERS:
        op.execute(
            f"CREATE TRIGGER {name} BEFORE {event} ON {table} "
            f"FOR EACH ROW EXECUTE FUNCTION {function}()"
        )


def _has_data(connection: sa.Connection) -> bool:
    """Hay datos si existen gastos o claves de operación, o ingresos en USD o anulados."""
    checks = (
        "SELECT EXISTS (SELECT 1 FROM expenses)",
        "SELECT EXISTS (SELECT 1 FROM idempotency_keys)",
        "SELECT EXISTS (SELECT 1 FROM incomes WHERE currency <> 'CRC' OR voided)",
    )
    return any(connection.execute(sa.text(sql)).scalar() for sql in checks)


def downgrade() -> None:
    if os.environ.get(ALLOW_ENV, "").strip().lower() != "true" and _has_data(op.get_bind()):
        raise RuntimeError(
            "Downgrade de 0004_movements cancelado: hay gastos, claves de operación o ingresos en "
            "dólares o anulados, y se borrarían. Haz un respaldo (README) y, solo si estás seguro, "
            f"repite con {ALLOW_ENV}=true."
        )
    for name, _, table, _ in TRIGGERS:
        op.execute(f"DROP TRIGGER IF EXISTS {name} ON {table}")
    op.execute("DROP FUNCTION IF EXISTS pp_ledger_movement_update()")
    op.execute("DROP FUNCTION IF EXISTS pp_ledger_no_update()")
    op.execute("DROP FUNCTION IF EXISTS pp_ledger_no_delete()")
    op.drop_table("idempotency_keys")
    op.drop_index("ix_expenses_pocket_month", table_name="expenses")
    op.drop_index("ix_expenses_month", table_name="expenses")
    op.drop_table("expenses")
    # Con la variable, los ingresos anulados o en USD se pierden al quitar sus columnas: se borran
    # los anulados para que el índice del Hito 4 (un solo saldo inicial) pueda recrearse
    op.execute(
        "DELETE FROM income_allocations WHERE income_id IN (SELECT id FROM incomes WHERE voided)"
    )
    op.execute("DELETE FROM incomes WHERE voided")
    op.drop_index(INITIAL_INDEX, table_name="incomes")
    op.create_index(
        INITIAL_INDEX,
        "incomes",
        ["kind"],
        unique=True,
        postgresql_where=sa.text("kind = 'saldo_inicial'"),
    )
    for constraint in (
        "ck_incomes_void",
        "ck_incomes_exchange_rate",
        "ck_incomes_original_amount",
        "ck_incomes_currency",
    ):
        op.drop_constraint(constraint, "incomes", type_="check")
    for column in ("void_reason", "voided_at", "voided", "exchange_rate", "original_amount"):
        op.drop_column("incomes", column)
    op.drop_column("incomes", "currency")
