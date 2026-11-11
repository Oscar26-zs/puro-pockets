"""Bolsas flexibles y metas contra Postgres real, en la base temporal (Hito 7; datos sintéticos)."""

import threading
from datetime import date

import anyio
import pytest
from sqlalchemy import text

from puro_pockets.db.ledger_store import SqlLedgerStore
from puro_pockets.domain.balances import integrity_gap
from puro_pockets.domain.errors import GoalAlreadyActive, PocketAlreadyExists
from puro_pockets.domain.money import RateRange
from puro_pockets.domain.months import Month
from puro_pockets.services.ledger import LedgerService

pytestmark = [pytest.mark.integration, pytest.mark.anyio]

TODAY = date(2026, 11, 11)
NOV = Month(2026, 11)


@pytest.fixture
def store(budget_engine):
    store = SqlLedgerStore(budget_engine)
    store.replace_allocation(NOV, {1: 50, 2: 30, 3: 20})
    return store


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


async def _create(ledger, name, share, op, **kw):
    preview = await ledger.create_bolsa(name, "acumulable", percentage=share, **kw)
    return await ledger.create_bolsa(
        name,
        "acumulable",
        percentage=share,
        confirm=True,
        operation_id=op,
        preview_token=preview.preview_token,
        **kw,
    )


async def test_crear_bolsa_atomica_con_sus_porcentajes(ledger, store, budget_engine):
    await _create(ledger, "Emergencia", 10, "sql-bolsa-001")
    assert _rows(budget_engine, "SELECT name, behavior, active FROM pockets WHERE id = 4") == [
        ("Emergencia", "acumulable", True)
    ]
    assert _rows(
        budget_engine,
        "SELECT pocket_id, percentage FROM budget_month_allocations WHERE month = '2026-12' "
        "ORDER BY 1",
    ) == [
        (
            1,
            45,
        ),
        (2, 27),
        (3, 18),
        (4, 10),
    ]
    with pytest.raises(PocketAlreadyExists):
        await _create(ledger, "EMERGENCIA", 0, "sql-bolsa-002")
    assert _rows(budget_engine, "SELECT count(*) FROM pockets") == [(4,)]


async def test_archivar_reescribe_porcentajes_y_archiva_la_meta(ledger, store, budget_engine):
    await _create(ledger, "Viaje", 10, "sql-bolsa-003", month="2026-11")
    goal = await ledger.create_goal("Viaje", "Playa sintética", 300_000, "sql-meta-001")
    preview = await ledger.archive_bolsa("Viaje")
    await ledger.archive_bolsa(
        "Viaje", confirm=True, operation_id="sql-arch-001", preview_token=preview.preview_token
    )
    assert _rows(
        budget_engine, "SELECT active, archived_at IS NOT NULL FROM pockets WHERE id = 4"
    ) == [(False, True)]
    assert _rows(budget_engine, "SELECT archived_at IS NOT NULL FROM savings_goals") == [(True,)]
    rows = dict(
        _rows(
            budget_engine,
            "SELECT pocket_id, percentage FROM budget_month_allocations WHERE month = '2026-11'",
        )
    )
    assert 4 not in rows and sum(rows.values()) == 100
    assert goal.reference == "M-1"


async def test_meta_lograda_en_la_transaccion_del_ingreso(ledger, store, budget_engine):
    early = LedgerService(store, today=lambda: date(2026, 11, 1), rate_range=RateRange(300, 1000))
    await early.create_goal("Ahorro", "Viaje sintético", 500_000, "sql-meta-002")
    await ledger.add_income(
        2_000_000,
        income_date="2026-11-06",
        budget_month="2026-11",
        confirm=True,
        operation_id="sql-sal-001",
    )
    assert _rows(budget_engine, "SELECT status, achieved_on FROM savings_goals") == [
        ("lograda", date(2026, 11, 6))
    ]
    await ledger.add_expense(550_000, "sql-gasto-001", pocket="Ahorro")
    assert _rows(budget_engine, "SELECT status FROM savings_goals") == [("lograda",)]  # RN-24
    progress = (await ledger.get_goal_progress("Ahorro")).items[0]
    assert progress.balance == (await ledger.get_bolsa_status("Ahorro")).balance == 50_000
    assert _gap(store) == 0


def test_dos_metas_simultaneas_en_la_misma_bolsa_solo_una(ledger, budget_engine):
    barrier = threading.Barrier(2)
    outcomes = []

    def call(op: str) -> None:
        barrier.wait()
        try:
            outcomes.append(
                anyio.run(lambda: ledger.create_goal("Ahorro", f"Meta {op}", 100_000, op))
            )
        except GoalAlreadyActive as exc:
            outcomes.append(exc)

    threads = [threading.Thread(target=call, args=(f"sql-carrera-m{i}",)) for i in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    assert sorted(type(o).__name__ for o in outcomes) == ["GoalAlreadyActive", "GoalResult"]
    assert _rows(budget_engine, "SELECT count(*) FROM savings_goals") == [(1,)]
