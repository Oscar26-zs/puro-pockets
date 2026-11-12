"""Reglas puras del cierre de mes (Hito 9): mes cerrado, qué mes se cierra, propuesta y resultado.

Datos sintéticos. Los mensajes de error no llevan montos.
"""

from datetime import date

import pytest

from puro_pockets.domain.balances import AllocationEntry, ExpenseEntry, pocket_figures
from puro_pockets.domain.closures import (
    AdjustmentKind,
    ClosedMonths,
    ClosureState,
    analyze,
    check_closable,
    check_open,
    default_close_month,
    first_open,
    is_closed,
    last_day,
    parse_moves,
    pending_closure,
    plan_close,
)
from puro_pockets.domain.errors import ClosureProposalInvalid, MonthClosed, MonthNotClosable
from puro_pockets.domain.goals import Goal, GoalStatus
from puro_pockets.domain.months import Month
from puro_pockets.domain.pockets import Behavior, Pocket

OCT, NOV, DEC = Month(2026, 10), Month(2026, 11), Month(2026, 12)
NEC = Pocket(1, "Necesidades", Behavior.CONSUMO)
AHO = Pocket(2, "Ahorro", Behavior.ACUMULABLE)
GUS = Pocket(3, "Gustos", Behavior.CONSUMO)
VIA = Pocket(4, "Viaje", Behavior.ACUMULABLE)
OLD = Pocket(5, "Vieja", Behavior.CONSUMO, active=False)
POCKETS = [NEC, AHO, GUS, VIA, OLD]
GOAL = Goal(1, 2, "meta sintética", 1_000_000, None, GoalStatus.ACTIVE, None, date(2026, 10, 1))


def _state(closed=(), moves=(OCT, NOV)):
    return ClosureState(ClosedMonths(frozenset(closed)), frozenset(moves))


# --- La única regla de mes cerrado ---


def test_mes_cerrado_y_anteriores_cuentan_como_cerrados():
    closed = ClosedMonths(frozenset({OCT}))
    assert is_closed(OCT, closed)
    assert is_closed(Month(2026, 9), closed)  # anterior al último cerrado
    assert not is_closed(NOV, closed)
    assert not is_closed(NOV, ClosedMonths())  # sin fila: abierto


def test_check_open_dice_por_que_sin_montos():
    closed = ClosedMonths(frozenset({OCT}))
    with pytest.raises(MonthClosed, match="2026-10 está cerrado"):
        check_open(OCT, closed)
    with pytest.raises(MonthClosed, match="anterior a un mes ya cerrado"):
        check_open(Month(2026, 9), closed)
    check_open(NOV, closed)


def test_primer_mes_abierto_salta_el_actual_si_se_cerro():
    assert first_open(date(2026, 11, 30), ClosedMonths(frozenset({NOV}))) == DEC
    assert first_open(date(2026, 11, 30), ClosedMonths()) == NOV


# --- Qué mes se cierra (P1, PROPUESTO 1 a 3) ---


@pytest.mark.parametrize(
    ("month", "today", "state", "match"),
    [
        (OCT, date(2026, 11, 5), _state(closed={OCT}), "ya está cerrado"),
        (Month(2026, 9), date(2026, 11, 5), _state(closed={OCT}), "anterior a un mes ya cerrado"),
        (DEC, date(2026, 11, 30), _state(), "futuro"),
        (NOV, date(2026, 11, 30), _state(), "antes hay que cerrar 2026-10"),
        (NOV, date(2026, 11, 29), _state(closed={OCT}), "desde su último día"),
        (Month(2026, 9), date(2026, 11, 5), _state(), "anterior al primer mes con movimientos"),
        (OCT, date(2026, 11, 5), _state(moves=()), "no hay movimientos"),
    ],
)
def test_meses_que_no_se_pueden_cerrar(month, today, state, match):
    with pytest.raises(MonthNotClosable, match=match):
        check_closable(month, today, state)


def test_se_cierra_desde_el_ultimo_dia_y_en_orden():
    check_closable(OCT, date(2026, 10, 31), _state())
    check_closable(NOV, date(2026, 11, 30), _state(closed={OCT}))
    check_closable(NOV, date(2026, 11, 11), _state(closed={OCT}), allow_early=True)
    assert last_day(Month(2028, 2)) == date(2028, 2, 29)


def test_cierre_pendiente_incluye_meses_vacios_en_medio():
    state = _state(moves=(Month(2026, 8), OCT))
    pending = pending_closure(date(2026, 11, 11), state)
    assert [(str(p.month), p.has_movements) for p in pending] == [
        ("2026-08", True),
        ("2026-09", False),
        ("2026-10", True),
    ]
    assert default_close_month(date(2026, 11, 11), state) == Month(2026, 8)
    assert pending_closure(date(2026, 11, 30), _state(closed={OCT}))[0].month == NOV
    assert pending_closure(date(2026, 11, 29), _state(closed={OCT})) == []


# --- Propuesta y resultado (10.1, 10.2, RN-47, RN-50, RN-52, RN-58) ---


def _picture(nec=0, gus=0, aho=0, via=0, old=0, goals=(GOAL,)):
    """Disponibles de consumo y saldos acumulables del mes, armados con movimientos sintéticos."""
    entries, expenses = [], []
    for pocket, value in ((NEC, nec), (GUS, gus), (AHO, aho), (VIA, via), (OLD, old)):
        if value > 0:
            entries.append(AllocationEntry(pocket.id, NOV, value))
        elif value < 0:
            expenses.append(ExpenseEntry(pocket.id, NOV, -value))
    figures = {p.id: pocket_figures(p, NOV, entries, expenses) for p in POCKETS}
    return analyze(NOV, POCKETS, figures, goals)


def _moves(items, allow_null=False):
    return parse_moves(
        [{"from_pocket": f, "to_pocket": t, "amount": a} for f, t, a in items],
        POCKETS,
        allow_null,
    )


def test_el_sobrante_cubre_el_deficit_y_el_resto_va_a_ahorro():
    picture = _picture(nec=20_000, gus=-5_000, aho=100_000)
    plan = plan_close(
        picture,
        _moves([("Necesidades", "Gustos", 5_000)]),
        _moves([("Necesidades", "Ahorro", 15_000)], allow_null=True),
    )
    after = {o.pocket.name: o.after for o in plan.outcomes}
    assert after == {"Necesidades": 0, "Gustos": 0, "Ahorro": 115_000, "Viaje": 0}
    assert plan.adjustments == ()
    assert [(m.source.name, m.target.name) for m in plan.transfers] == [
        ("Necesidades", "Gustos"),
        ("Necesidades", "Ahorro"),
    ]
    assert plan.goal_effects[0].percent_after == 11


def test_lo_no_asignado_queda_como_no_destinado_explicito_o_por_resto():
    picture = _picture(nec=20_000, gus=3_000)
    plan = plan_close(
        picture, [], _moves([("Necesidades", None, 5_000), ("Gustos", "Viaje", 1_000)], True)
    )
    adjustments = {(a.pocket.name, a.kind): a.amount for a in plan.adjustments}
    assert adjustments == {
        ("Necesidades", AdjustmentKind.UNASSIGNED_SURPLUS): 20_000,
        ("Gustos", AdjustmentKind.UNASSIGNED_SURPLUS): 2_000,
    }
    assert plan.total(AdjustmentKind.UNASSIGNED_SURPLUS) == 22_000
    assert len(plan.transfers) == 1  # el null no es una transferencia


def test_deficit_sin_sobrantes_queda_como_sobregasto_no_cubierto():
    plan = plan_close(_picture(gus=-8_000, aho=50_000), [], [])
    assert [(a.kind, a.amount) for a in plan.adjustments] == [
        (AdjustmentKind.UNCOVERED_OVERSPEND, -8_000)
    ]
    assert any("sobregasto no cubierto" in w for w in plan.warnings)


def test_cobertura_desde_acumulable_solo_con_sobrantes_de_consumo_usados():
    picture = _picture(nec=2_000, gus=-8_000, aho=50_000)
    plan = plan_close(
        picture,
        _moves([("Necesidades", "Gustos", 2_000), ("Ahorro", "Gustos", 6_000)]),
        [],
    )
    assert [m.from_balance for m in plan.covers] == [False, True]
    assert any("saldo acumulado (RN-52)" in w for w in plan.warnings)
    assert plan.goal_effects[0].percent_before == 5
    assert plan.goal_effects[0].percent_after == 4
    with pytest.raises(ClosureProposalInvalid, match="primero se cubren"):
        plan_close(picture, _moves([("Ahorro", "Gustos", 8_000)]), [])


def test_rechazar_la_cobertura_desde_acumulable_es_valido():
    # 2b: el propietario no acepta tomar de Ahorro; lo restante queda no cubierto
    plan = plan_close(
        _picture(nec=2_000, gus=-8_000, aho=50_000),
        _moves([("Necesidades", "Gustos", 2_000)]),
        [],
    )
    assert [(a.kind, a.amount) for a in plan.adjustments] == [
        (AdjustmentKind.UNCOVERED_OVERSPEND, -6_000)
    ]


@pytest.mark.parametrize(
    ("covers", "destinations", "match"),
    [
        ([], [("Necesidades", "Ahorro", 10_000)], "primero se cubren"),
        ([("Necesidades", "Gustos", 6_000)], [], "supera su déficit"),
        ([("Necesidades", "Gustos", 5_000)], [("Necesidades", "Ahorro", 16_000)], "RN-47"),
        ([("Necesidades", "Gustos", 5_000)], [("Necesidades", "Gustos", 1_000)], "10.2"),
        ([("Gustos", "Necesidades", 1)], [], "no lo tiene"),
        ([("Necesidades", "Ahorro", 1)], [], "no lo tiene"),
        ([("Viaje", "Gustos", 1)], [], "no tiene saldo positivo"),
        ([("Necesidades", "Gustos", 5_000)], [("Gustos", None, 1)], "no tiene sobrante"),
    ],
)
def test_propuestas_invalidas(covers, destinations, match):
    picture = _picture(nec=20_000, gus=-5_000, aho=100_000)
    with pytest.raises(ClosureProposalInvalid, match=match):
        plan_close(picture, _moves(covers), _moves(destinations, True))


@pytest.mark.parametrize(
    ("raw", "match"),
    [
        ({"from_pocket": "Necesidades", "to_pocket": "Gustos", "amount": 0}, "mayor que 0"),
        ({"from_pocket": "Necesidades", "to_pocket": "Gustos", "amount": 1.5}, "sin decimales"),
        ({"from_pocket": "Necesidades", "to_pocket": "Gustos", "amount": "10"}, "sin decimales"),
        ({"from_pocket": "Vieja", "to_pocket": "Gustos", "amount": 1}, "archivada"),
        ({"from_pocket": "Nadie", "to_pocket": "Gustos", "amount": 1}, "no existe"),
        ({"from_pocket": "Necesidades", "to_pocket": None, "amount": 1}, "bolsa de destino"),
        ({"from_pocket": "Gustos", "to_pocket": "gustos", "amount": 1}, "misma bolsa"),
    ],
)
def test_movimientos_mal_formados(raw, match):
    with pytest.raises(ClosureProposalInvalid, match=match):
        parse_moves([raw], POCKETS, allow_null=False)


def test_par_repetido_se_rechaza():
    raw = [{"from_pocket": "Necesidades", "to_pocket": "Ahorro", "amount": 1}] * 2
    with pytest.raises(ClosureProposalInvalid, match="más de una vez"):
        parse_moves(raw, POCKETS, allow_null=True)


def test_archivada_con_cifras_va_entera_a_ajustes_y_acumulable_negativa_avisa():
    picture = _picture(old=4_000, via=-3_000, goals=())
    plan = plan_close(picture, [], [])
    assert [(a.pocket.name, a.amount) for a in plan.adjustments] == [("Vieja", 4_000)]
    warnings = " ".join(plan.warnings)
    assert "Vieja está archivada" in warnings
    assert "Viaje tiene saldo negativo" in warnings and "transferencia hacia ella" in warnings
    assert "no admitirá más movimientos" in warnings
    assert all("4000" not in w and "3000" not in w for w in plan.warnings)  # sin montos
