"""Porcentajes por mes y reparto en montos: RN-01, RN-03, RN-08 (datos sintéticos)."""

import random

import pytest

from puro_pockets.domain.allocation import (
    ensure_editable,
    pick_source_month,
    resolve_allocation,
    split_amount,
    validate_allocation,
)
from puro_pockets.domain.errors import DomainError
from puro_pockets.domain.months import Month
from puro_pockets.domain.pockets import Behavior, Pocket

NEC = Pocket(1, "Necesidades", Behavior.CONSUMO)
AHO = Pocket(2, "Ahorro", Behavior.ACUMULABLE)
GUS = Pocket(3, "Gustos", Behavior.CONSUMO)
ARCH = Pocket(4, "Viaje", Behavior.ACUMULABLE, active=False)
POCKETS = [NEC, AHO, GUS, ARCH]


# --- RN-01: validación ---


def test_50_30_20_valido_en_orden_de_creacion():
    rows = validate_allocation([("gustos", 20), ("Necesidades", 50), ("  AHORRO ", 30)], POCKETS)
    assert rows == {1: 50, 2: 30, 3: 20}
    assert list(rows) == [1, 2, 3]


@pytest.mark.parametrize("values, total", [((50, 30, 30), 110), ((50, 30, 10), 90)])
def test_suma_distinta_de_100_indica_la_suma(values, total):
    requested = list(zip(["Necesidades", "Ahorro", "Gustos"], values, strict=True))
    with pytest.raises(DomainError, match=f"suman {total}"):
        validate_allocation(requested, POCKETS)


def test_falta_una_bolsa_activa():
    with pytest.raises(DomainError, match="Falta el porcentaje de: Gustos"):
        validate_allocation([("Necesidades", 50), ("Ahorro", 50)], POCKETS)


def test_lista_vacia_nombra_todas_las_bolsas():
    with pytest.raises(DomainError, match="Necesidades, Ahorro, Gustos"):
        validate_allocation([], POCKETS)


def test_bolsa_repetida_aunque_cambie_la_capitalizacion():
    with pytest.raises(DomainError, match="más de una vez"):
        validate_allocation(
            [("Necesidades", 50), ("necesidades", 0), ("Ahorro", 30), ("Gustos", 20)], POCKETS
        )


@pytest.mark.parametrize("name", ["Viaje", "Inexistente"])
def test_bolsa_archivada_o_inexistente(name):
    with pytest.raises(DomainError, match=f"'{name}' no existe o está archivada"):
        validate_allocation(
            [("Necesidades", 50), ("Ahorro", 30), ("Gustos", 20), (name, 0)], POCKETS
        )


@pytest.mark.parametrize("bad", [-1, 101, 20.5, "20", True, None])
def test_porcentaje_no_entero_o_fuera_de_rango(bad):
    with pytest.raises(DomainError, match="porcentaje de Gustos debe ser un entero entre 0 y 100"):
        validate_allocation([("Necesidades", 50), ("Ahorro", 30), ("Gustos", bad)], POCKETS)


def test_cero_por_ciento_es_valido():
    assert validate_allocation([("Necesidades", 100), ("Ahorro", 0), ("Gustos", 0)], POCKETS) == {
        1: 100,
        2: 0,
        3: 0,
    }


def test_mes_pasado_no_editable():
    ensure_editable(Month(2026, 11), Month(2026, 11))
    ensure_editable(Month(2027, 1), Month(2026, 11))
    with pytest.raises(DomainError, match="2026-10: es un mes pasado"):
        ensure_editable(Month(2026, 10), Month(2026, 11))


# --- RN-03: herencia ---


def test_hereda_del_mes_anterior_mas_cercano():
    months = [Month(2026, 9), Month(2026, 11), Month(2027, 2)]
    assert pick_source_month(Month(2026, 11), months) == Month(2026, 11)
    assert pick_source_month(Month(2027, 1), months) == Month(2026, 11)
    assert pick_source_month(Month(2030, 5), months) == Month(2027, 2)
    assert pick_source_month(Month(2026, 8), months) is None


def test_resolucion_indica_origen_y_rellena_bolsas_sin_fila():
    resolved = resolve_allocation(Month(2026, 12), Month(2026, 11), {1: 60, 2: 40}, POCKETS)
    assert resolved.defined and resolved.source_month == Month(2026, 11)
    assert [(p.name, pct) for p, pct in resolved.items] == [
        ("Necesidades", 60),
        ("Ahorro", 40),
        ("Gustos", 0),
    ]


def test_sin_porcentajes_definidos():
    resolved = resolve_allocation(Month(2026, 12), None, {}, POCKETS)
    assert not resolved.defined and resolved.items == ()


# --- RN-08: reparto en enteros ---


def test_10001_con_50_30_20():
    assert split_amount(10_001, [("N", 50), ("A", 30), ("G", 20)]) == [
        ("N", 5_000),
        ("A", 3_000),
        ("G", 2_001),
    ]


def test_cero_por_ciento_intermedio_recibe_cero():
    assert split_amount(999, [("N", 50), ("A", 0), ("G", 50)]) == [("N", 499), ("A", 0), ("G", 500)]


def test_residuo_en_la_ultima_aunque_tenga_cero_por_ciento():
    # Consecuencia documentada de RN-08: el residuo es menor que la cantidad de bolsas
    assert split_amount(1, [("N", 50), ("A", 50), ("G", 0)]) == [("N", 0), ("A", 0), ("G", 1)]


def test_reparto_exacto_y_sin_negativos_con_datos_generados():
    seed = 20261110
    rng = random.Random(seed)
    for case in range(2_000):
        count = rng.randint(1, 8)
        cuts = sorted(rng.randint(0, 100) for _ in range(count - 1))
        percentages = [b - a for a, b in zip([0, *cuts], [*cuts, 100], strict=True)]
        amount = rng.choice([0, 1, 7, rng.randint(1, 10_000_000), rng.randint(1, 10**15)])
        parts = split_amount(amount, list(enumerate(percentages)))
        assert sum(p for _, p in parts) == amount, f"semilla={seed} caso={case}"
        assert all(p >= 0 for _, p in parts), f"semilla={seed} caso={case}"


@pytest.mark.parametrize(
    "amount, shares",
    [(-1, [("N", 100)]), (10, []), (10, [("N", 50), ("A", 40)]), (10.5, [("N", 100)])],
)
def test_reparto_invalido(amount, shares):
    with pytest.raises(DomainError):
        split_amount(amount, shares)
