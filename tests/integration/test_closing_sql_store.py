"""Cierre de mes contra Postgres real, en la base temporal (Hito 9; datos sintéticos).

Octubre de 2026 (hoy = 2026-11-11): salario 1 000 000; Necesidades queda con sobrante 20 000 y
Gustos con déficit 5 000. La concurrencia se prueba con almacenes que se detienen dentro de la
transacción, con los bloqueos ya tomados, y un límite de tiempo: si hubiera un interbloqueo,
Postgres abortaría una de las dos (DeadlockDetected) o la prueba excedería el límite.
"""

import threading
import time
from datetime import date

import anyio
import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, OperationalError

from puro_pockets.db.ledger_store import SqlLedgerStore
from puro_pockets.domain.balances import integrity_gap
from puro_pockets.domain.closures import is_closed
from puro_pockets.domain.errors import ClosureStateChanged, MonthClosed
from puro_pockets.domain.money import Converted, Currency, RateRange
from puro_pockets.domain.months import Month
from puro_pockets.services.ledger import LedgerService
from puro_pockets.services.records import NewExpense, Operation

pytestmark = [pytest.mark.integration, pytest.mark.anyio]

TODAY = date(2026, 11, 11)
OCT, NOV = Month(2026, 10), Month(2026, 11)
PAUSE = 0.8  # segundos dentro de la transacción, con los bloqueos tomados
LIMIT = 15  # segundos: más que esto sería un bloqueo sin salida
COVERS = [{"from_pocket": "Necesidades", "to_pocket": "Gustos", "amount": 5_000}]
DESTS = [{"from_pocket": "Necesidades", "to_pocket": "Ahorro", "amount": 10_000}]


class SlowCloseStore(SqlLedgerStore):
    """Se detiene dentro de `record_closure`, con el bloqueo exclusivo y las bolsas tomadas."""

    def record_closure(self, month, closed_at, day, operation, verify):
        def slow(snapshot):
            time.sleep(PAUSE)
            return verify(snapshot)

        return super().record_closure(month, closed_at, day, operation, slow)


class SlowExpenseStore(SqlLedgerStore):
    """Se detiene dentro de `record_expense`, después de la guardia (bloqueo compartido)."""

    def record_expense(self, expense, operation, respond):
        def slow(expense_id):
            time.sleep(PAUSE)
            return respond(expense_id)

        return super().record_expense(expense, operation, slow)


class SlowTransferStore(SqlLedgerStore):
    """Se detiene dentro de `record_transfer`, con la guardia y las dos bolsas bloqueadas."""

    def record_transfer(self, new, operation, verify, on):
        def slow(snapshot):
            time.sleep(PAUSE)
            return verify(snapshot)

        return super().record_transfer(new, operation, slow, on)


class FailingStore(SqlLedgerStore):
    """Falla a mitad del cierre: después de la marca y las transferencias, antes de los ajustes."""

    def _before_adjustments(self, conn):
        raise RuntimeError("fallo simulado a mitad del cierre")


def _service(store):
    return LedgerService(store, today=lambda: TODAY, rate_range=RateRange(300, 1000))


@pytest.fixture
async def store(budget_engine):
    store = SqlLedgerStore(budget_engine)
    store.replace_allocation(OCT, {1: 50, 2: 30, 3: 20})
    store.replace_allocation(NOV, {1: 50, 2: 30, 3: 20})
    ledger = _service(store)
    await ledger.add_income(
        1_000_000,
        income_date="2026-09-30",
        budget_month="2026-10",
        confirm=True,
        operation_id="sql-h9-sal",
    )
    await ledger.add_expense(480_000, "sql-h9-g1", pocket="Necesidades", expense_date="2026-10-10")
    await ledger.add_expense(205_000, "sql-h9-g2", pocket="Gustos", expense_date="2026-10-12")
    return store


def _rows(engine, sql):
    with engine.connect() as conn:
        return [tuple(r) for r in conn.execute(text(sql)).all()]


def _gap(store):
    closed = store.closure_state().closed
    return integrity_gap(
        store.distributed_income_total(),
        store.expense_total(),
        store.list_pockets(),
        store.allocation_entries(),
        store.expense_entries(),
        store.transfer_entries(),
        lambda m: is_closed(m, closed),
        sum(a.amount for a in store.closure_adjustments(None)),
    )


async def _preview(ledger, covers=COVERS, dests=DESTS):
    return await ledger.preview_month_close("2026-10", covers, dests)


async def _close(ledger, token, op="sql-h9-close", covers=COVERS, dests=DESTS):
    return await ledger.close_month(
        "2026-10", covers, dests, confirm=True, preview_token=token, operation_id=op
    )


def _run(fn, results, key):
    def target():
        try:
            results[key] = anyio.run(fn)
        except Exception as exc:  # noqa: BLE001 - la prueba revisa el tipo
            results[key] = exc

    return threading.Thread(target=target)


async def test_cierre_atomico_con_transferencias_ajustes_y_clave(store, budget_engine):
    ledger = _service(store)
    preview = await _preview(ledger)
    result = await _close(ledger, preview.preview_token)
    assert result.saved and [t.reference for t in result.transfers] == ["T-1", "T-2"]
    assert _rows(
        budget_engine, "SELECT transfer_date, month, from_pocket_id, to_pocket_id, amount, "
        "reason, note FROM transfers ORDER BY id"
    ) == [
        (TODAY, "2026-10", 1, 3, 5_000, "cierre_de_mes", None),
        (TODAY, "2026-10", 1, 2, 10_000, "cierre_de_mes", None),
    ]  # fmt: skip
    adjustments = _rows(
        budget_engine, "SELECT month, pocket_id, kind, amount FROM closure_adjustments"
    )
    assert adjustments == [("2026-10", 1, "sobrante_no_destinado", 5_000)]
    assert _rows(budget_engine, "SELECT month, status FROM month_closures") == [
        ("2026-10", "cerrado")
    ]
    assert _rows(budget_engine, "SELECT tool FROM idempotency_keys WHERE operation_id = "
                 "'sql-h9-close'") == [("close_month",)]  # fmt: skip
    again = await _close(ledger, preview.preview_token)
    assert again == result and _rows(budget_engine, "SELECT count(*) FROM transfers") == [(2,)]
    assert _gap(store) == 0
    for name in ("Necesidades", "Gustos"):  # el mes siguiente empieza en cero
        assert (await ledger.get_bolsa_status(name, "2026-11")).available == 0


async def test_cierre_interrumpido_no_deja_nada(store, budget_engine):
    preview = await _preview(_service(store))
    failing = _service(FailingStore(budget_engine))
    with pytest.raises(RuntimeError, match="fallo simulado"):
        await _close(failing, preview.preview_token)
    for table in ("month_closures", "closure_adjustments", "transfers", "idempotency_keys"):
        extra = " WHERE tool = 'close_month'" if table == "idempotency_keys" else ""
        assert _rows(budget_engine, f"SELECT count(*) FROM {table}{extra}") == [(0,)], table
    assert (await _close(_service(store), preview.preview_token)).saved  # y luego sí cierra


async def test_la_guardia_del_almacen_rechaza_el_mes_cerrado(store):
    ledger = _service(store)
    await _close(ledger, (await _preview(ledger)).preview_token)
    money = Converted(Currency.CRC, 1_000, None, 1_000)
    for day in (date(2026, 10, 31), date(2026, 9, 1)):  # cerrado y anterior al cerrado
        with pytest.raises(MonthClosed):
            store.record_expense(  # sin pasar por el servicio: decide la transacción
                NewExpense(day, Month.of(day), 3, None, None, money),
                Operation(f"sql-h9-direct-{day.month}", "add_expense", "0" * 64),
                lambda _id: {},
            )
    with pytest.raises(MonthClosed):
        store.replace_allocation(OCT, {1: 100, 2: 0, 3: 0})
    with pytest.raises(MonthClosed):
        await ledger.void_transaction("G-1", "error sintético", "sql-h9-void", confirm=True)


async def test_disparadores_impiden_reabrir_y_borrar(store, budget_engine):
    ledger = _service(store)
    await _close(ledger, (await _preview(ledger)).preview_token)
    for sql in (
        "UPDATE month_closures SET status = 'abierto', closed_at = NULL",
        "DELETE FROM month_closures",
        "UPDATE closure_adjustments SET amount = 1",
        "DELETE FROM closure_adjustments",
    ):
        with pytest.raises(IntegrityError):
            with budget_engine.begin() as conn:
                conn.execute(text(sql))
    assert _rows(budget_engine, "SELECT status FROM month_closures") == [("cerrado",)]


async def test_gasto_del_mes_durante_el_cierre_espera_y_se_rechaza(store, budget_engine):
    """El cierre toma primero los bloqueos; el gasto espera y, al entrar, el mes ya está cerrado."""
    preview = await _preview(_service(store))
    closer = _service(SlowCloseStore(budget_engine))
    writer = _service(SqlLedgerStore(budget_engine))
    results = {}
    a = _run(lambda: _close(closer, preview.preview_token), results, "close")
    b = _run(
        lambda: writer.add_expense(
            1_000, "sql-h9-race-1", pocket="Gustos", expense_date="2026-10-31"
        ),
        results,
        "expense",
    )
    start = time.monotonic()
    a.start()
    time.sleep(0.2)
    b.start()
    a.join(LIMIT)
    b.join(LIMIT)
    assert time.monotonic() - start < LIMIT and not a.is_alive() and not b.is_alive()
    assert results["close"].saved
    assert isinstance(results["expense"], MonthClosed)
    assert not any(isinstance(r, OperationalError) for r in results.values())  # sin deadlock
    assert _rows(budget_engine, "SELECT count(*) FROM expenses WHERE month = '2026-10'") == [(2,)]
    assert _gap(store) == 0


async def test_cierre_durante_un_gasto_del_mes_espera_y_pide_repetir(store, budget_engine):
    """El gasto entra primero (bloqueo compartido); el cierre espera y ve el cambio."""
    preview = await _preview(_service(store))
    writer = _service(SlowExpenseStore(budget_engine))
    closer = _service(SqlLedgerStore(budget_engine))
    results = {}
    a = _run(
        lambda: writer.add_expense(
            1_000, "sql-h9-race-2", pocket="Gustos", expense_date="2026-10-31"
        ),
        results,
        "expense",
    )
    b = _run(lambda: _close(closer, preview.preview_token), results, "close")
    start = time.monotonic()
    a.start()
    time.sleep(0.2)
    b.start()
    a.join(LIMIT)
    b.join(LIMIT)
    assert time.monotonic() - start < LIMIT and not a.is_alive() and not b.is_alive()
    assert results["expense"].reference == "G-3"
    assert isinstance(results["close"], ClosureStateChanged)
    assert _rows(budget_engine, "SELECT count(*) FROM month_closures") == [(0,)]


async def test_transferencia_y_cierre_a_la_vez_sin_interbloqueo(store, budget_engine):
    """Los dos bloquean bolsas: el orden "guardia, bolsas" evita el interbloqueo. La
    transferencia de hoy (noviembre) no cambia las cifras de octubre: el cierre pasa igual."""
    preview = await _preview(_service(store))
    mover = _service(SlowTransferStore(budget_engine))
    closer = _service(SqlLedgerStore(budget_engine))

    async def transfer():
        args = ("Necesidades", "Gustos", 1_000, "reasignacion")
        token = (await mover.preview_transfer(*args)).preview_token
        return await mover.transfer_between_bolsas(
            *args, confirm=True, operation_id="sql-h9-t-race", preview_token=token
        )

    store.replace_allocation(NOV, {1: 50, 2: 30, 3: 20})
    await _service(store).add_income(
        100_000, income_date="2026-10-31", confirm=True, operation_id="sql-h9-sal-nov"
    )
    preview = await _preview(_service(store))  # el salario de noviembre cambia el saldo de Ahorro
    results = {}
    a = _run(transfer, results, "transfer")
    b = _run(lambda: _close(closer, preview.preview_token), results, "close")
    start = time.monotonic()
    a.start()
    time.sleep(0.2)
    b.start()
    a.join(LIMIT)
    b.join(LIMIT)
    assert time.monotonic() - start < LIMIT and not a.is_alive() and not b.is_alive()
    assert results["transfer"].saved and results["close"].saved, results
    assert _gap(store) == 0
