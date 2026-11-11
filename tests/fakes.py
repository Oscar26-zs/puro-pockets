"""Dobles de prueba compartidos."""

from __future__ import annotations

from dataclasses import replace

from puro_pockets.domain.balances import AllocationEntry, IncomeKind
from puro_pockets.domain.errors import InitialBalanceAlreadyLoaded
from puro_pockets.domain.pockets import Behavior, Pocket
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


class InMemoryBudgetStore:
    """Almacén del presupuesto en memoria con la misma semántica que el almacén SQL."""

    def __init__(self, pockets=None) -> None:
        self.pockets = list(
            pockets
            if pockets is not None
            else [
                Pocket(1, "Necesidades", Behavior.CONSUMO),
                Pocket(2, "Ahorro", Behavior.ACUMULABLE),
                Pocket(3, "Gustos", Behavior.CONSUMO),
            ]
        )
        self.allocations = {}  # Month -> {pocket_id: percentage}
        self.incomes = []  # (id, kind, income_date, budget_month, amount)
        self.lines = []  # (income_id, AllocationLine)
        self.writes = 0

    def list_pockets(self):
        return sorted(self.pockets, key=lambda p: p.id)

    def allocation_months(self, up_to):
        return sorted(m for m in self.allocations if m <= up_to)

    def allocation_rows(self, month):
        return dict(self.allocations.get(month, {}))

    def replace_allocation(self, month, rows):
        self.writes += 1
        self.allocations[month] = dict(rows)

    def has_initial_balance(self):
        return any(kind is IncomeKind.INITIAL_BALANCE for _, kind, *_ in self.incomes)

    def record_distributed_income(self, kind, income_date, budget_month, lines):
        if kind is IncomeKind.INITIAL_BALANCE and self.has_initial_balance():
            raise InitialBalanceAlreadyLoaded()
        self.writes += 1
        income_id = len(self.incomes) + 1
        amount = sum(line.amount for line in lines)
        self.incomes.append((income_id, kind, income_date, budget_month, amount))
        self.lines.extend((income_id, line) for line in lines)
        return income_id

    def allocation_entries(self):
        info = {i[0]: i for i in self.incomes}
        return [
            AllocationEntry(line.pocket_id, info[iid][3], line.amount, info[iid][1])
            for iid, line in self.lines
        ]

    def distributed_income_total(self):
        return sum(i[4] for i in self.incomes)
