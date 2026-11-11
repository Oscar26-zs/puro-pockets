"""Saldo inicial (RN-54): una sola carga, por montos explícitos en colones entre bolsas activas."""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from puro_pockets.domain.errors import DomainError
from puro_pockets.domain.pockets import Pocket, is_plain_int, ordered_active, resolve_named

# Límite técnico: las columnas son BIGINT
MAX_TOTAL = 2**63 - 1


def validate_initial_balance(
    requested: Sequence[tuple[object, object]], pockets: Iterable[Pocket]
) -> list[tuple[Pocket, int]]:
    """Devuelve el monto de cada bolsa activa (en orden de creación); las omitidas cuentan como 0.

    Montos enteros >= 0 y total > 0. Los mensajes nunca incluyen montos.
    """
    active = ordered_active(pockets)
    resolved = resolve_named(requested, active)
    for pocket, value in resolved:
        if not is_plain_int(value) or value < 0:  # type: ignore[operator]
            raise DomainError(f"El monto de {pocket.name} debe ser un entero mayor o igual a 0.")
    given = {pocket.id: int(value) for pocket, value in resolved}  # type: ignore[call-overload]
    items = [(p, given.get(p.id, 0)) for p in active]
    total = sum(amount for _, amount in items)
    if total <= 0:
        raise DomainError("El saldo inicial debe tener al menos un monto mayor que 0.")
    if total > MAX_TOTAL:
        raise DomainError("El total del saldo inicial excede el máximo que se puede guardar.")
    return items
