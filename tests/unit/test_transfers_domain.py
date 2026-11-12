"""Dominio de las transferencias (Hito 8): cálculos 9.1/11.1/11.2, validaciones y RN-58.

Datos sintéticos. Incluye pruebas de propiedades con semilla fija (se imprime al fallar).
"""

import random
from datetime import date

import pytest

from puro_pockets.domain.balances import (
    AllocationEntry,
    ExpenseEntry,
    TransferEntry,
    accumulated_balance,
    consumption_available,
    integrity_gap,
    pocket_figures,
)
from puro_pockets.domain.errors import (
    DomainError,
    TransferExceedsAvailable,
    TransferFromNegative,
    TransferSamePocket,
    TransfersAreFinal,
)
from puro_pockets.domain.goals import Goal, GoalStatus, net_monthly_change
from puro_pockets.domain.ledger import MovementRef
from puro_pockets.domain.months import Month
from puro_pockets.domain.pockets import Behavior, Pocket
from puro_pockets.domain.transfers import (
    MAX_NOTE,
    TransferReason,
    TransferRef,
    check_available,
    check_pockets,
    goal_effect,
    parse_reason,
    parse_transfer_amount,
    transfer_date,
    validate_note,
)

NOV, DEC = Month(2026, 11), Month(2026, 12)
NEC = Pocket(1, "Necesidades", Behavior.CONSUMO)
AHO = Pocket(2, "Ahorro", Behavior.ACUMULABLE)
GUS = Pocket(3, "Gustos", Behavior.CONSUMO)
TODAY = date(2026, 11, 11)
SEED = 20261111

ENTRIES = [
    AllocationEntry(1, NOV, 100_000),
    AllocationEntry(2, NOV, 300_000),
    AllocationEntry(3, NOV, 50_000),
    AllocationEntry(2, DEC, 40_000),
]
EXPENSES = [ExpenseEntry(1, NOV, 30_000), ExpenseEntry(3, NOV, 70_000)]
TRANSFERS = [TransferEntry(1, 3, NOV, 20_000), TransferEntry(2, 1, NOV, 5_000)]


# --- 9.1, 11.1, 11.2 con transferencias ---


def test_consumo_presupuesto_ajustado_y_disponible():
    f = pocket_figures(NEC, NOV, ENTRIES, EXPENSES, TRANSFERS)
    assert (f.assigned, f.transfers_in, f.transfers_out) == (100_000, 5_000, 20_000)
    assert f.adjusted_budget == 85_000  # 100 000 + 5 000 − 20 000 (9.1)
    assert f.available == 55_000 and f.balance is None  # 85 000 − 30 000 (11.1)
    assert f.percent_used == 35 and f.percent_used_original == 30  # sobre ajustado y original
    assert not f.negative and f.amount == 55_000


def test_gustos_en_negativo_vuelve_a_cero_con_una_transferencia():
    before = pocket_figures(GUS, NOV, ENTRIES, EXPENSES)
    assert before.available == -20_000 and before.negative
    after = pocket_figures(GUS, NOV, ENTRIES, EXPENSES, TRANSFERS[:1])
    assert after.available == 0 and not after.negative
    assert after.adjusted_budget == 70_000


def test_acumulable_el_saldo_incluye_todas_las_transferencias():
    f = pocket_figures(AHO, DEC, ENTRIES, EXPENSES, TRANSFERS)
    assert f.balance == 335_000  # 300 000 + 40 000 − 5 000 (11.2)
    assert f.available is None and f.percent_used is None
    assert accumulated_balance(ENTRIES, 2, EXPENSES, TRANSFERS) == 335_000


def test_las_transferencias_de_otro_mes_no_tocan_el_disponible_del_mes():
    moved = [TransferEntry(1, 3, DEC, 9_000)]
    assert consumption_available(ENTRIES, 1, NOV, EXPENSES, moved) == 70_000
    assert consumption_available(ENTRIES, 1, DEC, EXPENSES, moved) == -9_000


def test_propiedad_ajustado_es_asignado_mas_recibidas_menos_enviadas_e_invariante():
    """Con transferencias aleatorias: el ajustado de cada bolsa de consumo es asignado + recibidas
    − enviadas, y la suma de saldos y disponibles no cambia (11.4)."""
    rng = random.Random(SEED)
    pockets = [NEC, AHO, GUS]
    for case in range(500):
        entries = [
            AllocationEntry(rng.choice([1, 2, 3]), rng.choice([NOV, DEC]), rng.randint(0, 500_000))
            for _ in range(rng.randint(1, 8))
        ]
        expenses = [
            ExpenseEntry(rng.choice([1, 2, 3]), rng.choice([NOV, DEC]), rng.randint(1, 300_000))
            for _ in range(rng.randint(0, 6))
        ]
        income = sum(e.amount for e in entries)
        spent = sum(e.amount for e in expenses)
        assert integrity_gap(income, spent, pockets, entries, expenses) == 0
        moved = []
        for _ in range(rng.randint(1, 6)):
            a, b = rng.sample([1, 2, 3], 2)
            moved.append(TransferEntry(a, b, rng.choice([NOV, DEC]), rng.randint(1, 200_000)))
        message = f"semilla={SEED} caso={case}"
        assert integrity_gap(income, spent, pockets, entries, expenses, moved) == 0, message
        for pocket in (NEC, GUS):
            for month in (NOV, DEC):
                f = pocket_figures(pocket, month, entries, expenses, moved)
                incoming = sum(
                    t.amount for t in moved if t.to_pocket_id == pocket.id and t.month == month
                )
                outgoing = sum(
                    t.amount for t in moved if t.from_pocket_id == pocket.id and t.month == month
                )
                assert f.adjusted_budget == f.assigned + incoming - outgoing, message
                assert f.available == f.adjusted_budget - f.spent, message


# --- Validaciones ---


def test_motivos_permitidos_y_reservado():
    assert parse_reason("cubrir_sobregasto") is TransferReason.COVER_OVERSPEND
    assert parse_reason(" Reasignacion ") is TransferReason.REASSIGNMENT
    assert parse_reason("ajuste") is TransferReason.ADJUSTMENT
    with pytest.raises(DomainError, match="reservado"):
        parse_reason("cierre_de_mes")
    for bad in ("regalo", "", None, 3):
        with pytest.raises(DomainError, match="cubrir_sobregasto, reasignacion o ajuste"):
            parse_reason(bad)


def test_nota_hasta_140_y_nunca_en_el_error():
    assert validate_note(None) is None and validate_note("   ") is None
    assert validate_note("x" * MAX_NOTE) == "x" * MAX_NOTE
    secret = "nota secreta sintética " + "y" * 130
    with pytest.raises(DomainError) as exc:
        validate_note(secret)
    assert "secreta" not in exc.value.message and "140" in exc.value.message
    with pytest.raises(DomainError):
        validate_note(12)


@pytest.mark.parametrize("bad", [0, -1, -50_000, 1.5, 10_000.0, True, "100", None])
def test_monto_entero_positivo_y_sin_el_monto_en_el_error(bad):
    with pytest.raises(DomainError) as exc:
        parse_transfer_amount(bad)
    assert "50000" not in exc.value.message and "10000" not in exc.value.message


def test_monto_valido():
    assert parse_transfer_amount(1) == 1
    assert parse_transfer_amount(123_457) == 123_457


def test_fecha_solo_hoy():
    assert transfer_date(None, TODAY) == TODAY
    assert transfer_date("", TODAY) == TODAY
    assert transfer_date("2026-11-11", TODAY) == TODAY
    for bad in ("2026-11-10", "2026-11-12", "2025-01-01"):
        with pytest.raises(DomainError, match="fecha de hoy"):
            transfer_date(bad, TODAY)
    with pytest.raises(DomainError, match="AAAA-MM-DD"):
        transfer_date("11/11/2026", TODAY)


def test_referencia_t_n_y_no_se_anula_con_void():
    assert str(TransferRef.parse(" t - 7 ")) == "T-7"
    assert TransferRef.matches("T-3") and not TransferRef.matches("G-3")
    with pytest.raises(DomainError):
        TransferRef.parse("T-0")
    with pytest.raises(TransfersAreFinal, match="sentido contrario"):
        MovementRef.parse("T-3")  # void_transaction no admite transferencias (RN-43)


def test_origen_distinto_del_destino_y_bolsas_activas():
    with pytest.raises(TransferSamePocket):
        check_pockets(NEC, NEC)
    archived = Pocket(9, "Viaje", Behavior.CONSUMO, active=False)
    with pytest.raises(DomainError, match="archivada"):
        check_pockets(NEC, archived)
    with pytest.raises(DomainError, match="archivada"):
        check_pockets(archived, NEC)
    check_pockets(NEC, GUS)


def test_rn42_no_mas_de_lo_disponible_ni_desde_negativo():
    nec = pocket_figures(NEC, NOV, ENTRIES, EXPENSES, TRANSFERS)  # disponible 55 000
    check_available(nec, 55_000)  # exactamente lo disponible sí
    with pytest.raises(TransferExceedsAvailable, match="disponible del mes") as exc:
        check_available(nec, 55_001)
    assert "55" not in exc.value.message
    aho = pocket_figures(AHO, NOV, ENTRIES, EXPENSES, TRANSFERS)  # saldo histórico 335 000
    with pytest.raises(TransferExceedsAvailable, match="saldo"):
        check_available(aho, 335_001)
    gus = pocket_figures(GUS, NOV, ENTRIES, EXPENSES)  # −20 000
    with pytest.raises(TransferFromNegative, match="negativo"):
        check_available(gus, 1)


# --- RN-58 y RN-28 ---


def _goal(target=1_000_000):
    return Goal(1, 2, "Meta sintética", target, None, GoalStatus.ACTIVE, None, TODAY)


def test_efecto_en_la_meta_baja_y_se_completa():
    down = goal_effect(_goal(), 360_000, 300_000)
    assert (down.percent_before, down.percent_after) == (36, 30)
    assert down.message == "El avance de la meta M-1 baja de 36 % a 30 %." and not down.completes
    up = goal_effect(_goal(), 900_000, 1_000_000)
    assert up.completes and up.missing_after == 0 and "lograda" in up.message
    same = goal_effect(_goal(), 1_200_000, 1_100_000)  # ya pasaba el objetivo: tope de 100 %
    assert same.percent_before == same.percent_after == 100 and not same.completes
    assert "Meta sintética" not in down.message + up.message + same.message


def test_rn28_la_variacion_neta_incluye_las_transferencias():
    entries = [
        AllocationEntry(2, Month(2026, 9), 100_000),
        AllocationEntry(2, Month(2026, 10), 100_000),
    ]
    moved = [
        TransferEntry(2, 1, Month(2026, 10), 40_000),
        TransferEntry(1, 2, Month(2026, 9), 10_000),
    ]
    change = net_monthly_change(entries, [], 2, NOV, moved)
    assert change.months == 2 and change.average == (110_000 + 60_000) // 2
