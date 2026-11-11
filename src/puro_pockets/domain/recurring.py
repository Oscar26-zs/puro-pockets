"""Gastos fijos mensuales (sección 8.1, RN-35, RN-36): plantillas, vencimiento y pendientes.

Una plantilla tiene nombre, moneda, día del mes, bolsa por defecto, categoría opcional y mes de
inicio. Su monto tiene historial: cada fila vale desde su mes (`from_month`) hasta la siguiente,
para que cambiar el monto afecte solo meses futuros. La app solo recuerda: un fijo se paga con un
gasto normal enlazado a la plantilla (un solo pago vigente por plantilla y mes). Nunca convierte
dólares: un pago en USD exige el tipo de cambio de ese pago (decisión #12d).

Referencia pública: `F-<n>` (fijo). Los mensajes de error no incluyen montos ni nombres.
"""

from __future__ import annotations

import calendar
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date

from puro_pockets.domain.errors import DomainError
from puro_pockets.domain.money import Currency
from puro_pockets.domain.months import Month
from puro_pockets.domain.pockets import is_plain_int, normalize_name

MAX_NAME = 60
_REF = re.compile(r"^\s*[Ff]\s*-\s*([0-9]{1,18})\s*$")


@dataclass(frozen=True)
class RecurringRef:
    number: int

    @classmethod
    def match(cls, text: object) -> RecurringRef | None:
        """`F-3` → RecurringRef(3); cualquier otro texto → None (puede ser un nombre)."""
        found = _REF.match(text) if isinstance(text, str) else None
        if found is None or int(found.group(1)) < 1:
            return None
        return cls(int(found.group(1)))

    def __str__(self) -> str:
        return f"F-{self.number}"


@dataclass(frozen=True)
class RecurringTemplate:
    id: int  # interno; se muestra solo como F-<id>
    name: str
    currency: Currency
    day_of_month: int
    pocket_id: int
    category_id: int | None
    start_month: Month
    active: bool
    amounts: tuple[tuple[Month, int], ...]  # (desde el mes, monto original), orden ascendente

    @property
    def reference(self) -> str:
        return str(RecurringRef(self.id))

    def amount_for(self, month: Month) -> int:
        """Monto original vigente en `month` (CRC: colones; USD: centavos)."""
        valid = [amount for since, amount in self.amounts if since <= month]
        if valid:
            return valid[-1]
        return self.amounts[0][1]  # antes del primer cambio rige el monto inicial

    def scheduled_change(self, month: Month) -> tuple[Month, int] | None:
        """Primer cambio de monto posterior a `month`, si lo hay."""
        return next(((since, amt) for since, amt in self.amounts if since > month), None)


def validate_recurring_name(value: object) -> str:
    text = value.strip() if isinstance(value, str) else ""
    if not 1 <= len(text) <= MAX_NAME:
        raise DomainError(f"El nombre del gasto fijo es obligatorio, hasta {MAX_NAME} caracteres.")
    if RecurringRef.match(text) is not None:
        raise DomainError("El nombre del gasto fijo no puede tener la forma de una referencia F-n.")
    return text


def validate_day(value: object) -> int:
    if not is_plain_int(value) or not 1 <= value <= 31:  # type: ignore[operator]
        raise DomainError("El día del mes debe ser un entero entre 1 y 31.")
    return int(value)  # type: ignore[call-overload]


def due_date(month: Month, day_of_month: int) -> date:
    """Vencimiento en `month`; si el mes es más corto, el último día (31 en febrero → 28 o 29)."""
    last = calendar.monthrange(month.year, month.month)[1]
    return date(month.year, month.month, min(day_of_month, last))


def find_recurring(templates: Iterable[RecurringTemplate], key: object) -> RecurringTemplate:
    """Por referencia (`F-3`, activa o no) o por nombre (entre las activas, sin mayúsculas)."""
    items = list(templates)
    ref = RecurringRef.match(key)
    if ref is not None:
        for template in items:
            if template.id == ref.number:
                return template
        raise DomainError(f"No existe el gasto fijo {ref}. Consúltalos con manage_recurring.")
    if isinstance(key, str) and key.strip():
        wanted = normalize_name(key)
        for template in items:
            if template.active and normalize_name(template.name) == wanted:
                return template
    raise DomainError(
        "No hay un gasto fijo activo con ese nombre. Usa su referencia (F-n) o consúltalos con "
        "manage_recurring."
    )


@dataclass(frozen=True)
class PendingRecurring:
    template: RecurringTemplate
    amount: int  # original, en la moneda de la plantilla
    due: date
    overdue: bool


def pending_in_month(
    templates: Sequence[RecurringTemplate],
    paid_ids: Iterable[int],
    month: Month,
    today: date,
) -> list[PendingRecurring]:
    """RN-35: plantillas activas, desde su mes de inicio, sin pago vigente en `month`.

    Atrasado: hoy ya pasó el vencimiento. Ordenado por vencimiento y referencia.
    """
    paid = set(paid_ids)
    result = []
    for template in templates:
        if not template.active or template.start_month > month or template.id in paid:
            continue
        due = due_date(month, template.day_of_month)
        result.append(PendingRecurring(template, template.amount_for(month), due, today > due))
    return sorted(result, key=lambda p: (p.due, p.template.id))
