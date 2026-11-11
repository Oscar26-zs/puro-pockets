"""Casos de uso del presupuesto (Hito 4): porcentajes por mes, saldo inicial y saldos de bolsas.

Las reglas viven en `domain/`; aquí se orquesta el almacén y el reloj. El almacén es síncrono
(psycopg 3 en modo síncrono), así que sus llamadas corren en un hilo. Los registros nunca
incluyen montos ni saldos.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from functools import partial
from typing import Protocol, TypeVar
from zoneinfo import ZoneInfo

import anyio

from puro_pockets.domain.allocation import (
    ResolvedAllocation,
    ensure_editable,
    pick_source_month,
    resolve_allocation,
    validate_allocation,
)
from puro_pockets.domain.balances import AllocationEntry, IncomeKind, PocketBalance, pocket_balance
from puro_pockets.domain.errors import InitialBalanceAlreadyLoaded
from puro_pockets.domain.initial_balance import validate_initial_balance
from puro_pockets.domain.months import Month
from puro_pockets.domain.pockets import Pocket, ordered_active

logger = logging.getLogger("puro_pockets.budget")

T = TypeVar("T")


@dataclass(frozen=True)
class AllocationLine:
    """Lo asignado a una bolsa por un ingreso: porcentaje (None si es por monto) y monto."""

    pocket_id: int
    percentage: int | None
    amount: int


class BudgetStore(Protocol):
    """Almacén del presupuesto. Cada método es una transacción propia."""

    def list_pockets(self) -> list[Pocket]: ...

    def allocation_months(self, up_to: Month) -> list[Month]: ...

    def allocation_rows(self, month: Month) -> dict[int, int]: ...

    def replace_allocation(self, month: Month, rows: Mapping[int, int]) -> None: ...

    def has_initial_balance(self) -> bool: ...

    def record_distributed_income(
        self,
        kind: IncomeKind,
        income_date: date,
        budget_month: Month,
        lines: Sequence[AllocationLine],
    ) -> int:
        """Guarda un ingreso ya repartido y sus repartos en una transacción.

        Un segundo saldo inicial lanza `InitialBalanceAlreadyLoaded` (índice único).
        """
        ...

    def allocation_entries(self) -> list[AllocationEntry]: ...

    def distributed_income_total(self) -> int: ...


@dataclass(frozen=True)
class InitialBalanceView:
    month: Month
    total: int
    items: tuple[tuple[Pocket, int], ...]
    already_loaded: bool
    saved: bool = False


@dataclass(frozen=True)
class PocketsView:
    month: Month
    pockets: tuple[PocketBalance, ...]


def local_today(timezone: str) -> Callable[[], date]:
    zone = ZoneInfo(timezone)
    return lambda: datetime.now(zone).date()


class BudgetService:
    def __init__(self, store: BudgetStore, today: Callable[[], date]) -> None:
        self._store = store
        self._today = today

    async def _run(self, fn: Callable[[], T]) -> T:
        return await anyio.to_thread.run_sync(fn)

    def current_month(self) -> Month:
        return Month.of(self._today())

    def _month(self, month: str | None) -> Month:
        return self.current_month() if month is None else Month.parse(month)

    # --- Porcentajes (RN-01, RN-02, RN-03) ---

    async def set_allocation(
        self, percentages: Sequence[tuple[object, object]], month: str | None = None
    ) -> ResolvedAllocation:
        target = self._month(month)
        ensure_editable(target, self.current_month())
        pockets = await self._run(self._store.list_pockets)
        rows = validate_allocation(percentages, pockets)
        await self._run(partial(self._store.replace_allocation, target, rows))
        logger.info("Porcentajes guardados: mes=%s bolsas=%d", target, len(rows))
        return resolve_allocation(target, target, rows, pockets)

    async def get_allocation(self, month: str | None = None) -> ResolvedAllocation:
        target = self._month(month)
        return await self._run(partial(self._resolve, target))

    def _resolve(self, month: Month) -> ResolvedAllocation:
        pockets = self._store.list_pockets()
        source = pick_source_month(month, self._store.allocation_months(month))
        rows = self._store.allocation_rows(source) if source is not None else {}
        return resolve_allocation(month, source, rows, pockets)

    # --- Saldo inicial (RN-54) ---

    async def preview_initial_balance(
        self, amounts: Sequence[tuple[object, object]]
    ) -> InitialBalanceView:
        """Vista previa: valida y calcula, sin guardar nada (principio 3.2)."""
        pockets = await self._run(self._store.list_pockets)
        items = validate_initial_balance(amounts, pockets)
        loaded = await self._run(self._store.has_initial_balance)
        return InitialBalanceView(
            month=self.current_month(),
            total=sum(amount for _, amount in items),
            items=tuple(items),
            already_loaded=loaded,
        )

    async def load_initial_balance(
        self, amounts: Sequence[tuple[object, object]], confirm: bool = False
    ) -> InitialBalanceView:
        """Carga el saldo inicial una sola vez. Sin `confirm=True` solo devuelve la vista previa."""
        preview = await self.preview_initial_balance(amounts)
        if not confirm:
            return preview
        if preview.already_loaded:
            logger.warning("Segunda carga del saldo inicial rechazada")
            raise InitialBalanceAlreadyLoaded()
        lines = [AllocationLine(p.id, None, amount) for p, amount in preview.items]
        try:
            await self._run(
                partial(
                    self._store.record_distributed_income,
                    IncomeKind.INITIAL_BALANCE,
                    self._today(),
                    preview.month,
                    lines,
                )
            )
        except InitialBalanceAlreadyLoaded:
            logger.warning("Carga simultánea del saldo inicial rechazada")
            raise
        logger.info("Saldo inicial cargado: mes=%s bolsas=%d", preview.month, len(lines))
        return InitialBalanceView(
            month=preview.month,
            total=preview.total,
            items=preview.items,
            already_loaded=True,
            saved=True,
        )

    # --- Bolsas y saldos (RN-10 a RN-12) ---

    async def list_pockets(self) -> PocketsView:
        return await self._run(self._list_pockets)

    def _list_pockets(self) -> PocketsView:
        current = self.current_month()
        pockets = ordered_active(self._store.list_pockets())
        entries = self._store.allocation_entries()
        return PocketsView(current, tuple(pocket_balance(p, entries, current) for p in pockets))
