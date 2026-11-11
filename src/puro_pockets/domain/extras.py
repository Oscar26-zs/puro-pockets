"""Ingreso extra (sección 5.3, RN-04 a RN-09): porcentajes del reparto y ficha de vista previa.

El extra no tiene regla fija (RN-04): cada vez se indican porcentajes enteros de 0 a 100 que suman
exactamente 100 (RN-01), solo entre bolsas activas existentes; puede ir el 100 % a una sola bolsa,
también a una personalizada (RN-07). Las bolsas omitidas reciben 0. El reparto en montos usa
`allocate_by_percentages` (RN-08: la última bolsa que recibe absorbe el residuo).

La ficha de vista previa (`preview_token`) obliga a pasar por la vista previa con exactamente esos
porcentajes antes de confirmar: no prueba que el propietario aprobó, pero impide confirmar un
reparto que nunca se mostró (ver plan técnico, "Extras y gastos fijos").
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Sequence

from puro_pockets.domain.errors import DomainError
from puro_pockets.domain.pockets import Pocket, is_plain_int, ordered_active, resolve_named


def validate_extra_shares(
    requested: Sequence[tuple[object, object]], pockets: Iterable[Pocket]
) -> list[tuple[Pocket, int]]:
    """[(bolsa, porcentaje)] en orden de creación, con todas las bolsas activas (omitidas = 0)."""
    active = ordered_active(pockets)
    if not requested:
        raise DomainError("Indica al menos una bolsa con su porcentaje; deben sumar 100.")
    resolved = resolve_named(requested, active)
    for pocket, value in resolved:
        if not is_plain_int(value) or not 0 <= value <= 100:  # type: ignore[operator]
            raise DomainError(f"El porcentaje de {pocket.name} debe ser un entero entre 0 y 100.")
    given = {pocket.id: int(value) for pocket, value in resolved}  # type: ignore[call-overload]
    total = sum(given.values())
    if total != 100:
        raise DomainError(f"Los porcentajes deben sumar exactamente 100; suman {total}.")
    return [(p, given.get(p.id, 0)) for p in active]


def preview_token(reference: str, amount_crc: int, shares: Sequence[tuple[Pocket, int]]) -> str:
    """Ficha determinista de una vista previa: cambia si cambian el extra, su monto o el reparto."""
    canonical = "|".join(
        [reference, str(amount_crc), *(f"{p.id}:{pct}" for p, pct in shares if pct > 0)]
    )
    return hashlib.sha256(f"confirm_allocation|{canonical}".encode()).hexdigest()[:24]
