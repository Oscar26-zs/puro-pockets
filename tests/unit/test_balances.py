"""Saldos 11.1 / 11.2, RN-11, RN-12, RN-33, RN-37 y RN-54 (datos sintéticos)."""

from puro_pockets.domain.balances import (
    AllocationEntry,
    BalanceKind,
    ExpenseEntry,
    IncomeKind,
    integrity_gap,
    month_income_total,
    percent_used,
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
EXPENSES = [
    ExpenseEntry(1, NOV, 30_000),
    ExpenseEntry(1, DEC, 55_000),  # sobregasto de diciembre
    ExpenseEntry(2, NOV, 7_000),  # gasto contra acumulable (RN-33)
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


def test_gastos_restan_del_mes_en_consumo_y_del_saldo_en_acumulable():
    assert pocket_balance(NEC, ENTRIES, NOV, EXPENSES).balance == 70_000
    assert pocket_balance(NEC, ENTRIES, DEC, EXPENSES).balance == -15_000  # negativo (RN-37, 38)
    assert pocket_balance(AHO, ENTRIES, DEC, EXPENSES).balance == 503_000


def test_saldo_inicial_no_cuenta_como_ingreso_del_mes_pero_si_en_saldos():
    assert month_income_total(ENTRIES, NOV) == 0  # RN-54
    assert month_income_total(ENTRIES, DEC) == 50_000
    assert pocket_balance(AHO, ENTRIES, NOV).balance > 0


def test_porcentaje_usado_entero_o_vacio():
    assert percent_used(30_000, 100_000) == 30
    assert percent_used(2, 3) == 66  # hacia abajo
    assert percent_used(55_000, 40_000) == 137
    assert percent_used(1, 0) is None
    assert percent_used(1, -5) is None


def test_invariante_cuadra_y_detecta_descuadres():
    income = sum(e.amount for e in ENTRIES)
    spent = sum(e.amount for e in EXPENSES)
    pockets = [NEC, AHO]
    assert integrity_gap(income, 0, pockets, ENTRIES) == 0
    assert integrity_gap(income, spent, pockets, ENTRIES, EXPENSES) == 0
    assert integrity_gap(income + 1, spent, pockets, ENTRIES, EXPENSES) == 1
    assert integrity_gap(income, spent + 1, pockets, ENTRIES, EXPENSES) == -1


def test_invariante_con_gasto_en_un_mes_sin_asignacion():
    expenses = [*EXPENSES, ExpenseEntry(1, Month(2027, 3), 1_234)]
    income = sum(e.amount for e in ENTRIES)
    spent = sum(e.amount for e in expenses)
    assert integrity_gap(income, spent, [NEC, AHO], ENTRIES, expenses) == 0
