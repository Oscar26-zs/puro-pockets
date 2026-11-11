"""Validación del saldo inicial: RN-54 (datos sintéticos)."""

import pytest

from puro_pockets.domain.errors import DomainError
from puro_pockets.domain.initial_balance import validate_initial_balance
from puro_pockets.domain.pockets import Behavior, Pocket

POCKETS = [
    Pocket(1, "Necesidades", Behavior.CONSUMO),
    Pocket(2, "Ahorro", Behavior.ACUMULABLE),
    Pocket(3, "Gustos", Behavior.CONSUMO),
    Pocket(4, "Viaje", Behavior.ACUMULABLE, active=False),
]


def _names(items):
    return [(p.name, amount) for p, amount in items]


def test_montos_por_bolsa_y_omitidas_cuentan_como_cero():
    items = validate_initial_balance([("ahorro", 500_000), ("Necesidades", 100_000)], POCKETS)
    assert _names(items) == [("Necesidades", 100_000), ("Ahorro", 500_000), ("Gustos", 0)]


@pytest.mark.parametrize("bad", [-1, 10.5, "100", True, None])
def test_monto_negativo_o_no_entero(bad):
    with pytest.raises(DomainError, match="monto de Gustos debe ser un entero mayor o igual a 0"):
        validate_initial_balance([("Gustos", bad)], POCKETS)


@pytest.mark.parametrize("requested", [[], [("Gustos", 0), ("Ahorro", 0)]])
def test_todo_en_cero(requested):
    with pytest.raises(DomainError, match="al menos un monto mayor que 0"):
        validate_initial_balance(requested, POCKETS)


@pytest.mark.parametrize("name", ["Viaje", "Inexistente"])
def test_bolsa_archivada_o_inexistente(name):
    with pytest.raises(DomainError, match="no existe o está archivada"):
        validate_initial_balance([(name, 100)], POCKETS)


def test_bolsa_repetida():
    with pytest.raises(DomainError, match="más de una vez"):
        validate_initial_balance([("Ahorro", 1), ("AHORRO", 2)], POCKETS)


def test_total_excesivo():
    with pytest.raises(DomainError, match="excede el máximo"):
        validate_initial_balance([("Ahorro", 2**62), ("Gustos", 2**62)], POCKETS)


def test_los_mensajes_no_incluyen_montos():
    with pytest.raises(DomainError) as exc:
        validate_initial_balance([("Ahorro", 123_456_789), ("Gustos", -987_654)], POCKETS)
    assert "987654" not in exc.value.message and "123456789" not in exc.value.message
