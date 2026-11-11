"""Movimientos contra Postgres real, en la base temporal (Hito 5; datos sintéticos)."""

import threading
from datetime import date

import anyio
import pytest
from sqlalchemy import text

from puro_pockets.db.ledger_store import SqlLedgerStore
from puro_pockets.domain.errors import DomainError, IdempotencyConflict
from puro_pockets.domain.money import RateRange
from puro_pockets.domain.months import Month
from puro_pockets.services.budget import BudgetService
from puro_pockets.services.ledger import LedgerService

pytestmark = [pytest.mark.integration, pytest.mark.anyio]

TODAY = date(2026, 11, 10)
P_50_30_20 = {1: 50, 2: 30, 3: 20}


@pytest.fixture
def store(budget_engine):
    return SqlLedgerStore(budget_engine)


@pytest.fixture
def ledger(store):
    return LedgerService(store, today=lambda: TODAY, rate_range=RateRange(300, 1000))


@pytest.fixture
def budget(store):
    return BudgetService(store, today=lambda: TODAY)


def _rows(engine, sql):
    with engine.connect() as conn:
        return [tuple(r) for r in conn.execute(text(sql)).all()]


def _count(engine, table):
    return _rows(engine, f"SELECT count(*) FROM {table}")[0][0]


async def test_salario_atomico_con_porcentaje_guardado(ledger, store, budget_engine):
    store.replace_allocation(Month(2026, 12), P_50_30_20)
    result = await ledger.add_income(
        "1000.00", currency="USD", exchange_rate="512.34", confirm=True, operation_id="sql-inc-1"
    )
    assert result.reference == "I-1" and result.amount_crc == 512_340
    assert _rows(
        budget_engine,
        "SELECT kind, budget_month, currency, original_amount, exchange_rate, amount, voided "
        "FROM incomes",
    ) == [("base", "2026-12", "USD", 100_000, 51_234, 512_340, False)]
    assert _rows(
        budget_engine, "SELECT pocket_id, percentage, amount FROM income_allocations ORDER BY 1"
    ) == [(1, 50, 256_170), (2, 30, 153_702), (3, 20, 102_468)]
    stored = _rows(budget_engine, "SELECT tool, response->>'reference' FROM idempotency_keys")
    assert stored == [("add_income", "I-1")]


async def test_sin_porcentajes_no_guarda_nada(ledger, budget_engine):
    with pytest.raises(DomainError, match="set_allocation"):
        await ledger.add_income(1_000, confirm=True, operation_id="sql-inc-2")
    assert _count(budget_engine, "incomes") == 0 and _count(budget_engine, "idempotency_keys") == 0


async def test_gasto_categoria_sobregasto_y_listado(ledger, budget_engine):
    await ledger.create_category("Súper", "Necesidades")
    with pytest.raises(DomainError, match="Ya existe"):
        await ledger.create_category("SÚPER", "Gustos")
    result = await ledger.add_expense(
        "19.87",
        "sql-exp-1",
        category="súper",
        currency="USD",
        exchange_rate="611.23",
        description="compra sintética",
    )
    assert (result.pocket, result.category, result.amount_crc, result.overspent) == (
        "Necesidades",
        "Súper",
        12_145,
        True,
    )
    assert _rows(
        budget_engine,
        "SELECT month, currency, original_amount, exchange_rate, amount, description FROM expenses",
    ) == [("2026-11", "USD", 1_987, 61_123, 12_145, "compra sintética")]
    listing = await ledger.list_transactions()
    assert [i.reference for i in listing.items] == ["G-1"]
    top = await ledger.top_categories()
    assert [(i.category, i.amount_crc) for i in top.items] == [("Súper", 12_145)]


async def test_anular_y_recargar_el_saldo_inicial(ledger, budget, budget_engine):
    await budget.load_initial_balance([("Ahorro", 5_000)], confirm=True)
    voided = await ledger.void_transaction("I-1", "monto mal cargado", "sql-void-1", confirm=True)
    assert voided.movement == "saldo_inicial" and voided.initial_balance_reloadable
    await budget.load_initial_balance([("Ahorro", 7_000)], confirm=True)
    assert _rows(budget_engine, "SELECT id, voided, void_reason FROM incomes ORDER BY id") == [
        (1, True, "monto mal cargado"),
        (2, False, None),
    ]
    listing = await budget.list_pockets()
    assert [b.balance for b in listing.pockets if b.pocket.name == "Ahorro"] == [7_000]
    with pytest.raises(DomainError, match="ya está anulado"):
        await ledger.void_transaction("I-1", "otra vez", "sql-void-2", confirm=True)


async def test_anular_salario_revierte_sin_borrar(ledger, store, budget_engine):
    store.replace_allocation(Month(2026, 11), P_50_30_20)
    await ledger.add_income(100_000, budget_month="2026-11", confirm=True, operation_id="sql-inc-3")
    await ledger.add_expense(30_000, "sql-exp-2", pocket="Gustos")
    result = await ledger.void_transaction("i-1", "salario repetido", "sql-void-3", confirm=True)
    assert [(p.pocket, p.balance) for p in result.negative_pockets] == [("Gustos", -30_000)]
    assert _count(budget_engine, "income_allocations") == 3  # nada se borra
    status = await ledger.get_bolsa_status("Gustos")
    assert (status.assigned, status.spent, status.available) == (0, 30_000, -30_000)


async def test_idempotencia_en_la_base(ledger, budget_engine):
    first = await ledger.add_expense(4_000, "sql-idem-1", pocket="Gustos")
    again = await ledger.add_expense(4_000, "sql-idem-1", pocket="gustos")
    assert again == first and _count(budget_engine, "expenses") == 1
    with pytest.raises(IdempotencyConflict):
        await ledger.add_expense(4_001, "sql-idem-1", pocket="Gustos")


def test_dos_llamadas_simultaneas_con_la_misma_clave_un_solo_gasto(ledger, budget_engine):
    barrier = threading.Barrier(2)
    results = []

    def call() -> None:
        barrier.wait()
        results.append(
            anyio.run(lambda: ledger.add_expense(6_500, "sql-carrera-1", pocket="Gustos"))
        )

    threads = [threading.Thread(target=call) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    assert len(results) == 2 and results[0] == results[1]
    assert _count(budget_engine, "expenses") == 1
    assert _count(budget_engine, "idempotency_keys") == 1
