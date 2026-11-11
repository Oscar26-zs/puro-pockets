"""Idempotencia de las tools que escriben (plan técnico 12.2.2).

La misma clave de operación con el mismo contenido devuelve la respuesta original; con otro
contenido es un error. La huella se calcula sobre la entrada ya normalizada (sin `float`).
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping

from puro_pockets.domain.errors import DomainError

_OPERATION_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{7,99}$")


def validate_operation_id(value: object) -> str:
    if value is None or (isinstance(value, str) and not value.strip()):
        raise DomainError(
            "Falta la clave de operación (operation_id): genera una nueva para esta operación "
            "(por ejemplo un UUID) y repítela si reintentas la misma llamada."
        )
    if not isinstance(value, str) or not _OPERATION_ID.match(value.strip()):
        raise DomainError(
            "La clave de operación (operation_id) debe tener de 8 a 100 caracteres: letras, "
            "números, punto, guion, guion bajo o dos puntos."
        )
    return value.strip()


def _check(value: object) -> None:
    if isinstance(value, float):
        raise TypeError("La huella no admite float")
    if isinstance(value, Mapping):
        for item in value.values():
            _check(item)
    elif isinstance(value, list | tuple):
        for item in value:
            _check(item)


def fingerprint(tool: str, payload: Mapping[str, object]) -> str:
    """SHA-256 del contenido canónico (claves ordenadas)."""
    _check(payload)
    canonical = json.dumps(
        {"tool": tool, "payload": payload},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
