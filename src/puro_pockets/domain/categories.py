"""Categorías de gasto: lista editable, cada una con una bolsa por defecto (sección 8, RN-34)."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from puro_pockets.domain.errors import DomainError
from puro_pockets.domain.pockets import normalize_name

# RN-34: un gasto sin categoría no se pierde; se muestra así
UNCLASSIFIED = "pendiente de clasificar"
MAX_NAME = 60


@dataclass(frozen=True)
class Category:
    id: int  # interno; nunca se muestra
    name: str
    pocket_id: int
    active: bool = True


def validate_category_name(value: object) -> str:
    text = value.strip() if isinstance(value, str) else ""
    if not 1 <= len(text) <= MAX_NAME:
        raise DomainError(f"El nombre de la categoría es obligatorio, hasta {MAX_NAME} caracteres.")
    if normalize_name(text) == normalize_name(UNCLASSIFIED):
        raise DomainError(f"'{UNCLASSIFIED}' está reservado para los gastos sin categoría.")
    return text


def find_category(categories: Iterable[Category], name: object) -> Category:
    if isinstance(name, str):
        key = normalize_name(name)
        for category in categories:
            if category.active and normalize_name(category.name) == key:
                return category
    label = name.strip() if isinstance(name, str) else str(name)
    raise DomainError(
        f"La categoría '{label}' no existe. Créala con create_category o registra el gasto sin "
        "categoría."
    )
