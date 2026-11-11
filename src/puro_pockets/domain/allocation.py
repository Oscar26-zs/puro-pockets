"""Porcentajes por mes y reparto en montos (RN-01, RN-02, RN-03, RN-08)."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

from puro_pockets.domain.errors import DomainError
from puro_pockets.domain.months import Month
from puro_pockets.domain.pockets import Pocket, is_plain_int, ordered_active, resolve_named


def validate_allocation(
    requested: Sequence[tuple[object, object]], pockets: Iterable[Pocket]
) -> dict[int, int]:
    """Valida una configuración de porcentajes y devuelve {id de bolsa: porcentaje}.

    Cada bolsa activa aparece exactamente una vez, con un entero entre 0 y 100, y la suma es
    exactamente 100 (RN-01).
    """
    active = ordered_active(pockets)
    resolved = resolve_named(requested, active)
    for pocket, value in resolved:
        if not is_plain_int(value) or not 0 <= value <= 100:  # type: ignore[operator]
            raise DomainError(f"El porcentaje de {pocket.name} debe ser un entero entre 0 y 100.")
    given = {pocket.id: int(value) for pocket, value in resolved}  # type: ignore[call-overload]
    missing = [p.name for p in active if p.id not in given]
    if missing:
        raise DomainError(
            f"Falta el porcentaje de: {', '.join(missing)}. "
            "Indica todas las bolsas activas (0 si no recibe)."
        )
    total = sum(given.values())
    if total != 100:
        raise DomainError(f"Los porcentajes deben sumar exactamente 100; suman {total}.")
    return {p.id: given[p.id] for p in active}


def ensure_editable(month: Month, current: Month) -> None:
    """Solo se editan el mes actual y los futuros: protege RN-02 sin cierre de mes todavía."""
    if month < current:
        raise DomainError(
            f"No se pueden cambiar los porcentajes de {month}: es un mes pasado. "
            f"Solo se editan el mes actual ({current}) y los siguientes."
        )


def pick_source_month(month: Month, months_with_rows: Iterable[Month]) -> Month | None:
    """RN-03: el propio mes si tiene porcentajes; si no, el anterior más cercano que los tenga."""
    candidates = [m for m in months_with_rows if m <= month]
    return max(candidates) if candidates else None


@dataclass(frozen=True)
class ResolvedAllocation:
    month: Month
    source_month: Month | None  # None: ni este mes ni uno anterior tiene porcentajes
    items: tuple[tuple[Pocket, int], ...]

    @property
    def defined(self) -> bool:
        return self.source_month is not None


def resolve_allocation(
    month: Month,
    source_month: Month | None,
    rows: Mapping[int, int],
    pockets: Iterable[Pocket],
) -> ResolvedAllocation:
    """Arma los porcentajes de `month` a partir de las filas del mes de origen (no guarda nada).

    Una bolsa activa sin fila en el mes de origen aparece con 0.
    """
    if source_month is None:
        return ResolvedAllocation(month, None, ())
    items = tuple((p, rows.get(p.id, 0)) for p in ordered_active(pockets))
    return ResolvedAllocation(month, source_month, items)


def split_amount[K](amount: int, shares: Sequence[tuple[K, int]]) -> list[tuple[K, int]]:
    """RN-08: reparte un monto entero según porcentajes, en enteros y con suma exacta.

    Todas las bolsas menos la última reciben el monto redondeado hacia abajo; la última absorbe el
    residuo por resta. Así ningún monto es negativo y la suma es exactamente `amount`.
    """
    if not is_plain_int(amount) or amount < 0:
        raise DomainError("El monto a repartir debe ser un entero mayor o igual a 0.")
    if not shares:
        raise DomainError("No hay bolsas entre las que repartir.")
    if sum(pct for _, pct in shares) != 100 or any(not 0 <= pct <= 100 for _, pct in shares):
        raise DomainError("Los porcentajes del reparto deben sumar exactamente 100.")
    result = [(key, amount * pct // 100) for key, pct in shares[:-1]]
    result.append((shares[-1][0], amount - sum(part for _, part in result)))
    return result


def allocate_by_percentages[K](
    amount: int, items: Sequence[tuple[K, int]]
) -> list[tuple[K, int, int]]:
    """Reparto de un ingreso por porcentajes: (clave, porcentaje, monto) para cada bolsa.

    RN-08 se aplica entre las bolsas que reciben (porcentaje > 0): la última de ellas absorbe el
    residuo. Una bolsa con 0 % recibe 0, aunque sea la última por orden de creación.
    """
    receiving = [(key, pct) for key, pct in items if pct > 0]
    parts = iter(split_amount(amount, receiving))
    return [(key, pct, next(parts)[1] if pct > 0 else 0) for key, pct in items]
