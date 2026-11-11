"""Transferencias entre bolsas (sección 9; RN-39 a RN-44 y RN-58). RN-45 está derogada.

Una transferencia mueve colones de una bolsa a otra y queda en un registro que nunca se edita ni se
borra (RN-43): un error se corrige con otra transferencia en sentido contrario. Siempre en colones,
sin moneda ni tipo de cambio. La fecha es hoy (America/Costa_Rica) y el mes es el de esa fecha;
hasta el Hito 9 todos los meses están abiertos (RN-44 se completa allí).

Las cifras de cada bolsa salen de `balances.pocket_figures` (la misma función de las consultas):
lo disponible para mover (RN-42) es el saldo de una acumulable o el disponible del mes de una de
consumo. Los errores nunca incluyen montos, notas ni nombres de metas.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from enum import StrEnum

from puro_pockets.domain.balances import PocketFigures
from puro_pockets.domain.errors import (
    DomainError,
    TransferExceedsAvailable,
    TransferFromNegative,
    TransferSamePocket,
)
from puro_pockets.domain.goals import Goal, progress
from puro_pockets.domain.ledger import parse_date
from puro_pockets.domain.money import MAX_MONEY
from puro_pockets.domain.pockets import Behavior, Pocket, is_plain_int

MAX_NOTE = 140
_REF = re.compile(r"^\s*[Tt]\s*-\s*([0-9]{1,18})\s*$")


class TransferReason(StrEnum):
    """Motivos permitidos (sección 9). `cierre_de_mes` lo usa solo el cierre del Hito 9."""

    COVER_OVERSPEND = "cubrir_sobregasto"
    REASSIGNMENT = "reasignacion"
    MONTH_CLOSE = "cierre_de_mes"
    ADJUSTMENT = "ajuste"


TOOL_REASONS = (
    TransferReason.COVER_OVERSPEND,
    TransferReason.REASSIGNMENT,
    TransferReason.ADJUSTMENT,
)


@dataclass(frozen=True)
class TransferRef:
    number: int

    @classmethod
    def parse(cls, text: object) -> TransferRef:
        found = _REF.match(text) if isinstance(text, str) else None
        if found is None or int(found.group(1)) < 1:
            raise DomainError("La transferencia se indica por su referencia T-n.")
        return cls(int(found.group(1)))

    @staticmethod
    def matches(text: object) -> bool:
        return isinstance(text, str) and _REF.match(text) is not None

    def __str__(self) -> str:
        return f"T-{self.number}"


def parse_reason(value: object) -> TransferReason:
    """Motivo de una transferencia pedida por la tool; `cierre_de_mes` queda para el Hito 9."""
    text = value.strip().casefold() if isinstance(value, str) else ""
    if text == TransferReason.MONTH_CLOSE.value:
        raise DomainError(
            "El motivo 'cierre_de_mes' está reservado para el cierre de mes (Hito 9). Usa "
            "cubrir_sobregasto, reasignacion o ajuste."
        )
    for reason in TOOL_REASONS:
        if text == reason.value:
            return reason
    raise DomainError("El motivo debe ser cubrir_sobregasto, reasignacion o ajuste.")


def validate_note(value: object) -> str | None:
    """Nota opcional de hasta 140 caracteres. Nunca va a los registros ni a los errores."""
    if value is None:
        return None
    if not isinstance(value, str):
        raise DomainError("La nota debe ser texto.")
    text = value.strip()
    if len(text) > MAX_NOTE:
        raise DomainError(f"La nota admite como máximo {MAX_NOTE} caracteres.")
    return text or None


def parse_transfer_amount(value: object) -> int:
    """RN-41: entero positivo en colones (sin decimales ni moneda)."""
    if isinstance(value, float) or not is_plain_int(value):
        raise DomainError(
            "El monto de una transferencia es en colones: un entero positivo, sin decimales."
        )
    if not 0 < value <= MAX_MONEY:  # type: ignore[operator]
        raise DomainError("El monto de una transferencia debe ser mayor que 0 (RN-41).")
    return int(value)  # type: ignore[call-overload]


def transfer_date(value: object, today: date) -> date:
    """La fecha de una transferencia es siempre hoy: se puede omitir o repetir, pero no cambiar."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return today
    day = parse_date(value, "de la transferencia")
    if day != today:
        raise DomainError(
            "Una transferencia se registra siempre con la fecha de hoy "
            f"({today.isoformat()}); no admite fechas pasadas ni futuras."
        )
    return today


def check_pockets(source: Pocket, target: Pocket) -> None:
    """RN-41: origen distinto del destino; ambas bolsas activas (las búsquedas ya lo exigen)."""
    if source.id == target.id:
        raise TransferSamePocket()
    for pocket in (source, target):
        if not pocket.active:
            raise DomainError(f"La bolsa '{pocket.name}' está archivada: no admite transferencias.")


def available_to_move(figures: PocketFigures) -> int:
    """RN-42: saldo (acumulable) o disponible del mes (consumo)."""
    return figures.amount


def check_available(figures: PocketFigures, amount: int) -> None:
    """RN-42: nunca más de lo disponible en el origen, y nunca desde una bolsa en negativo."""
    kind = "saldo" if figures.pocket.behavior is Behavior.ACUMULABLE else "disponible del mes"
    have = available_to_move(figures)
    if have < 0:
        raise TransferFromNegative(figures.pocket.name, kind)
    if amount > have:
        raise TransferExceedsAvailable(figures.pocket.name, kind)


@dataclass(frozen=True)
class GoalEffect:
    """RN-58: cómo cambia el avance de la meta activa de una bolsa con la transferencia."""

    goal: Goal
    percent_before: int
    percent_after: int
    missing_before: int
    missing_after: int
    completes: bool  # la transferencia la llevaría al objetivo

    @property
    def message(self) -> str:
        if self.completes:
            return f"La meta {self.goal.reference} alcanzaría su objetivo (pasaría a lograda)."
        ref = self.goal.reference
        verb = "baja" if self.percent_after < self.percent_before else "sube"
        if self.percent_after == self.percent_before:
            return f"El avance de la meta {ref} se mantiene en {self.percent_after} %."
        return (
            f"El avance de la meta {self.goal.reference} {verb} de {self.percent_before} % a "
            f"{self.percent_after} %."
        )


def goal_effect(goal: Goal, balance_before: int, balance_after: int) -> GoalEffect:
    before = progress(goal, balance_before)
    after = progress(goal, balance_after)
    completes = balance_before < goal.target_amount <= balance_after
    return GoalEffect(goal, before.percent, after.percent, before.missing, after.missing, completes)
