"""Estadísticas del dashboard (Hito 10, domain/stats.py). Datos sintéticos, calculados a mano."""

import pytest

from puro_pockets.domain.balances import AllocationEntry, IncomeKind
from puro_pockets.domain.months import Month
from puro_pockets.domain.pockets import Behavior, Pocket
from puro_pockets.domain.stats import (
    PocketAlert,
    SavingsTransfer,
    estimate_goal_month,
    month_saved,
    pocket_alert,
    trailing_months,
)

OCT, NOV = Month(2026, 10), Month(2026, 11)
NEC, AHO, GUS, VIA = 1, 2, 3, 4
POCKETS = [
    Pocket(NEC, "Necesidades", Behavior.CONSUMO),
    Pocket(AHO, "Ahorro", Behavior.ACUMULABLE),
    Pocket(GUS, "Gustos", Behavior.CONSUMO),
    Pocket(VIA, "Viaje", Behavior.ACUMULABLE, active=False),  # archivada: también cuenta
]


def _transfer(src, dst, month, amount, close=False):
    return SavingsTransfer(src, dst, month, amount, close)


def test_ahorrado_con_todas_las_fuentes_y_su_desglose():
    entries = [
        AllocationEntry(AHO, NOV, 150_000, IncomeKind.BASE),  # salario: 30 % a Ahorro
        AllocationEntry(NEC, NOV, 250_000, IncomeKind.BASE),  # consumo: no es ahorro
        AllocationEntry(AHO, NOV, 10_000, IncomeKind.EXTRA),  # extra repartido
        AllocationEntry(AHO, NOV, 900_000, IncomeKind.INITIAL_BALANCE),  # saldo inicial: no
        AllocationEntry(AHO, OCT, 140_000, IncomeKind.BASE),  # otro mes: no
    ]
    transfers = [
        _transfer(NEC, AHO, NOV, 7_000),  # recibida
        _transfer(AHO, GUS, NOV, 3_000),  # enviada
        _transfer(AHO, VIA, NOV, 20_000),  # entre acumulables: se anula
        _transfer(GUS, AHO, NOV, 5_000, close=True),  # sobrante de cierre de noviembre
        _transfer(AHO, NEC, NOV, 2_000, close=True),  # cobertura desde acumulable (RN-52)
        _transfer(NEC, AHO, OCT, 9_000, close=True),  # cierre de otro mes: no
    ]
    saved = month_saved(POCKETS, entries, transfers, NOV)
    assert (saved.base, saved.extra) == (150_000, 10_000)
    assert saved.transfers_in == 7_000 + 20_000
    assert saved.transfers_out == 3_000 + 20_000 + 2_000
    assert saved.closure_surplus == 5_000
    assert saved.total == 150_000 + 10_000 + 7_000 - 3_000 + 5_000 - 2_000


def test_ahorrado_sin_movimientos_es_cero():
    assert month_saved(POCKETS, [], [], NOV).total == 0


def test_ahorrado_puede_ser_negativo_si_sale_mas_de_lo_que_entra():
    saved = month_saved(POCKETS, [], [_transfer(AHO, NEC, NOV, 4_000)], NOV)
    assert saved.total == -4_000


@pytest.mark.parametrize(
    ("missing", "average", "projectable", "expected"),
    [
        (20_000, 60_000, True, Month(2026, 12)),  # ejemplo de docs/dashboard.md
        (150_000, 25_000, True, Month(2027, 5)),  # 6 meses
        (150_001, 25_000, True, Month(2027, 6)),  # techo: un colón más, un mes más
        (20_000, 60_000, False, None),  # no proyectable (RN-28)
        (20_000, None, True, None),
        (20_000, 0, True, None),
        (20_000, -5, True, None),
        (0, 60_000, True, None),  # ya lograda
    ],
)
def test_fecha_estimada(missing, average, projectable, expected):
    assert estimate_goal_month(NOV, missing, average, projectable) == expected


@pytest.mark.parametrize(
    ("percent", "negative", "expected"),
    [
        (None, False, None),
        (79, False, None),
        (80, False, PocketAlert.WARNING),
        (99, False, PocketAlert.WARNING),
        (100, False, PocketAlert.DANGER),
        (104, False, PocketAlert.DANGER),
        (None, True, PocketAlert.DANGER),  # acumulable en negativo
        (50, True, PocketAlert.DANGER),
    ],
)
def test_alerta_de_bolsa(percent, negative, expected):
    assert pocket_alert(percent, negative) == expected


def test_seis_meses_que_cruzan_el_año():
    assert [str(m) for m in trailing_months(Month(2027, 2))] == [
        "2026-09",
        "2026-10",
        "2026-11",
        "2026-12",
        "2027-01",
        "2027-02",
    ]
