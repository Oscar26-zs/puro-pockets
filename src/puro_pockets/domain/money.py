"""Monedas y conversión a colones (RN-55, RN-56, RN-57; decisión #12).

Colones enteros; dólares en centavos enteros; tipo de cambio como colones por dólar ×100. El texto
con decimales se lee con `Decimal` y se pasa a enteros con una comprobación exacta; nunca se usa
`float`. Un número con decimales que llega como `float` (JSON) se rechaza y se pide como texto.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from puro_pockets.domain.errors import DomainError

# Límite técnico: las columnas son BIGINT
MAX_MONEY = 2**63 - 1

_DIGITS = re.compile(r"^[0-9]{1,18}$")
_DECIMAL_2 = re.compile(r"^[0-9]{1,15}(\.[0-9]{1,2})?$")


class Currency(StrEnum):
    CRC = "CRC"
    USD = "USD"


def parse_currency(value: object) -> Currency:
    if isinstance(value, str):
        try:
            return Currency(value.strip().upper())
        except ValueError:
            pass
    raise DomainError("La moneda debe ser CRC (colones) o USD (dólares).")


def _blank(value: object) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _scaled(text: str) -> int:
    """'10.5' -> 1050 (×100), exacto."""
    scaled = Decimal(text) * 100
    if scaled != scaled.to_integral_value():  # pragma: no cover - lo impide la expresión regular
        raise DomainError("El valor admite como máximo 2 decimales.")
    return int(scaled)


def parse_amount(value: object, currency: Currency) -> int:
    """Monto positivo en la unidad mínima: colones (CRC) o centavos (USD)."""
    if isinstance(value, float):
        if currency is Currency.CRC:
            raise DomainError("El monto en colones debe ser un entero, sin decimales.")
        raise DomainError(
            'Un monto en dólares con decimales debe enviarse como texto, por ejemplo "10.50".'
        )
    if isinstance(value, bool) or not isinstance(value, int | str):
        raise DomainError("El monto debe ser un número positivo.")
    if currency is Currency.CRC:
        if isinstance(value, str):
            if not _DIGITS.match(value.strip()):
                raise DomainError(
                    "El monto en colones debe ser un entero positivo, sin decimales ni separadores."
                )
            value = int(value.strip())
        minor = value
    else:
        if isinstance(value, str):
            if not _DECIMAL_2.match(value.strip()):
                raise DomainError(
                    'El monto en dólares admite hasta 2 decimales con punto, por ejemplo "10.50", '
                    "sin separador de miles."
                )
            minor = _scaled(value.strip())
        else:
            minor = value * 100
    if minor <= 0:
        raise DomainError("El monto debe ser mayor que 0.")
    if minor > MAX_MONEY:
        raise DomainError("El monto excede el máximo que se puede guardar.")
    return minor


def parse_exchange_rate(value: object) -> int:
    """Colones por dólar ×100 (512,34 -> 51234)."""
    if isinstance(value, float):
        raise DomainError(
            'Un tipo de cambio con decimales debe enviarse como texto, por ejemplo "512.34".'
        )
    if isinstance(value, bool) or not isinstance(value, int | str):
        raise DomainError("El tipo de cambio debe ser un número positivo.")
    if isinstance(value, str):
        if not _DECIMAL_2.match(value.strip()):
            raise DomainError(
                'El tipo de cambio admite hasta 2 decimales con punto, por ejemplo "512.34".'
            )
        rate = _scaled(value.strip())
    else:
        rate = value * 100
    if rate <= 0:
        raise DomainError("El tipo de cambio debe ser mayor que 0.")
    return rate


@dataclass(frozen=True)
class RateRange:
    """Rango aceptado, en colones por dólar enteros (inclusivo)."""

    min_crc: int
    max_crc: int

    def check(self, rate_x100: int) -> None:
        if not self.min_crc * 100 <= rate_x100 <= self.max_crc * 100:
            raise DomainError(
                f"El tipo de cambio debe estar entre {self.min_crc} y {self.max_crc} colones por "
                "dólar. Revisa el valor indicado."
            )


def to_crc(cents: int, rate_x100: int) -> int:
    """RN-57: redondeo half-up de centavos × tipo_cambio_x100 / 10 000, en enteros."""
    return (cents * rate_x100 + 5_000) // 10_000


@dataclass(frozen=True)
class Converted:
    """Movimiento convertido: se guarda tal cual y no se recalcula (RN-57)."""

    currency: Currency
    original_amount: int  # CRC: colones; USD: centavos
    exchange_rate: int | None  # colones por USD ×100; None en CRC
    amount_crc: int


def convert(
    amount: object, currency: object, exchange_rate: object, rate_range: RateRange
) -> Converted:
    cur = parse_currency(currency)
    if cur is Currency.CRC:
        if not _blank(exchange_rate):
            raise DomainError("El tipo de cambio solo se indica en movimientos en dólares (USD).")
        colones = parse_amount(amount, cur)
        return Converted(cur, colones, None, colones)
    if _blank(exchange_rate):
        raise DomainError(
            "Falta el tipo de cambio: indica cuántos colones vale un dólar en este movimiento. "
            "No se asume ninguno."
        )
    cents = parse_amount(amount, cur)
    rate = parse_exchange_rate(exchange_rate)
    rate_range.check(rate)
    crc = to_crc(cents, rate)
    if crc <= 0:
        raise DomainError("El monto en dólares equivale a 0 colones; no se puede registrar.")
    if crc > MAX_MONEY:
        raise DomainError("El monto excede el máximo que se puede guardar.")
    return Converted(cur, cents, rate, crc)


def format_original(currency: Currency, original_amount: int) -> str:
    if currency is Currency.CRC:
        return str(original_amount)
    return f"{original_amount // 100}.{original_amount % 100:02d}"


def format_rate(rate_x100: int) -> str:
    return f"{rate_x100 // 100}.{rate_x100 % 100:02d}"
