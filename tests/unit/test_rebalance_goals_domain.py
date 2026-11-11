"""Dominio del Hito 7: reajuste de porcentajes (RN-13, RN-14, RN-17) y metas (RN-19 a RN-28).

Datos sintéticos. La prueba de propiedades usa una semilla fija y la imprime si falla.
"""

import random
from datetime import date

import pytest

from puro_pockets.domain.balances import AllocationEntry, ExpenseEntry
from puro_pockets.domain.errors import DomainError
from puro_pockets.domain.goals import (
    Goal,
    GoalRef,
    GoalStatus,
    balance_function,
    net_monthly_change,
    progress,
    reached,
    validate_target_amount,
    validate_target_date,
)
from puro_pockets.domain.months import Month
from puro_pockets.domain.pockets import parse_behavior, validate_group, validate_pocket_name
from puro_pockets.domain.rebalance import (
    Strategy,
    parse_strategy,
    rebalance_add,
    rebalance_remove,
)

SEED = 20261111
CURRENT = [("N", 50), ("A", 30), ("G", 20)]


def _percentages(rng, count):
    cuts = sorted(rng.randint(0, 100) for _ in range(count - 1))
    return [b - a for a, b in zip([0, *cuts], [*cuts, 100], strict=True)]


# --- Reajuste ---


def test_proporcional_al_crear_con_residuo_en_la_ultima():
    result = rebalance_add(CURRENT, "E", 10, Strategy.PROPORTIONAL)
    assert result == [("N", 45), ("A", 27), ("G", 18), ("E", 10)]
    # 33/33/34 ceden 7: floor(33*93/100)=30, 30, la última absorbe el residuo
    assert rebalance_add([("a", 33), ("b", 33), ("c", 34)], "n", 7, Strategy.PROPORTIONAL) == [
        ("a", 30),
        ("b", 30),
        ("c", 33),
        ("n", 7),
    ]


def test_desde_una_bolsa_y_manual_al_crear():
    assert rebalance_add(CURRENT, "E", 10, Strategy.FROM_ONE, source="A") == [
        ("N", 50),
        ("A", 20),
        ("G", 20),
        ("E", 10),
    ]
    with pytest.raises(DomainError, match="no alcanza"):
        rebalance_add(CURRENT, "E", 25, Strategy.FROM_ONE, source="G")
    manual = {"N": 40, "A": 30, "G": 20, "E": 10}
    assert rebalance_add(CURRENT, "E", 0, Strategy.MANUAL, manual=manual)[-1] == ("E", 10)


@pytest.mark.parametrize(
    ("manual", "message"),
    [
        ({"N": 40, "A": 30, "G": 20, "E": 5}, "suman 95"),
        ({"N": 40, "A": 30, "G": 30}, "todas las bolsas"),
        ({"N": 40, "A": 30, "G": 20, "E": 10, "X": 0}, "todas las bolsas"),
        ({"N": 40.0, "A": 30, "G": 20, "E": 10}, "entero"),
        (None, "indica el porcentaje"),
    ],
)
def test_manual_invalido(manual, message):
    with pytest.raises(DomainError, match=message):
        rebalance_add(CURRENT, "E", 0, Strategy.MANUAL, manual=manual)


def test_al_archivar_se_redistribuye():
    assert rebalance_remove(CURRENT, "G", Strategy.PROPORTIONAL) == [("N", 62), ("A", 38)]
    assert rebalance_remove(CURRENT, "G", Strategy.FROM_ONE, target="A") == [("N", 50), ("A", 50)]
    assert rebalance_remove([("N", 100), ("X", 0)], "X", Strategy.PROPORTIONAL) == [("N", 100)]
    with pytest.raises(DomainError, match="proporcional no es posible"):
        rebalance_remove([("N", 0), ("X", 100)], "X", Strategy.PROPORTIONAL)
    with pytest.raises(DomainError, match="única bolsa"):
        rebalance_remove([("N", 100)], "N", Strategy.PROPORTIONAL)
    with pytest.raises(DomainError, match="otra bolsa activa"):
        rebalance_remove(CURRENT, "G", Strategy.FROM_ONE, target="G")


def test_errores_de_entrada():
    with pytest.raises(DomainError, match="estrategia"):
        parse_strategy("equitativa")
    with pytest.raises(DomainError, match="entero entre 0 y 100"):
        rebalance_add(CURRENT, "E", 101, Strategy.PROPORTIONAL)
    with pytest.raises(DomainError, match="No hay porcentajes"):
        rebalance_add([], "E", 30, Strategy.PROPORTIONAL)
    assert rebalance_add([], "E", 100, Strategy.PROPORTIONAL) == [("E", 100)]


def test_propiedad_la_suma_es_100_y_nada_es_negativo():
    rng = random.Random(SEED)
    for case in range(3000):
        count = rng.randint(1, 9)
        current = list(zip(range(count), _percentages(rng, count), strict=True))
        share = rng.randint(0, 100)
        strategy = rng.choice([Strategy.PROPORTIONAL, Strategy.FROM_ONE])
        source = rng.randrange(count)
        try:
            added = rebalance_add(current, "nueva", share, strategy, source=source)
        except DomainError:
            assert strategy is Strategy.FROM_ONE and dict(current)[source] < share, case
        else:
            assert sum(p for _, p in added) == 100, f"semilla={SEED} caso={case}"
            assert all(0 <= p <= 100 for _, p in added), f"semilla={SEED} caso={case}"
            assert dict(added)["nueva"] == share
        if count > 1:
            removed = rng.randrange(count)
            try:
                left = rebalance_remove(current, removed, strategy, target=(removed + 1) % count)
            except DomainError:
                rest = sum(p for k, p in current if k != removed)
                assert strategy is Strategy.PROPORTIONAL and rest == 0, case
            else:
                assert sum(p for _, p in left) == 100, f"semilla={SEED} caso={case}"
                assert all(p >= 0 for _, p in left) and removed not in dict(left)


def test_validaciones_de_bolsa():
    assert validate_pocket_name("  Emergencia ") == "Emergencia"
    assert validate_group("  ") is None and validate_group("Ahorros") == "Ahorros"
    assert parse_behavior("Acumulable").value == "acumulable"
    for bad in ("", "x" * 41, None):
        with pytest.raises(DomainError):
            validate_pocket_name(bad)
    with pytest.raises(DomainError, match="consumo o acumulable"):
        parse_behavior("gasto")


# --- Metas ---

TODAY = date(2026, 11, 11)


def _goal(id_=1, pocket=2, target=500_000, status=GoalStatus.ACTIVE, created=TODAY, archived=False):
    return Goal(id_, pocket, "Viaje sintético", target, None, status, None, created, archived)


def test_referencia_y_validaciones():
    assert GoalRef.parse(" m-7 ") == GoalRef(7) and str(GoalRef(7)) == "M-7"
    with pytest.raises(DomainError, match="M-n"):
        GoalRef.parse("G-7")
    for bad in (0, -1, 10.5, "500000", True):
        with pytest.raises(DomainError):
            validate_target_amount(bad)
    with pytest.raises(DomainError, match="pasado"):
        validate_target_date(date(2026, 11, 10), TODAY)


def test_progreso_con_tope_y_faltante():
    goal = _goal()
    assert progress(goal, 180_000) == progress(goal, 180_000)
    assert (progress(goal, 180_000).percent, progress(goal, 180_000).missing) == (36, 320_000)
    assert (progress(goal, 650_000).percent, progress(goal, 650_000).missing) == (100, 0)
    assert progress(goal, -5_000).percent == 0


def test_lograda_solo_metas_vivas_y_nunca_antes_de_crearse():
    goals = [
        _goal(1, pocket=2),
        _goal(2, pocket=3, status=GoalStatus.PAUSED),
        _goal(3, pocket=4, archived=True),
        _goal(4, pocket=5, created=date(2026, 11, 20)),
        _goal(5, pocket=6, target=10**9),
    ]
    result = reached(goals, lambda pocket: 600_000, date(2026, 11, 15))
    assert result == [(1, date(2026, 11, 15)), (4, date(2026, 11, 20))]


def test_avance_usa_el_saldo_oficial_11_2():
    entries = [
        AllocationEntry(2, Month(2026, 10), 300_000),
        AllocationEntry(2, Month(2026, 11), 100_000),
    ]
    expenses = [ExpenseEntry(2, Month(2026, 11), 50_000)]
    assert balance_function(entries, expenses)(2) == 350_000


def test_variacion_neta_mensual_rn_28():
    entries = [AllocationEntry(2, Month(2026, m), 100_000) for m in (7, 8, 9, 10, 11)]
    expenses = [ExpenseEntry(2, Month(2026, 10), 40_000)]
    change = net_monthly_change(entries, expenses, 2, Month(2026, 11))
    # meses completos: 10, 9, 8 → (60 000 + 100 000 + 100 000) / 3
    assert (change.months, change.average, change.projectable) == (3, 86_666, True)
    short = net_monthly_change(entries[-2:], [], 2, Month(2026, 11))  # solo octubre completo
    assert (short.months, short.average) == (1, 100_000)
    new = net_monthly_change([AllocationEntry(2, Month(2026, 11), 1)], [], 2, Month(2026, 11))
    assert (new.months, new.average, new.projectable) == (0, None, False)
    negative = net_monthly_change(
        entries[:1], [ExpenseEntry(2, Month(2026, 8), 200_000)], 2, Month(2026, 11)
    )
    assert negative.projectable is False and negative.average < 0
