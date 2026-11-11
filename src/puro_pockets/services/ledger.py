"""Casos de uso de los movimientos: salario, gastos, anulación, categorías y consultas (Hito 5);
extras y gastos fijos (Hito 6, en `services/extras.py` y `services/recurring.py`).

Las reglas viven en `domain/`; aquí se orquestan el almacén, el reloj y la idempotencia. El almacén
es síncrono, así que sus llamadas corren en un hilo. Las respuestas son modelos que las tools
devuelven tal cual; las de escritura se guardan con la clave de operación para devolver el
resultado original en un reintento. Los registros nunca incluyen montos ni descripciones.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from functools import partial
from typing import Literal

from pydantic import BaseModel, Field

from puro_pockets.domain.allocation import (
    allocate_by_percentages,
    pick_source_month,
    resolve_allocation,
)
from puro_pockets.domain.balances import (
    AllocationEntry,
    ExpenseEntry,
    IncomeKind,
    accumulated_balance,
    assigned,
    percent_used,
    pocket_balance,
    spent,
)
from puro_pockets.domain.categories import (
    UNCLASSIFIED,
    Category,
    find_category,
    validate_category_name,
)
from puro_pockets.domain.errors import (
    AlreadyVoided,
    CategoryAlreadyExists,
    DomainError,
    MovementNotFound,
    RecurringAlreadyPaid,
    RecurringInactive,
)
from puro_pockets.domain.idempotency import fingerprint, validate_operation_id
from puro_pockets.domain.ledger import (
    MovementKind,
    MovementRef,
    income_budget_month,
    movement_date,
    parse_date,
    validate_description,
    validate_reason,
)
from puro_pockets.domain.money import (
    Converted,
    convert,
    format_original,
    format_rate,
    parse_currency,
)
from puro_pockets.domain.months import Month
from puro_pockets.domain.pockets import (
    Behavior,
    Pocket,
    find_pocket,
    normalize_name,
    ordered_active,
)
from puro_pockets.domain.recurring import RecurringRef, RecurringTemplate, find_recurring
from puro_pockets.services.budget import AllocationLine
from puro_pockets.services.extras import ExtrasMixin
from puro_pockets.services.ledger_core import (
    AllocationShare,
    BalanceKindName,
    BehaviorName,
    CurrencyName,
    PocketFigure,
    UnassignedSummary,
    figure,
    logger,
    parse_limit,
    unassigned_summary,
)
from puro_pockets.services.records import (
    ExpenseRow,
    IncomeRow,
    LedgerStore,
    NewExpense,
    NewIncome,
    NewRecurring,
    Operation,
    OperationTaken,
    RecurringChange,
    StoredOperation,
)
from puro_pockets.services.recurring import RecurringMixin

__all__ = [
    "AllocationShare",
    "BalanceKindName",
    "ExpenseRow",
    "IncomeRow",
    "LedgerService",
    "LedgerStore",
    "NewExpense",
    "NewIncome",
    "NewRecurring",
    "Operation",
    "OperationTaken",
    "PocketFigure",
    "RecurringChange",
    "StoredOperation",
]

DEFAULT_LIST_LIMIT, MAX_LIST_LIMIT = 20, 100
DEFAULT_TOP_LIMIT, MAX_TOP_LIMIT = 5, 20


# --- Respuestas (las tools las devuelven tal cual) ---


class IncomeResult(BaseModel):
    saved: bool = Field(description="True solo si se guardó el ingreso.")
    reference: str | None = Field(description="Referencia del ingreso (I-n); null si no se guardó.")
    kind: Literal["base"]
    income_date: str
    budget_month: str = Field(description="Mes presupuestario al que pertenece (5.1).")
    currency: CurrencyName
    original_amount: str = Field(description="Monto en su moneda (USD con 2 decimales).")
    exchange_rate: str | None = Field(description="Colones por dólar; null en CRC.")
    amount_crc: int = Field(description="Equivalente en colones, calculado una vez (RN-57).")
    allocation_source_month: str = Field(description="Mes del que vienen los porcentajes (RN-03).")
    items: list[AllocationShare]


class ExpenseResult(BaseModel):
    reference: str = Field(description="Referencia del gasto (G-n).")
    expense_date: str
    month: str = Field(description="Mes calendario del gasto (RN-32).")
    pocket: str
    category: str = Field(description='Nombre de la categoría o "pendiente de clasificar".')
    currency: CurrencyName
    original_amount: str
    exchange_rate: str | None
    amount_crc: int
    pocket_balance: PocketFigure = Field(description="Cómo queda la bolsa tras el gasto.")
    overspent: bool = Field(description="True si la bolsa quedó en negativo (RN-37).")
    warning: str | None
    available_pockets: list[PocketFigure] = Field(
        description="Solo con sobregasto: otras bolsas con saldo disponible."
    )
    recurring: str | None = Field(
        default=None, description="Gasto fijo pagado con este gasto (F-n), si lo es."
    )


class VoidResult(BaseModel):
    saved: bool = Field(description="True solo si se anuló; false es la vista previa.")
    reference: str
    movement: Literal["gasto", "ingreso", "extra", "saldo_inicial"]
    date: str
    month: str
    amount_crc: int
    voided_on: str | None
    negative_pockets: list[PocketFigure] = Field(
        description="Bolsas que quedan en negativo al anular (RN-59, RN-37)."
    )
    warning: str | None
    initial_balance_reloadable: bool = Field(
        description="True si se anuló el saldo inicial: ya se puede cargar uno nuevo."
    )


class BolsaStatus(BaseModel):
    pocket: str
    behavior: BehaviorName
    month: str
    assigned: int = Field(description="Asignado por los ingresos del mes (presupuesto original).")
    transfers_in: int = Field(description="Transferencias recibidas (0 hasta el Hito 8).")
    transfers_out: int = Field(description="Transferencias enviadas (0 hasta el Hito 8).")
    adjusted_budget: int = Field(description="Presupuesto ajustado (9.1).")
    spent: int = Field(description="Gastado en el mes.")
    available: int | None = Field(description="Consumo: disponible del mes (11.1).")
    percent_used: int | None = Field(description="Consumo: % usado, entero hacia abajo.")
    balance: int | None = Field(description="Acumulable: saldo histórico (11.2).")
    negative: bool


class SummaryPocket(BaseModel):
    pocket: str
    behavior: BehaviorName
    assigned: int
    spent: int
    available: int | None = Field(description="Consumo: disponible del mes.")
    balance: int | None = Field(description="Acumulable: saldo actual (todo el historial).")
    negative: bool


class SummaryResult(BaseModel):
    month: str
    income_total: int = Field(
        description="Ingresos repartidos del mes (base + extras repartidos); el saldo inicial no "
        "cuenta."
    )
    extra_income_total: int = Field(description="Parte de income_total que son extras repartidos.")
    expense_total: int
    pockets: list[SummaryPocket]
    negative_pockets: list[str]
    unassigned: UnassignedSummary = Field(
        description='Extras "sin asignar" (pendientes de repartir, RN-06), de cualquier mes.'
    )


class CategoryTotal(BaseModel):
    category: str
    amount_crc: int
    count: int
    percent: int = Field(description="% del total gastado en el mes, entero hacia abajo.")


class TopCategoriesResult(BaseModel):
    month: str
    total_spent: int
    items: list[CategoryTotal]


class TransactionItem(BaseModel):
    reference: str
    type: Literal["gasto", "ingreso"]
    kind: str | None = Field(description="Solo ingresos: base, extra o saldo_inicial.")
    date: str
    month: str = Field(description="Gastos: mes calendario; ingresos: mes presupuestario.")
    pocket: str | None
    category: str | None
    description: str | None
    currency: CurrencyName
    original_amount: str
    exchange_rate: str | None
    amount_crc: int
    voided: bool
    void_reason: str | None
    allocation_status: Literal["pendiente", "repartido"] | None = Field(
        default=None, description='Solo ingresos: "pendiente" = extra sin asignar (RN-06).'
    )
    recurring: str | None = Field(default=None, description="Solo gastos: fijo pagado (F-n).")


class TransactionsResult(BaseModel):
    items: list[TransactionItem]
    has_more: bool = Field(description="True si hay más movimientos que el límite.")
    unassigned: UnassignedSummary = Field(
        description='Extras "sin asignar" (pendientes de repartir, RN-06), de cualquier mes.'
    )


class CategoryItem(BaseModel):
    name: str
    pocket: str = Field(description="Bolsa por defecto de la categoría.")


class CategoriesResult(BaseModel):
    items: list[CategoryItem]


# --- Servicio ---


@dataclass(frozen=True)
class _IncomeDraft:
    income_date: date
    budget_month: Month
    money: Converted
    payload: dict


@dataclass(frozen=True)
class _ExpenseRequest:
    amount: object
    currency: object
    exchange_rate: object
    pocket: object
    category: object
    expense_date: object
    description: str | None
    recurring: object


def _blank(value: object) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _name_key(value: object) -> str | None:
    return normalize_name(value) if isinstance(value, str) and value.strip() else None


def _recurring_key(value: object) -> str:
    ref = RecurringRef.match(value)
    if ref is not None:
        return str(ref)
    if not isinstance(value, str):
        raise DomainError("Indica el gasto fijo por su referencia (F-n) o por su nombre.")
    return normalize_name(value)


def _raw_amount(value: object) -> int | str | None:
    """Monto tal como llegó, para la huella (sin `float`); se valida al convertirlo."""
    if _blank(value):
        return None
    if isinstance(value, float):
        raise DomainError('Un monto con decimales debe enviarse como texto, por ejemplo "10.50".')
    if isinstance(value, bool) or not isinstance(value, int | str):
        raise DomainError("El monto debe ser un número positivo.")
    return value.strip() if isinstance(value, str) else value


def _raw_rate(value: object) -> int | str | None:
    if _blank(value):
        return None
    if isinstance(value, float):
        raise DomainError(
            'Un tipo de cambio con decimales debe enviarse como texto, por ejemplo "512.34".'
        )
    if isinstance(value, bool) or not isinstance(value, int | str):
        raise DomainError("El tipo de cambio debe ser un número positivo.")
    return value.strip() if isinstance(value, str) else value


class LedgerService(ExtrasMixin, RecurringMixin):
    """Casos de uso de movimientos. Los extras (Hito 6) y los gastos fijos viven en mixins."""

    # --- Ingreso base (constitución 5.1; RN-02, RN-03, RN-08, RN-55 a 57) ---

    def _income_draft(
        self,
        amount: object,
        currency: object,
        exchange_rate: object,
        income_date: object,
        budget_month: object,
    ) -> _IncomeDraft:
        money = convert(amount, currency, exchange_rate, self._rates)
        day = movement_date(income_date, "del ingreso", self._today())
        month = income_budget_month(day, budget_month)
        explicit_date = parse_date(income_date, "del ingreso")
        explicit_month = isinstance(budget_month, str) and bool(budget_month.strip())
        payload = {
            "amount": money.original_amount,
            "currency": money.currency.value,
            "exchange_rate": money.exchange_rate,
            "income_date": explicit_date.isoformat() if explicit_date else None,
            "budget_month": str(month) if explicit_month else None,
        }
        return _IncomeDraft(day, month, money, payload)

    def _income_preview(self, draft: _IncomeDraft) -> tuple[IncomeResult, list[AllocationLine]]:
        pockets = self._store.list_pockets()
        source = pick_source_month(
            draft.budget_month, self._store.allocation_months(draft.budget_month)
        )
        if source is None:
            raise DomainError(
                f"No hay porcentajes definidos para {draft.budget_month} ni para un mes anterior. "
                "Defínelos con set_allocation antes de registrar el salario."
            )
        resolved = resolve_allocation(
            draft.budget_month, source, self._store.allocation_rows(source), pockets
        )
        parts = allocate_by_percentages(draft.money.amount_crc, list(resolved.items))
        lines = [AllocationLine(p.id, pct, amount) for p, pct, amount in parts]
        result = IncomeResult(
            saved=False,
            reference=None,
            kind="base",
            income_date=draft.income_date.isoformat(),
            budget_month=str(draft.budget_month),
            currency=draft.money.currency.value,
            original_amount=format_original(draft.money.currency, draft.money.original_amount),
            exchange_rate=format_rate(draft.money.exchange_rate)
            if draft.money.exchange_rate is not None
            else None,
            amount_crc=draft.money.amount_crc,
            allocation_source_month=str(source),
            items=[
                AllocationShare(
                    pocket=p.name, behavior=p.behavior.value, percentage=pct, amount=amount
                )
                for p, pct, amount in parts
            ],
        )
        return result, lines

    async def preview_income(
        self,
        amount: object,
        currency: object = "CRC",
        exchange_rate: object = None,
        income_date: object = None,
        budget_month: object = None,
    ) -> IncomeResult:
        """Vista previa del salario: valida y reparte, sin guardar nada (principio 3.2)."""
        draft = self._income_draft(amount, currency, exchange_rate, income_date, budget_month)
        result, _ = await self._run(partial(self._income_preview, draft))
        return result

    async def add_income(
        self,
        amount: object,
        currency: object = "CRC",
        exchange_rate: object = None,
        income_date: object = None,
        budget_month: object = None,
        confirm: bool = False,
        operation_id: object = None,
    ) -> IncomeResult:
        """Registra el salario repartido. Sin `confirm=True` solo devuelve la vista previa."""
        if not confirm:
            return await self.preview_income(
                amount, currency, exchange_rate, income_date, budget_month
            )
        op_id = validate_operation_id(operation_id)
        draft = self._income_draft(amount, currency, exchange_rate, income_date, budget_month)
        operation = Operation(op_id, "add_income", fingerprint("add_income", draft.payload))
        return await self._run(partial(self._write_income, draft, operation))

    def _write_income(self, draft: _IncomeDraft, operation: Operation) -> IncomeResult:
        replay = self._replay(operation)
        if replay is not None:
            return IncomeResult.model_validate(replay)
        preview, lines = self._income_preview(draft)

        def respond(income_id: int) -> dict:
            reference = str(MovementRef(MovementKind.INCOME, income_id))
            return preview.model_copy(update={"saved": True, "reference": reference}).model_dump(
                mode="json"
            )

        income = NewIncome(IncomeKind.BASE, draft.income_date, draft.budget_month, draft.money)
        try:
            response = self._store.record_income(income, lines, operation, respond)
        except OperationTaken:
            return IncomeResult.model_validate(self._after_race(operation))
        result = IncomeResult.model_validate(response)
        logger.info(
            "Salario registrado: ref=%s mes=%s moneda=%s bolsas=%d",
            result.reference,
            result.budget_month,
            result.currency,
            len(lines),
        )
        return result

    # --- Gastos (RN-31 a RN-34, RN-37, RN-38) y pago de gastos fijos (RN-35) ---

    async def add_expense(
        self,
        amount: object = None,
        operation_id: object = None,
        pocket: object = None,
        category: object = None,
        currency: object = None,
        exchange_rate: object = None,
        expense_date: object = None,
        description: object = None,
        recurring: object = None,
    ) -> ExpenseResult:
        op_id = validate_operation_id(operation_id)
        explicit_date = parse_date(expense_date, "del gasto")
        movement_date(expense_date, "del gasto", self._today())
        text = validate_description(description)
        request = _ExpenseRequest(
            amount, currency, exchange_rate, pocket, category, expense_date, text, recurring
        )
        common = {
            "pocket": _name_key(pocket),
            "category": _name_key(category),
            "expense_date": explicit_date.isoformat() if explicit_date else None,
            "description": text,
        }
        if _blank(recurring):
            money = convert(
                amount, "CRC" if _blank(currency) else currency, exchange_rate, self._rates
            )
            # Mismo contenido de huella que en el Hito 5 (sin la clave "recurring")
            payload = {
                "amount": money.original_amount,
                "currency": money.currency.value,
                "exchange_rate": money.exchange_rate,
                **common,
            }
        else:
            money = None  # el monto puede salir de la plantilla: se resuelve con el almacén
            payload = {
                "recurring": _recurring_key(recurring),
                "amount": _raw_amount(amount),
                "currency": None if _blank(currency) else parse_currency(currency).value,
                "exchange_rate": _raw_rate(exchange_rate),
                **common,
            }
        operation = Operation(op_id, "add_expense", fingerprint("add_expense", payload))
        return await self._run(partial(self._write_expense, operation, money, request))

    def _expense_target(
        self,
        pockets: list[Pocket],
        pocket: object,
        category: object,
        template: RecurringTemplate | None = None,
    ) -> tuple[Pocket, Category | None]:
        categories = self._store.list_categories()
        chosen = None
        if isinstance(category, str) and category.strip():
            chosen = find_category(categories, category)
        elif template is not None and template.category_id is not None:
            chosen = next(
                (c for c in categories if c.id == template.category_id and c.active), None
            )
        if isinstance(pocket, str) and pocket.strip():
            return find_pocket(pockets, pocket), chosen
        if template is not None:
            default = next((p for p in pockets if p.id == template.pocket_id and p.active), None)
            if default is None:
                raise DomainError(
                    f"La bolsa por defecto del gasto fijo {template.reference} está archivada; "
                    "indica la bolsa del pago."
                )
            return default, chosen
        if chosen is None:
            raise DomainError(
                "Indica la bolsa del gasto, o una categoría para usar su bolsa por defecto."
            )
        default = next((p for p in pockets if p.id == chosen.pocket_id and p.active), None)
        if default is None:
            raise DomainError(
                f"La bolsa por defecto de la categoría '{chosen.name}' está archivada; indica la "
                "bolsa del gasto."
            )
        return default, chosen

    def _template_money(
        self, template: RecurringTemplate, month: Month, request: _ExpenseRequest
    ) -> Converted:
        """Monto del pago: el indicado o el de la plantilla en ese mes. En USD siempre exige el
        tipo de cambio de este pago; nunca reutiliza otro (decisión #12d)."""
        if _blank(request.currency):
            currency = template.currency
        else:
            currency = parse_currency(request.currency)
        amount = request.amount
        if _blank(amount):
            if currency is not template.currency:
                raise DomainError(
                    "Indica el monto: la moneda del pago es distinta de la del gasto fijo."
                )
            amount = format_original(currency, template.amount_for(month))
        return convert(amount, currency.value, request.exchange_rate, self._rates)

    def _write_expense(
        self, operation: Operation, money: Converted | None, request: _ExpenseRequest
    ) -> ExpenseResult:
        replay = self._replay(operation)
        if replay is not None:
            return ExpenseResult.model_validate(replay)
        pockets = self._store.list_pockets()
        day = movement_date(request.expense_date, "del gasto", self._today())
        month = Month.of(day)
        template = None
        if not _blank(request.recurring):
            template = find_recurring(self._store.list_recurring(), request.recurring)
            if not template.active:
                raise RecurringInactive(template.reference)
            if month < template.start_month:
                raise DomainError(
                    f"El gasto fijo {template.reference} empieza en {template.start_month}; un "
                    f"pago con fecha de {month} no le corresponde."
                )
            if template.id in self._store.recurring_payments(month):
                raise RecurringAlreadyPaid(template.reference, str(month))
            money = self._template_money(template, month, request)
        if money is None:  # pragma: no cover - sin plantilla, el monto ya se convirtió
            raise DomainError("Falta el monto del gasto.")
        target, chosen = self._expense_target(pockets, request.pocket, request.category, template)

        entries = self._store.allocation_entries()
        after = [*self._store.expense_entries(), ExpenseEntry(target.id, month, money.amount_crc)]
        balance = pocket_balance(target, entries, month, after)
        overspent = balance.balance < 0
        available = []
        warning = None
        if overspent:
            available = [
                figure(b)
                for b in (
                    pocket_balance(p, entries, month, after)
                    for p in ordered_active(pockets)
                    if p.id != target.id
                )
                if b.balance > 0
            ]
            names = ", ".join(f.pocket for f in available)
            warning = (
                f"La bolsa {target.name} queda en negativo con este gasto. "
                "El gasto se guardó igual (RN-37) y la bolsa queda marcada hasta cubrirla (RN-38). "
                + (
                    f"Bolsas con saldo disponible: {names}."
                    if names
                    else "Ninguna otra bolsa tiene saldo disponible."
                )
            )
        paid = money

        def respond(expense_id: int) -> dict:
            return ExpenseResult(
                reference=str(MovementRef(MovementKind.EXPENSE, expense_id)),
                expense_date=day.isoformat(),
                month=str(month),
                pocket=target.name,
                category=chosen.name if chosen else UNCLASSIFIED,
                currency=paid.currency.value,
                original_amount=format_original(paid.currency, paid.original_amount),
                exchange_rate=format_rate(paid.exchange_rate)
                if paid.exchange_rate is not None
                else None,
                amount_crc=paid.amount_crc,
                pocket_balance=figure(balance),
                overspent=overspent,
                warning=warning,
                available_pockets=available,
                recurring=template.reference if template else None,
            ).model_dump(mode="json")

        expense = NewExpense(
            day,
            month,
            target.id,
            chosen.id if chosen else None,
            request.description,
            money,
            template.id if template else None,
        )
        try:
            response = self._store.record_expense(expense, operation, respond)
        except OperationTaken:
            return ExpenseResult.model_validate(self._after_race(operation))
        result = ExpenseResult.model_validate(response)
        logger.info(
            "Gasto registrado: ref=%s mes=%s moneda=%s sobregasto=%s fijo=%s",
            result.reference,
            result.month,
            result.currency,
            "sí" if overspent else "no",
            result.recurring or "-",
        )
        return result

    # --- Anulación (RN-53, RN-59, RN-54) ---

    async def void_transaction(
        self, reference: object, reason: object, operation_id: object, confirm: bool = False
    ) -> VoidResult:
        """Anula un ingreso o gasto con motivo. Sin `confirm=True` solo muestra el efecto."""
        ref = MovementRef.parse(reference)
        why = validate_reason(reason)
        op_id = validate_operation_id(operation_id)
        payload = {"reference": str(ref), "reason": why}
        operation = Operation(op_id, "void_transaction", fingerprint("void_transaction", payload))
        return await self._run(partial(self._void, ref, why, operation, confirm))

    def _void(
        self, ref: MovementRef, reason: str, operation: Operation, confirm: bool
    ) -> VoidResult:
        if confirm:
            replay = self._replay(operation)
            if replay is not None:
                return VoidResult.model_validate(replay)
        pockets = {p.id: p for p in self._store.list_pockets()}
        negatives: list[PocketFigure] = []
        initial = False
        notes = []
        if ref.kind is MovementKind.INCOME:
            income = self._store.get_income(ref.number)
            if income is None:
                raise MovementNotFound(str(ref))
            if income.voided:
                raise AlreadyVoided(str(ref))
            initial = income.kind is IncomeKind.INITIAL_BALANCE
            label = {IncomeKind.INITIAL_BALANCE: "saldo_inicial", IncomeKind.EXTRA: "extra"}.get(
                income.kind, "ingreso"
            )
            day, month, amount = income.income_date, income.budget_month, income.amount
            if income.pending:
                notes.append("El extra seguía sin asignar: anularlo no cambia ninguna bolsa.")
            else:
                negatives = self._negatives_after_void(income, pockets)
        else:
            expense = self._store.get_expense(ref.number)
            if expense is None:
                raise MovementNotFound(str(ref))
            if expense.voided:
                raise AlreadyVoided(str(ref))
            label = "gasto"  # anular un gasto solo sube la bolsa: nunca deja negativos
            day, month, amount = expense.expense_date, expense.month, expense.amount
            if expense.recurring_id is not None:
                notes.append(
                    f"El gasto fijo {RecurringRef(expense.recurring_id)} vuelve a quedar "
                    f"pendiente en {expense.month}."
                )

        if negatives:
            names = ", ".join(n.pocket for n in negatives)
            notes.append(f"Al anularlo, estas bolsas quedan en negativo: {names} (RN-59, RN-37).")
        if initial:
            notes.append(
                "Después de anularlo puedes cargar un saldo inicial nuevo con load_initial_balance."
            )
        preview = VoidResult(
            saved=False,
            reference=str(ref),
            movement=label,
            date=day.isoformat(),
            month=str(month),
            amount_crc=amount,
            voided_on=None,
            negative_pockets=negatives,
            warning=" ".join(notes) or None,
            initial_balance_reloadable=False,
        )
        if not confirm:
            return preview
        result = preview.model_copy(
            update={
                "saved": True,
                "voided_on": self._today().isoformat(),
                "initial_balance_reloadable": initial,
            }
        )
        try:
            self._store.void_movement(
                ref, reason, self._now(), operation, result.model_dump(mode="json")
            )
        except OperationTaken:
            return VoidResult.model_validate(self._after_race(operation))
        logger.info("Movimiento anulado: ref=%s tipo=%s", result.reference, label)
        return result

    def _negatives_after_void(
        self, income: IncomeRow, pockets: dict[int, Pocket]
    ) -> list[PocketFigure]:
        """RN-59: sin las asignaciones del ingreso, qué bolsas quedan en negativo."""
        lines = self._store.income_lines(income.id)
        entries = self._store.allocation_entries()
        expenses = self._store.expense_entries()
        removed = [
            AllocationEntry(line.pocket_id, income.budget_month, -line.amount) for line in lines
        ]
        after = [*entries, *removed]
        negatives = []
        for pocket_id in sorted({line.pocket_id for line in lines if line.amount > 0}):
            pocket = pockets[pocket_id]
            balance = pocket_balance(pocket, after, income.budget_month, expenses)
            if balance.balance < 0:
                negatives.append(figure(balance))
        return negatives

    # --- Categorías ---

    async def create_category(self, name: object, pocket: object) -> CategoryItem:
        clean = validate_category_name(name)
        return await self._run(partial(self._create_category, clean, pocket))

    def _create_category(self, name: str, pocket: object) -> CategoryItem:
        target = find_pocket(self._store.list_pockets(), pocket)
        key = normalize_name(name)
        if any(normalize_name(c.name) == key for c in self._store.list_categories()):
            raise CategoryAlreadyExists(name)
        created = self._store.create_category(name, target.id)
        logger.info("Categoría creada")
        return CategoryItem(name=created.name, pocket=target.name)

    async def list_categories(self) -> CategoriesResult:
        return await self._run(self._list_categories)

    def _list_categories(self) -> CategoriesResult:
        names = {p.id: p.name for p in self._store.list_pockets()}
        items = sorted(
            (c for c in self._store.list_categories() if c.active),
            key=lambda c: normalize_name(c.name),
        )
        return CategoriesResult(
            items=[CategoryItem(name=c.name, pocket=names[c.pocket_id]) for c in items]
        )

    # --- Consultas (11.1, 11.2) ---

    async def get_bolsa_status(self, pocket: object, month: object = None) -> BolsaStatus:
        target_month = self._month(month)
        return await self._run(partial(self._bolsa_status, pocket, target_month))

    def _bolsa_status(self, pocket: object, month: Month) -> BolsaStatus:
        target = find_pocket(self._store.list_pockets(), pocket)
        entries = self._store.allocation_entries()
        expenses = self._store.expense_entries()
        line = self._pocket_line(target, month, entries, expenses)
        budget = line.assigned  # sin transferencias: ajustado = original (9.1)
        return BolsaStatus(
            pocket=target.name,
            behavior=target.behavior.value,
            month=str(month),
            assigned=line.assigned,
            transfers_in=0,
            transfers_out=0,
            adjusted_budget=budget,
            spent=line.spent,
            available=line.available,
            percent_used=percent_used(line.spent, budget)
            if target.behavior is Behavior.CONSUMO
            else None,
            balance=line.balance,
            negative=line.negative,
        )

    @staticmethod
    def _pocket_line(
        pocket: Pocket,
        month: Month,
        entries: Sequence[AllocationEntry],
        expenses: Sequence[ExpenseEntry],
    ) -> SummaryPocket:
        got = assigned(entries, pocket.id, month)
        used = spent(expenses, pocket.id, month)
        if pocket.behavior is Behavior.CONSUMO:
            available, balance = got - used, None
            negative = available < 0
        else:
            available, balance = None, accumulated_balance(entries, pocket.id, expenses)
            negative = balance < 0
        return SummaryPocket(
            pocket=pocket.name,
            behavior=pocket.behavior.value,
            assigned=got,
            spent=used,
            available=available,
            balance=balance,
            negative=negative,
        )

    async def get_summary(self, month: object = None) -> SummaryResult:
        target_month = self._month(month)
        return await self._run(partial(self._summary, target_month))

    def _summary(self, month: Month) -> SummaryResult:
        pockets = ordered_active(self._store.list_pockets())
        entries = self._store.allocation_entries()
        expenses = self._store.expense_entries()
        lines = [self._pocket_line(p, month, entries, expenses) for p in pockets]
        extras = self._store.extra_income_total(month)
        return SummaryResult(
            month=str(month),
            income_total=self._store.base_income_total(month) + extras,
            extra_income_total=extras,
            unassigned=unassigned_summary(self._store.pending_extras()),
            expense_total=sum(e.amount for e in expenses if e.month == month),
            pockets=lines,
            negative_pockets=[line.pocket for line in lines if line.negative],
        )

    async def top_categories(
        self, month: object = None, limit: object = None
    ) -> TopCategoriesResult:
        target_month = self._month(month)
        size = parse_limit(limit, DEFAULT_TOP_LIMIT, MAX_TOP_LIMIT)
        return await self._run(partial(self._top_categories, target_month, size))

    def _top_categories(self, month: Month, size: int) -> TopCategoriesResult:
        names = {c.id: c.name for c in self._store.list_categories()}
        totals: dict[str, list[int]] = {}
        for row in self._store.expenses_in_month(month):
            label = names.get(row.category_id, UNCLASSIFIED) if row.category_id else UNCLASSIFIED
            bucket = totals.setdefault(label, [0, 0])
            bucket[0] += row.amount
            bucket[1] += 1
        total = sum(amount for amount, _ in totals.values())
        ordered = sorted(totals.items(), key=lambda kv: (-kv[1][0], normalize_name(kv[0])))
        return TopCategoriesResult(
            month=str(month),
            total_spent=total,
            items=[
                CategoryTotal(
                    category=label,
                    amount_crc=amount,
                    count=count,
                    percent=amount * 100 // total if total > 0 else 0,
                )
                for label, (amount, count) in ordered[:size]
            ],
        )

    async def list_transactions(
        self,
        month: object = None,
        type: object = None,  # noqa: A002 - nombre del contrato de la tool
        pocket: object = None,
        include_voided: bool = True,
        limit: object = None,
    ) -> TransactionsResult:
        blank = month is None or (isinstance(month, str) and not month.strip())
        target_month = None if blank else Month.parse(month)
        size = parse_limit(limit, DEFAULT_LIST_LIMIT, MAX_LIST_LIMIT)
        kind = type.strip().casefold() if isinstance(type, str) and type.strip() else None
        if kind not in (None, "gasto", "ingreso"):
            raise DomainError("El tipo debe ser 'gasto' o 'ingreso'.")
        has_pocket = isinstance(pocket, str) and bool(pocket.strip())
        if has_pocket and kind == "ingreso":
            raise DomainError("El filtro por bolsa solo aplica a gastos.")
        return await self._run(
            partial(
                self._list_transactions,
                target_month,
                kind,
                pocket if has_pocket else None,
                bool(include_voided),
                size,
            )
        )

    def _list_transactions(
        self,
        month: Month | None,
        kind: str | None,
        pocket: object,
        include_voided: bool,
        size: int,
    ) -> TransactionsResult:
        pockets = self._store.list_pockets()
        pocket_names = {p.id: p.name for p in pockets}
        category_names = {c.id: c.name for c in self._store.list_categories()}
        pocket_id = find_pocket(pockets, pocket).id if pocket is not None else None
        rows: list[tuple[tuple, TransactionItem]] = []
        if kind in (None, "ingreso") and pocket_id is None:
            for inc in self._store.recent_incomes(month, include_voided, size + 1):
                rows.append(((inc.income_date, 0, inc.id), self._income_item(inc)))
        if kind in (None, "gasto"):
            for exp in self._store.recent_expenses(month, pocket_id, include_voided, size + 1):
                item = self._expense_item(exp, pocket_names, category_names)
                rows.append(((exp.expense_date, 1, exp.id), item))
        rows.sort(key=lambda r: r[0], reverse=True)
        return TransactionsResult(
            items=[item for _, item in rows[:size]],
            has_more=len(rows) > size,
            unassigned=unassigned_summary(self._store.pending_extras()),
        )

    @staticmethod
    def _income_item(row: IncomeRow) -> TransactionItem:
        return TransactionItem(
            reference=str(MovementRef(MovementKind.INCOME, row.id)),
            type="ingreso",
            kind=row.kind.value,
            date=row.income_date.isoformat(),
            month=str(row.budget_month),
            pocket=None,
            category=None,
            description=row.source,
            currency=row.currency.value,
            original_amount=format_original(row.currency, row.original_amount),
            exchange_rate=format_rate(row.exchange_rate) if row.exchange_rate is not None else None,
            amount_crc=row.amount,
            voided=row.voided,
            void_reason=row.void_reason,
            allocation_status="pendiente" if row.pending else "repartido",
        )

    @staticmethod
    def _expense_item(
        row: ExpenseRow, pocket_names: dict[int, str], category_names: dict[int, str]
    ) -> TransactionItem:
        return TransactionItem(
            reference=str(MovementRef(MovementKind.EXPENSE, row.id)),
            type="gasto",
            kind=None,
            date=row.expense_date.isoformat(),
            month=str(row.month),
            pocket=pocket_names.get(row.pocket_id),
            category=category_names.get(row.category_id, UNCLASSIFIED)
            if row.category_id
            else UNCLASSIFIED,
            description=row.description,
            currency=row.currency.value,
            original_amount=format_original(row.currency, row.original_amount),
            exchange_rate=format_rate(row.exchange_rate) if row.exchange_rate is not None else None,
            amount_crc=row.amount,
            voided=row.voided,
            void_reason=row.void_reason,
            recurring=str(RecurringRef(row.recurring_id)) if row.recurring_id else None,
        )
