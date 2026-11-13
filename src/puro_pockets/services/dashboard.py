"""Capa de lectura del dashboard (Hito 10). Solo lee: ninguna llamada escribe en la base.

Compone `LedgerService` y usa sus mismas consultas que las tools (`get_summary`, `get_bolsa_status`,
`get_goal_progress`, `list_transactions`, `top_categories`, `list_pending_recurring`), así que las
cifras son las mismas que Claude ve. Lo que las tools no traen (ahorrado, disponible del mes, fecha
estimada, alertas, evolución) sale de `domain/stats.py` sobre las mismas entradas. Las respuestas
llevan solo lo que la pantalla usa (minimización, principio 3.10).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from functools import partial
from typing import Literal

import anyio
from pydantic import BaseModel

from puro_pockets.domain.errors import DomainError
from puro_pockets.domain.money import Currency
from puro_pockets.domain.months import Month
from puro_pockets.domain.stats import (
    SavedBreakdown,
    SavingsTransfer,
    estimate_goal_month,
    month_saved,
    pocket_alert,
    trailing_months,
)
from puro_pockets.domain.transfers import TransferReason
from puro_pockets.services.ledger import LedgerService, SummaryResult
from puro_pockets.services.ledger_core import BehaviorName, CurrencyName
from puro_pockets.services.records import LedgerStore

PAGE_SIZE = 10
MAX_PAGES = 10  # 10 × 10 = el máximo de 100 de list_transactions
MAX_CATEGORIES = 20
ALL_ROWS = 2**31 - 1

AlertKind = Literal["close_pending", "overspent", "high_usage", "unassigned"]
PocketAlertName = Literal["warning", "danger"]


# --- Respuestas de la API ---


class SavedBreakdownOut(BaseModel):
    base: int
    extra: int
    transfers_in: int
    transfers_out: int
    closure_surplus: int


class UnassignedOut(BaseModel):
    count: int
    total_crc: int
    crc_count: int
    crc_total: int
    usd_count: int
    usd_total: str


class AdjustmentOut(BaseModel):
    pocket: str
    kind: Literal["sobrante_no_destinado", "sobregasto_no_cubierto"]
    amount: int


class PendingClosureOut(BaseModel):
    month: str
    has_movements: bool


class AlertOut(BaseModel):
    kind: AlertKind
    month: str | None = None
    pocket: str | None = None
    amount: int | None = None
    percent: int | None = None
    count: int | None = None
    crc_total: int | None = None
    usd_count: int | None = None
    usd_total: str | None = None


class SummaryOut(BaseModel):
    month: str
    current_month: str
    month_closed: bool
    income: int
    extra_income: int
    spent: int
    available: int
    saved: int
    saved_breakdown: SavedBreakdownOut
    unassigned: UnassignedOut
    closure_adjustments: list[AdjustmentOut]
    pending_closure: list[PendingClosureOut]
    alerts: list[AlertOut]


class GoalOut(BaseModel):
    reference: str
    name: str
    status: Literal["activa", "lograda", "pausada"]
    target: int
    balance: int
    progress: int
    remaining: int
    excess: int
    monthly_average: int | None
    projectable: bool
    estimated_month: str | None


class PocketOut(BaseModel):
    name: str
    kind: BehaviorName
    assigned: int
    received: int
    sent: int
    adjusted: int
    spent: int
    available: int | None
    used: int | None
    used_original: int | None
    balance: int | None
    negative: bool
    alert: PocketAlertName | None
    goal: GoalOut | None


class PocketsOut(BaseModel):
    month: str
    month_closed: bool
    items: list[PocketOut]


class MovementOut(BaseModel):
    ref: str
    type: Literal["gasto", "ingreso", "transferencia"]
    kind: str | None
    date: str
    month: str
    description: str | None
    pocket: str | None
    from_pocket: str | None
    to_pocket: str | None
    category: str | None
    currency: CurrencyName
    original_amount: str
    amount_crc: int
    voided: bool
    void_reason: str | None
    pending: bool
    reason: str | None
    note: str | None
    recurring: str | None


class MovementsOut(BaseModel):
    items: list[MovementOut]
    page: int
    page_size: int
    has_more: bool


class CategoryOut(BaseModel):
    name: str
    value: int
    count: int
    percent: int


class CategoriesOut(BaseModel):
    month: str
    total: int
    items: list[CategoryOut]


class HistoryMonthOut(BaseModel):
    month: str
    income: int
    spent: int
    saved: int


class HistoryOut(BaseModel):
    months: list[HistoryMonthOut]


class FixedItemOut(BaseModel):
    reference: str
    name: str
    currency: CurrencyName
    amount: str
    amount_crc: int | None
    status: Literal["paid", "pending", "overdue"]
    due_date: str | None
    expense_reference: str | None


class FixedOut(BaseModel):
    month: str
    pending_count: int
    overdue_count: int
    items: list[FixedItemOut]


class PendingClosuresOut(BaseModel):
    items: list[PendingClosureOut]


# --- Servicio ---


class DashboardService:
    def __init__(
        self, ledger: LedgerService, store: LedgerStore, today: Callable[[], date]
    ) -> None:
        self._ledger = ledger
        self._store = store
        self._today = today

    def current_month(self) -> Month:
        return Month.of(self._today())

    def _month(self, month: str | None) -> Month:
        if month is None or not month.strip():
            return self.current_month()
        return Month.parse(month)

    # --- Cálculos comunes ---

    def _saved_by_month(self, months: list[Month]) -> dict[Month, SavedBreakdown]:
        pockets = self._store.list_pockets()
        entries = self._store.allocation_entries()
        transfers = [
            SavingsTransfer(
                t.from_pocket_id,
                t.to_pocket_id,
                t.month,
                t.amount,
                t.reason is TransferReason.MONTH_CLOSE,
            )
            for t in self._store.list_transfers(None, None, ALL_ROWS)
        ]
        return {m: month_saved(pockets, entries, transfers, m) for m in months}

    def _unassigned(self, summary: SummaryResult) -> UnassignedOut:
        pending = self._store.pending_extras()
        crc = [row for row in pending if row.currency is Currency.CRC]
        unassigned = summary.unassigned
        return UnassignedOut(
            count=unassigned.count,
            total_crc=unassigned.total_crc,
            crc_count=len(crc),
            crc_total=sum(row.amount for row in crc),
            usd_count=unassigned.usd_count,
            usd_total=unassigned.usd_total,
        )

    @staticmethod
    def _alerts(summary: SummaryResult, unassigned: UnassignedOut) -> list[AlertOut]:
        """Avisos del mes (P4). En un mes cerrado la pantalla los reemplaza por el de solo lectura,
        pero la API los entrega igual."""
        alerts = [AlertOut(kind="close_pending", month=p.month) for p in summary.pending_closure]
        for line in summary.pockets:
            level = pocket_alert(line.percent_used, line.negative)
            if level is None:
                continue
            if level.value == "danger":
                over = -(line.available if line.available is not None else line.balance or 0)
                alerts.append(AlertOut(kind="overspent", pocket=line.pocket, amount=max(0, over)))
            else:
                alerts.append(
                    AlertOut(kind="high_usage", pocket=line.pocket, percent=line.percent_used)
                )
        if unassigned.count:
            alerts.append(
                AlertOut(
                    kind="unassigned",
                    count=unassigned.count,
                    crc_total=unassigned.crc_total,
                    usd_count=unassigned.usd_count,
                    usd_total=unassigned.usd_total,
                )
            )
        return alerts

    # --- Endpoints ---

    async def summary(self, month: str | None) -> SummaryOut:
        target = self._month(month)
        summary = await self._ledger.get_summary(str(target))
        saved = (await anyio.to_thread.run_sync(partial(self._saved_by_month, [target])))[target]
        unassigned = await anyio.to_thread.run_sync(partial(self._unassigned, summary))
        available = sum(
            line.available or 0 for line in summary.pockets if line.behavior == "consumo"
        )
        return SummaryOut(
            month=summary.month,
            current_month=str(self.current_month()),
            month_closed=summary.month_closed,
            income=summary.income_total,
            extra_income=summary.extra_income_total,
            spent=summary.expense_total,
            available=available,
            saved=saved.total,
            saved_breakdown=SavedBreakdownOut(
                base=saved.base,
                extra=saved.extra,
                transfers_in=saved.transfers_in,
                transfers_out=saved.transfers_out,
                closure_surplus=saved.closure_surplus,
            ),
            unassigned=unassigned,
            closure_adjustments=[
                AdjustmentOut(pocket=a.pocket, kind=a.kind, amount=a.amount)
                for a in summary.closure_adjustments
            ],
            pending_closure=[
                PendingClosureOut(month=p.month, has_movements=p.has_movements)
                for p in summary.pending_closure
            ],
            alerts=self._alerts(summary, unassigned),
        )

    async def pockets(self, month: str | None) -> PocketsOut:
        target = self._month(month)
        summary = await self._ledger.get_summary(str(target))
        progress = await self._ledger.get_goal_progress()  # metas activas (11.3, RN-28)
        current = Month.parse(progress.month)
        goals = {item.pocket: item for item in progress.items}
        items = []
        for line in summary.pockets:
            goal = goals.get(line.pocket) if line.behavior == "acumulable" else None
            level = pocket_alert(line.percent_used, line.negative)
            estimate = (
                estimate_goal_month(
                    current, goal.missing, goal.avg_monthly_net_change, goal.projectable
                )
                if goal is not None
                else None
            )
            items.append(
                PocketOut(
                    name=line.pocket,
                    kind=line.behavior,
                    assigned=line.assigned,
                    received=line.transfers_in,
                    sent=line.transfers_out,
                    adjusted=line.adjusted_budget,
                    spent=line.spent,
                    available=line.available,
                    used=line.percent_used,
                    used_original=line.percent_used_original,
                    balance=line.balance,
                    negative=line.negative,
                    alert=level.value if level is not None else None,
                    goal=GoalOut(
                        reference=goal.reference,
                        name=goal.name,
                        status=goal.status,
                        target=goal.target_amount,
                        balance=goal.balance,
                        progress=goal.percent,
                        remaining=goal.missing,
                        excess=goal.excess,
                        monthly_average=goal.avg_monthly_net_change,
                        projectable=goal.projectable,
                        estimated_month=str(estimate) if estimate is not None else None,
                    )
                    if goal is not None
                    else None,
                )
            )
        return PocketsOut(month=summary.month, month_closed=summary.month_closed, items=items)

    async def movements(
        self,
        month: str | None,
        type: str | None,  # noqa: A002 - mismo nombre que el filtro de la tool
        pocket: str | None,
        include_voided: bool,
        page: int,
    ) -> MovementsOut:
        if not 1 <= page <= MAX_PAGES:
            raise DomainError(f"La página debe estar entre 1 y {MAX_PAGES}.")
        result = await self._ledger.list_transactions(
            month or None, type or None, pocket or None, include_voided, page * PAGE_SIZE
        )
        start = (page - 1) * PAGE_SIZE
        rows = result.items[start : start + PAGE_SIZE]
        return MovementsOut(
            items=[
                MovementOut(
                    ref=row.reference,
                    type=row.type,
                    kind=row.kind,
                    date=row.date,
                    month=row.month,
                    description=row.description,
                    pocket=row.pocket,
                    from_pocket=row.from_pocket,
                    to_pocket=row.to_pocket,
                    category=row.category,
                    currency=row.currency,
                    original_amount=row.original_amount,
                    amount_crc=row.amount_crc,
                    voided=row.voided,
                    void_reason=row.void_reason,
                    pending=row.allocation_status == "pendiente",
                    reason=row.reason,
                    note=row.note,
                    recurring=row.recurring,
                )
                for row in rows
            ],
            page=page,
            page_size=PAGE_SIZE,
            has_more=result.has_more and page < MAX_PAGES,
        )

    async def categories(self, month: str | None) -> CategoriesOut:
        target = self._month(month)
        result = await self._ledger.top_categories(str(target), MAX_CATEGORIES)
        return CategoriesOut(
            month=result.month,
            total=result.total_spent,
            items=[
                CategoryOut(name=i.category, value=i.amount_crc, count=i.count, percent=i.percent)
                for i in result.items
            ],
        )

    def _history(self, months: list[Month]) -> HistoryOut:
        saved = self._saved_by_month(months)
        expenses = self._store.expense_entries()
        return HistoryOut(
            months=[
                HistoryMonthOut(
                    month=str(m),
                    # los mismos totales que get_summary: ingresos sin el saldo inicial
                    income=self._store.base_income_total(m) + self._store.extra_income_total(m),
                    spent=sum(e.amount for e in expenses if e.month == m),
                    saved=saved[m].total,
                )
                for m in months
            ]
        )

    async def history(self, month: str | None) -> HistoryOut:
        months = trailing_months(self._month(month))
        return await anyio.to_thread.run_sync(partial(self._history, months))

    async def fixed(self, month: str | None) -> FixedOut:
        target = self._month(month)
        result = await self._ledger.list_pending_recurring(str(target))
        items = [
            FixedItemOut(
                reference=p.reference,
                name=p.name,
                currency=p.currency,
                amount=p.amount,
                amount_crc=p.amount_crc,
                status="overdue" if p.overdue else "pending",
                due_date=p.due_date,
                expense_reference=None,
            )
            for p in result.pending
        ]
        items += [
            FixedItemOut(
                reference=p.reference,
                name=p.name,
                currency="CRC",
                amount=str(p.amount_crc),
                amount_crc=p.amount_crc,
                status="paid",
                due_date=None,
                expense_reference=p.expense_reference,
            )
            for p in result.paid
        ]
        return FixedOut(
            month=result.month,
            pending_count=result.pending_count,
            overdue_count=result.overdue_count,
            items=items,
        )

    async def pending_closures(self) -> PendingClosuresOut:
        summary = await self._ledger.get_summary(None)
        return PendingClosuresOut(
            items=[
                PendingClosureOut(month=p.month, has_movements=p.has_movements)
                for p in summary.pending_closure
            ]
        )
