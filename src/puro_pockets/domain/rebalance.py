"""Reajuste de porcentajes al crear o archivar una bolsa (RN-13, RN-14, RN-17; RN-01).

Función pura: recibe los porcentajes vigentes del mes objetivo (en orden de creación de las bolsas)
y devuelve el conjunto completo nuevo, con enteros de 0 a 100 que suman exactamente 100.

Estrategias:
- `proporcional`: todas las bolsas existentes cambian en la misma proporción; enteros hacia abajo y
  la última bolsa existente absorbe el residuo (RN-14). Al crear, ceden; al archivar, reciben.
- `desde_una_bolsa`: solo una bolsa cede el porcentaje de la nueva (o recibe el de la archivada).
- `manual`: el propietario da el reparto completo.

Ningún resultado es negativo: los montos hacia abajo nunca superan el total y el residuo es >= 0.
"""

from __future__ import annotations

from collections.abc import Hashable, Mapping, Sequence
from enum import StrEnum

from puro_pockets.domain.errors import DomainError
from puro_pockets.domain.pockets import is_plain_int


class Strategy(StrEnum):
    PROPORTIONAL = "proporcional"
    FROM_ONE = "desde_una_bolsa"
    MANUAL = "manual"


def parse_strategy(value: object) -> Strategy:
    if isinstance(value, str):
        try:
            return Strategy(value.strip().casefold())
        except ValueError:
            pass
    raise DomainError("La estrategia debe ser proporcional, desde_una_bolsa o manual.")


def validate_share(value: object, label: str = "la bolsa nueva") -> int:
    if not is_plain_int(value) or not 0 <= value <= 100:  # type: ignore[operator]
        raise DomainError(f"El porcentaje de {label} debe ser un entero entre 0 y 100.")
    return int(value)  # type: ignore[call-overload]


def _scale[K: Hashable](current: Sequence[tuple[K, int]], target: int) -> list[tuple[K, int]]:
    """Lleva `current` (suma S > 0) a sumar `target`, en proporción; residuo a la última (RN-14)."""
    total = sum(pct for _, pct in current)
    scaled = [(key, pct * target // total) for key, pct in current[:-1]]
    scaled.append((current[-1][0], target - sum(pct for _, pct in scaled)))
    return scaled


def _check_manual[K: Hashable](
    keys: Sequence[K], manual: Mapping[K, int] | None
) -> list[tuple[K, int]]:
    if not manual:
        raise DomainError("Con la estrategia manual indica el porcentaje de cada bolsa.")
    missing = [key for key in keys if key not in manual]
    extra = [key for key in manual if key not in keys]
    if missing or extra:
        raise DomainError(
            "Con la estrategia manual indica todas las bolsas activas resultantes, una vez cada "
            "una."
        )
    for value in manual.values():
        validate_share(value, "cada bolsa")
    total = sum(manual.values())
    if total != 100:
        raise DomainError(f"Los porcentajes deben sumar exactamente 100; suman {total}.")
    return [(key, int(manual[key])) for key in keys]


def rebalance_add[K: Hashable](
    current: Sequence[tuple[K, int]],
    new_key: K,
    share: int,
    strategy: Strategy,
    source: K | None = None,
    manual: Mapping[K, int] | None = None,
) -> list[tuple[K, int]]:
    """Porcentajes al agregar `new_key` con `share` % (la nueva va al final)."""
    keys = [key for key, _ in current] + [new_key]
    if strategy is Strategy.MANUAL:
        return _check_manual(keys, manual)
    share = validate_share(share)
    _check_current(current)
    if not current:
        if share != 100:
            raise DomainError(
                "No hay porcentajes definidos para ese mes: la bolsa nueva recibiría el 100 %. "
                "Usa la estrategia manual o define los porcentajes con set_allocation."
            )
        return [(new_key, 100)]
    if strategy is Strategy.PROPORTIONAL:
        if share == 100:
            return [(key, 0) for key, _ in current] + [(new_key, 100)]
        return [*_scale(current, 100 - share), (new_key, share)]
    donor = _require_key(current, source, "cede")
    result = []
    for key, pct in current:
        if key == donor:
            if pct < share:
                raise DomainError(
                    f"La bolsa que cede tiene {pct} % y no alcanza para el {share} % de la nueva."
                )
            pct -= share
        result.append((key, pct))
    return [*result, (new_key, share)]


def rebalance_remove[K: Hashable](
    current: Sequence[tuple[K, int]],
    removed: K,
    strategy: Strategy,
    target: K | None = None,
    manual: Mapping[K, int] | None = None,
) -> list[tuple[K, int]]:
    """Porcentajes al quitar `removed`: su porcentaje se redistribuye entre las demás (RN-17)."""
    if removed not in [key for key, _ in current]:
        raise DomainError("La bolsa a archivar no está entre las bolsas activas del mes.")
    rest = [(key, pct) for key, pct in current if key != removed]
    if not rest:
        raise DomainError("No se puede archivar la única bolsa activa.")
    if strategy is Strategy.MANUAL:
        return _check_manual([key for key, _ in rest], manual)
    _check_current(current)
    freed = dict(current)[removed]
    if strategy is Strategy.PROPORTIONAL:
        if freed == 0:
            return rest
        if sum(pct for _, pct in rest) == 0:
            raise DomainError(
                "Las demás bolsas tienen 0 %: el reparto proporcional no es posible. Usa "
                "desde_una_bolsa (indica cuál recibe) o manual."
            )
        return _scale(rest, 100)
    receiver = _require_key(rest, target, "recibe")
    return [(key, pct + freed if key == receiver else pct) for key, pct in rest]


def _check_current[K: Hashable](current: Sequence[tuple[K, int]]) -> None:
    if current and sum(pct for _, pct in current) != 100:  # pragma: no cover - lo garantiza RN-01
        raise DomainError("Los porcentajes vigentes no suman 100; revísalos con get_allocation.")


def _require_key[K: Hashable](items: Sequence[tuple[K, int]], key: K | None, verb: str) -> K:
    if key is None:
        raise DomainError(f"Con desde_una_bolsa indica la bolsa que {verb} el porcentaje.")
    if key not in [k for k, _ in items]:
        raise DomainError(f"La bolsa que {verb} el porcentaje debe ser otra bolsa activa.")
    return key
