"""Casos de uso del presupuesto con almacén en memoria (US1 a US3; datos sintéticos)."""

import logging
from datetime import date

import pytest

from puro_pockets.domain.balances import BalanceKind
from puro_pockets.domain.errors import DomainError, InitialBalanceAlreadyLoaded
from puro_pockets.domain.months import Month
from puro_pockets.services.budget import BudgetService
from tests.fakes import InMemoryBudgetStore

pytestmark = pytest.mark.anyio

TODAY = date(2026, 11, 10)
P_50_30_20 = [("Necesidades", 50), ("Ahorro", 30), ("Gustos", 20)]
# Montos sintéticos poco comunes, para buscarlos en los registros
SYNTH = [("Necesidades", 104_729), ("Gustos", 56_311), ("Ahorro", 523_717)]


@pytest.fixture
def store():
    return InMemoryBudgetStore()


@pytest.fixture
def service(store):
    return BudgetService(store, today=lambda: TODAY)


def _pcts(resolved):
    return [(p.name, pct) for p, pct in resolved.items]


# --- US1 ---


async def test_definir_y_consultar_el_mes_actual(service):
    saved = await service.set_allocation(P_50_30_20)
    assert saved.month == Month(2026, 11) and saved.source_month == Month(2026, 11)
    got = await service.get_allocation("2026-11")
    assert _pcts(got) == [("Necesidades", 50), ("Ahorro", 30), ("Gustos", 20)]


async def test_suma_distinta_de_100_no_guarda_nada(service, store):
    with pytest.raises(DomainError, match="suman 110"):
        await service.set_allocation([("Necesidades", 50), ("Ahorro", 30), ("Gustos", 30)])
    assert store.writes == 0 and store.allocations == {}


async def test_mes_pasado_rechazado_aunque_no_tuviera_porcentajes(service, store):
    with pytest.raises(DomainError, match="mes pasado"):
        await service.set_allocation(P_50_30_20, "2026-10")
    assert store.writes == 0


async def test_mes_futuro_y_formato_invalido(service):
    await service.set_allocation(P_50_30_20, "2027-03")
    with pytest.raises(DomainError, match="AAAA-MM"):
        await service.set_allocation(P_50_30_20, "2027-3")


async def test_reemplaza_los_del_mismo_mes(service):
    await service.set_allocation(P_50_30_20)
    await service.set_allocation([("Necesidades", 60), ("Ahorro", 30), ("Gustos", 10)])
    assert _pcts(await service.get_allocation()) == [
        ("Necesidades", 60),
        ("Ahorro", 30),
        ("Gustos", 10),
    ]


# --- US2 ---


async def test_cambiar_el_mes_siguiente_no_altera_el_anterior(service):
    await service.set_allocation(P_50_30_20, "2026-11")
    await service.set_allocation([("Necesidades", 40), ("Ahorro", 40), ("Gustos", 20)], "2026-12")
    assert _pcts(await service.get_allocation("2026-11"))[0] == ("Necesidades", 50)
    assert _pcts(await service.get_allocation("2026-12"))[0] == ("Necesidades", 40)


async def test_hereda_sin_guardar_nada(service, store):
    await service.set_allocation(P_50_30_20)
    writes = store.writes
    got = await service.get_allocation("2027-02")
    assert got.source_month == Month(2026, 11) and _pcts(got)[0] == ("Necesidades", 50)
    assert store.writes == writes and Month(2027, 2) not in store.allocations


async def test_sin_porcentajes_definidos(service):
    got = await service.get_allocation()
    assert not got.defined and got.items == ()


# --- US3 ---


async def test_vista_previa_no_guarda_nada(service, store):
    view = await service.preview_initial_balance(SYNTH)
    assert view.total == 684_757 and not view.already_loaded and not view.saved
    assert [(p.name, a) for p, a in view.items] == [
        ("Necesidades", 104_729),
        ("Ahorro", 523_717),
        ("Gustos", 56_311),
    ]
    assert store.writes == 0


async def test_sin_confirm_solo_vista_previa(service, store):
    view = await service.load_initial_balance(SYNTH)
    assert not view.saved and store.writes == 0


async def test_carga_y_listado_de_bolsas(service):
    view = await service.load_initial_balance(SYNTH, confirm=True)
    assert view.saved and view.month == Month(2026, 11)
    listing = await service.list_pockets()
    assert [(b.pocket.name, b.balance, b.kind) for b in listing.pockets] == [
        ("Necesidades", 104_729, BalanceKind.MONTH_AVAILABLE),
        ("Ahorro", 523_717, BalanceKind.BALANCE),
        ("Gustos", 56_311, BalanceKind.MONTH_AVAILABLE),
    ]


async def test_segunda_carga_rechazada(service, store):
    await service.load_initial_balance(SYNTH, confirm=True)
    with pytest.raises(InitialBalanceAlreadyLoaded):
        await service.load_initial_balance([("Ahorro", 1)], confirm=True)
    assert (await service.preview_initial_balance([("Ahorro", 1)])).already_loaded
    assert len(store.incomes) == 1


async def test_en_el_mes_siguiente_consumo_empieza_en_cero(store):
    await BudgetService(store, today=lambda: TODAY).load_initial_balance(SYNTH, confirm=True)
    december = BudgetService(store, today=lambda: date(2026, 12, 1))
    balances = {b.pocket.name: b.balance for b in (await december.list_pockets()).pockets}
    assert balances == {"Necesidades": 0, "Ahorro": 523_717, "Gustos": 0}


async def test_los_registros_no_incluyen_montos(service, caplog):
    caplog.set_level(logging.DEBUG)
    await service.preview_initial_balance(SYNTH)
    await service.load_initial_balance(SYNTH, confirm=True)
    with pytest.raises(InitialBalanceAlreadyLoaded):
        await service.load_initial_balance(SYNTH, confirm=True)
    await service.list_pockets()
    text = caplog.text.replace(".", "").replace(",", "")
    assert "Saldo inicial cargado" in caplog.text
    for amount in ("104729", "56311", "523717", "684757"):
        assert amount not in text
