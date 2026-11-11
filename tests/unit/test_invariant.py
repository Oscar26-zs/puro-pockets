"""Invariante de integridad (sección 11.4) con 200 conjuntos sintéticos, en memoria.

Gobernanza, regla no negociable 3: desde el primer hito que registra dinero. La versión contra
Postgres está en tests/integration/test_invariant_sql.py.
"""

import pytest

from puro_pockets.domain.balances import integrity_gap
from puro_pockets.domain.pockets import Pocket
from puro_pockets.services.budget import BudgetService
from tests.fakes import InMemoryBudgetStore
from tests.synthetic import DATASETS, TODAY, datasets, record_incomes

pytestmark = pytest.mark.anyio


async def _load(dataset):
    pockets = [Pocket(i + 1, name, behavior) for i, (name, behavior) in enumerate(dataset.pockets)]
    store = InMemoryBudgetStore(pockets)
    service = BudgetService(store, today=lambda: TODAY)
    await service.load_initial_balance(list(dataset.initial), confirm=True)
    record_incomes(store, dataset)
    return store


async def test_invariante_con_200_conjuntos_sinteticos():
    all_sets = datasets()
    assert len(all_sets) == DATASETS == 200
    for dataset in all_sets:
        store = await _load(dataset)
        gap = integrity_gap(
            store.distributed_income_total(), store.list_pockets(), store.allocation_entries()
        )
        assert gap == 0, f"El invariante no cuadra: semilla={dataset.seed} diferencia={gap}"


async def test_la_prueba_detecta_un_reparto_que_no_suma_el_ingreso():
    dataset = datasets(1)[0]
    store = await _load(dataset)
    income_id, line = store.lines[0]
    store.lines[0] = (income_id, type(line)(line.pocket_id, line.percentage, line.amount + 1))
    gap = integrity_gap(
        store.distributed_income_total(), store.list_pockets(), store.allocation_entries()
    )
    assert gap == -1
