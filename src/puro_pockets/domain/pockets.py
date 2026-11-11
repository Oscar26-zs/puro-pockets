"""Bolsas ("pockets"). Los comportamientos son datos (RN-10); no hay bolsas fijas en el código."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from enum import StrEnum

from puro_pockets.domain.errors import DomainError


class Behavior(StrEnum):
    CONSUMO = "consumo"  # empieza cada mes en cero; no arrastra saldo (RN-11)
    ACUMULABLE = "acumulable"  # siempre conserva su saldo (RN-12)


@dataclass(frozen=True)
class Pocket:
    id: int  # interno: fija el orden de creación (RN-08); nunca se muestra
    name: str
    behavior: Behavior
    active: bool = True


def normalize_name(name: str) -> str:
    """Clave de comparación: sin distinguir mayúsculas ni espacios al borde."""
    return name.strip().casefold()


def ordered_active(pockets: Iterable[Pocket]) -> list[Pocket]:
    return sorted((p for p in pockets if p.active), key=lambda p: p.id)


def resolve_named(
    requested: Sequence[tuple[object, object]], active: Sequence[Pocket]
) -> list[tuple[Pocket, object]]:
    """Asocia cada (nombre, valor) a una bolsa activa. Rechaza desconocidas y repetidas."""
    by_key = {normalize_name(p.name): p for p in active}
    seen: set[int] = set()
    resolved: list[tuple[Pocket, object]] = []
    for name, value in requested:
        label = name.strip() if isinstance(name, str) else str(name)
        pocket = by_key.get(normalize_name(name)) if isinstance(name, str) else None
        if pocket is None:
            raise DomainError(f"La bolsa '{label}' no existe o está archivada.")
        if pocket.id in seen:
            raise DomainError(f"La bolsa '{pocket.name}' aparece más de una vez.")
        seen.add(pocket.id)
        resolved.append((pocket, value))
    return resolved


def is_plain_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)
