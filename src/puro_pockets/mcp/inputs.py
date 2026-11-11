"""Entradas de las tools sin `float` y traducción de errores de negocio (compartido).

Un número JSON con decimales llega como `float` antes de llegar a la tool; la capa de dominio lo
rechaza con un mensaje en español (principio 3.5). Los montos con decimales (USD, tipo de cambio) se
envían como texto ("10.50"); el SDK no convierte a número un texto que decodifica a un escalar.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from functools import wraps
from typing import Annotated, Any

from mcp.server.mcpserver.exceptions import ToolError
from pydantic import BeforeValidator, Field, WithJsonSchema

from puro_pockets.domain.errors import DomainError


def whole_number(value: Any, message: str) -> Any:
    """Acepta solo enteros: rechaza decimales (aunque sean 50.0), texto y booleanos."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(message)
    return value


def _limit(value: Any) -> Any:
    if value is None:
        return value
    return whole_number(value, "El límite debe ser un número entero.")


# Los montos NO se validan con pydantic: su error incluye el valor recibido (input_value=...) y el
# SDK registra ese texto. Pasan tal cual a la capa de dominio, que los rechaza con mensajes en
# español sin el monto (incluido un float: se pide como texto). El esquema JSON sigue declarando
# entero o texto para que Claude sepa qué enviar.
MoneyInput = Annotated[
    Any,
    WithJsonSchema(
        {
            "anyOf": [{"type": "integer"}, {"type": "string"}],
            "description": "Colones: entero (12500). Dólares: entero o texto con hasta 2 "
            'decimales ("10.50").',
        }
    ),
]
RateInput = Annotated[
    Any,
    WithJsonSchema(
        {
            "anyOf": [{"type": "integer"}, {"type": "string"}, {"type": "null"}],
            "default": None,
            "description": "Solo en USD y obligatorio: colones por dólar, texto con hasta 2 "
            'decimales ("512.34"). Nunca se asume.',
        }
    ),
]
OptionalMoneyInput = Annotated[
    Any,
    WithJsonSchema(
        {
            "anyOf": [{"type": "integer"}, {"type": "string"}, {"type": "null"}],
            "default": None,
            "description": "Colones: entero (12500). Dólares: entero o texto con hasta 2 "
            'decimales ("10.50"). Opcional.',
        }
    ),
]
WholeNumberInput = Annotated[Any, WithJsonSchema({"type": "integer"})]
OptionalWholeNumberInput = Annotated[
    Any, WithJsonSchema({"anyOf": [{"type": "integer"}, {"type": "null"}], "default": None})
]
CurrencyInput = Annotated[str, Field(description="CRC (colones, por defecto) o USD (dólares).")]
LimitInput = Annotated[int | None, BeforeValidator(_limit)]

MONTH_DESCRIPTION = "Mes en formato AAAA-MM. Si se omite, el mes actual (America/Costa_Rica)."
DATE_DESCRIPTION = "Fecha AAAA-MM-DD. Si se omite, hoy (America/Costa_Rica); no puede ser futura."
OPERATION_DESCRIPTION = (
    "Clave de operación: texto nuevo de 8 a 100 caracteres (por ejemplo un UUID) para esta "
    "operación; repite la misma clave solo al reintentar exactamente la misma llamada."
)


def domain_errors[**P, R](fn: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]:
    """`DomainError` → `ToolError` (is_error con el mensaje en español, sin montos)."""

    @wraps(fn)
    async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        try:
            return await fn(*args, **kwargs)
        except DomainError as exc:
            raise ToolError(exc.message) from None

    return wrapper
