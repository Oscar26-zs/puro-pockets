"""Dobles de prueba compartidos."""

from __future__ import annotations

from dataclasses import replace

from puro_pockets.services.oauth import CodeRecord, TokenRecord


class InMemoryOAuthStore:
    """Almacén OAuth en memoria con la misma semántica que el almacén SQL."""

    def __init__(self) -> None:
        self.clients: dict[str, str] = {}
        self.codes: dict[str, CodeRecord] = {}
        self.access: dict[str, TokenRecord] = {}
        self.refresh: dict[str, TokenRecord] = {}

    def count_clients(self) -> int:
        return len(self.clients)

    def get_client(self, client_id: str) -> str | None:
        return self.clients.get(client_id)

    def save_client(self, client_id: str, metadata_json: str) -> None:
        self.clients[client_id] = metadata_json

    def save_code(self, record: CodeRecord) -> None:
        self.codes[record.code_hash] = record

    def get_code(self, code_hash: str) -> CodeRecord | None:
        return self.codes.get(code_hash)

    def consume_code(self, code_hash: str, now: float) -> bool:
        record = self.codes.get(code_hash)
        if record is None or record.used_at is not None or record.expires_at <= now:
            return False
        self.codes[code_hash] = replace(record, used_at=now)
        return True

    def save_token_pair(self, access: TokenRecord, refresh: TokenRecord) -> None:
        self.access[access.token_hash] = access
        self.refresh[refresh.token_hash] = refresh

    def get_access_token(self, token_hash: str) -> TokenRecord | None:
        return self.access.get(token_hash)

    def get_refresh_token(self, token_hash: str) -> TokenRecord | None:
        return self.refresh.get(token_hash)

    def consume_refresh_token(self, token_hash: str, now: float) -> bool:
        record = self.refresh.get(token_hash)
        if (
            record is None
            or record.used_at is not None
            or record.revoked_at is not None
            or record.expires_at <= now
        ):
            return False
        self.refresh[token_hash] = replace(record, used_at=now)
        return True

    def revoke_family(self, family_id: str, now: float) -> None:
        for table in (self.access, self.refresh):
            for key, record in list(table.items()):
                if record.family_id == family_id and record.revoked_at is None:
                    table[key] = replace(record, revoked_at=now)

    def revoke_all(self, now: float) -> int:
        count = 0
        for table in (self.access, self.refresh):
            for key, record in list(table.items()):
                if record.revoked_at is None:
                    table[key] = replace(record, revoked_at=now)
                    count += 1
        return count


class FakeClock:
    def __init__(self, now: float = 1_000_000.0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds
