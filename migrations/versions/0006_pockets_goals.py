"""Bolsas flexibles y metas (Hito 7): archivado de bolsas y tabla de metas.

Conserva los datos del Hito 6. En `pockets` solo falta registrar cuándo se archivó (`archived_at`,
con `active = (archived_at IS NULL)`) y proteger lo que no cambia: una bolsa no se borra (RN-16), no
se reactiva ni cambia de comportamiento. `savings_goals` guarda el objetivo de cada meta, no dinero
(RN-23): el avance se calcula del saldo de la bolsa. Una sola meta activa por bolsa (RN-22, decisión
#11) con un índice único parcial. Una meta archivada con su bolsa queda con `archived_at`.

El downgrade borra datos: se niega si hay metas o bolsas archivadas, salvo con
ALLOW_DESTRUCTIVE_DOWNGRADE=true (ver README).

Revision ID: 0006_pockets_goals
Revises: 0005_extras_recurring
Create Date: 2026-11-11
"""

import os
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_pockets_goals"
down_revision: str | None = "0005_extras_recurring"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ALLOW_ENV = "ALLOW_DESTRUCTIVE_DOWNGRADE"
ACTIVE_GOAL_INDEX = "ux_savings_goals_active_pocket"

FUNCTIONS = """
CREATE FUNCTION pp_pockets_no_delete() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'Una bolsa no se borra: se archiva (RN-16).' USING ERRCODE = 'restrict_violation';
END $$;

CREATE FUNCTION pp_pockets_update() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NOT OLD.active AND NEW.active THEN
    RAISE EXCEPTION 'Una bolsa archivada no se reactiva.' USING ERRCODE = 'restrict_violation';
  END IF;
  IF NEW.behavior IS DISTINCT FROM OLD.behavior THEN
    RAISE EXCEPTION 'El comportamiento de una bolsa no cambia (RN-10).'
      USING ERRCODE = 'restrict_violation';
  END IF;
  RETURN NEW;
END $$;

CREATE FUNCTION pp_goals_no_delete() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'Una meta no se borra: se pausa o se archiva con su bolsa.'
    USING ERRCODE = 'restrict_violation';
END $$;

CREATE FUNCTION pp_goals_update() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.pocket_id IS DISTINCT FROM OLD.pocket_id OR NEW.name IS DISTINCT FROM OLD.name
     OR NEW.created_on IS DISTINCT FROM OLD.created_on THEN
    RAISE EXCEPTION 'La bolsa, el nombre y la fecha de creación de una meta no cambian.'
      USING ERRCODE = 'restrict_violation';
  END IF;
  IF OLD.status = 'lograda' AND (NEW.status IS DISTINCT FROM OLD.status
     OR NEW.achieved_on IS DISTINCT FROM OLD.achieved_on
     OR NEW.target_amount IS DISTINCT FROM OLD.target_amount) THEN
    RAISE EXCEPTION 'Una meta lograda se queda lograda (RN-24).'
      USING ERRCODE = 'restrict_violation';
  END IF;
  IF OLD.archived_at IS NOT NULL AND NEW IS DISTINCT FROM OLD THEN
    RAISE EXCEPTION 'Una meta archivada con su bolsa no cambia.'
      USING ERRCODE = 'restrict_violation';
  END IF;
  RETURN NEW;
END $$;
"""

TRIGGERS = (
    ("trg_pockets_no_delete", "DELETE", "pockets", "pp_pockets_no_delete"),
    ("trg_pockets_update", "UPDATE", "pockets", "pp_pockets_update"),
    ("trg_savings_goals_no_delete", "DELETE", "savings_goals", "pp_goals_no_delete"),
    ("trg_savings_goals_update", "UPDATE", "savings_goals", "pp_goals_update"),
)


def upgrade() -> None:
    # --- pockets: cuándo se archivó (conserva los datos: las activas quedan con NULL) ---
    op.add_column("pockets", sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True))
    op.execute("UPDATE pockets SET archived_at = created_at WHERE NOT active")
    op.create_check_constraint("ck_pockets_archived", "pockets", "active = (archived_at IS NULL)")

    # --- savings_goals: objetivo de una bolsa acumulable, sin dinero propio ---
    op.create_table(
        "savings_goals",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("pocket_id", sa.BigInteger(), sa.ForeignKey("pockets.id"), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("target_amount", sa.BigInteger(), nullable=False),  # colones (RN-19)
        sa.Column("target_date", sa.Date(), nullable=True),  # opcional (RN-20)
        sa.Column("status", sa.Text(), nullable=False, server_default="activa"),
        sa.Column("achieved_on", sa.Date(), nullable=True),  # al pasar a lograda (RN-24)
        sa.Column("created_on", sa.Date(), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint("char_length(name) BETWEEN 1 AND 60", name="ck_goals_name"),
        sa.CheckConstraint("target_amount > 0", name="ck_goals_target"),
        sa.CheckConstraint("status IN ('activa','lograda','pausada')", name="ck_goals_status"),
        sa.CheckConstraint(
            "(status = 'lograda') = (achieved_on IS NOT NULL)", name="ck_goals_achieved"
        ),
    )
    # RN-22 (decisión #11): una sola meta activa por bolsa
    op.create_index(
        ACTIVE_GOAL_INDEX,
        "savings_goals",
        ["pocket_id"],
        unique=True,
        postgresql_where=sa.text("status = 'activa' AND archived_at IS NULL"),
    )

    op.execute(FUNCTIONS)
    for name, event, table, function in TRIGGERS:
        op.execute(
            f"CREATE TRIGGER {name} BEFORE {event} ON {table} "
            f"FOR EACH ROW EXECUTE FUNCTION {function}()"
        )


def _has_data(connection: sa.Connection) -> bool:
    """Hay datos si existen metas o bolsas archivadas."""
    checks = (
        "SELECT EXISTS (SELECT 1 FROM savings_goals)",
        "SELECT EXISTS (SELECT 1 FROM pockets WHERE archived_at IS NOT NULL)",
    )
    return any(connection.execute(sa.text(sql)).scalar() for sql in checks)


def downgrade() -> None:
    if os.environ.get(ALLOW_ENV, "").strip().lower() != "true" and _has_data(op.get_bind()):
        raise RuntimeError(
            "Downgrade de 0006_pockets_goals cancelado: hay metas o bolsas archivadas, y se "
            "perderían. Haz un respaldo (README) y, solo si estás seguro, repite con "
            f"{ALLOW_ENV}=true."
        )
    for name, _, table, _ in TRIGGERS:
        op.execute(f"DROP TRIGGER IF EXISTS {name} ON {table}")
    for function in (
        "pp_goals_update",
        "pp_goals_no_delete",
        "pp_pockets_update",
        "pp_pockets_no_delete",
    ):
        op.execute(f"DROP FUNCTION IF EXISTS {function}()")
    op.drop_index(ACTIVE_GOAL_INDEX, table_name="savings_goals")
    op.drop_table("savings_goals")
    op.drop_constraint("ck_pockets_archived", "pockets", type_="check")
    op.drop_column("pockets", "archived_at")  # con la variable: las archivadas siguen inactivas
