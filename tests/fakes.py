"""Dobles de prueba compartidos."""

from __future__ import annotations

from dataclasses import replace
from datetime import date

from puro_pockets.domain.balances import (
    AllocationEntry,
    ExpenseEntry,
    IncomeKind,
    TransferEntry,
)
from puro_pockets.domain.categories import Category
from puro_pockets.domain.errors import (
    AlreadyVoided,
    CategoryAlreadyExists,
    ExtraAlreadyDistributed,
    GoalAlreadyActive,
    InitialBalanceAlreadyLoaded,
    MovementNotFound,
    MovementVoided,
    PocketAlreadyExists,
    RecurringAlreadyPaid,
    RecurringNameTaken,
)
from puro_pockets.domain.goals import Goal, GoalStatus, balance_function, reached
from puro_pockets.domain.ledger import MovementKind
from puro_pockets.domain.money import Converted, Currency
from puro_pockets.domain.pockets import Behavior, Pocket, normalize_name
from puro_pockets.domain.recurring import RecurringRef, RecurringTemplate
from puro_pockets.services.ledger import (
    ExpenseRow,
    IncomeRow,
    OperationTaken,
    StoredOperation,
)
from puro_pockets.services.oauth import CodeRecord, TokenRecord
from puro_pockets.services.records import LedgerSnapshot, TransferRow


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
        self.recurring = []  # RecurringTemplate
        self.goals = []  # Goal
        self.transfers = []  # TransferRow (nunca se editan ni se borran, RN-43)
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

    def _add_income(
        self, kind, income_date, budget_month, money, lines, pending=False, source=None
    ):
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
                pending,
                source,
            )
        )
        self.lines.extend((income_id, line) for line in lines)
        if lines:
            self._settle_goals(income_date)
        return income_id

    def record_distributed_income(self, kind, income_date, budget_month, lines):
        total = sum(line.amount for line in lines)
        money = Converted(Currency.CRC, total, None, total)
        return self._add_income(kind, income_date, budget_month, money, lines)

    def _live_incomes(self):
        # Como LIVE_INCOME en SQL: vigentes y repartidos (los extras pendientes no cuentan, RN-06)
        return {r.id: r for r in self.incomes if not r.voided and not r.pending}

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

    def transfer_entries(self):
        return [
            TransferEntry(t.from_pocket_id, t.to_pocket_id, t.month, t.amount)
            for t in self.transfers
        ]

    def _settle_goals(self, on):
        """Como el almacén SQL: `reached` con el saldo oficial (11.2), en la misma operación."""
        balance_of = balance_function(
            self.allocation_entries(), self.expense_entries(), self.transfer_entries()
        )
        hits = dict(reached(self.goals, balance_of, on))
        self.goals = [
            replace(g, status=GoalStatus.ACHIEVED, achieved_on=hits[g.id]) if g.id in hits else g
            for g in self.goals
        ]
        return list(hits)


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
            income.kind,
            income.income_date,
            income.budget_month,
            income.money,
            lines,
            income.pending,
            income.source,
        )
        response = respond(income_id)
        self._save_operation(operation, response)
        return response

    def distribute_extra(self, income_id, lines, operation, respond, on=None):
        if operation.operation_id in self.operations:
            raise OperationTaken()
        index = next(i for i, r in enumerate(self.incomes) if r.id == income_id)
        row = self.incomes[index]
        ref = f"I-{income_id}"
        if row.voided:
            raise MovementVoided(ref)
        if not row.pending or row.kind is not IncomeKind.EXTRA:
            raise ExtraAlreadyDistributed(ref)
        self.writes += 1
        self.incomes[index] = replace(row, pending=False)
        self.lines.extend((income_id, line) for line in lines)
        self._settle_goals(on or date.today())
        response = respond()
        self._save_operation(operation, response)
        return response

    def record_expense(self, expense, operation, respond):
        if operation.operation_id in self.operations:
            raise OperationTaken()
        if expense.recurring_id is not None and expense.recurring_id in self.recurring_payments(
            expense.month
        ):
            raise RecurringAlreadyPaid(str(RecurringRef(expense.recurring_id)), str(expense.month))
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
                expense.recurring_id,
            )
        )
        response = respond(expense_id)
        self._save_operation(operation, response)
        return response

    def void_movement(self, ref, reason, voided_at, operation, response, on=None):
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
        if ref.kind is MovementKind.EXPENSE:
            self._settle_goals(on or voided_at.date())
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

    def extra_income_total(self, month):
        return sum(
            r.amount
            for r in self.incomes
            if r.kind is IncomeKind.EXTRA
            and r.budget_month == month
            and not r.voided
            and not r.pending
        )

    def pending_extras(self):
        return [
            r for r in self.incomes if r.kind is IncomeKind.EXTRA and r.pending and not r.voided
        ]

    def distributed_extras(self, limit):
        rows = [
            r for r in self.incomes if r.kind is IncomeKind.EXTRA and not r.pending and not r.voided
        ]
        return sorted(rows, key=lambda r: (r.income_date, r.id), reverse=True)[:limit]

    # --- Gastos fijos ---

    def list_recurring(self):
        return list(self.recurring)

    def _name_free(self, name, except_id=None):
        key = normalize_name(name)
        if any(
            t.active and t.id != except_id and normalize_name(t.name) == key for t in self.recurring
        ):
            raise RecurringNameTaken()

    def create_recurring(self, new, operation, respond):
        if operation.operation_id in self.operations:
            raise OperationTaken()
        self._name_free(new.name)
        self.writes += 1
        recurring_id = len(self.recurring) + 1
        self.recurring.append(
            RecurringTemplate(
                recurring_id,
                new.name,
                new.currency,
                new.day_of_month,
                new.pocket_id,
                new.category_id,
                new.start_month,
                True,
                ((new.start_month, new.original_amount),),
            )
        )
        response = respond(recurring_id)
        self._save_operation(operation, response)
        return response

    def update_recurring(self, change, operation, respond):
        if operation.operation_id in self.operations:
            raise OperationTaken()
        index = next(i for i, t in enumerate(self.recurring) if t.id == change.recurring_id)
        template = self.recurring[index]
        if change.name is not None:
            self._name_free(change.name, template.id)
        amounts = template.amounts
        if change.amount is not None:
            since, amount = change.amount
            amounts = tuple(sorted({**dict(amounts), since: amount}.items()))
        self.writes += 1
        self.recurring[index] = replace(
            template,
            name=change.name if change.name is not None else template.name,
            day_of_month=change.day_of_month or template.day_of_month,
            pocket_id=change.pocket_id or template.pocket_id,
            category_id=change.category_id or template.category_id,
            amounts=amounts,
        )
        response = respond()
        self._save_operation(operation, response)
        return response

    def deactivate_recurring(self, recurring_id, at, operation, respond):
        if operation.operation_id in self.operations:
            raise OperationTaken()
        index = next(i for i, t in enumerate(self.recurring) if t.id == recurring_id)
        self.writes += 1
        self.recurring[index] = replace(self.recurring[index], active=False)
        response = respond()
        self._save_operation(operation, response)
        return response

    def recurring_payments(self, month):
        return {
            e.recurring_id: e.id
            for e in self.expenses
            if e.recurring_id is not None and e.month == month and not e.voided
        }

    # --- Bolsas flexibles y metas (Hito 7) ---

    def future_allocation_months(self, after):
        return sorted(m for m in self.allocations if m > after)

    def create_pocket(self, new, operation, respond):
        if operation.operation_id in self.operations:
            raise OperationTaken()
        if any(normalize_name(p.name) == normalize_name(new.name) for p in self.pockets):
            raise PocketAlreadyExists()
        self.writes += 1
        pocket_id = max((p.id for p in self.pockets), default=0) + 1
        self.pockets.append(Pocket(pocket_id, new.name, new.behavior))
        self.allocations[new.month] = {**new.existing, pocket_id: new.share}
        response = respond(pocket_id)
        self._save_operation(operation, response)
        return response

    def _snapshot(self, pocket_ids):
        ids = set(pocket_ids)
        return LedgerSnapshot(
            {p.id: p for p in self.pockets if p.id in ids},
            [e for e in self.allocation_entries() if e.pocket_id in ids],
            [e for e in self.expense_entries() if e.pocket_id in ids],
            [
                t
                for t in self.transfer_entries()
                if t.from_pocket_id in ids or t.to_pocket_id in ids
            ],
        )

    def archive_pocket(self, pocket_id, at, months, operation, respond, verify=None):
        if operation.operation_id in self.operations:
            raise OperationTaken()
        if verify is not None:
            verify(self._snapshot([pocket_id]))
        self.writes += 1
        self.pockets = [replace(p, active=False) if p.id == pocket_id else p for p in self.pockets]
        self.goals = [
            replace(g, archived=True) if g.pocket_id == pocket_id else g for g in self.goals
        ]
        for month, rows in months.items():
            self.allocations[month] = dict(rows)
        response = respond()
        self._save_operation(operation, response)
        return response

    def list_goals(self):
        return list(self.goals)

    def create_goal(self, new, operation, respond, on):
        if operation.operation_id in self.operations:
            raise OperationTaken()
        if any(g.live and g.pocket_id == new.pocket_id for g in self.goals):
            raise GoalAlreadyActive("otra")
        self.writes += 1
        goal_id = len(self.goals) + 1
        self.goals.append(
            Goal(
                goal_id,
                new.pocket_id,
                new.name,
                new.target_amount,
                new.target_date,
                GoalStatus.ACTIVE,
                None,
                new.created_on,
            )
        )
        self._settle_goals(on)
        response = respond(goal_id)
        self._save_operation(operation, response)
        return response

    def update_goal(self, change, operation, respond, on):
        if operation.operation_id in self.operations:
            raise OperationTaken()
        index = next(i for i, g in enumerate(self.goals) if g.id == change.goal_id)
        goal = self.goals[index]
        status = change.status or goal.status
        if status is GoalStatus.ACTIVE and any(
            g.live and g.pocket_id == goal.pocket_id and g.id != goal.id for g in self.goals
        ):
            raise GoalAlreadyActive("otra")
        self.writes += 1
        self.goals[index] = replace(
            goal,
            target_amount=change.target_amount or goal.target_amount,
            target_date=None
            if change.clear_target_date
            else (change.target_date or goal.target_date),
            status=status,
        )
        self._settle_goals(on)
        response = respond()
        self._save_operation(operation, response)
        return response

    # --- Transferencias (Hito 8) ---

    def record_transfer(self, new, operation, verify, on):
        if operation.operation_id in self.operations:
            raise OperationTaken()
        respond = verify(self._snapshot([new.from_pocket_id, new.to_pocket_id]))
        self.writes += 1
        transfer_id = len(self.transfers) + 1
        self.transfers.append(
            TransferRow(
                transfer_id,
                new.transfer_date,
                new.month,
                new.from_pocket_id,
                new.to_pocket_id,
                new.amount,
                new.reason,
                new.note,
            )
        )
        self._settle_goals(on)
        response = respond(transfer_id)
        self._save_operation(operation, response)
        return response

    def list_transfers(self, month, pocket_id, limit):
        rows = [
            t
            for t in self.transfers
            if (month is None or t.month == month)
            and (pocket_id is None or pocket_id in (t.from_pocket_id, t.to_pocket_id))
        ]
        return sorted(rows, key=lambda t: (t.transfer_date, t.id), reverse=True)[:limit]
