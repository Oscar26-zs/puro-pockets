"""Extras y gastos fijos (Hito 6): plantillas, historial de montos y pago enlazado.

Conserva los datos del Hito 5. Reutiliza lo que ya existe en `incomes` (`kind = 'extra'` y
`allocation_status` pendiente/repartido, desde 0003): solo agrega que el estado pendiente es
exclusivo de los extras, el límite de largo de `source` y que un reparto no se deshace.

- `recurring_expenses`: plantillas (nunca se borran: se desactivan; nombre único entre las activas).
- `recurring_expense_amounts`: monto de cada plantilla desde un mes (cambiar el monto afecta solo
  meses futuros).
- `expenses.recurring_id`: pago de un fijo; un solo pago vigente por plantilla y mes (índice único
  parcial que ignora los anulados, así un pago anulado deja el fijo pendiente otra vez).

El downgrade borra datos: se niega si hay plantillas, extras o pagos enlazados, salvo con
ALLOW_DESTRUCTIVE_DOWNGRADE=true (ver README).

Revision ID: 0005_extras_recurring
Revises: 0004_movements
Create Date: 2026-11-11
"""

import os
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_extras_recurring"
down_revision: str | None = "0004_movements"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

MONTH_CHECK = "~ '^[0-9]{4}-(0[1-9]|1[0-2])$'"
ALLOW_ENV = "ALLOW_DESTRUCTIVE_DOWNGRADE"
PAYMENT_INDEX = "ux_expenses_recurring_month"
NAME_INDEX = "ux_recurring_expenses_name_active"

# Igual que en 0004, más: un reparto no vuelve a pendiente y un ingreso anulado no se reparte.
# allocation_status se lee con to_jsonb: la función también protege `expenses`, que no lo tiene.
MOVEMENT_UPDATE_V2 = """
CREATE OR REPLACE FUNCTION pp_ledger_movement_update() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
  mutable text[] := ARRAY['voided', 'voided_at', 'void_reason', 'allocation_status'];
  old_status text := to_jsonb(OLD) ->> 'allocation_status';
  new_status text := to_jsonb(NEW) ->> 'allocation_status';
BEGIN
  IF OLD.voided AND (NOT NEW.voided OR NEW.voided_at IS DISTINCT FROM OLD.voided_at
                     OR NEW.void_reason IS DISTINCT FROM OLD.void_reason) THEN
    RAISE EXCEPTION 'Una anulación no se deshace ni se modifica (RN-53).'
      USING ERRCODE = 'restrict_violation';
  END IF;
  IF old_status IS DISTINCT FROM new_status AND (old_status = 'repartido' OR OLD.voided) THEN
    RAISE EXCEPTION 'Un reparto no se deshace ni se hace sobre un ingreso anulado (RN-53, RN-59).'
      USING ERRCODE = 'restrict_violation';
  END IF;
  IF (to_jsonb(NEW) - mutable) IS DISTINCT FROM (to_jsonb(OLD) - mutable) THEN
    RAISE EXCEPTION 'Un movimiento no se edita: se anula y se registra uno nuevo (RN-53).'
      USING ERRCODE = 'restrict_violation';
  END IF;
  RETURN NEW;
END $$;
"""

# Cuerpo de 0004, para restaurarlo en el downgrade
MOVEMENT_UPDATE_V1 = """
CREATE OR REPLACE FUNCTION pp_ledger_movement_update() RETURNS trigger LANGUAGE plpgsql AS $$
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

RECURRING_FUNCTIONS = """
CREATE FUNCTION pp_recurring_no_delete() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'Los gastos fijos no se borran: se desactivan (principio 3.8).'
    USING ERRCODE = 'restrict_violation';
END $$;

CREATE FUNCTION pp_recurring_update() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.currency IS DISTINCT FROM OLD.currency
     OR NEW.start_month IS DISTINCT FROM OLD.start_month THEN
    RAISE EXCEPTION 'La moneda y el mes de inicio de un gasto fijo no se cambian.'
      USING ERRCODE = 'restrict_violation';
  END IF;
  IF NOT OLD.active AND NEW IS DISTINCT FROM OLD THEN
    RAISE EXCEPTION 'Un gasto fijo desactivado no se reactiva ni se modifica.'
      USING ERRCODE = 'restrict_violation';
  END IF;
  RETURN NEW;
END $$;
"""

TRIGGERS = (
    ("trg_recurring_expenses_no_delete", "DELETE", "recurring_expenses", "pp_recurring_no_delete"),
    (
        "trg_recurring_amounts_no_delete",
        "DELETE",
        "recurring_expense_amounts",
        "pp_recurring_no_delete",
    ),
    ("trg_recurring_expenses_update", "UPDATE", "recurring_expenses", "pp_recurring_update"),
)


def _check_existing_incomes(connection: sa.Connection) -> None:
    bad = connection.execute(
        sa.text(
            "SELECT count(*) FROM incomes "
            "WHERE kind <> 'extra' AND allocation_status <> 'repartido'"
        )
    ).scalar()
    if bad:
        raise RuntimeError(
            "Migración 0005 cancelada: hay ingresos que no son extras en estado pendiente; "
            "revísalos antes de migrar (no se modificó nada)."
        )


def upgrade() -> None:
    _check_existing_incomes(op.get_bind())

    # --- incomes: el estado pendiente es solo de los extras (RN-06) ---
    op.create_check_constraint(
        "ck_incomes_pending_only_extra",
        "incomes",
        "kind = 'extra' OR allocation_status = 'repartido'",
    )
    op.create_check_constraint(
        "ck_incomes_source", "incomes", "source IS NULL OR char_length(source) <= 120"
    )
    op.execute(MOVEMENT_UPDATE_V2)

    # --- recurring_expenses ---
    op.create_table(
        "recurring_expenses",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("currency", sa.Text(), nullable=False),
        sa.Column("day_of_month", sa.Integer(), nullable=False),
        sa.Column("pocket_id", sa.BigInteger(), sa.ForeignKey("pockets.id"), nullable=False),
        sa.Column("category_id", sa.BigInteger(), sa.ForeignKey("categories.id"), nullable=True),
        sa.Column("start_month", sa.CHAR(7), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("deactivated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint("char_length(name) BETWEEN 1 AND 60", name="ck_recurring_name"),
        sa.CheckConstraint("currency IN ('CRC','USD')", name="ck_recurring_currency"),
        sa.CheckConstraint("day_of_month BETWEEN 1 AND 31", name="ck_recurring_day"),
        sa.CheckConstraint(f"start_month {MONTH_CHECK}", name="ck_recurring_start_month"),
        sa.CheckConstraint("active = (deactivated_at IS NULL)", name="ck_recurring_active"),
    )
    op.create_index(
        NAME_INDEX,
        "recurring_expenses",
        [sa.text("lower(name)")],
        unique=True,
        postgresql_where=sa.text("active"),
    )

    # --- recurring_expense_amounts: el monto vale desde from_month ---
    op.create_table(
        "recurring_expense_amounts",
        sa.Column(
            "recurring_id",
            sa.BigInteger(),
            sa.ForeignKey("recurring_expenses.id"),
            primary_key=True,
        ),
        sa.Column("from_month", sa.CHAR(7), primary_key=True),
        sa.Column(
            "original_amount", sa.BigInteger(), nullable=False
        ),  # CRC: colones; USD: centavos
        sa.CheckConstraint(f"from_month {MONTH_CHECK}", name="ck_recurring_amount_month"),
        sa.CheckConstraint("original_amount > 0", name="ck_recurring_amount_positive"),
    )

    # --- expenses: pago enlazado, uno vigente por plantilla y mes ---
    op.add_column(
        "expenses",
        sa.Column(
            "recurring_id", sa.BigInteger(), sa.ForeignKey("recurring_expenses.id"), nullable=True
        ),
    )
    op.create_index(
        PAYMENT_INDEX,
        "expenses",
        ["recurring_id", "month"],
        unique=True,
        postgresql_where=sa.text("recurring_id IS NOT NULL AND NOT voided"),
    )

    op.execute(RECURRING_FUNCTIONS)
    for name, event, table, function in TRIGGERS:
        op.execute(
            f"CREATE TRIGGER {name} BEFORE {event} ON {table} "
            f"FOR EACH ROW EXECUTE FUNCTION {function}()"
        )


def _has_data(connection: sa.Connection) -> bool:
    """Hay datos si existen plantillas, extras o gastos enlazados a una plantilla."""
    checks = (
        "SELECT EXISTS (SELECT 1 FROM recurring_expenses)",
        "SELECT EXISTS (SELECT 1 FROM incomes WHERE kind = 'extra')",
        "SELECT EXISTS (SELECT 1 FROM expenses WHERE recurring_id IS NOT NULL)",
    )
    return any(connection.execute(sa.text(sql)).scalar() for sql in checks)


def downgrade() -> None:
    if os.environ.get(ALLOW_ENV, "").strip().lower() != "true" and _has_data(op.get_bind()):
        raise RuntimeError(
            "Downgrade de 0005_extras_recurring cancelado: hay gastos fijos, extras o pagos "
            "enlazados, y se perderían. Haz un respaldo (README) y, solo si estás seguro, repite "
            f"con {ALLOW_ENV}=true."
        )
    for name, _, table, _ in TRIGGERS:
        op.execute(f"DROP TRIGGER IF EXISTS {name} ON {table}")
    op.execute("DROP FUNCTION IF EXISTS pp_recurring_update()")
    op.execute("DROP FUNCTION IF EXISTS pp_recurring_no_delete()")
    op.drop_index(PAYMENT_INDEX, table_name="expenses")
    op.drop_column("expenses", "recurring_id")  # con la variable: los gastos quedan sin enlace
    op.drop_table("recurring_expense_amounts")
    op.drop_index(NAME_INDEX, table_name="recurring_expenses")
    op.drop_table("recurring_expenses")
    op.execute(MOVEMENT_UPDATE_V1)
    op.drop_constraint("ck_incomes_source", "incomes", type_="check")
    op.drop_constraint("ck_incomes_pending_only_extra", "incomes", type_="check")
