"""Tablas de autenticación OAuth (Hito 3). Solo se guardan hashes SHA-256 de códigos y tokens.

Revision ID: 0002_oauth
Revises: 0001_base
Create Date: 2026-11-09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_oauth"
down_revision: str | None = "0001_base"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        )
    ]


def upgrade() -> None:
    op.create_table(
        "oauth_clients",
        sa.Column("client_id", sa.String(64), primary_key=True),
        # Metadatos registrados (RFC 7591) en JSON. Solo clientes públicos: no hay secreto.
        sa.Column("client_metadata", sa.Text(), nullable=False),
        *_timestamps(),
    )
    op.create_table(
        "oauth_authorization_codes",
        sa.Column("code_hash", sa.CHAR(64), primary_key=True),
        sa.Column(
            "client_id",
            sa.String(64),
            sa.ForeignKey("oauth_clients.client_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("redirect_uri", sa.Text(), nullable=False),
        sa.Column("redirect_uri_provided_explicitly", sa.Boolean(), nullable=False),
        sa.Column("code_challenge", sa.Text(), nullable=False),
        sa.Column("scopes", sa.Text(), nullable=False),
        sa.Column("resource", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
    )
    for table in ("oauth_access_tokens", "oauth_refresh_tokens"):
        extra = (
            [sa.Column("used_at", sa.DateTime(timezone=True), nullable=True)]
            if table == "oauth_refresh_tokens"
            else []
        )
        op.create_table(
            table,
            sa.Column("token_hash", sa.CHAR(64), primary_key=True),
            sa.Column(
                "client_id",
                sa.String(64),
                sa.ForeignKey("oauth_clients.client_id", ondelete="CASCADE"),
                nullable=False,
            ),
            # Cadena de tokens nacida de un mismo código; reutilizar un refresco la revoca entera
            sa.Column("family_id", sa.String(36), nullable=False, index=True),
            sa.Column("scopes", sa.Text(), nullable=False),
            sa.Column("resource", sa.Text(), nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
            *extra,
            *_timestamps(),
        )


def downgrade() -> None:
    op.drop_table("oauth_refresh_tokens")
    op.drop_table("oauth_access_tokens")
    op.drop_table("oauth_authorization_codes")
    op.drop_table("oauth_clients")
