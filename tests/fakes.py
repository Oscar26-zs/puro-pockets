"""Dobles de prueba compartidos."""

from __future__ import annotations

from dataclasses import replace

from puro_pockets.domain.balances import AllocationEntry, ExpenseEntry, IncomeKind
from puro_pockets.domain.categories import Category
from puro_pockets.domain.errors import (
    AlreadyVoided,
    CategoryAlreadyExists,
    InitialBalanceAlreadyLoaded,
    MovementNotFound,
)
from puro_pockets.domain.ledger import MovementKind
from puro_pockets.domain.money import Converted, Currency
from puro_pockets.domain.pockets import Behavior, Pocket, normalize_name
from puro_pockets.services.ledger import (
    ExpenseRow,
    IncomeRow,
    OperationTaken,
    StoredOperation,
)
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
    """Almacén del presupuesto en memoria con la misma semántica que el almacén SQL.

    Como en la base, lo anulado no cuenta en las lecturas y nada se borra.
    """

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
        self.incomes = []  # IncomeRow
        self.lines = []  # (income_id, AllocationLine)
        self.expenses = []  # ExpenseRow
        self.categories = []  # Category
        self.operations = {}  # operation_id -> StoredOperation
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
        return any(r.kind is IncomeKind.INITIAL_BALANCE and not r.voided for r in self.incomes)

    def _add_income(self, kind, income_date, budget_month, money, lines):
        if kind is IncomeKind.INITIAL_BALANCE and self.has_initial_balance():
            raise InitialBalanceAlreadyLoaded()
        self.writes += 1
        income_id = len(self.incomes) + 1
        self.incomes.append(
            IncomeRow(
                income_id,
                kind,
                income_date,
                budget_month,
                money.currency,
                money.original_amount,
                money.exchange_rate,
                money.amount_crc,
                False,
                None,
            )
        )
        self.lines.extend((income_id, line) for line in lines)
        return income_id

    def record_distributed_income(self, kind, income_date, budget_month, lines):
        total = sum(line.amount for line in lines)
        money = Converted(Currency.CRC, total, None, total)
        return self._add_income(kind, income_date, budget_month, money, lines)

    def _live_incomes(self):
        return {r.id: r for r in self.incomes if not r.voided}

    def allocation_entries(self):
        live = self._live_incomes()
        return [
            AllocationEntry(line.pocket_id, live[iid].budget_month, line.amount, live[iid].kind)
            for iid, line in self.lines
            if iid in live
        ]

    def distributed_income_total(self):
        return sum(r.amount for r in self._live_incomes().values())

    def expense_entries(self):
        return [ExpenseEntry(e.pocket_id, e.month, e.amount) for e in self.expenses if not e.voided]

    def expense_total(self):
        return sum(e.amount for e in self.expenses if not e.voided)


class InMemoryLedgerStore(InMemoryBudgetStore):
    """Almacén de movimientos en memoria (Hito 5), con la semántica del almacén SQL."""

    def list_categories(self):
        return list(self.categories)

    def create_category(self, name, pocket_id):
        key = normalize_name(name)
        if any(normalize_name(c.name) == key for c in self.categories):
            raise CategoryAlreadyExists(name)
        category = Category(len(self.categories) + 1, name, pocket_id)
        self.categories.append(category)
        return category

    def get_operation(self, operation_id):
        return self.operations.get(operation_id)

    def _save_operation(self, operation, response):
        if operation.operation_id in self.operations:
            raise OperationTaken()
        self.operations[operation.operation_id] = StoredOperation(
            operation.tool, operation.fingerprint, response
        )

    def record_income(self, income, lines, operation, respond):
        if operation.operation_id in self.operations:
            raise OperationTaken()
        income_id = self._add_income(
            income.kind, income.income_date, income.budget_month, income.money, lines
        )
        response = respond(income_id)
        self._save_operation(operation, response)
        return response

    def record_expense(self, expense, operation, respond):
        if operation.operation_id in self.operations:
            raise OperationTaken()
        self.writes += 1
        expense_id = len(self.expenses) + 1
        money = expense.money
        self.expenses.append(
            ExpenseRow(
                expense_id,
                expense.expense_date,
                expense.month,
                expense.pocket_id,
                expense.category_id,
                expense.description,
                money.currency,
                money.original_amount,
                money.exchange_rate,
                money.amount_crc,
                False,
                None,
            )
        )
        response = respond(expense_id)
        self._save_operation(operation, response)
        return response

    def void_movement(self, ref, reason, voided_at, operation, response):
        if operation.operation_id in self.operations:
            raise OperationTaken()
        rows = self.incomes if ref.kind is MovementKind.INCOME else self.expenses
        index = next((i for i, r in enumerate(rows) if r.id == ref.number), None)
        if index is None:
            raise MovementNotFound(str(ref))
        if rows[index].voided:
            raise AlreadyVoided(str(ref))
        self.writes += 1
        rows[index] = replace(rows[index], voided=True, void_reason=reason)
        self._save_operation(operation, response)

    def get_income(self, income_id):
        return next((r for r in self.incomes if r.id == income_id), None)

    def get_expense(self, expense_id):
        return next((r for r in self.expenses if r.id == expense_id), None)

    def income_lines(self, income_id):
        return [line for iid, line in self.lines if iid == income_id]

    def recent_incomes(self, month, include_voided, limit):
        rows = [
            r
            for r in self.incomes
            if (month is None or r.budget_month == month) and (include_voided or not r.voided)
        ]
        return sorted(rows, key=lambda r: (r.income_date, r.id), reverse=True)[:limit]

    def recent_expenses(self, month, pocket_id, include_voided, limit):
        rows = [
            r
            for r in self.expenses
            if (month is None or r.month == month)
            and (pocket_id is None or r.pocket_id == pocket_id)
            and (include_voided or not r.voided)
        ]
        return sorted(rows, key=lambda r: (r.expense_date, r.id), reverse=True)[:limit]

    def expenses_in_month(self, month):
        return [r for r in self.expenses if r.month == month and not r.voided]

    def base_income_total(self, month):
        return sum(
            r.amount
            for r in self.incomes
            if r.kind is IncomeKind.BASE and r.budget_month == month and not r.voided
        )
