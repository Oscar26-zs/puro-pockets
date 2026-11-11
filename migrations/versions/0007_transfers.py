"""Transferencias entre bolsas (Hito 8): registro inmutable de movimientos entre bolsas.

Conserva los datos del Hito 7: solo agrega la tabla `transfers` (RN-40), sus índices y un
disparador que rechaza UPDATE y DELETE (RN-43, principio 3.4): una transferencia nunca se edita ni
se borra; un error se corrige con otra en sentido contrario. Siempre en colones, sin moneda ni tipo
de cambio. Restricciones: monto > 0 y origen distinto del destino (RN-41), motivo permitido
(sección 9, incluido `cierre_de_mes`, reservado para el Hito 9), mes `YYYY-MM`, nota de hasta 140
caracteres, y claves foráneas a `pockets` con ON DELETE RESTRICT.

El downgrade borra datos: se niega si hay transferencias, salvo con
ALLOW_DESTRUCTIVE_DOWNGRADE=true (ver README).

Revision ID: 0007_transfers
Revises: 0006_pockets_goals
Create Date: 2026-11-11
"""

import os
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007_transfers"
down_revision: str | None = "0006_pockets_goals"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ALLOW_ENV = "ALLOW_DESTRUCTIVE_DOWNGRADE"
MONTH_FORMAT = "month ~ '^[0-9]{4}-(0[1-9]|1[0-2])$'"
INDEXES = (
    ("ix_transfers_month", ["month"]),
    ("ix_transfers_from_month", ["from_pocket_id", "month"]),
    ("ix_transfers_to_month", ["to_pocket_id", "month"]),
)

FUNCTION = """
CREATE FUNCTION pp_transfers_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION
    'Una transferencia no se edita ni se borra (RN-43): se corrige con otra en sentido contrario.'
    USING ERRCODE = 'restrict_violation';
END $$;
"""
TRIGGER = "trg_transfers_immutable"


def upgrade() -> None:
    op.create_table(
        "transfers",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("transfer_date", sa.Date(), nullable=False),
        sa.Column("month", sa.CHAR(7), nullable=False),  # mes de la fecha (presupuestario)
        sa.Column(
            "from_pocket_id",
            sa.BigInteger(),
            sa.ForeignKey("pockets.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "to_pocket_id",
            sa.BigInteger(),
            sa.ForeignKey("pockets.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("amount", sa.BigInteger(), nullable=False),  # colones
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint("amount > 0", name="ck_transfers_amount"),
        sa.CheckConstraint("from_pocket_id <> to_pocket_id", name="ck_transfers_distinct"),
        sa.CheckConstraint(
            "reason IN ('cubrir_sobregasto','reasignacion','cierre_de_mes','ajuste')",
            name="ck_transfers_reason",
        ),
        sa.CheckConstraint(MONTH_FORMAT, name="ck_transfers_month"),
        sa.CheckConstraint("note IS NULL OR char_length(note) <= 140", name="ck_transfers_note"),
    )
    for name, columns in INDEXES:
        op.create_index(name, "transfers", columns)
    op.execute(FUNCTION)
    op.execute(
        f"CREATE TRIGGER {TRIGGER} BEFORE UPDATE OR DELETE ON transfers "
        "FOR EACH ROW EXECUTE FUNCTION pp_transfers_immutable()"
    )


def _has_data(connection: sa.Connection) -> bool:
    return bool(connection.execute(sa.text("SELECT EXISTS (SELECT 1 FROM transfers)")).scalar())


def downgrade() -> None:
    if os.environ.get(ALLOW_ENV, "").strip().lower() != "true" and _has_data(op.get_bind()):
        raise RuntimeError(
            "Downgrade de 0007_transfers cancelado: hay transferencias, y se perderían. Haz un "
            f"respaldo (README) y, solo si estás seguro, repite con {ALLOW_ENV}=true."
        )
    op.execute(f"DROP TRIGGER IF EXISTS {TRIGGER} ON transfers")
    op.execute("DROP FUNCTION IF EXISTS pp_transfers_immutable()")
    for name, _ in INDEXES:
        op.drop_index(name, table_name="transfers")
    op.drop_table("transfers")
