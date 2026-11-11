"""Gastos fijos mensuales (sección 8.1, RN-35, RN-36): plantillas y pendientes del mes (Hito 6).

`manage_recurring` crea, lista, actualiza y desactiva plantillas (nunca se borran). Cambiar el monto
afecta solo meses futuros: el nuevo monto vale desde el mes siguiente (o desde el mes de inicio, si
es posterior). `list_pending_recurring` muestra qué falta pagar en un mes; el pago es un gasto
normal enlazado a la plantilla (`add_expense` con `recurring`). Nunca se convierten dólares: un
pago en USD exige el tipo de cambio de ese pago (decisión #12d). Los registros y los errores no
incluyen montos ni nombres de plantillas, solo referencias.
"""

from __future__ import annotations

from dataclasses import replace
from functools import partial
from typing import Literal

from pydantic import BaseModel, Field

from puro_pockets.domain.categories import Category, find_category
from puro_pockets.domain.errors import DomainError, RecurringInactive, RecurringNameTaken
from puro_pockets.domain.idempotency import fingerprint, validate_operation_id
from puro_pockets.domain.money import Currency, format_original, parse_amount, parse_currency
from puro_pockets.domain.months import Month
from puro_pockets.domain.pockets import Pocket, find_pocket, normalize_name
from puro_pockets.domain.recurring import (
    RecurringRef,
    RecurringTemplate,
    find_recurring,
    pending_in_month,
    validate_day,
    validate_recurring_name,
)
from puro_pockets.services.ledger_core import CurrencyName, LedgerCore, logger
from puro_pockets.services.records import (
    NewRecurring,
    Operation,
    OperationTaken,
    RecurringChange,
)

Action = Literal["crear", "listar", "actualizar", "desactivar"]
ACTIONS: tuple[str, ...] = ("crear", "listar", "actualizar", "desactivar")


class ScheduledChange(BaseModel):
    from_month: str = Field(description="Mes desde el que vale el nuevo monto.")
    amount: str = Field(description="Nuevo monto en la moneda de la plantilla.")


class RecurringItem(BaseModel):
    reference: str = Field(description="Referencia del gasto fijo (F-n).")
    name: str
    currency: CurrencyName
    amount: str = Field(
        description="Monto vigente este mes, en su moneda (USD con 2 decimales, sin convertir)."
    )
    scheduled_change: ScheduledChange | None = Field(
        description="Cambio de monto ya programado para un mes futuro, si lo hay."
    )
    day_of_month: int = Field(description="Día de pago (si el mes es más corto, el último día).")
    pocket: str = Field(description="Bolsa por defecto del pago.")
    category: str | None = Field(description="Categoría por defecto (opcional).")
    start_month: str = Field(description="Primer mes en que se espera el pago.")
    active: bool


class RecurringResult(BaseModel):
    action: Action
    saved: bool = Field(description="True si se guardó un cambio (crear, actualizar, desactivar).")
    items: list[RecurringItem]
    note: str | None = None


class PendingRecurringItem(BaseModel):
    reference: str
    name: str
    currency: CurrencyName
    amount: str = Field(description="Monto en la moneda de la plantilla; USD sin convertir.")
    amount_crc: int | None = Field(description="Colones; null en USD (no se convierte).")
    due_date: str = Field(description="Vencimiento en el mes.")
    overdue: bool = Field(description="True si hoy ya pasó el vencimiento.")
    pocket: str
    category: str | None


class PaidRecurringItem(BaseModel):
    reference: str
    name: str
    expense_reference: str = Field(description="Gasto vigente que lo pagó (G-n).")
    amount_crc: int


class PendingRecurringResult(BaseModel):
    month: str
    pending: list[PendingRecurringItem]
    paid: list[PaidRecurringItem]
    pending_count: int
    overdue_count: int
    pending_total_crc: int = Field(description="Σ de los pendientes en colones (solo los CRC).")
    pending_usd_count: int
    pending_usd_total: str = Field(description="Σ de los pendientes en USD, sin convertir.")


def _blank(value: object) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _apply_change(template: RecurringTemplate, change: RecurringChange) -> RecurringTemplate:
    amounts = template.amounts
    if change.amount is not None:
        since, amount = change.amount
        amounts = tuple(sorted({**dict(amounts), since: amount}.items()))
    return replace(
        template,
        name=change.name if change.name is not None else template.name,
        day_of_month=change.day_of_month
        if change.day_of_month is not None
        else template.day_of_month,
        pocket_id=change.pocket_id if change.pocket_id is not None else template.pocket_id,
        category_id=change.category_id if change.category_id is not None else template.category_id,
        amounts=amounts,
    )


class RecurringMixin(LedgerCore):
    # --- Vistas ---

    def _recurring_item(
        self,
        template: RecurringTemplate,
        pockets: dict[int, str],
        categories: dict[int, str],
        month: Month,
    ) -> RecurringItem:
        change = template.scheduled_change(month)
        return RecurringItem(
            reference=template.reference,
            name=template.name,
            currency=template.currency.value,
            amount=format_original(template.currency, template.amount_for(month)),
            scheduled_change=ScheduledChange(
                from_month=str(change[0]),
                amount=format_original(template.currency, change[1]),
            )
            if change
            else None,
            day_of_month=template.day_of_month,
            pocket=pockets.get(template.pocket_id, "?"),
            category=categories.get(template.category_id) if template.category_id else None,
            start_month=str(template.start_month),
            active=template.active,
        )

    def _names(self) -> tuple[dict[int, str], dict[int, str]]:
        return (
            {p.id: p.name for p in self._store.list_pockets()},
            {c.id: c.name for c in self._store.list_categories()},
        )

    # --- manage_recurring ---

    async def manage_recurring(
        self,
        action: object,
        operation_id: object = None,
        recurring: object = None,
        name: object = None,
        amount: object = None,
        currency: object = None,
        day_of_month: object = None,
        pocket: object = None,
        category: object = None,
        start_month: object = None,
        include_inactive: bool = False,
    ) -> RecurringResult:
        verb = action.strip().casefold() if isinstance(action, str) else ""
        if verb not in ACTIONS:
            raise DomainError("La acción debe ser crear, listar, actualizar o desactivar.")
        if verb == "listar":
            return await self._run(partial(self._list_recurring, bool(include_inactive)))
        op_id = validate_operation_id(operation_id)
        if verb == "crear":
            return await self._create_recurring(
                op_id, name, amount, currency, day_of_month, pocket, category, start_month
            )
        if _blank(recurring):
            raise DomainError("Indica el gasto fijo por su referencia (F-n) o por su nombre.")
        if verb == "desactivar":
            payload = {"recurring": self._recurring_key(recurring)}
            operation = Operation(
                op_id, "manage_recurring", fingerprint("manage_recurring:desactivar", payload)
            )
            return await self._run(partial(self._deactivate, operation, recurring))
        return await self._update_recurring(
            op_id, recurring, name, amount, currency, day_of_month, pocket, category, start_month
        )

    @staticmethod
    def _recurring_key(value: object) -> str:
        ref = RecurringRef.match(value)
        return str(ref) if ref is not None else normalize_name(str(value))

    def _list_recurring(self, include_inactive: bool) -> RecurringResult:
        pockets, categories = self._names()
        month = Month.of(self._today())
        items = [
            self._recurring_item(t, pockets, categories, month)
            for t in sorted(self._store.list_recurring(), key=lambda t: t.id)
            if t.active or include_inactive
        ]
        return RecurringResult(action="listar", saved=False, items=items)

    def _target(
        self, pocket: object, category: object, current: RecurringTemplate | None = None
    ) -> tuple[Pocket | None, Category | None]:
        """Bolsa y categoría indicadas (None = sin cambio). Sin bolsa al crear, la de la
        categoría."""
        pockets = self._store.list_pockets()
        chosen = None
        if not _blank(category):
            chosen = find_category(self._store.list_categories(), category)
        target = None if _blank(pocket) else find_pocket(pockets, pocket)
        if target is None and current is None:
            if chosen is None:
                raise DomainError(
                    "Indica la bolsa por defecto del gasto fijo, o una categoría para usar la suya."
                )
            target = next((p for p in pockets if p.id == chosen.pocket_id and p.active), None)
            if target is None:
                raise DomainError(
                    "La bolsa por defecto de esa categoría está archivada; indica la bolsa."
                )
        return target, chosen

    def _ensure_name_free(self, name: str, except_id: int | None = None) -> None:
        key = normalize_name(name)
        if any(
            t.active and t.id != except_id and normalize_name(t.name) == key
            for t in self._store.list_recurring()
        ):
            raise RecurringNameTaken()

    async def _create_recurring(
        self,
        op_id: str,
        name: object,
        amount: object,
        currency: object,
        day_of_month: object,
        pocket: object,
        category: object,
        start_month: object,
    ) -> RecurringResult:
        clean = validate_recurring_name(name)
        cur = Currency.CRC if _blank(currency) else parse_currency(currency)
        if _blank(amount):
            raise DomainError("Indica el monto del gasto fijo.")
        original = parse_amount(amount, cur)
        day = validate_day(day_of_month)
        start = self._month(start_month)
        payload = {
            "name": normalize_name(clean),
            "currency": cur.value,
            "amount": original,
            "day_of_month": day,
            "pocket": None if _blank(pocket) else normalize_name(str(pocket)),
            "category": None if _blank(category) else normalize_name(str(category)),
            "start_month": str(start),
        }
        operation = Operation(
            op_id, "manage_recurring", fingerprint("manage_recurring:crear", payload)
        )

        def write() -> RecurringResult:
            replay = self._replay(operation)
            if replay is not None:
                return RecurringResult.model_validate(replay)
            target, chosen = self._target(pocket, category)
            assert target is not None  # al crear, _target siempre resuelve la bolsa
            self._ensure_name_free(clean)
            new = NewRecurring(
                clean, cur, original, day, target.id, chosen.id if chosen else None, start
            )
            month = Month.of(self._today())

            def respond(recurring_id: int) -> dict:
                template = RecurringTemplate(
                    recurring_id,
                    clean,
                    cur,
                    day,
                    target.id,
                    new.category_id,
                    start,
                    True,
                    ((start, original),),
                )
                pockets, categories = self._names()
                item = self._recurring_item(template, pockets, categories, month)
                return RecurringResult(action="crear", saved=True, items=[item]).model_dump(
                    mode="json"
                )

            try:
                response = self._store.create_recurring(new, operation, respond)
            except OperationTaken:
                return RecurringResult.model_validate(self._after_race(operation))
            result = RecurringResult.model_validate(response)
            logger.info(
                "Gasto fijo creado: ref=%s moneda=%s inicio=%s",
                result.items[0].reference,
                cur.value,
                start,
            )
            return result

        return await self._run(write)

    async def _update_recurring(
        self,
        op_id: str,
        recurring: object,
        name: object,
        amount: object,
        currency: object,
        day_of_month: object,
        pocket: object,
        category: object,
        start_month: object,
    ) -> RecurringResult:
        if not _blank(currency):
            raise DomainError(
                "La moneda de un gasto fijo no se cambia: desactívalo y crea otro en la nueva "
                "moneda."
            )
        if not _blank(start_month):
            raise DomainError(
                "El mes de inicio de un gasto fijo no se cambia: desactívalo y crea otro."
            )
        clean = None if _blank(name) else validate_recurring_name(name)
        day = None if day_of_month is None else validate_day(day_of_month)
        if all(_blank(v) for v in (name, amount, pocket, category)) and day is None:
            raise DomainError("Indica qué cambiar: nombre, monto, día del mes, bolsa o categoría.")
        if isinstance(amount, float):
            raise DomainError(
                'Un monto con decimales debe enviarse como texto, por ejemplo "10.50".'
            )
        if not _blank(amount) and (isinstance(amount, bool) or not isinstance(amount, int | str)):
            raise DomainError("El monto debe ser un número positivo.")
        payload = {
            "recurring": self._recurring_key(recurring),
            "name": normalize_name(clean) if clean else None,
            "amount": None
            if _blank(amount)
            else (amount.strip() if isinstance(amount, str) else amount),
            "day_of_month": day,
            "pocket": None if _blank(pocket) else normalize_name(str(pocket)),
            "category": None if _blank(category) else normalize_name(str(category)),
        }
        operation = Operation(
            op_id, "manage_recurring", fingerprint("manage_recurring:actualizar", payload)
        )

        def write() -> RecurringResult:
            replay = self._replay(operation)
            if replay is not None:
                return RecurringResult.model_validate(replay)
            template = find_recurring(self._store.list_recurring(), recurring)
            if not template.active:
                raise RecurringInactive(template.reference)
            if clean is not None:
                self._ensure_name_free(clean, template.id)
            target, chosen = self._target(pocket, category, template)
            month = Month.of(self._today())
            new_amount = None
            note = None
            if not _blank(amount):
                since = max(month.next(), template.start_month)
                new_amount = (since, parse_amount(amount, template.currency))
                note = (
                    f"El nuevo monto vale desde {since}; los meses anteriores conservan el monto "
                    "que tenían."
                )
            change = RecurringChange(
                template.id,
                name=clean,
                amount=new_amount,
                day_of_month=day,
                pocket_id=target.id if target else None,
                category_id=chosen.id if chosen else None,
            )
            updated = _apply_change(template, change)

            def respond() -> dict:
                pockets, categories = self._names()
                item = self._recurring_item(updated, pockets, categories, month)
                return RecurringResult(
                    action="actualizar", saved=True, items=[item], note=note
                ).model_dump(mode="json")

            try:
                response = self._store.update_recurring(change, operation, respond)
            except OperationTaken:
                return RecurringResult.model_validate(self._after_race(operation))
            logger.info(
                "Gasto fijo actualizado: ref=%s monto_cambiado=%s",
                template.reference,
                "sí" if new_amount else "no",
            )
            return RecurringResult.model_validate(response)

        return await self._run(write)

    def _deactivate(self, operation: Operation, recurring: object) -> RecurringResult:
        replay = self._replay(operation)
        if replay is not None:
            return RecurringResult.model_validate(replay)
        template = find_recurring(self._store.list_recurring(), recurring)
        if not template.active:
            raise RecurringInactive(template.reference)
        month = Month.of(self._today())

        def respond() -> dict:
            pockets, categories = self._names()
            item = self._recurring_item(replace(template, active=False), pockets, categories, month)
            return RecurringResult(
                action="desactivar",
                saved=True,
                items=[item],
                note="Desactivado: deja de figurar como pendiente; su historial se conserva.",
            ).model_dump(mode="json")

        try:
            response = self._store.deactivate_recurring(
                template.id, self._now(), operation, respond
            )
        except OperationTaken:
            return RecurringResult.model_validate(self._after_race(operation))
        logger.info("Gasto fijo desactivado: ref=%s", template.reference)
        return RecurringResult.model_validate(response)

    # --- list_pending_recurring ---

    async def list_pending_recurring(self, month: object = None) -> PendingRecurringResult:
        target = self._month(month)
        return await self._run(partial(self._list_pending, target))

    def _list_pending(self, month: Month) -> PendingRecurringResult:
        templates = {t.id: t for t in self._store.list_recurring()}
        payments = self._store.recurring_payments(month)
        pending = pending_in_month(list(templates.values()), payments, month, self._today())
        pockets, categories = self._names()
        items = [
            PendingRecurringItem(
                reference=p.template.reference,
                name=p.template.name,
                currency=p.template.currency.value,
                amount=format_original(p.template.currency, p.amount),
                amount_crc=p.amount if p.template.currency is Currency.CRC else None,
                due_date=p.due.isoformat(),
                overdue=p.overdue,
                pocket=pockets.get(p.template.pocket_id, "?"),
                category=categories.get(p.template.category_id) if p.template.category_id else None,
            )
            for p in pending
        ]
        paid = []
        for recurring_id, expense_id in sorted(payments.items()):
            expense = self._store.get_expense(expense_id)
            template = templates.get(recurring_id)
            if expense is None or template is None:  # pragma: no cover - integridad referencial
                continue
            paid.append(
                PaidRecurringItem(
                    reference=template.reference,
                    name=template.name,
                    expense_reference=f"G-{expense_id}",
                    amount_crc=expense.amount,
                )
            )
        usd = [p for p in pending if p.template.currency is Currency.USD]
        return PendingRecurringResult(
            month=str(month),
            pending=items,
            paid=paid,
            pending_count=len(pending),
            overdue_count=sum(p.overdue for p in pending),
            pending_total_crc=sum(p.amount for p in pending if p.template.currency is Currency.CRC),
            pending_usd_count=len(usd),
            pending_usd_total=format_original(Currency.USD, sum(p.amount for p in usd)),
        )
