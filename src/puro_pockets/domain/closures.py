"""Cierre de mes (Hito 9; sección 10, RN-44, RN-46 a RN-53, RN-58; 6.5; 11.1, 11.2 y 11.4).

Reglas puras, sin base de datos ni MCP:

- `is_closed` es la **única** función que decide si un mes está cerrado: tiene su cierre guardado o
  es anterior o igual al último mes cerrado (los cierres van en orden, así que un mes anterior ya
  no puede recibir nada). La usan los servicios (para fallar temprano) y el almacén (dentro de cada
  transacción de escritura) a través de `check_open`.
- Qué mes se puede cerrar (`check_closable`) y cuáles tienen el cierre pendiente (`pending_closure`,
  RN-49).
- `analyze` arma los datos del mes (sobrante o déficit de cada bolsa de consumo, saldo de cada
  acumulable) y `plan_close` valida una propuesta de coberturas y destinos (10.1, 10.2, RN-47,
  RN-50, RN-52) y calcula el resultado: transferencias, ajustes y efecto en metas (RN-58). La app
  no recomienda (principio 3.1): la propuesta la arma Claude.

Los mensajes nunca incluyen montos.
"""

from __future__ import annotations

import calendar
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum

from puro_pockets.domain.balances import PocketFigures
from puro_pockets.domain.errors import (
    ClosureProposalInvalid,
    DomainError,
    MonthClosed,
    MonthNotClosable,
)
from puro_pockets.domain.goals import Goal
from puro_pockets.domain.money import MAX_MONEY
from puro_pockets.domain.months import Month
from puro_pockets.domain.pockets import Behavior, Pocket, is_plain_int, normalize_name
from puro_pockets.domain.transfers import GoalEffect, goal_effect

CLOSED_WARNING = (
    "Al cerrar, el mes {month} no admitirá más movimientos (gastos, ingresos, extras, repartos, "
    "transferencias ni anulaciones), ni siquiera los de hoy. Un cierre no se reabre."
)


class AdjustmentKind(StrEnum):
    UNASSIGNED_SURPLUS = "sobrante_no_destinado"  # suma (RN-50, 10.2)
    UNCOVERED_OVERSPEND = "sobregasto_no_cubierto"  # resta (RN-50)


class Situation(StrEnum):
    SURPLUS = "sobrante"
    DEFICIT = "deficit"
    ZERO = "cero"


# --- Estado de los meses ---


@dataclass(frozen=True)
class ClosedMonths:
    """Los meses con cierre guardado."""

    months: frozenset[Month] = frozenset()

    @property
    def latest(self) -> Month | None:
        return max(self.months) if self.months else None


def is_closed(month: Month, closed: ClosedMonths) -> bool:
    """La única regla de "mes cerrado" (RN-44, RN-48, RN-53): cerrado, o anterior al último
    cerrado."""
    latest = closed.latest
    return month in closed.months or (latest is not None and month <= latest)


def check_open(month: Month, closed: ClosedMonths) -> None:
    """Lanza `MonthClosed` si el mes no admite escrituras."""
    if is_closed(month, closed):
        raise MonthClosed(str(month), earlier=month not in closed.months)


def last_day(month: Month) -> date:
    return date(month.year, month.month, calendar.monthrange(month.year, month.month)[1])


def first_open(today: date, closed: ClosedMonths) -> Month:
    """El primer mes abierto desde el mes de hoy (el de hoy, o el siguiente si hoy ya se cerró)."""
    month = Month.of(today)
    while is_closed(month, closed):
        month = month.next()
    return month


@dataclass(frozen=True)
class ClosureState:
    """Lo que el almacén sabe de los cierres: meses cerrados y meses con movimientos."""

    closed: ClosedMonths
    movement_months: frozenset[Month]

    @property
    def oldest(self) -> Month | None:
        return min(self.movement_months) if self.movement_months else None

    def first_closable(self) -> Month | None:
        """El siguiente al último cerrado; sin cierres, el más antiguo con movimientos (P1)."""
        latest = self.closed.latest
        if latest is not None:
            return latest.next()
        return self.oldest


def check_closable(
    month: Month, today: date, state: ClosureState, allow_early: bool = False
) -> None:
    """P1 y PROPUESTO 1 a 3: desde su último día, en orden estricto y nunca dos veces. Con
    `allow_early` (solo la vista previa) no exige haber llegado al último día."""
    label = str(month)
    if is_closed(month, state.closed):
        if month in state.closed.months:
            raise MonthNotClosable(label, "ya está cerrado. Un cierre no se reabre.")
        raise MonthNotClosable(label, "es anterior a un mes ya cerrado y cuenta como cerrado.")
    if month > Month.of(today):
        raise MonthNotClosable(label, "es un mes futuro.")
    first = state.first_closable()
    if first is None:
        raise MonthNotClosable(label, "todavía no hay movimientos; no hay nada que cerrar.")
    if month < first:
        raise MonthNotClosable(
            label, "es anterior al primer mes con movimientos; no hace falta cerrarlo."
        )
    if month > first:
        raise MonthNotClosable(label, f"los cierres van en orden y antes hay que cerrar {first}.")
    if not allow_early and today < last_day(month):
        raise MonthNotClosable(
            label, f"se puede cerrar desde su último día ({last_day(month).isoformat()})."
        )


@dataclass(frozen=True)
class PendingClosure:
    month: Month
    has_movements: bool


def pending_closure(today: date, state: ClosureState) -> list[PendingClosure]:
    """RN-49: meses ya terminados (o en su último día) sin cerrar, desde el primero cerrable. Un mes
    vacío en medio también se lista: los cierres van en orden (PROPUESTO 1)."""
    month = state.first_closable()
    result: list[PendingClosure] = []
    while month is not None and last_day(month) <= today:
        result.append(PendingClosure(month, month in state.movement_months))
        month = month.next()
    return result


def default_close_month(today: date, state: ClosureState) -> Month | None:
    """El mes más antiguo cerrable hoy, o None si no hay ninguno."""
    pending = pending_closure(today, state)
    return pending[0].month if pending else None


# --- Datos del mes ---


@dataclass(frozen=True)
class ConsumptionLine:
    figures: PocketFigures

    @property
    def pocket(self) -> Pocket:
        return self.figures.pocket

    @property
    def available(self) -> int:
        return self.figures.available or 0

    @property
    def situation(self) -> Situation:
        if self.available > 0:
            return Situation.SURPLUS
        if self.available < 0:
            return Situation.DEFICIT
        return Situation.ZERO


@dataclass(frozen=True)
class AccumulableLine:
    figures: PocketFigures
    goal: Goal | None

    @property
    def pocket(self) -> Pocket:
        return self.figures.pocket

    @property
    def balance(self) -> int:
        return self.figures.balance or 0


@dataclass(frozen=True)
class MonthPicture:
    """Datos del mes para el cierre (11.1 y 11.2). Las archivadas solo aparecen si tienen cifras
    distintas de cero en el mes (PROPUESTO 7)."""

    month: Month
    consumption: tuple[ConsumptionLine, ...]
    accumulable: tuple[AccumulableLine, ...]

    def warnings(self) -> list[str]:
        notes = [CLOSED_WARNING.format(month=self.month)]
        for line in self.consumption:
            if not line.pocket.active and line.situation is not Situation.ZERO:
                notes.append(
                    f"La bolsa {line.pocket.name} está archivada: no envía ni recibe en el cierre "
                    "y su sobrante o déficit queda en la tabla de ajustes."
                )
        for line in self.accumulable:
            if line.balance < 0:  # 2c: advertencia con el camino para corregirla
                notes.append(
                    f"La bolsa acumulable {line.pocket.name} tiene saldo negativo: el cierre no la "
                    "corrige (conserva su saldo, RN-12). Puedes cubrirla con una transferencia "
                    "hacia ella (preview_transfer, motivo cubrir_sobregasto) en un mes abierto."
                )
        return notes


def analyze(
    month: Month,
    pockets: Iterable[Pocket],
    figures_of: Mapping[int, PocketFigures],
    goals: Iterable[Goal],
) -> MonthPicture:
    live = {g.pocket_id: g for g in goals if g.live}
    consumption: list[ConsumptionLine] = []
    accumulable: list[AccumulableLine] = []
    for pocket in sorted(pockets, key=lambda p: p.id):
        figures = figures_of[pocket.id]
        if pocket.behavior is Behavior.CONSUMO:
            line = ConsumptionLine(figures)
            if pocket.active or line.situation is not Situation.ZERO:
                consumption.append(line)
        elif pocket.active:
            accumulable.append(AccumulableLine(figures, live.get(pocket.id)))
    return MonthPicture(month, tuple(consumption), tuple(accumulable))


# --- Propuesta y resultado ---


@dataclass(frozen=True)
class Move:
    """Una cobertura o un destino. `target` None = sobrante no destinado (explícito)."""

    source: Pocket
    target: Pocket | None
    amount: int

    @property
    def from_balance(self) -> bool:
        """RN-52: la cobertura sale del saldo de una acumulable."""
        return self.source.behavior is Behavior.ACUMULABLE


@dataclass(frozen=True)
class Adjustment:
    pocket: Pocket
    kind: AdjustmentKind
    amount: int  # con signo: sobrante +, sobregasto −


@dataclass(frozen=True)
class PocketOutcome:
    pocket: Pocket
    before: int  # disponible del mes (consumo) o saldo (acumulable)
    after: int


@dataclass(frozen=True)
class ClosePlan:
    month: Month
    covers: tuple[Move, ...]
    destinations: tuple[Move, ...]
    adjustments: tuple[Adjustment, ...]
    outcomes: tuple[PocketOutcome, ...]
    goal_effects: tuple[GoalEffect, ...]
    warnings: tuple[str, ...] = field(default=())

    @property
    def transfers(self) -> tuple[Move, ...]:
        """Las transferencias `cierre_de_mes` a guardar, en orden 10.1: coberturas y después
        destinos hacia acumulables."""
        return (*self.covers, *(d for d in self.destinations if d.target is not None))

    def total(self, kind: AdjustmentKind) -> int:
        return sum(a.amount for a in self.adjustments if a.kind is kind)


def _amount(value: object) -> int:
    if isinstance(value, float) or not is_plain_int(value):
        raise ClosureProposalInvalid("cada monto es un entero positivo en colones, sin decimales.")
    if not 0 < value <= MAX_MONEY:  # type: ignore[operator]
        raise ClosureProposalInvalid("cada monto debe ser mayor que 0.")
    return int(value)  # type: ignore[call-overload]


def _pocket(pockets: Sequence[Pocket], name: object) -> Pocket:
    if isinstance(name, str) and name.strip():
        key = normalize_name(name)
        for pocket in pockets:
            if normalize_name(pocket.name) == key:
                if not pocket.active:
                    raise ClosureProposalInvalid(
                        f"la bolsa '{pocket.name}' está archivada: no participa en el cierre."
                    )
                return pocket
        raise ClosureProposalInvalid(f"la bolsa '{name.strip()}' no existe.")
    raise ClosureProposalInvalid("cada movimiento necesita el nombre de su bolsa de origen.")


def parse_moves(
    raw: Sequence[Mapping[str, object]] | None, pockets: Sequence[Pocket], allow_null: bool
) -> list[Move]:
    """Lee coberturas (`allow_null=False`) o destinos (`to_pocket` puede ser null)."""
    moves: list[Move] = []
    seen: set[tuple[int, int | None]] = set()
    for item in raw or ():
        if not isinstance(item, Mapping):
            raise ClosureProposalInvalid("cada movimiento lleva origen, destino y monto.")
        source = _pocket(pockets, item.get("from_pocket"))
        target_name = item.get("to_pocket")
        if target_name is None or (isinstance(target_name, str) and not target_name.strip()):
            if not allow_null:
                raise ClosureProposalInvalid("cada cobertura necesita una bolsa de destino.")
            target = None
        else:
            target = _pocket(pockets, target_name)
        if target is not None and target.id == source.id:
            raise ClosureProposalInvalid(
                f"el origen y el destino son la misma bolsa ({source.name})."
            )
        key = (source.id, None if target is None else target.id)
        if key in seen:
            raise ClosureProposalInvalid(
                f"el par {source.name} → {target.name if target else 'no destinado'} aparece más "
                "de una vez; súmalo en un solo movimiento."
            )
        seen.add(key)
        moves.append(Move(source, target, _amount(item.get("amount"))))
    return moves


def plan_close(
    picture: MonthPicture, covers: Sequence[Move], destinations: Sequence[Move]
) -> ClosePlan:
    """Valida la propuesta (10.1, 10.2, RN-47, RN-52) y calcula el resultado (RN-50, RN-58)."""
    by_id_consumption = {line.pocket.id: line for line in picture.consumption}
    by_id_accumulable = {line.pocket.id: line for line in picture.accumulable}
    surplus = {
        pid: line.available
        for pid, line in by_id_consumption.items()
        if line.pocket.active and line.available > 0
    }
    deficit = {
        pid: -line.available
        for pid, line in by_id_consumption.items()
        if line.pocket.active and line.available < 0
    }
    out: dict[int, int] = defaultdict(int)  # todo lo asignado: transferencias y null (RN-47)
    moved: dict[int, int] = defaultdict(int)  # solo lo que sale con una transferencia
    cover_in: dict[int, int] = defaultdict(int)
    dest_in: dict[int, int] = defaultdict(int)

    for move in covers:
        target = move.target
        assert target is not None  # parse_moves lo exige en coberturas
        if target.behavior is not Behavior.CONSUMO or target.id not in deficit:
            raise ClosureProposalInvalid(
                f"una cobertura va hacia una bolsa de consumo con déficit en el mes, y "
                f"'{target.name}' no lo tiene."
            )
        if move.source.behavior is Behavior.CONSUMO:
            if move.source.id not in surplus:
                raise ClosureProposalInvalid(
                    f"'{move.source.name}' no tiene sobrante en el mes para cubrir un déficit."
                )
        else:
            line = by_id_accumulable.get(move.source.id)
            if line is None or line.balance <= 0:
                raise ClosureProposalInvalid(
                    f"la bolsa acumulable '{move.source.name}' no tiene saldo positivo para cubrir."
                )
        cover_in[target.id] += move.amount
        out[move.source.id] += move.amount
        moved[move.source.id] += move.amount

    for move in destinations:
        if move.source.behavior is not Behavior.CONSUMO or move.source.id not in surplus:
            raise ClosureProposalInvalid(
                f"un destino reparte el sobrante de una bolsa de consumo, y '{move.source.name}' "
                "no tiene sobrante en el mes."
            )
        if move.target is not None and move.target.behavior is not Behavior.ACUMULABLE:
            raise ClosureProposalInvalid(
                f"el destino de un sobrante es una bolsa acumulable activa o null (sobrante no "
                f"destinado), y '{move.target.name}' no es acumulable (10.2)."
            )
        out[move.source.id] += move.amount
        if move.target is not None:  # null: se queda en el mes como sobrante no destinado
            moved[move.source.id] += move.amount
            dest_in[move.target.id] += move.amount

    for pid, got in cover_in.items():
        if got > deficit[pid]:
            name = by_id_consumption[pid].pocket.name
            raise ClosureProposalInvalid(
                f"lo que recibe '{name}' supera su déficit; cubrir de más sería enviar un sobrante "
                "a una bolsa de consumo (10.2)."
            )
    for pid, gone in out.items():
        if pid in by_id_consumption:
            if gone > surplus.get(pid, 0):
                raise ClosureProposalInvalid(
                    f"lo que sale de '{by_id_consumption[pid].pocket.name}' supera su sobrante "
                    "(RN-47)."
                )
        elif gone > by_id_accumulable[pid].balance:
            raise ClosureProposalInvalid(
                f"lo que sale de '{by_id_accumulable[pid].pocket.name}' supera su saldo (RN-47)."
            )

    uncovered = sum(deficit[pid] - cover_in.get(pid, 0) for pid in deficit)
    consumption_to_covers = sum(m.amount for m in covers if not m.from_balance)
    any_from_balance = any(m.from_balance for m in covers)
    if (uncovered > 0 or any_from_balance) and consumption_to_covers < sum(surplus.values()):
        raise ClosureProposalInvalid(
            "primero se cubren los déficits con los sobrantes de las bolsas de consumo (10.1). "
            "Mientras quede un déficit sin cubrir, o si una cobertura sale del saldo de una "
            "acumulable (RN-52), todo el sobrante de consumo debe ir a coberturas."
        )

    adjustments: list[Adjustment] = []
    outcomes: list[PocketOutcome] = []
    for line in picture.consumption:
        pid = line.pocket.id
        after = line.available - moved.get(pid, 0) + cover_in.get(pid, 0)
        outcomes.append(PocketOutcome(line.pocket, line.available, after))
        if after > 0:
            adjustments.append(Adjustment(line.pocket, AdjustmentKind.UNASSIGNED_SURPLUS, after))
        elif after < 0:
            adjustments.append(Adjustment(line.pocket, AdjustmentKind.UNCOVERED_OVERSPEND, after))
    effects: list[GoalEffect] = []
    notes = picture.warnings()
    for line in picture.accumulable:
        pid = line.pocket.id
        after = line.balance - moved.get(pid, 0) + dest_in.get(pid, 0)
        outcomes.append(PocketOutcome(line.pocket, line.balance, after))
        if line.goal is not None and after != line.balance:
            effect = goal_effect(line.goal, line.balance, after)
            effects.append(effect)
            notes.append(effect.message)
    for move in covers:
        if move.from_balance:
            notes.append(
                f"La cobertura desde {move.source.name} usa su saldo acumulado (RN-52): requiere "
                "la aprobación explícita del propietario; si no la da, quítala y lo no cubierto "
                "queda como sobregasto no cubierto (RN-50)."
            )
    if uncovered > 0:
        notes.append(
            "Queda sobregasto no cubierto: se registra en la tabla de ajustes y el mes se cierra "
            "igual (RN-50)."
        )
    return ClosePlan(
        picture.month,
        tuple(covers),
        tuple(destinations),
        tuple(adjustments),
        tuple(outcomes),
        tuple(effects),
        tuple(notes),
    )


def require_month(value: object) -> Month:
    if value is None or (isinstance(value, str) and not value.strip()):
        raise DomainError("Indica el mes a cerrar (AAAA-MM), el mismo de la vista previa.")
    return Month.parse(value)
