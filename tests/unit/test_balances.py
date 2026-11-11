"""Saldos 11.1 / 11.2, RN-11, RN-12 y RN-54 (datos sintéticos)."""

from puro_pockets.domain.balances import (
    AllocationEntry,
    BalanceKind,
    IncomeKind,
    integrity_gap,
    month_income_total,
    pocket_balance,
)
from puro_pockets.domain.months import Month
from puro_pockets.domain.pockets import Behavior, Pocket

NEC = Pocket(1, "Necesidades", Behavior.CONSUMO)
AHO = Pocket(2, "Ahorro", Behavior.ACUMULABLE)
NOV, DEC = Month(2026, 11), Month(2026, 12)
INITIAL = IncomeKind.INITIAL_BALANCE

ENTRIES = [
    AllocationEntry(1, NOV, 100_000, INITIAL),
    AllocationEntry(2, NOV, 500_000, INITIAL),
    AllocationEntry(1, DEC, 40_000),
    AllocationEntry(2, DEC, 10_000),
]


def test_consumo_disponible_del_mes_y_empieza_en_cero_en_otro_mes():
    assert pocket_balance(NEC, ENTRIES, NOV).balance == 100_000
    assert pocket_balance(NEC, ENTRIES, DEC).balance == 40_000  # no arrastra noviembre (RN-11)
    assert pocket_balance(NEC, ENTRIES, Month(2027, 1)).balance == 0
    assert pocket_balance(NEC, ENTRIES, NOV).kind is BalanceKind.MONTH_AVAILABLE


def test_acumulable_conserva_su_saldo():
    assert pocket_balance(AHO, ENTRIES, NOV).balance == 510_000  # RN-12, 11.2
    assert pocket_balance(AHO, ENTRIES, Month(2030, 1)).balance == 510_000
    assert pocket_balance(AHO, ENTRIES, NOV).kind is BalanceKind.BALANCE


def test_saldo_inicial_no_cuenta_como_ingreso_del_mes_pero_si_en_saldos():
    assert month_income_total(ENTRIES, NOV) == 0  # RN-54
    assert month_income_total(ENTRIES, DEC) == 50_000
    assert pocket_balance(AHO, ENTRIES, NOV).balance > 0


def test_invariante_cuadra_y_detecta_descuadres():
    total = sum(e.amount for e in ENTRIES)
    assert integrity_gap(total, [NEC, AHO], ENTRIES) == 0
    assert integrity_gap(total + 1, [NEC, AHO], ENTRIES) == 1
