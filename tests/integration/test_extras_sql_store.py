"""Extras y gastos fijos contra Postgres real, en la base temporal (Hito 6; datos sintéticos)."""

import threading
from datetime import date

import anyio
import pytest
from sqlalchemy import text

from puro_pockets.db.ledger_store import SqlLedgerStore
from puro_pockets.domain.balances import integrity_gap
from puro_pockets.domain.errors import (
    DomainError,
    ExtraAlreadyDistributed,
    RecurringAlreadyPaid,
    RecurringNameTaken,
)
from puro_pockets.domain.money import RateRange
from puro_pockets.domain.months import Month
from puro_pockets.services.ledger import LedgerService

pytestmark = [pytest.mark.integration, pytest.mark.anyio]

TODAY = date(2026, 11, 10)


@pytest.fixture
def store(budget_engine):
    return SqlLedgerStore(budget_engine)


@pytest.fixture
def ledger(store):
    return LedgerService(store, today=lambda: TODAY, rate_range=RateRange(300, 1000))


def _rows(engine, sql):
    with engine.connect() as conn:
        return [tuple(r) for r in conn.execute(text(sql)).all()]


def _gap(store):
    return integrity_gap(
        store.distributed_income_total(),
        store.expense_total(),
        store.list_pockets(),
        store.allocation_entries(),
        store.expense_entries(),
    )


async def _distribute(ledger, ref, shares, op):
    preview = await ledger.confirm_allocation(ref, shares)
    return await ledger.confirm_allocation(
        ref, shares, confirm=True, operation_id=op, preview_token=preview.preview_token
    )


async def test_extra_pendiente_y_reparto_atomico(ledger, store, budget_engine):
    extra = await ledger.register_extra_income(
        "80.00", "sql-extra-01", currency="USD", exchange_rate="512.34", source="venta sintética"
    )
    assert _rows(
        budget_engine,
        "SELECT kind, budget_month, allocation_status, currency, original_amount, amount, source "
        "FROM incomes",
    ) == [("extra", "2026-11", "pendiente", "USD", 8_000, 40_987, "venta sintética")]
    assert store.distributed_income_total() == 0 and _gap(store) == 0
    assert [r.id for r in store.pending_extras()] == [1]

    await _distribute(ledger, extra.reference, [("Ahorro", 60), ("Gustos", 40)], "sql-reparto-1")
    assert _rows(budget_engine, "SELECT allocation_status FROM incomes") == [("repartido",)]
    assert _rows(
        budget_engine, "SELECT pocket_id, percentage, amount FROM income_allocations ORDER BY 1"
    ) == [(2, 60, 24_592), (3, 40, 16_395)]
    assert store.distributed_income_total() == 40_987 and _gap(store) == 0
    assert store.extra_income_total(Month(2026, 11)) == 40_987

    await ledger.void_transaction(extra.reference, "monto mal", "sql-void-ex1", confirm=True)
    assert store.allocation_entries() == [] and _gap(store) == 0


def test_dos_confirmaciones_simultaneas_con_claves_distintas_reparten_una_vez(
    ledger, budget_engine
):
    extra = anyio.run(lambda: ledger.register_extra_income(50_000, "sql-extra-02"))
    shares = [("Ahorro", 100)]
    token = anyio.run(lambda: ledger.confirm_allocation(extra.reference, shares)).preview_token
    barrier = threading.Barrier(2)
    outcomes = []

    def call(op: str) -> None:
        barrier.wait()
        try:
            outcomes.append(
                anyio.run(
                    lambda: ledger.confirm_allocation(
                        extra.reference, shares, confirm=True, operation_id=op, preview_token=token
                    )
                )
            )
        except ExtraAlreadyDistributed as exc:
            outcomes.append(exc)

    threads = [threading.Thread(target=call, args=(f"sql-carrera-r{i}",)) for i in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    assert sorted(type(o).__name__ for o in outcomes) == [
        "ExtraAllocationResult",
        "ExtraAlreadyDistributed",
    ]
    assert _rows(budget_engine, "SELECT count(*) FROM income_allocations") == [(1,)]


def test_dos_pagos_simultaneos_del_mismo_fijo_uno_solo(ledger, budget_engine):
    anyio.run(
        lambda: ledger.manage_recurring(
            "crear",
            "sql-fijo-001",
            name="Alquiler sintético",
            amount=300_000,
            day_of_month=1,
            pocket="Necesidades",
        )
    )
    barrier = threading.Barrier(2)
    outcomes = []

    def call(op: str) -> None:
        barrier.wait()
        try:
            outcomes.append(anyio.run(lambda: ledger.add_expense(operation_id=op, recurring="F-1")))
        except RecurringAlreadyPaid as exc:
            outcomes.append(exc)

    threads = [threading.Thread(target=call, args=(f"sql-carrera-p{i}",)) for i in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    assert sorted(type(o).__name__ for o in outcomes) == ["ExpenseResult", "RecurringAlreadyPaid"]
    assert _rows(budget_engine, "SELECT count(*) FROM expenses WHERE recurring_id = 1") == [(1,)]


async def test_plantillas_historial_de_monto_y_desactivacion(ledger, store, budget_engine):
    await ledger.manage_recurring(
        "crear",
        "sql-fijo-002",
        name="Nube sintética",
        amount="12.50",
        currency="USD",
        day_of_month=31,
        pocket="Gustos",
    )
    with pytest.raises(RecurringNameTaken):
        await ledger.manage_recurring(
            "crear",
            "sql-fijo-003",
            name="NUBE sintética",
            amount=1,
            day_of_month=1,
            pocket="Gustos",
        )
    await ledger.manage_recurring("actualizar", "sql-fijo-004", recurring="F-1", amount="15.00")
    await ledger.manage_recurring("actualizar", "sql-fijo-005", recurring="F-1", amount="16.00")
    assert _rows(
        budget_engine,
        "SELECT from_month, original_amount FROM recurring_expense_amounts ORDER BY 1",
    ) == [("2026-11", 1_250), ("2026-12", 1_600)]  # el mismo mes futuro se reemplaza
    nov = (await ledger.list_pending_recurring()).pending[0]
    assert nov.amount == "12.50" and nov.due_date == "2026-11-30"
    with pytest.raises(DomainError, match="Falta el tipo de cambio"):
        await ledger.add_expense(operation_id="sql-pago-001", recurring="F-1")
    paid = await ledger.add_expense(
        operation_id="sql-pago-002", recurring="F-1", exchange_rate="500.00"
    )
    assert paid.amount_crc == 6_250
    assert _rows(budget_engine, "SELECT recurring_id, currency, original_amount FROM expenses") == [
        (1, "USD", 1_250)
    ]
    await ledger.manage_recurring("desactivar", "sql-fijo-006", recurring="F-1")
    assert _rows(
        budget_engine, "SELECT active, deactivated_at IS NOT NULL FROM recurring_expenses"
    ) == [(False, True)]
    assert [t.active for t in store.list_recurring()] == [False]
    assert _gap(store) == 0
