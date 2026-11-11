"""Movimientos del libro mayor (Hito 5): referencias, fechas, mes del salario, motivo y descripción.

Las referencias públicas son cortas (`I-3` para ingresos, `G-12` para gastos; `T-5` para las
transferencias del Hito 8, que no se anulan) y no exponen otros identificadores internos. Los
mensajes de error nunca incluyen montos ni descripciones.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from enum import StrEnum

from puro_pockets.domain.errors import DomainError, TransfersAreFinal
from puro_pockets.domain.months import Month

MAX_DESCRIPTION = 120
MIN_REASON, MAX_REASON = 3, 200

_REF = re.compile(r"^\s*([IiGg])\s*-\s*([0-9]{1,18})\s*$")
_TRANSFER_REF = re.compile(r"^\s*[Tt]\s*-\s*([0-9]{1,18})\s*$")
_DATE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")


class MovementKind(StrEnum):
    INCOME = "ingreso"
    EXPENSE = "gasto"


_PREFIX = {MovementKind.INCOME: "I", MovementKind.EXPENSE: "G"}
_KIND = {"I": MovementKind.INCOME, "G": MovementKind.EXPENSE}


@dataclass(frozen=True)
class MovementRef:
    kind: MovementKind
    number: int

    @classmethod
    def parse(cls, text: object) -> MovementRef:
        transfer = _TRANSFER_REF.match(text) if isinstance(text, str) else None
        if transfer is not None:  # RN-43: las transferencias no se anulan ni se editan
            raise TransfersAreFinal(f"T-{int(transfer.group(1))}")
        match = _REF.match(text) if isinstance(text, str) else None
        if match is None or int(match.group(2)) < 1:
            raise DomainError(
                "La referencia debe tener la forma G-12 (gasto) o I-3 (ingreso); "
                "consúltala con list_transactions."
            )
        return cls(_KIND[match.group(1).upper()], int(match.group(2)))

    def __str__(self) -> str:
        return f"{_PREFIX[self.kind]}-{self.number}"


def parse_date(value: object, label: str) -> date | None:
    """`AAAA-MM-DD` o None (omitida)."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    if isinstance(value, str) and _DATE.match(value.strip()):
        try:
            return date.fromisoformat(value.strip())
        except ValueError:
            pass
    raise DomainError(
        f"La fecha {label} debe tener el formato AAAA-MM-DD (por ejemplo 2026-11-30)."
    )


def movement_date(value: object, label: str, today: date) -> date:
    """Fecha del movimiento: hoy si se omite; nunca futura."""
    day = parse_date(value, label) or today
    if day > today:
        raise DomainError(f"La fecha {label} no puede ser futura (hoy es {today.isoformat()}).")
    return day


def income_budget_month(income_date: date, explicit: object) -> Month:
    """Constitución 5.1: el salario financia el mes siguiente; se puede indicar otro mes."""
    if explicit is None or (isinstance(explicit, str) and not explicit.strip()):
        return Month.of(income_date).next()
    return Month.parse(explicit)


def validate_reason(value: object) -> str:
    text = value.strip() if isinstance(value, str) else ""
    if not MIN_REASON <= len(text) <= MAX_REASON:
        raise DomainError(
            f"El motivo de la anulación es obligatorio, de {MIN_REASON} a {MAX_REASON} caracteres."
        )
    return text


def validate_description(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise DomainError("La descripción debe ser texto.")
    text = value.strip()
    if len(text) > MAX_DESCRIPTION:
        raise DomainError(f"La descripción admite como máximo {MAX_DESCRIPTION} caracteres.")
    return text or None
