"""Ingreso extra (sección 5.3, RN-04 a RN-09) y su reparto propuesto por Claude (Hito 6).

Flujo: `register_extra_income` (queda pendiente y "sin asignar", RN-06) → `get_allocation_context`
(solo agregados del mes) → Claude propone bolsas y porcentajes con una explicación breve (RN-05; la
app no recomienda, principio 3.1) → el propietario aprueba de forma explícita → `confirm_allocation`
con la ficha de la vista previa. Un extra se reparte una sola vez; corregir es anular y registrar
de nuevo (RN-53, RN-59). Los registros no incluyen montos ni el origen del extra.
"""

from __future__ import annotations

from collections.abc import Sequence
from functools import partial
from typing import Literal

from pydantic import BaseModel, Field

from puro_pockets.domain.allocation import allocate_by_percentages, pick_source_month
from puro_pockets.domain.balances import IncomeKind
from puro_pockets.domain.errors import (
    DomainError,
    ExtraAlreadyDistributed,
    MovementNotFound,
    MovementVoided,
    NotAnExtra,
    PreviewRequired,
)
from puro_pockets.domain.extras import preview_token, validate_extra_shares
from puro_pockets.domain.goals import balance_function, progress
from puro_pockets.domain.idempotency import fingerprint, validate_operation_id
from puro_pockets.domain.ledger import (
    MovementKind,
    MovementRef,
    movement_date,
    parse_date,
    validate_description,
)
from puro_pockets.domain.money import Currency, convert, format_original, format_rate
from puro_pockets.domain.months import Month
from puro_pockets.domain.pockets import is_plain_int, normalize_name, ordered_active
from puro_pockets.domain.recurring import PendingRecurring
from puro_pockets.services.budget import AllocationLine
from puro_pockets.services.ledger_core import (
    AllocationShare,
    BehaviorName,
    CurrencyName,
    LedgerCore,
    logger,
)
from puro_pockets.services.records import IncomeRow, NewIncome, Operation, OperationTaken

RECENT_EXTRAS = 3


class ExtraIncomeResult(BaseModel):
    reference: str = Field(description="Referencia del extra (I-n).")
    kind: Literal["extra"]
    income_date: str
    budget_month: str = Field(description="Mes de su fecha (RN-09).")
    currency: CurrencyName
    original_amount: str
    exchange_rate: str | None
    amount_crc: int = Field(description="Equivalente en colones, calculado una vez (RN-57).")
    allocation_status: Literal["pendiente"]
    source: str | None = Field(description="Origen del extra (opcional).")
    note: str


class ExtraInfo(BaseModel):
    reference: str
    income_date: str
    budget_month: str
    currency: CurrencyName
    original_amount: str
    exchange_rate: str | None
    amount_crc: int
    allocation_status: Literal["pendiente", "repartido"]


class ContextPocket(BaseModel):
    pocket: str
    behavior: BehaviorName
    percentage: int | None = Field(
        description="Porcentaje vigente del mes (RN-03); null si no hay."
    )
    budget: int = Field(
        description="Asignado en el mes (presupuesto original; sin extras pendientes)."
    )
    transfers_in: int = Field(default=0, description="Transferencias recibidas en el mes.")
    transfers_out: int = Field(default=0, description="Transferencias enviadas en el mes.")
    adjusted_budget: int = Field(
        default=0, description="Presupuesto ajustado (9.1): asignado + recibidas − enviadas."
    )
    spent: int = Field(description="Gastado en el mes.")
    available: int | None = Field(
        description="Consumo: disponible del mes (11.1) = ajustado − gastado."
    )
    balance: int | None = Field(
        description="Acumulable: saldo actual (11.2), con las transferencias incluidas."
    )
    negative: bool


class ContextRecurring(BaseModel):
    count: int = Field(description="Gastos fijos pendientes del mes (RN-36).")
    overdue_count: int
    total_crc: int = Field(description="Σ de los pendientes en colones (solo los CRC).")
    usd_count: int = Field(description="Pendientes en dólares, listados aparte.")
    usd_total: str = Field(description="Σ de los pendientes en USD, sin convertir.")


class PocketPercent(BaseModel):
    pocket: str
    percentage: int


class RecentExtra(BaseModel):
    budget_month: str
    shares: list[PocketPercent] = Field(description="Porcentajes con que se repartió.")


class ContextGoal(BaseModel):
    pocket: str
    target_amount: int = Field(description="Objetivo en colones.")
    balance: int = Field(description="Saldo de la bolsa = avance (RN-23).")
    percent: int = Field(description="Avance en %, con tope de 100.")


class AllocationContextResult(BaseModel):
    extra: ExtraInfo
    month: str = Field(description="Mes presupuestario del extra: el de los datos siguientes.")
    percentages_source_month: str | None = Field(
        description="Mes del que vienen los porcentajes vigentes (RN-03); null si no hay."
    )
    pockets: list[ContextPocket] = Field(description="Bolsas activas, en orden de creación.")
    recurring_pending: ContextRecurring
    recent_extras: list[RecentExtra] = Field(
        description=f"Últimos {RECENT_EXTRAS} extras repartidos (solo porcentajes)."
    )
    goals: list[ContextGoal] = Field(
        default_factory=list,
        description="Metas activas con su avance (RN-05): bolsa, objetivo, saldo y %.",
    )


class ExtraAllocationResult(BaseModel):
    saved: bool = Field(description="True solo si se guardó el reparto; false es la vista previa.")
    reference: str
    budget_month: str
    amount_crc: int
    items: list[AllocationShare] = Field(description="Reparto en colones (RN-08).")
    preview_token: str | None = Field(
        description="Solo en la vista previa: ficha que confirm_allocation exige con confirm=true."
    )
    allocation_status: Literal["pendiente", "repartido"]


def _extra_info(row: IncomeRow) -> ExtraInfo:
    return ExtraInfo(
        reference=str(MovementRef(MovementKind.INCOME, row.id)),
        income_date=row.income_date.isoformat(),
        budget_month=str(row.budget_month),
        currency=row.currency.value,
        original_amount=format_original(row.currency, row.original_amount),
        exchange_rate=format_rate(row.exchange_rate) if row.exchange_rate is not None else None,
        amount_crc=row.amount,
        allocation_status="pendiente" if row.pending else "repartido",
    )


def _recurring_context(pending: Sequence[PendingRecurring]) -> ContextRecurring:
    usd = [p for p in pending if p.template.currency is Currency.USD]
    return ContextRecurring(
        count=len(pending),
        overdue_count=sum(p.overdue for p in pending),
        total_crc=sum(p.amount for p in pending if p.template.currency is Currency.CRC),
        usd_count=len(usd),
        usd_total=format_original(Currency.USD, sum(p.amount for p in usd)),
    )


class ExtrasMixin(LedgerCore):
    # --- register_extra_income (RN-06, RN-09) ---

    async def register_extra_income(
        self,
        amount: object,
        operation_id: object,
        currency: object = "CRC",
        exchange_rate: object = None,
        income_date: object = None,
        source: object = None,
    ) -> ExtraIncomeResult:
        op_id = validate_operation_id(operation_id)
        money = convert(amount, "CRC" if currency is None else currency, exchange_rate, self._rates)
        explicit = parse_date(income_date, "del ingreso")
        day = movement_date(income_date, "del ingreso", self._today())
        text = validate_description(source)
        payload = {
            "amount": money.original_amount,
            "currency": money.currency.value,
            "exchange_rate": money.exchange_rate,
            "income_date": explicit.isoformat() if explicit else None,
            "source": text,
        }
        operation = Operation(
            op_id, "register_extra_income", fingerprint("register_extra_income", payload)
        )
        month = Month.of(day)  # RN-09: el mes en que entra
        income = NewIncome(IncomeKind.EXTRA, day, month, money, pending=True, source=text)

        def write() -> ExtraIncomeResult:
            replay = self._replay(operation)
            if replay is not None:
                return ExtraIncomeResult.model_validate(replay)
            self._ensure_open(month)  # RN-44, RN-48: extras por mes presupuestario

            def respond(income_id: int) -> dict:
                return ExtraIncomeResult(
                    reference=str(MovementRef(MovementKind.INCOME, income_id)),
                    kind="extra",
                    income_date=day.isoformat(),
                    budget_month=str(month),
                    currency=money.currency.value,
                    original_amount=format_original(money.currency, money.original_amount),
                    exchange_rate=format_rate(money.exchange_rate)
                    if money.exchange_rate is not None
                    else None,
                    amount_crc=money.amount_crc,
                    allocation_status="pendiente",
                    source=text,
                    note='Queda pendiente y "sin asignar": no suma a ninguna bolsa hasta '
                    "confirmar su reparto (RN-06).",
                ).model_dump(mode="json")

            try:
                response = self._store.record_income(income, [], operation, respond)
            except OperationTaken:
                return ExtraIncomeResult.model_validate(self._after_race(operation))
            result = ExtraIncomeResult.model_validate(response)
            logger.info(
                "Extra registrado (pendiente): ref=%s mes=%s moneda=%s",
                result.reference,
                result.budget_month,
                result.currency,
            )
            return result

        return await self._run(write)

    # --- get_allocation_context (RN-05, RN-36) ---

    def _extra(self, reference: object, allow_distributed: bool) -> IncomeRow:
        ref = MovementRef.parse(reference)
        if ref.kind is not MovementKind.INCOME:
            raise NotAnExtra(str(ref))
        row = self._store.get_income(ref.number)
        if row is None:
            raise MovementNotFound(str(ref))
        if row.kind is not IncomeKind.EXTRA:
            raise NotAnExtra(str(ref))
        if row.voided:
            raise MovementVoided(str(ref))
        if not row.pending and not allow_distributed:
            raise ExtraAlreadyDistributed(str(ref))
        return row

    async def get_allocation_context(self, extra: object) -> AllocationContextResult:
        MovementRef.parse(extra)  # formato antes de ir al almacén
        return await self._run(partial(self._allocation_context, extra))

    def _allocation_context(self, extra: object) -> AllocationContextResult:
        row = self._extra(extra, allow_distributed=True)
        month = row.budget_month
        all_pockets = self._store.list_pockets()
        names = {p.id: p.name for p in all_pockets}
        source = pick_source_month(month, self._store.allocation_months(month))
        rows = self._store.allocation_rows(source) if source else {}
        data = self._data()
        pockets = []
        for pocket in ordered_active(all_pockets):
            figures = data.figures(pocket, month)  # la misma función que get_bolsa_status
            pockets.append(
                ContextPocket(
                    pocket=pocket.name,
                    behavior=pocket.behavior.value,
                    percentage=rows.get(pocket.id, 0) if source else None,
                    budget=figures.assigned,
                    transfers_in=figures.transfers_in,
                    transfers_out=figures.transfers_out,
                    adjusted_budget=figures.adjusted_budget,
                    spent=figures.spent,
                    available=figures.available,
                    balance=figures.balance,
                    negative=figures.negative,
                )
            )
        balance_of = balance_function(data.entries, data.expenses, data.transfers)
        recent = [
            RecentExtra(
                budget_month=str(past.budget_month),
                shares=[
                    PocketPercent(pocket=names.get(line.pocket_id, "?"), percentage=line.percentage)
                    for line in self._store.income_lines(past.id)
                    if line.percentage
                ],
            )
            for past in self._store.distributed_extras(RECENT_EXTRAS)
        ]
        logger.info("Contexto de reparto entregado: ref=I-%d mes=%s", row.id, month)
        return AllocationContextResult(
            extra=_extra_info(row),
            month=str(month),
            percentages_source_month=str(source) if source else None,
            pockets=pockets,
            recurring_pending=_recurring_context(self._pending_recurring(month)),
            recent_extras=recent,
            goals=[
                ContextGoal(
                    pocket=names.get(goal.pocket_id, "?"),
                    target_amount=goal.target_amount,
                    balance=balance_of(goal.pocket_id),
                    percent=progress(goal, balance_of(goal.pocket_id)).percent,
                )
                for goal in self._store.list_goals()
                if goal.live
            ],
        )

    # --- confirm_allocation (RN-01, RN-07, RN-08) ---

    async def confirm_allocation(
        self,
        extra: object,
        percentages: Sequence[tuple[object, object]],
        confirm: bool = False,
        operation_id: object = None,
        preview_token: object = None,
    ) -> ExtraAllocationResult:
        ref = MovementRef.parse(extra)
        if ref.kind is not MovementKind.INCOME:
            raise NotAnExtra(str(ref))
        pairs = list(percentages or [])
        for name, value in pairs:
            label = name.strip() if isinstance(name, str) else "?"
            if not isinstance(name, str):
                raise DomainError("Cada bolsa se indica por su nombre.")
            if not is_plain_int(value) or not 0 <= value <= 100:  # type: ignore[operator]
                raise DomainError(f"El porcentaje de {label} debe ser un entero entre 0 y 100.")
        operation = None
        if confirm:
            op_id = validate_operation_id(operation_id)
            payload = {
                "extra": str(ref),
                "percentages": sorted(
                    [normalize_name(name), int(value)]  # type: ignore[arg-type, call-overload]
                    for name, value in pairs
                    if value
                ),
            }
            operation = Operation(
                op_id, "confirm_allocation", fingerprint("confirm_allocation", payload)
            )
        return await self._run(
            partial(self._confirm_allocation, ref, pairs, operation, preview_token)
        )

    def _confirm_allocation(
        self,
        ref: MovementRef,
        pairs: list[tuple[object, object]],
        operation: Operation | None,
        token: object,
    ) -> ExtraAllocationResult:
        if operation is not None:
            replay = self._replay(operation)
            if replay is not None:
                return ExtraAllocationResult.model_validate(replay)
        row = self._extra(str(ref), allow_distributed=False)
        self._ensure_open(row.budget_month)  # RN-44, RN-48: repartos del mes cerrado
        shares = validate_extra_shares(pairs, self._store.list_pockets())
        parts = allocate_by_percentages(row.amount, shares)
        expected = preview_token(str(ref), row.amount, shares)
        preview = ExtraAllocationResult(
            saved=False,
            reference=str(ref),
            budget_month=str(row.budget_month),
            amount_crc=row.amount,
            items=[
                AllocationShare(
                    pocket=p.name, behavior=p.behavior.value, percentage=pct, amount=amount
                )
                for p, pct, amount in parts
                if pct > 0
            ],
            preview_token=expected,
            allocation_status="pendiente",
        )
        if operation is None:
            return preview
        if not isinstance(token, str) or token.strip() != expected:
            raise PreviewRequired()
        lines = [AllocationLine(p.id, pct, amount) for p, pct, amount in parts if pct > 0]
        result = preview.model_copy(
            update={"saved": True, "preview_token": None, "allocation_status": "repartido"}
        )
        try:
            response = self._store.distribute_extra(
                row.id, lines, operation, lambda: result.model_dump(mode="json"), on=self._today()
            )
        except OperationTaken:
            return ExtraAllocationResult.model_validate(self._after_race(operation))
        logger.info(
            "Extra repartido: ref=%s mes=%s bolsas=%d", str(ref), row.budget_month, len(lines)
        )
        return ExtraAllocationResult.model_validate(response)
