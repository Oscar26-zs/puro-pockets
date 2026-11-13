"""Estadísticas del dashboard (Hito 10; plan técnico, sección 13.3). Capa de dominio: puro.

No agrega reglas de negocio: agrega cifras oficiales para las preguntas de la sección 13.1. Lo
asignado y las transferencias son las mismas entradas que usa `balances.pocket_figures`; lo anulado
no llega aquí (el almacén solo entrega movimientos vigentes, RN-53). Todo en colones enteros.

- `month_saved` [PROPUESTO]: "Ahorrado" del mes, con desglose por origen.
- `estimate_goal_month` [PROPUESTO]: fecha estimada de una meta con los números de RN-28.
- `pocket_alert` [PROPUESTO]: uso alto (≥ 80 %) y sobregasto (≥ 100 % o negativo, RN-38).
- `trailing_months`: los meses de la evolución mensual.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum

from puro_pockets.domain.balances import AllocationEntry, IncomeKind
from puro_pockets.domain.months import Month
from puro_pockets.domain.pockets import Behavior, Pocket

HIGH_USAGE_PERCENT = 80
OVERSPENT_PERCENT = 100
HISTORY_MONTHS = 6


@dataclass(frozen=True)
class SavingsTransfer:
    """Una transferencia con lo que el "ahorrado" necesita saber: si es del cierre de mes."""

    from_pocket_id: int
    to_pocket_id: int
    month: Month
    amount: int
    month_close: bool


@dataclass(frozen=True)
class SavedBreakdown:
    base: int
    extra: int
    transfers_in: int
    transfers_out: int
    closure_surplus: int

    @property
    def total(self) -> int:
        return (
            self.base + self.extra + self.transfers_in - self.transfers_out + self.closure_surplus
        )


def month_saved(
    pockets: Iterable[Pocket],
    entries: Iterable[AllocationEntry],
    transfers: Iterable[SavingsTransfer],
    month: Month,
) -> SavedBreakdown:
    """Ahorrado(M) = base + extras + recibidas − enviadas + sobrantes de cierre (plan técnico 13.3).

    - base / extras: lo asignado a bolsas acumulables por ingresos base / extra con mes
      presupuestario M; el saldo inicial no cuenta (RN-54).
    - sobrantes de cierre: transferencias `cierre_de_mes` del mes M desde una bolsa de consumo hacia
      una acumulable (destinos de sobrante, 10.2).
    - recibidas: las demás transferencias del mes M hacia una acumulable.
    - enviadas: transferencias del mes M desde una acumulable (incluye coberturas de cierre, RN-52).
    Entre dos acumulables, la recibida y la enviada se anulan. Incluye bolsas archivadas.
    """
    accumulable = {p.id for p in pockets if p.behavior is Behavior.ACUMULABLE}
    base = extra = received = sent = surplus = 0
    for entry in entries:
        if entry.budget_month != month or entry.pocket_id not in accumulable:
            continue
        if entry.income_kind is IncomeKind.BASE:
            base += entry.amount
        elif entry.income_kind is IncomeKind.EXTRA:
            extra += entry.amount
    for transfer in transfers:
        if transfer.month != month:
            continue
        to_acc = transfer.to_pocket_id in accumulable
        from_acc = transfer.from_pocket_id in accumulable
        if to_acc and transfer.month_close and not from_acc:
            surplus += transfer.amount
        elif to_acc:
            received += transfer.amount
        if from_acc:
            sent += transfer.amount
    return SavedBreakdown(base, extra, received, sent, surplus)


def estimate_goal_month(
    current: Month, missing: int, average: int | None, projectable: bool
) -> Month | None:
    """Mes estimado para completar una meta [PROPUESTO]: ⌈faltante ÷ promedio mensual⌉ meses desde
    el mes actual, con el promedio de RN-28. Sin estimación si no es proyectable, si el promedio no
    es positivo o si ya no falta nada."""
    if not projectable or average is None or average <= 0 or missing <= 0:
        return None
    months = -(-missing // average)  # techo con enteros, sin float
    target = current
    for _ in range(months):
        target = target.next()
    return target


class PocketAlert(StrEnum):
    WARNING = "warning"  # uso alto
    DANGER = "danger"  # sobregasto


def pocket_alert(percent_used: int | None, negative: bool) -> PocketAlert | None:
    """Alerta de una bolsa (plan técnico 13.2) [PROPUESTO]: sobregasto si el % usado sobre el
    ajustado llega a 100 o la bolsa está en negativo (RN-38); uso alto desde 80 %."""
    if negative or (percent_used is not None and percent_used >= OVERSPENT_PERCENT):
        return PocketAlert.DANGER
    if percent_used is not None and percent_used >= HIGH_USAGE_PERCENT:
        return PocketAlert.WARNING
    return None


def trailing_months(last: Month, count: int = HISTORY_MONTHS) -> list[Month]:
    """Los `count` meses que terminan en `last`, del más antiguo al más reciente."""
    months = [last]
    while len(months) < count:
        months.append(months[-1].previous())
    return list(reversed(months))
