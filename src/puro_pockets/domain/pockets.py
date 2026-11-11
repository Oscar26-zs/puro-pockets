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


def find_pocket(pockets: Iterable[Pocket], name: object) -> Pocket:
    """Bolsa activa por nombre (sin distinguir mayúsculas)."""
    if isinstance(name, str):
        key = normalize_name(name)
        for pocket in pockets:
            if pocket.active and normalize_name(pocket.name) == key:
                return pocket
    label = name.strip() if isinstance(name, str) else str(name)
    raise DomainError(f"La bolsa '{label}' no existe o está archivada.")


def is_plain_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


MAX_POCKET_NAME = 40
MAX_GROUP = 40


def validate_pocket_name(value: object) -> str:
    text = value.strip() if isinstance(value, str) else ""
    if not 1 <= len(text) <= MAX_POCKET_NAME:
        raise DomainError(
            f"El nombre de la bolsa es obligatorio, hasta {MAX_POCKET_NAME} caracteres."
        )
    return text


def validate_group(value: object) -> str | None:
    """Grupo opcional, solo para estadísticas (sección 6.1)."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    if not isinstance(value, str) or len(value.strip()) > MAX_GROUP:
        raise DomainError(f"El grupo es texto opcional, hasta {MAX_GROUP} caracteres.")
    return value.strip()


def parse_behavior(value: object) -> Behavior:
    """RN-10: consumo o acumulable."""
    if isinstance(value, str):
        try:
            return Behavior(value.strip().casefold())
        except ValueError:
            pass
    raise DomainError("El comportamiento debe ser consumo o acumulable.")
