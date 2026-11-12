"""Cierre de mes (Hito 9): `month_closures`, `closure_adjustments` y mes de las transferencias.

Conserva los datos del Hito 8 y no cierra ningún mes: un mes sin fila cuenta como abierto (los datos
existentes quedan abiertos).

- `month_closures`: un mes 'YYYY-MM' por fila (clave primaria con CHECK de formato), estado y
  `closed_at`. Disparador: no se borra ni sale de `cerrado` (un cierre no se reabre, RN-48).
- `closure_adjustments`: sobrante no destinado (+) y sobregasto no cubierto (−) por mes y bolsa
  (RN-50, 10.2), con signo según el tipo, claves foráneas ON DELETE RESTRICT y disparador que
  rechaza UPDATE y DELETE.
- `transfers`: CHECK nuevo; el mes es el de la fecha, salvo el motivo `cierre_de_mes`, cuyo mes es
  el cerrado (nunca posterior al de la fecha). El upgrade comprueba antes que los datos lo cumplen.
- `pockets.surplus_target_pocket_id` (destino de sobrante sugerido, 6.5) ya existe desde 0003.

El downgrade borra datos: se niega si hay cierres o ajustes, salvo con
ALLOW_DESTRUCTIVE_DOWNGRADE=true (ver README).

Revision ID: 0008_month_closures
Revises: 0007_transfers
Create Date: 2026-11-11
"""

import os
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008_month_closures"
down_revision: str | None = "0007_transfers"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ALLOW_ENV = "ALLOW_DESTRUCTIVE_DOWNGRADE"
MONTH_FORMAT = "month ~ '^[0-9]{4}-(0[1-9]|1[0-2])$'"
TRANSFER_MONTH_RULE = (
    "(reason <> 'cierre_de_mes' AND month = to_char(transfer_date, 'YYYY-MM')) "
    "OR (reason = 'cierre_de_mes' AND month <= to_char(transfer_date, 'YYYY-MM'))"
)

CLOSURES_FUNCTION = """
CREATE FUNCTION pp_month_closures_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'Un cierre de mes no se borra (RN-48).' USING ERRCODE = 'restrict_violation';
  END IF;
  IF OLD.status = 'cerrado' AND (NEW.status <> 'cerrado' OR NEW.month <> OLD.month
      OR NEW.closed_at IS DISTINCT FROM OLD.closed_at) THEN
    RAISE EXCEPTION 'Un mes cerrado no se reabre ni se modifica (RN-48).'
      USING ERRCODE = 'restrict_violation';
  END IF;
  RETURN NEW;
END $$;
"""
ADJUSTMENTS_FUNCTION = """
CREATE FUNCTION pp_closure_adjustments_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'Un ajuste de cierre no se edita ni se borra (RN-48, RN-50).'
    USING ERRCODE = 'restrict_violation';
END $$;
"""
CLOSURES_TRIGGER = "trg_month_closures_guard"
ADJUSTMENTS_TRIGGER = "trg_closure_adjustments_immutable"


def upgrade() -> None:
    bind = op.get_bind()
    broken = bind.execute(
        sa.text(f"SELECT count(*) FROM transfers WHERE NOT ({TRANSFER_MONTH_RULE})")
    ).scalar()
    if broken:
        raise RuntimeError(
            "Upgrade a 0008_month_closures cancelado: hay transferencias cuyo mes no es el de su "
            "fecha. Revísalas antes de migrar (no se cambió nada)."
        )
    op.create_table(
        "month_closures",
        sa.Column("month", sa.CHAR(7), primary_key=True),
        sa.Column("status", sa.Text(), nullable=False, server_default="cerrado"),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(MONTH_FORMAT, name="ck_month_closures_month"),
        sa.CheckConstraint("status IN ('abierto','cerrado')", name="ck_month_closures_status"),
        sa.CheckConstraint(
            "(status = 'cerrado') = (closed_at IS NOT NULL)", name="ck_month_closures_closed_at"
        ),
    )
    op.create_table(
        "closure_adjustments",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column(
            "month",
            sa.CHAR(7),
            sa.ForeignKey("month_closures.month", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "pocket_id",
            sa.BigInteger(),
            sa.ForeignKey("pockets.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("amount", sa.BigInteger(), nullable=False),  # colones, con signo
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "kind IN ('sobrante_no_destinado','sobregasto_no_cubierto')",
            name="ck_closure_adjustments_kind",
        ),
        sa.CheckConstraint(
            "(kind = 'sobrante_no_destinado' AND amount > 0) "
            "OR (kind = 'sobregasto_no_cubierto' AND amount < 0)",
            name="ck_closure_adjustments_sign",
        ),
        sa.UniqueConstraint("month", "pocket_id", "kind", name="ux_closure_adjustments_month"),
    )
    op.create_check_constraint("ck_transfers_month_date", "transfers", TRANSFER_MONTH_RULE)
    op.execute(CLOSURES_FUNCTION)
    op.execute(
        f"CREATE TRIGGER {CLOSURES_TRIGGER} BEFORE UPDATE OR DELETE ON month_closures "
        "FOR EACH ROW EXECUTE FUNCTION pp_month_closures_guard()"
    )
    op.execute(ADJUSTMENTS_FUNCTION)
    op.execute(
        f"CREATE TRIGGER {ADJUSTMENTS_TRIGGER} BEFORE UPDATE OR DELETE ON closure_adjustments "
        "FOR EACH ROW EXECUTE FUNCTION pp_closure_adjustments_immutable()"
    )


def _has_data(connection: sa.Connection) -> bool:
    return bool(
        connection.execute(
            sa.text(
                "SELECT EXISTS (SELECT 1 FROM month_closures) "
                "OR EXISTS (SELECT 1 FROM closure_adjustments)"
            )
        ).scalar()
    )


def downgrade() -> None:
    if os.environ.get(ALLOW_ENV, "").strip().lower() != "true" and _has_data(op.get_bind()):
        raise RuntimeError(
            "Downgrade de 0008_month_closures cancelado: hay meses cerrados, y se perderían sus "
            f"cierres y ajustes. Haz un respaldo (README) y, solo si estás seguro, repite con "
            f"{ALLOW_ENV}=true."
        )
    op.execute(f"DROP TRIGGER IF EXISTS {ADJUSTMENTS_TRIGGER} ON closure_adjustments")
    op.execute("DROP FUNCTION IF EXISTS pp_closure_adjustments_immutable()")
    op.execute(f"DROP TRIGGER IF EXISTS {CLOSURES_TRIGGER} ON month_closures")
    op.execute("DROP FUNCTION IF EXISTS pp_month_closures_guard()")
    op.drop_constraint("ck_transfers_month_date", "transfers", type_="check")
    op.drop_table("closure_adjustments")
    op.drop_table("month_closures")
