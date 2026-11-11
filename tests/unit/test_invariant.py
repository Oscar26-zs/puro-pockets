"""Invariante de integridad (sección 11.4) con 200 conjuntos sintéticos, en memoria.

Gobernanza, regla no negociable 3. Desde el Hito 5 cubre salarios en CRC y USD, gastos, sobregastos
y anulaciones (incluido el saldo inicial y su nueva carga); desde el Hito 6, extras pendientes
(fuera), repartidos (dentro) y anulados (revierten), y pagos de gastos fijos. La versión contra
Postgres está en tests/integration/test_invariant_sql.py.
"""

import pytest

from puro_pockets.domain.balances import IncomeKind, integrity_gap
from puro_pockets.domain.pockets import Pocket
from tests.fakes import InMemoryLedgerStore
from tests.synthetic import DATASETS, apply, datasets

pytestmark = pytest.mark.anyio


async def _load(dataset):
    pockets = [Pocket(i + 1, name, behavior) for i, (name, behavior) in enumerate(dataset.pockets)]
    store = InMemoryLedgerStore(pockets)
    await apply(store, dataset)
    return store


def _gap(store, expenses=None):
    return integrity_gap(
        store.distributed_income_total(),
        store.expense_total(),
        store.list_pockets(),
        store.allocation_entries(),
        store.expense_entries() if expenses is None else expenses,
    )


async def test_invariante_con_200_conjuntos_sinteticos():
    all_sets = datasets()
    assert len(all_sets) == DATASETS == 200
    usd = voids = reloads = expenses = 0
    pending = distributed = voided_extras = payments = repaid = 0
    for dataset in all_sets:
        store = await _load(dataset)
        assert _gap(store) == 0, f"El invariante no cuadra: semilla={dataset.seed}"
        usd += sum(r.currency.value == "USD" for r in [*store.incomes, *store.expenses])
        voids += sum(r.voided for r in [*store.incomes, *store.expenses])
        reloads += dataset.reload_initial is not None
        expenses += len(store.expenses)
        extras = [r for r in store.incomes if r.kind is IncomeKind.EXTRA]
        pending += sum(r.pending and not r.voided for r in extras)
        distributed += sum(not r.pending and not r.voided for r in extras)
        voided_extras += sum(r.voided for r in extras)
        payments += sum(e.recurring_id is not None for e in store.expenses)
        repaid += sum(e.recurring_id is not None and e.voided for e in store.expenses)
    # Los conjuntos ejercitan de verdad lo que agregan los Hitos 5 y 6
    assert usd > 50 and voids > 50 and reloads > 20 and expenses > 500
    assert pending > 50 and distributed > 80 and voided_extras > 40
    assert payments > 300 and repaid > 40


async def test_los_extras_pendientes_quedan_fuera_del_invariante():
    dataset = next(d for d in datasets(40) if any(e.shares is None for e in d.extras))
    store = await _load(dataset)
    pending = sum(r.amount for r in store.pending_extras())
    assert pending > 0, f"semilla={dataset.seed}"
    # Si un pendiente contara como repartido, el invariante dejaría de cuadrar (RN-06)
    counted = integrity_gap(
        store.distributed_income_total() + pending,
        store.expense_total(),
        store.list_pockets(),
        store.allocation_entries(),
        store.expense_entries(),
    )
    assert counted == pending


async def test_la_prueba_detecta_un_reparto_que_no_suma_el_ingreso():
    dataset = datasets(1)[0]
    store = await _load(dataset)
    index = next(i for i, (iid, _) in enumerate(store.lines) if not store.get_income(iid).voided)
    income_id, line = store.lines[index]
    store.lines[index] = (income_id, type(line)(line.pocket_id, line.percentage, line.amount + 1))
    assert _gap(store) == -1


async def test_la_prueba_detecta_un_gasto_que_no_resta_de_ninguna_bolsa():
    dataset = next(d for d in datasets(20) if d.expenses)
    store = await _load(dataset)
    entries = store.expense_entries()
    assert entries, f"semilla={dataset.seed}"
    assert _gap(store, entries[1:]) == -entries[0].amount
