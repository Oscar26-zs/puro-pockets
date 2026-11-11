"""Reglas puras de los movimientos (Hito 5): referencias, fechas, mes del salario y claves."""

from datetime import date

import pytest

from puro_pockets.domain.categories import (
    UNCLASSIFIED,
    Category,
    find_category,
    validate_category_name,
)
from puro_pockets.domain.errors import DomainError
from puro_pockets.domain.idempotency import fingerprint, validate_operation_id
from puro_pockets.domain.ledger import (
    MovementKind,
    MovementRef,
    income_budget_month,
    movement_date,
    validate_description,
    validate_reason,
)
from puro_pockets.domain.months import Month
from puro_pockets.domain.pockets import Behavior, Pocket, find_pocket

TODAY = date(2026, 11, 10)


# --- Referencias ---


@pytest.mark.parametrize(
    ("text", "kind", "number"),
    [
        ("G-12", MovementKind.EXPENSE, 12),
        ("g-12", MovementKind.EXPENSE, 12),
        (" i - 3 ", MovementKind.INCOME, 3),
    ],
)
def test_referencias_validas(text, kind, number):
    ref = MovementRef.parse(text)
    assert (ref.kind, ref.number) == (kind, number)


def test_referencia_se_muestra_corta():
    assert str(MovementRef(MovementKind.INCOME, 3)) == "I-3"
    assert str(MovementRef(MovementKind.EXPENSE, 12)) == "G-12"


@pytest.mark.parametrize("text", ["12", "X-1", "G-", "G-0", "G-1.5", "G12a", None, 12])
def test_referencias_invalidas(text):
    with pytest.raises(DomainError, match="G-12"):
        MovementRef.parse(text)


# --- Fechas y mes del salario ---


def test_fecha_por_defecto_hoy_y_no_futura():
    assert movement_date(None, "del gasto", TODAY) == TODAY
    assert movement_date("2026-11-01", "del gasto", TODAY) == date(2026, 11, 1)
    with pytest.raises(DomainError, match="no puede ser futura"):
        movement_date("2026-11-11", "del gasto", TODAY)


@pytest.mark.parametrize("bad", ["2026-13-01", "30/11/2026", "2026-11-31", "ayer", 20261110])
def test_fecha_invalida(bad):
    with pytest.raises(DomainError, match="AAAA-MM-DD"):
        movement_date(bad, "del gasto", TODAY)


def test_mes_presupuestario_del_salario():
    assert income_budget_month(date(2026, 11, 30), None) == Month(2026, 12)  # constitución 5.1
    assert income_budget_month(date(2026, 12, 30), None) == Month(2027, 1)
    assert income_budget_month(date(2026, 11, 30), "2026-11") == Month(2026, 11)  # explícito
    with pytest.raises(DomainError, match="AAAA-MM"):
        income_budget_month(date(2026, 11, 30), "noviembre")


# --- Textos ---


def test_motivo_obligatorio_y_acotado():
    assert validate_reason("  monto equivocado ") == "monto equivocado"
    for bad in (None, "", "ab", "x" * 201):
        with pytest.raises(DomainError, match="motivo"):
            validate_reason(bad)


def test_descripcion_opcional_y_acotada():
    assert validate_description(None) is None
    assert validate_description("   ") is None
    assert validate_description(" almuerzo ") == "almuerzo"
    with pytest.raises(DomainError, match="120"):
        validate_description("x" * 121)


# --- Categorías y bolsas por nombre ---


def test_nombre_de_categoria():
    assert validate_category_name(" Restaurantes ") == "Restaurantes"
    for bad in ("", "x" * 61, None, "Pendiente de clasificar"):
        with pytest.raises(DomainError):
            validate_category_name(bad)
    assert UNCLASSIFIED == "pendiente de clasificar"


def test_buscar_categoria_y_bolsa_sin_distinguir_mayusculas():
    cats = [Category(1, "Restaurantes", 3)]
    assert find_category(cats, "RESTAURANTES").id == 1
    with pytest.raises(DomainError, match="create_category"):
        find_category(cats, "Cine")
    pockets = [Pocket(1, "Gustos", Behavior.CONSUMO), Pocket(2, "Viejo", Behavior.CONSUMO, False)]
    assert find_pocket(pockets, " gustos ").id == 1
    with pytest.raises(DomainError, match="no existe o está archivada"):
        find_pocket(pockets, "Viejo")


# --- Clave de operación ---


def test_clave_de_operacion():
    assert validate_operation_id(" 7f3c2a10-uuid ") == "7f3c2a10-uuid"
    with pytest.raises(DomainError, match="Falta la clave"):
        validate_operation_id(None)
    for bad in ("corta", "con espacio 123", "x" * 101, "-empieza-mal", 12345678):
        with pytest.raises(DomainError, match="8 a 100"):
            validate_operation_id(bad)


def test_huella_determinista_y_sensible_al_contenido():
    a = fingerprint("add_expense", {"amount": 1_000, "pocket": "gustos"})
    b = fingerprint("add_expense", {"pocket": "gustos", "amount": 1_000})
    assert a == b and len(a) == 64
    assert a != fingerprint("add_expense", {"amount": 1_001, "pocket": "gustos"})
    assert a != fingerprint("add_income", {"amount": 1_000, "pocket": "gustos"})


def test_huella_rechaza_float():
    with pytest.raises(TypeError):
        fingerprint("add_expense", {"amount": 10.5})
