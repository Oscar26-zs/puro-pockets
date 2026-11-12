"""Base común de los casos de uso de movimientos: almacén, reloj, idempotencia y vistas compartidas.

`LedgerService` (Hito 5) y sus mixins de extras y gastos fijos (Hito 6) heredan de `LedgerCore`. El
almacén es síncrono, así que sus llamadas corren en un hilo. Los registros nunca incluyen montos ni
descripciones.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Literal, TypeVar

import anyio
from pydantic import BaseModel, Field

from puro_pockets.domain.balances import (
    AllocationEntry,
    ExpenseEntry,
    PocketBalance,
    PocketFigures,
    TransferEntry,
    pocket_figures,
)
from puro_pockets.domain.errors import DomainError, IdempotencyConflict
from puro_pockets.domain.money import Currency, RateRange, format_original
from puro_pockets.domain.months import Month
from puro_pockets.domain.pockets import Pocket, is_plain_int
from puro_pockets.domain.recurring import PendingRecurring, pending_in_month
from puro_pockets.services.records import IncomeRow, LedgerStore, Operation

logger = logging.getLogger("puro_pockets.ledger")

T = TypeVar("T")

BehaviorName = Literal["consumo", "acumulable"]
BalanceKindName = Literal["saldo", "disponible_del_mes"]
CurrencyName = Literal["CRC", "USD"]


class AllocationShare(BaseModel):
    pocket: str
    behavior: BehaviorName
    percentage: int
    amount: int = Field(description="Colones.")


class PocketFigure(BaseModel):
    pocket: str
    balance: int = Field(description="Colones: saldo (acumulable) o disponible del mes (consumo).")
    balance_kind: BalanceKindName


class UnassignedSummary(BaseModel):
    """Extras pendientes de repartir (RN-06): no suman a ninguna bolsa."""

    count: int = Field(description="Cuántos extras siguen pendientes (de cualquier mes).")
    total_crc: int = Field(
        description="Total en colones de todos los pendientes (los de USD con el equivalente "
        "calculado al registrarlos, RN-57)."
    )
    usd_count: int = Field(description="Cuántos de los pendientes son en dólares.")
    usd_total: str = Field(description="Total original de los pendientes en dólares (USD).")
    references: list[str] = Field(description="Referencias (I-n) de los extras pendientes.")


def figure(balance: PocketBalance) -> PocketFigure:
    return PocketFigure(
        pocket=balance.pocket.name, balance=balance.balance, balance_kind=balance.kind.value
    )


def parse_limit(value: object, default: int, maximum: int) -> int:
    if value is None:
        return default
    if not is_plain_int(value) or not 1 <= value <= maximum:  # type: ignore[operator]
        raise DomainError(f"El límite debe ser un entero entre 1 y {maximum}.")
    return int(value)  # type: ignore[call-overload]


def unassigned_summary(pending: list[IncomeRow]) -> UnassignedSummary:
    usd = [row for row in pending if row.currency is Currency.USD]
    return UnassignedSummary(
        count=len(pending),
        total_crc=sum(row.amount for row in pending),
        usd_count=len(usd),
        usd_total=format_original(Currency.USD, sum(row.original_amount for row in usd)),
        references=[f"I-{row.id}" for row in sorted(pending, key=lambda r: r.id)],
    )


@dataclass(frozen=True)
class LedgerData:
    """Repartos, gastos y transferencias vigentes, leídos una vez por consulta."""

    entries: list[AllocationEntry]
    expenses: list[ExpenseEntry]
    transfers: list[TransferEntry]

    def figures(self, pocket: Pocket, month: Month) -> PocketFigures:
        """Las cifras oficiales de la bolsa (9.1, 11.1, 11.2): siempre `pocket_figures`."""
        return pocket_figures(pocket, month, self.entries, self.expenses, self.transfers)


class LedgerCore:
    def __init__(
        self,
        store: LedgerStore,
        today: Callable[[], date],
        rate_range: RateRange,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._store = store
        self._today = today
        self._rates = rate_range
        self._now = now or (lambda: datetime.now(UTC))

    def _data(self) -> LedgerData:
        return LedgerData(
            self._store.allocation_entries(),
            self._store.expense_entries(),
            self._store.transfer_entries(),
        )

    async def _run(self, fn: Callable[[], T]) -> T:
        return await anyio.to_thread.run_sync(fn)

    def _month(self, month: object) -> Month:
        if month is None or (isinstance(month, str) and not month.strip()):
            return Month.of(self._today())
        return Month.parse(month)

    def _pending_recurring(self, month: Month) -> list[PendingRecurring]:
        """RN-35/RN-36: fijos activos sin pago vigente en el mes (lista y contexto de extras)."""
        payments = self._store.recurring_payments(month)
        return pending_in_month(self._store.list_recurring(), payments, month, self._today())

    # --- Idempotencia ---

    def _replay(self, operation: Operation) -> dict | None:
        stored = self._store.get_operation(operation.operation_id)
        if stored is None:
            return None
        if stored.tool != operation.tool or stored.fingerprint != operation.fingerprint:
            logger.warning(
                "Clave de operación reutilizada con otro contenido: tool=%s", operation.tool
            )
            raise IdempotencyConflict()
        logger.info("Reintento con la misma clave: tool=%s (sin duplicar)", operation.tool)
        return stored.response

    def _after_race(self, operation: Operation) -> dict:
        replay = self._replay(operation)
        if replay is None:  # pragma: no cover - la clave existe si hubo carrera
            raise DomainError("No se pudo completar la operación; reinténtala con la misma clave.")
        return replay
