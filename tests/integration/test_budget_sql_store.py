"""Presupuesto contra Postgres real, en la base temporal (US1 a US3; datos sintéticos)."""

import threading
from datetime import date

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from puro_pockets.db.budget_store import SqlBudgetStore
from puro_pockets.domain.balances import IncomeKind
from puro_pockets.domain.errors import DomainError, InitialBalanceAlreadyLoaded
from puro_pockets.domain.months import Month
from puro_pockets.services.budget import AllocationLine, BudgetService

pytestmark = [pytest.mark.integration, pytest.mark.anyio]

TODAY = date(2026, 11, 10)
P_50_30_20 = [("Necesidades", 50), ("Ahorro", 30), ("Gustos", 20)]
SYNTH = [("Necesidades", 104_729), ("Gustos", 56_311), ("Ahorro", 523_717)]


@pytest.fixture
def store(budget_engine):
    return SqlBudgetStore(budget_engine)


@pytest.fixture
def service(store):
    return BudgetService(store, today=lambda: TODAY)


def _count(engine, table):
    with engine.connect() as conn:
        return conn.execute(text(f"SELECT count(*) FROM {table}")).scalar()


async def test_definir_reemplazar_y_no_alterar_otros_meses(service, budget_engine):
    await service.set_allocation(P_50_30_20, "2026-11")
    await service.set_allocation([("Necesidades", 40), ("Ahorro", 40), ("Gustos", 20)], "2026-12")
    await service.set_allocation([("Necesidades", 45), ("Ahorro", 35), ("Gustos", 20)], "2026-12")
    nov = await service.get_allocation("2026-11")
    dec = await service.get_allocation("2026-12")
    assert [pct for _, pct in nov.items] == [50, 30, 20]  # RN-02
    assert [pct for _, pct in dec.items] == [45, 35, 20]  # reemplazo del mes
    assert _count(budget_engine, "budget_month_allocations") == 6


async def test_rechazo_no_guarda_nada(service, budget_engine):
    with pytest.raises(DomainError, match="suman 110"):
        await service.set_allocation([("Necesidades", 50), ("Ahorro", 30), ("Gustos", 30)])
    with pytest.raises(DomainError, match="mes pasado"):
        await service.set_allocation(P_50_30_20, "2026-10")
    assert _count(budget_engine, "budget_month_allocations") == 0


async def test_herencia_sin_escribir(service, budget_engine):
    assert not (await service.get_allocation()).defined
    await service.set_allocation(P_50_30_20)
    inherited = await service.get_allocation("2027-04")
    assert inherited.source_month == Month(2026, 11)
    assert [pct for _, pct in inherited.items] == [50, 30, 20]
    assert _count(budget_engine, "budget_month_allocations") == 3  # RN-03 no guarda nada


async def test_vista_previa_carga_atomica_y_listado(service, budget_engine):
    preview = await service.preview_initial_balance(SYNTH)
    unconfirmed = await service.load_initial_balance(SYNTH)
    assert not preview.saved and not unconfirmed.saved
    assert _count(budget_engine, "incomes") == 0

    await service.load_initial_balance(SYNTH, confirm=True)
    with budget_engine.connect() as conn:
        income = conn.execute(
            text("SELECT kind, budget_month, amount, allocation_status FROM incomes")
        ).one()
        lines = conn.execute(
            text("SELECT percentage, amount FROM income_allocations ORDER BY pocket_id")
        ).all()
    assert tuple(income) == ("saldo_inicial", "2026-11", 684_757, "repartido")
    assert [tuple(r) for r in lines] == [(None, 104_729), (None, 523_717), (None, 56_311)]

    listing = await service.list_pockets()
    assert [(b.pocket.name, b.balance) for b in listing.pockets] == [
        ("Necesidades", 104_729),
        ("Ahorro", 523_717),
        ("Gustos", 56_311),
    ]


async def test_segunda_carga_rechazada(service, budget_engine):
    await service.load_initial_balance(SYNTH, confirm=True)
    with pytest.raises(InitialBalanceAlreadyLoaded):
        await service.load_initial_balance([("Ahorro", 1)], confirm=True)
    assert _count(budget_engine, "incomes") == 1


def test_dos_cargas_simultaneas_solo_una_se_guarda(store, budget_engine):
    ids = [p.id for p in store.list_pockets()]
    lines = [AllocationLine(pid, None, 1_000 + pid) for pid in ids]
    barrier = threading.Barrier(2)
    outcomes: list[str] = []

    def load() -> None:
        barrier.wait()
        try:
            store.record_distributed_income(
                IncomeKind.INITIAL_BALANCE, TODAY, Month(2026, 11), lines
            )
            outcomes.append("ok")
        except InitialBalanceAlreadyLoaded:
            outcomes.append("rechazada")

    threads = [threading.Thread(target=load) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    assert sorted(outcomes) == ["ok", "rechazada"]
    assert _count(budget_engine, "incomes") == 1
    assert _count(budget_engine, "income_allocations") == len(ids)  # sin repartos huérfanos


def test_nombre_de_bolsa_unico_sin_distinguir_mayusculas(budget_engine):
    with pytest.raises(IntegrityError), budget_engine.begin() as conn:
        conn.execute(text("INSERT INTO pockets (name, behavior) VALUES ('gUsToS', 'consumo')"))
