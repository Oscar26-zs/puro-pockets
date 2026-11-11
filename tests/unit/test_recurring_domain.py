"""Dominio de gastos fijos y del reparto de extras (Hito 6). Datos sintéticos."""

from datetime import date

import pytest

from puro_pockets.domain.errors import DomainError
from puro_pockets.domain.extras import preview_token, validate_extra_shares
from puro_pockets.domain.money import Currency
from puro_pockets.domain.months import Month
from puro_pockets.domain.pockets import Behavior, Pocket
from puro_pockets.domain.recurring import (
    RecurringRef,
    RecurringTemplate,
    due_date,
    find_recurring,
    pending_in_month,
    validate_day,
    validate_recurring_name,
)

POCKETS = [
    Pocket(1, "Necesidades", Behavior.CONSUMO),
    Pocket(2, "Ahorro", Behavior.ACUMULABLE),
    Pocket(3, "Gustos", Behavior.CONSUMO),
    Pocket(4, "Viejo", Behavior.CONSUMO, active=False),
]


JAN = Month(2026, 1)


def _template(id_=1, day=31, start=JAN, active=True, amounts=None, name="Fijo sin"):
    return RecurringTemplate(
        id_,
        name,
        Currency.CRC,
        day,
        1,
        None,
        start,
        active,
        amounts or ((start, 10_000),),
    )


# --- Gastos fijos ---


@pytest.mark.parametrize(
    ("month", "expected"),
    [
        (Month(2026, 2), date(2026, 2, 28)),  # día 31 en febrero → último día
        (Month(2028, 2), date(2028, 2, 29)),  # bisiesto
        (Month(2026, 4), date(2026, 4, 30)),
        (Month(2026, 12), date(2026, 12, 31)),
    ],
)
def test_dia_31_cuenta_como_el_ultimo_dia_del_mes(month, expected):
    assert due_date(month, 31) == expected


def test_referencias_f():
    assert RecurringRef.match(" f - 12 ") == RecurringRef(12)
    assert str(RecurringRef(3)) == "F-3"
    for text in ("F-0", "G-3", "Internet", None, 3):
        assert RecurringRef.match(text) is None


@pytest.mark.parametrize("value", [0, 32, "5", 5.0, True, None])
def test_dia_invalido(value):
    with pytest.raises(DomainError, match="entre 1 y 31"):
        validate_day(value)


def test_nombre_valido_y_reservado():
    assert validate_recurring_name("  Internet  ") == "Internet"
    for bad in ("", "x" * 61, "F-2", None):
        with pytest.raises(DomainError):
            validate_recurring_name(bad)


def test_el_monto_tiene_historial_y_el_cambio_solo_afecta_meses_futuros():
    template = _template(
        start=Month(2026, 10), amounts=((Month(2026, 10), 10_000), (Month(2026, 12), 12_000))
    )
    assert template.amount_for(Month(2026, 10)) == 10_000
    assert template.amount_for(Month(2026, 11)) == 10_000
    assert template.amount_for(Month(2026, 12)) == 12_000
    assert template.amount_for(Month(2027, 3)) == 12_000
    assert template.scheduled_change(Month(2026, 11)) == (Month(2026, 12), 12_000)
    assert template.scheduled_change(Month(2026, 12)) is None


def test_pendientes_desde_el_inicio_sin_pago_y_atrasados():
    templates = [
        _template(1, day=5, start=Month(2026, 11)),
        _template(2, day=20, start=Month(2026, 11)),
        _template(3, day=1, start=Month(2026, 12)),  # empieza después
        _template(4, day=1, active=False),  # desactivada
        _template(5, day=8, start=Month(2026, 1)),  # pagada
    ]
    pending = pending_in_month(templates, {5: 99}, Month(2026, 11), date(2026, 11, 10))
    assert [(p.template.id, p.due.day, p.overdue) for p in pending] == [
        (1, 5, True),
        (2, 20, False),
    ]
    # un mes futuro nunca está atrasado
    future = pending_in_month(templates, {}, Month(2026, 12), date(2026, 11, 10))
    assert all(not p.overdue for p in future) and {p.template.id for p in future} == {1, 2, 3, 5}


def test_buscar_por_referencia_o_nombre():
    templates = [
        _template(1, name="Internet", active=False),
        _template(2, name="Internet"),
        _template(3, name="Alquiler"),
    ]
    assert find_recurring(templates, "internet").id == 2  # por nombre, solo activas
    assert find_recurring(templates, "F-1").id == 1  # por referencia, aunque esté desactivada
    with pytest.raises(DomainError, match="F-9"):
        find_recurring(templates, "F-9")
    with pytest.raises(DomainError, match="activo con ese nombre"):
        find_recurring(templates, "Agua")


# --- Reparto del extra ---


def test_reparto_del_extra_admite_100_a_una_sola_bolsa():
    shares = validate_extra_shares([("ahorro", 100)], POCKETS)
    assert [(p.name, pct) for p, pct in shares] == [
        ("Necesidades", 0),
        ("Ahorro", 100),
        ("Gustos", 0),
    ]


@pytest.mark.parametrize(
    ("pairs", "message"),
    [
        ([("Ahorro", 60), ("Gustos", 30)], "suman 90"),
        ([("Ahorro", 60), ("Gustos", 50)], "suman 110"),
        ([("Inventada", 100)], "no existe o está archivada"),
        ([("Viejo", 100)], "no existe o está archivada"),  # inactiva
        ([("Ahorro", 50), ("ahorro", 50)], "más de una vez"),
        ([("Ahorro", 50.0), ("Gustos", 50)], "entero entre 0 y 100"),
        ([("Ahorro", 101)], "entero entre 0 y 100"),
        ([], "al menos una bolsa"),
    ],
)
def test_reparto_del_extra_invalido(pairs, message):
    with pytest.raises(DomainError, match=message):
        validate_extra_shares(pairs, POCKETS)


def test_la_ficha_cambia_con_el_reparto_el_monto_y_el_extra():
    a = validate_extra_shares([("Ahorro", 70), ("Gustos", 30)], POCKETS)
    b = validate_extra_shares([("Ahorro", 60), ("Gustos", 40)], POCKETS)
    token = preview_token("I-3", 40_000, a)
    assert token == preview_token("I-3", 40_000, a)
    assert len({token, preview_token("I-3", 40_000, b), preview_token("I-4", 40_000, a)}) == 3
    assert token != preview_token("I-3", 40_001, a)
