"""Almacén OAuth en Postgres (SQLAlchemy Core). Solo guarda hashes de códigos y tokens."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import (
    CHAR,
    Boolean,
    Column,
    DateTime,
    Engine,
    ForeignKey,
    MetaData,
    String,
    Table,
    Text,
    func,
    insert,
    select,
    update,
)

from puro_pockets.services.oauth import CodeRecord, TokenRecord

metadata = MetaData()

oauth_clients = Table(
    "oauth_clients",
    metadata,
    Column("client_id", String(64), primary_key=True),
    Column("client_metadata", Text, nullable=False),
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
)

oauth_authorization_codes = Table(
    "oauth_authorization_codes",
    metadata,
    Column("code_hash", CHAR(64), primary_key=True),
    Column("client_id", String(64), ForeignKey("oauth_clients.client_id"), nullable=False),
    Column("redirect_uri", Text, nullable=False),
    Column("redirect_uri_provided_explicitly", Boolean, nullable=False),
    Column("code_challenge", Text, nullable=False),
    Column("scopes", Text, nullable=False),
    Column("resource", Text, nullable=False),
    Column("expires_at", DateTime(timezone=True), nullable=False),
    Column("used_at", DateTime(timezone=True)),
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
)


def _token_table(name: str, with_used_at: bool) -> Table:
    columns = [
        Column("token_hash", CHAR(64), primary_key=True),
        Column("client_id", String(64), ForeignKey("oauth_clients.client_id"), nullable=False),
        Column("family_id", String(36), nullable=False),
        Column("scopes", Text, nullable=False),
        Column("resource", Text, nullable=False),
        Column("expires_at", DateTime(timezone=True), nullable=False),
        Column("revoked_at", DateTime(timezone=True)),
        Column("created_at", DateTime(timezone=True), server_default=func.now()),
    ]
    if with_used_at:
        columns.append(Column("used_at", DateTime(timezone=True)))
    return Table(name, metadata, *columns)


oauth_access_tokens = _token_table("oauth_access_tokens", with_used_at=False)
oauth_refresh_tokens = _token_table("oauth_refresh_tokens", with_used_at=True)


def _dt(ts: float | None) -> datetime | None:
    return None if ts is None else datetime.fromtimestamp(ts, tz=UTC)


def _ts(value: datetime | None) -> float | None:
    return None if value is None else value.timestamp()


def _token_row(record: TokenRecord, with_used_at: bool) -> dict:
    row = {
        "token_hash": record.token_hash,
        "client_id": record.client_id,
        "family_id": record.family_id,
        "scopes": " ".join(record.scopes),
        "resource": record.resource,
        "expires_at": _dt(record.expires_at),
        "revoked_at": _dt(record.revoked_at),
    }
    if with_used_at:
        row["used_at"] = _dt(record.used_at)
    return row


def _token_record(row) -> TokenRecord:
    return TokenRecord(
        token_hash=row.token_hash,
        client_id=row.client_id,
        family_id=row.family_id,
        scopes=tuple(row.scopes.split()),
        resource=row.resource,
        expires_at=_ts(row.expires_at),
        revoked_at=_ts(row.revoked_at),
        used_at=_ts(getattr(row, "used_at", None)),
    )


class SqlOAuthStore:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def count_clients(self) -> int:
        with self._engine.connect() as conn:
            return conn.execute(select(func.count()).select_from(oauth_clients)).scalar_one()

    def get_client(self, client_id: str) -> str | None:
        with self._engine.connect() as conn:
            return conn.execute(
                select(oauth_clients.c.client_metadata).where(
                    oauth_clients.c.client_id == client_id
                )
            ).scalar_one_or_none()

    def save_client(self, client_id: str, metadata_json: str) -> None:
        with self._engine.begin() as conn:
            conn.execute(
                insert(oauth_clients).values(client_id=client_id, client_metadata=metadata_json)
            )

    def save_code(self, record: CodeRecord) -> None:
        with self._engine.begin() as conn:
            conn.execute(
                insert(oauth_authorization_codes).values(
                    code_hash=record.code_hash,
                    client_id=record.client_id,
                    redirect_uri=record.redirect_uri,
                    redirect_uri_provided_explicitly=record.redirect_uri_provided_explicitly,
                    code_challenge=record.code_challenge,
                    scopes=" ".join(record.scopes),
                    resource=record.resource,
                    expires_at=_dt(record.expires_at),
                )
            )

    def get_code(self, code_hash: str) -> CodeRecord | None:
        t = oauth_authorization_codes
        with self._engine.connect() as conn:
            row = conn.execute(select(t).where(t.c.code_hash == code_hash)).first()
        if row is None:
            return None
        return CodeRecord(
            code_hash=row.code_hash,
            client_id=row.client_id,
            redirect_uri=row.redirect_uri,
            redirect_uri_provided_explicitly=row.redirect_uri_provided_explicitly,
            code_challenge=row.code_challenge,
            scopes=tuple(row.scopes.split()),
            resource=row.resource,
            expires_at=_ts(row.expires_at),
            used_at=_ts(row.used_at),
        )

    def consume_code(self, code_hash: str, now: float) -> bool:
        """Marca el código como usado si sigue vigente. Atómico: un solo UPDATE condicional."""
        t = oauth_authorization_codes
        with self._engine.begin() as conn:
            result = conn.execute(
                update(t)
                .where(t.c.code_hash == code_hash, t.c.used_at.is_(None), t.c.expires_at > _dt(now))
                .values(used_at=_dt(now))
            )
            return result.rowcount == 1

    def save_token_pair(self, access: TokenRecord, refresh: TokenRecord) -> None:
        with self._engine.begin() as conn:
            conn.execute(insert(oauth_access_tokens).values(**_token_row(access, False)))
            conn.execute(insert(oauth_refresh_tokens).values(**_token_row(refresh, True)))

    def _get_token(self, table: Table, token_hash: str) -> TokenRecord | None:
        with self._engine.connect() as conn:
            row = conn.execute(select(table).where(table.c.token_hash == token_hash)).first()
        return None if row is None else _token_record(row)

    def get_access_token(self, token_hash: str) -> TokenRecord | None:
        return self._get_token(oauth_access_tokens, token_hash)

    def get_refresh_token(self, token_hash: str) -> TokenRecord | None:
        return self._get_token(oauth_refresh_tokens, token_hash)

    def consume_refresh_token(self, token_hash: str, now: float) -> bool:
        t = oauth_refresh_tokens
        with self._engine.begin() as conn:
            result = conn.execute(
                update(t)
                .where(
                    t.c.token_hash == token_hash,
                    t.c.used_at.is_(None),
                    t.c.revoked_at.is_(None),
                    t.c.expires_at > _dt(now),
                )
                .values(used_at=_dt(now))
            )
            return result.rowcount == 1

    def revoke_family(self, family_id: str, now: float) -> None:
        with self._engine.begin() as conn:
            for table in (oauth_access_tokens, oauth_refresh_tokens):
                conn.execute(
                    update(table)
                    .where(table.c.family_id == family_id, table.c.revoked_at.is_(None))
                    .values(revoked_at=_dt(now))
                )

    def revoke_all(self, now: float) -> int:
        total = 0
        with self._engine.begin() as conn:
            for table in (oauth_access_tokens, oauth_refresh_tokens):
                total += conn.execute(
                    update(table).where(table.c.revoked_at.is_(None)).values(revoked_at=_dt(now))
                ).rowcount
        return total
