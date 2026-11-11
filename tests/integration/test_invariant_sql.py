"""Invariante de integridad (11.4) contra Postgres con conjuntos sintéticos (regla no negociable 3).

El lado izquierdo se consulta directamente sobre `incomes`; el derecho sale de los saldos que
calcula la aplicación a partir de `income_allocations`.
"""

import pytest

from puro_pockets.db.budget_store import SqlBudgetStore
from puro_pockets.domain.balances import integrity_gap
from puro_pockets.services.budget import BudgetService
from tests.synthetic import TODAY, datasets, record_incomes

from .conftest import reset_budget

pytestmark = [pytest.mark.integration, pytest.mark.anyio]

# Cada conjunto reinicia las tablas: se usa una muestra; los 200 completos corren en memoria
SQL_DATASETS = 40


async def test_invariante_con_conjuntos_sinteticos_en_postgres(budget_engine, _session_database):
    _, name = _session_database
    store = SqlBudgetStore(budget_engine)
    for dataset in datasets(SQL_DATASETS):
        reset_budget(budget_engine, name, dataset.pockets)
        service = BudgetService(store, today=lambda: TODAY)
        await service.load_initial_balance(list(dataset.initial), confirm=True)
        record_incomes(store, dataset)
        gap = integrity_gap(
            store.distributed_income_total(), store.list_pockets(), store.allocation_entries()
        )
        assert gap == 0, f"El invariante no cuadra: semilla={dataset.seed} diferencia={gap}"
