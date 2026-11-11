"""Invariante de integridad (11.4) contra Postgres con conjuntos sintéticos (regla no negociable 3).

El lado izquierdo se consulta directamente sobre `incomes` y `expenses` (sumas en SQL); el derecho
sale de los saldos que calcula la aplicación a partir de `income_allocations` y de cada gasto.
Cubre salarios en CRC y USD, gastos, sobregastos y anulaciones.
"""

import pytest

from puro_pockets.db.ledger_store import SqlLedgerStore
from puro_pockets.domain.balances import integrity_gap
from tests.synthetic import apply, datasets

from .conftest import reset_budget

pytestmark = [pytest.mark.integration, pytest.mark.anyio]

# Cada conjunto reinicia las tablas: se usa una muestra; los 200 completos corren en memoria
SQL_DATASETS = 40


async def test_invariante_con_conjuntos_sinteticos_en_postgres(budget_engine, _session_database):
    _, name = _session_database
    store = SqlLedgerStore(budget_engine)
    for dataset in datasets(SQL_DATASETS):
        reset_budget(budget_engine, name, dataset.pockets)
        await apply(store, dataset)
        gap = integrity_gap(
            store.distributed_income_total(),
            store.expense_total(),
            store.list_pockets(),
            store.allocation_entries(),
            store.expense_entries(),
        )
        assert gap == 0, f"El invariante no cuadra: semilla={dataset.seed} diferencia={gap}"
