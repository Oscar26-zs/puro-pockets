"""Invariante de integridad (sección 11.4) con 200 conjuntos sintéticos, en memoria.

Gobernanza, regla no negociable 3. Desde el Hito 5 cubre salarios en CRC y USD, gastos, sobregastos
y anulaciones (incluido el saldo inicial y su nueva carga); desde el Hito 6, extras pendientes
(fuera), repartidos (dentro) y anulados (revierten), y pagos de gastos fijos. La versión contra
Postgres está en tests/integration/test_invariant_sql.py.
"""

import pytest

from puro_pockets.domain.balances import (
    IncomeKind,
    accumulated_balance,
    consumption_available,
    integrity_gap,
)
from puro_pockets.domain.goals import progress
from puro_pockets.domain.months import Month
from puro_pockets.domain.pockets import Behavior, Pocket
from tests.fakes import InMemoryLedgerStore
from tests.synthetic import DATASETS, apply, apply_money, apply_structure, datasets

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


MONTHS = [Month(2026, m) for m in range(6, 13)] + [Month(2027, 1)]


def _snapshot(store):
    """Saldo de cada acumulable (11.2) y disponible de cada consumo en cada mes (11.1)."""
    entries, expenses = store.allocation_entries(), store.expense_entries()
    result = {}
    for pocket in store.list_pockets():
        if pocket.behavior is Behavior.ACUMULABLE:
            result[pocket.id] = accumulated_balance(entries, pocket.id, expenses)
        else:
            result[pocket.id] = tuple(
                consumption_available(entries, pocket.id, m, expenses) for m in MONTHS
            )
    return result


async def test_estructura_no_mueve_saldos_y_el_avance_es_el_saldo():
    """Hito 7: crear bolsas, reajustar porcentajes, crear o cambiar metas y archivar bolsas vacías
    no altera ningún saldo ni la suma; el avance de cada meta es el saldo de su bolsa."""
    created = archived = goals = 0
    for dataset in datasets():
        pockets = [Pocket(i + 1, n, b) for i, (n, b) in enumerate(dataset.pockets)]
        store = InMemoryLedgerStore(pockets)
        await apply_money(store, dataset)
        before, lines = _snapshot(store), list(store.lines)
        await apply_structure(store, dataset)
        after = _snapshot(store)
        message = f"semilla={dataset.seed}"
        assert {k: v for k, v in after.items() if k in before} == before, message
        assert all(v in (0, (0,) * len(MONTHS)) for k, v in after.items() if k not in before), (
            message
        )
        assert store.lines == lines, message  # ningún reparto guardado se recalcula
        assert _gap(store) == 0, message
        entries, expenses = store.allocation_entries(), store.expense_entries()
        for goal in store.goals:
            balance = accumulated_balance(entries, goal.pocket_id, expenses)
            assert progress(goal, balance).balance == balance, message
            if goal.status.value == "lograda":
                assert goal.achieved_on is not None, message
        created += len(store.pockets) - len(pockets)
        archived += sum(not p.active for p in store.pockets)
        goals += len(store.goals)
    assert created > 150 and archived > 60 and goals > 150


async def test_cambiar_porcentajes_no_altera_meses_pasados():
    """Lo asignado en cada mes pasado queda igual tras crear y archivar bolsas (RN-02)."""
    from puro_pockets.domain.balances import assigned

    for dataset in datasets(60):
        pockets = [Pocket(i + 1, n, b) for i, (n, b) in enumerate(dataset.pockets)]
        store = InMemoryLedgerStore(pockets)
        await apply_money(store, dataset)
        past = [m for m in MONTHS if m < Month(2026, 11)]
        rows_before = {m: store.allocation_rows(m) for m in past}
        figures = {
            (p.id, m): assigned(store.allocation_entries(), p.id, m) for p in pockets for m in past
        }
        await apply_structure(store, dataset)
        assert {m: store.allocation_rows(m) for m in past} == rows_before, f"semilla={dataset.seed}"
        assert {
            (p.id, m): assigned(store.allocation_entries(), p.id, m) for p in pockets for m in past
        } == figures, f"semilla={dataset.seed}"
