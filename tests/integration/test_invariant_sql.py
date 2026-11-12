"""Invariante de integridad (11.4) contra Postgres con conjuntos sintéticos (regla no negociable 3).

El lado izquierdo se consulta directamente sobre `incomes` y `expenses` (sumas en SQL); el derecho
sale de los saldos que calcula la aplicación a partir de `income_allocations` y de cada gasto.
Cubre salarios en CRC y USD, gastos, sobregastos y anulaciones, extras, gastos fijos, bolsas
nuevas, metas, archivados, transferencias (Hito 8) y cierres de mes (Hito 9: disponibles solo de los
meses abiertos más los ajustes de cierre).
"""

import pytest

from puro_pockets.db.ledger_store import SqlLedgerStore
from puro_pockets.domain.balances import integrity_gap
from puro_pockets.domain.closures import is_closed
from tests.synthetic import apply, apply_closures, datasets

from .conftest import reset_budget

pytestmark = [pytest.mark.integration, pytest.mark.anyio]

# Cada conjunto reinicia las tablas: se usa una muestra; los 200 completos corren en memoria
SQL_DATASETS = 40


async def test_invariante_con_conjuntos_sinteticos_en_postgres(budget_engine, _session_database):
    _, name = _session_database
    store = SqlLedgerStore(budget_engine)
    closed_months = 0
    for dataset in datasets(SQL_DATASETS):
        reset_budget(budget_engine, name, dataset.pockets)
        await apply(store, dataset)
        counts = await apply_closures(store, dataset)
        closed_months += counts["closed"]
        closed = store.closure_state().closed
        gap = integrity_gap(
            store.distributed_income_total(),
            store.expense_total(),
            store.list_pockets(),
            store.allocation_entries(),
            store.expense_entries(),
            store.transfer_entries(),
            lambda month, closed=closed: is_closed(month, closed),
            sum(a.amount for a in store.closure_adjustments(None)),
        )
        assert gap == 0, f"El invariante no cuadra: semilla={dataset.seed} diferencia={gap}"
    assert closed_months > 40
