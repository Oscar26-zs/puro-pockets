"""Monedas y conversión (RN-55 a RN-57, decisión #12). Sin float en ningún punto."""

import pytest

from puro_pockets.domain.errors import DomainError
from puro_pockets.domain.money import (
    Currency,
    RateRange,
    convert,
    format_original,
    format_rate,
    parse_amount,
    parse_exchange_rate,
    to_crc,
)

RANGE = RateRange(300, 1000)


# --- Lectura de montos ---


@pytest.mark.parametrize(("value", "expected"), [(12_500, 12_500), ("12500", 12_500), (" 7 ", 7)])
def test_colones_enteros(value, expected):
    assert parse_amount(value, Currency.CRC) == expected


@pytest.mark.parametrize(
    "value", [12.5, 12.0, "12.5", "12,500", "1.000", True, 0, -5, "0", "", None]
)
def test_colones_invalidos(value):
    with pytest.raises(DomainError):
        parse_amount(value, Currency.CRC)


@pytest.mark.parametrize(
    ("value", "cents"),
    [(10, 1_000), ("10", 1_000), ("10.5", 1_050), ("10.50", 1_050), ("0.01", 1), (" 3.07 ", 307)],
)
def test_dolares_a_centavos(value, cents):
    assert parse_amount(value, Currency.USD) == cents


@pytest.mark.parametrize("value", ["10.505", "10,50", "1,000.00", "-1", "abc", "0.00", True, None])
def test_dolares_invalidos(value):
    with pytest.raises(DomainError):
        parse_amount(value, Currency.USD)


def test_un_numero_json_con_decimales_se_rechaza_y_pide_texto():
    with pytest.raises(DomainError, match="como texto"):
        parse_amount(10.5, Currency.USD)


def test_tipo_de_cambio_escalado_por_100():
    assert parse_exchange_rate("512.34") == 51_234
    assert parse_exchange_rate("512.3") == 51_230
    assert parse_exchange_rate(512) == 51_200
    for bad in (512.34, "512,34", "512.345", 0, "-1", True):
        with pytest.raises(DomainError):
            parse_exchange_rate(bad)


# --- Conversión half-up ---


def test_ejemplo_de_la_constitucion_usd_10_a_512_34():
    assert to_crc(1_000, 51_234) == 5_123  # 5 123,4 -> 5 123


def test_medio_colon_sube():
    assert to_crc(1, 50_000) == 5  # 0,01 × 500,00 = 5,0
    assert to_crc(5, 51_010) == 26  # 25,505 -> 26
    assert to_crc(1, 45_000) == 5  # 4,5 -> 5 (half-up)
    assert to_crc(1, 44_999) == 4  # 4,4999 -> 4


def test_convertir_crc_y_usd():
    crc = convert(12_500, "crc", None, RANGE)
    assert (crc.currency, crc.original_amount, crc.exchange_rate, crc.amount_crc) == (
        Currency.CRC,
        12_500,
        None,
        12_500,
    )
    usd = convert("10.00", "USD", "512.34", RANGE)
    assert (usd.currency, usd.original_amount, usd.exchange_rate, usd.amount_crc) == (
        Currency.USD,
        1_000,
        51_234,
        5_123,
    )


def test_usd_sin_tipo_de_cambio_nunca_se_asume():
    for missing in (None, "", "  "):
        with pytest.raises(DomainError, match="Falta el tipo de cambio"):
            convert("10.00", "USD", missing, RANGE)


def test_crc_con_tipo_de_cambio_se_rechaza():
    with pytest.raises(DomainError, match="solo se indica"):
        convert(1_000, "CRC", "512.34", RANGE)


def test_tipo_de_cambio_fuera_de_rango():
    for rate in ("299.99", "1000.01", "5"):
        with pytest.raises(DomainError, match="entre 300 y 1000"):
            convert("10.00", "USD", rate, RANGE)
    assert convert("1", "USD", "300", RANGE).amount_crc == 300
    assert convert("1", "USD", "1000", RANGE).amount_crc == 1_000


def test_conversion_que_da_cero_colones_se_rechaza():
    # 0,001 no se puede escribir; el mínimo es 0,01 × 300 = 3. Con un rango amplio sí puede dar 0.
    with pytest.raises(DomainError, match="0 colones"):
        convert("0.01", "USD", "40", RateRange(1, 1000))


def test_moneda_invalida():
    with pytest.raises(DomainError, match="CRC"):
        convert(1, "EUR", None, RANGE)


def test_formato_de_salida_sin_float():
    assert format_original(Currency.CRC, 12_500) == "12500"
    assert format_original(Currency.USD, 1_005) == "10.05"
    assert format_original(Currency.USD, 7) == "0.07"
    assert format_rate(51_234) == "512.34"
    assert format_rate(51_200) == "512.00"
