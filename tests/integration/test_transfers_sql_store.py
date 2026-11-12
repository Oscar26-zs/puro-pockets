"""Transferencias contra Postgres real, en la base temporal (Hito 8; datos sintéticos).

La concurrencia se prueba con un almacén que se detiene dentro de la transacción, después de
bloquear las bolsas: si faltara el bloqueo (`SELECT … FOR UPDATE`), la segunda transferencia leería
el saldo viejo y las dos pasarían, sobregirando el origen.
"""

import threading
import time
from datetime import date

import anyio
import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from puro_pockets.db.ledger_store import SqlLedgerStore
from puro_pockets.domain.balances import integrity_gap
from puro_pockets.domain.errors import DomainError, PocketNotEmpty, TransferExceedsAvailable
from puro_pockets.domain.money import RateRange
from puro_pockets.domain.months import Month
from puro_pockets.services.ledger import LedgerService

pytestmark = [pytest.mark.integration, pytest.mark.anyio]

TODAY = date(2026, 11, 11)
NOV = Month(2026, 11)
PAUSE = 0.6  # segundos dentro de la transacción, con las bolsas ya bloqueadas


class SlowStore(SqlLedgerStore):
    """Igual que el almacén real, pero se detiene tras bloquear y leer (para forzar la carrera)."""

    def record_transfer(self, new, operation, verify, on):
        def slow(snapshot):
            time.sleep(PAUSE)
            return verify(snapshot)

        return super().record_transfer(new, operation, slow, on)

    def archive_pocket(self, pocket_id, at, months, operation, respond, verify=None):
        def slow(snapshot):
            time.sleep(PAUSE)
            if verify is not None:
                verify(snapshot)

        return super().archive_pocket(pocket_id, at, months, operation, respond, slow)


@pytest.fixture
def store(budget_engine):
    store = SqlLedgerStore(budget_engine)
    store.replace_allocation(NOV, {1: 50, 2: 30, 3: 20})
    return store


def _service(store):
    return LedgerService(store, today=lambda: TODAY, rate_range=RateRange(300, 1000))


@pytest.fixture
def ledger(store):
    return _service(store)


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
        store.transfer_entries(),
    )


async def _salary(ledger):
    await ledger.add_income(
        1_000_000,
        budget_month="2026-11",
        income_date="2026-10-31",
        confirm=True,
        operation_id="sql-sal-h8",
    )


async def _transfer(ledger, source, target, amount, op, reason="reasignacion", note=None):
    preview = await ledger.preview_transfer(source, target, amount, reason, note)
    return await ledger.transfer_between_bolsas(
        source,
        target,
        amount,
        reason,
        note,
        confirm=True,
        operation_id=op,
        preview_token=preview.preview_token,
    )


async def test_transferencia_atomica_con_su_clave_y_consultas(ledger, store, budget_engine):
    await _salary(ledger)
    result = await _transfer(ledger, "Necesidades", "Gustos", 80_000, "sql-t-0001", note="x sint")
    assert result.reference == "T-1"
    assert _rows(
        budget_engine,
        "SELECT transfer_date, month, from_pocket_id, to_pocket_id, amount, reason, note "
        "FROM transfers",
    ) == [(TODAY, "2026-11", 1, 3, 80_000, "reasignacion", "x sint")]
    assert _rows(
        budget_engine,
        "SELECT tool FROM idempotency_keys WHERE operation_id = 'sql-t-0001'",
    ) == [("transfer_between_bolsas",)]
    status = await ledger.get_bolsa_status("Gustos")
    assert (status.transfers_in, status.adjusted_budget, status.available) == (
        80_000,
        280_000,
        280_000,
    )
    listed = await ledger.list_transactions(type="transferencia", pocket="Necesidades")
    assert [i.reference for i in listed.items] == ["T-1"]
    again = await _transfer(ledger, "Necesidades", "Gustos", 80_000, "sql-t-0001", note="x sint")
    assert again == result and _rows(budget_engine, "SELECT count(*) FROM transfers") == [(1,)]
    assert _gap(store) == 0


async def test_el_disparador_impide_editar_o_borrar(ledger, budget_engine):
    await _salary(ledger)
    await _transfer(ledger, "Necesidades", "Gustos", 1_000, "sql-t-0002")
    for sql in ("UPDATE transfers SET amount = 2", "DELETE FROM transfers"):
        with pytest.raises(IntegrityError, match="no se edita ni se borra"):
            with budget_engine.begin() as conn:
                conn.execute(text(sql))
    assert _rows(budget_engine, "SELECT amount FROM transfers") == [(1_000,)]


async def test_meta_lograda_en_la_transaccion_de_la_transferencia(ledger, store, budget_engine):
    await _salary(ledger)
    await ledger.create_goal("Ahorro", "Viaje sintético", 350_000, "sql-meta-h8")
    await _transfer(ledger, "Necesidades", "Ahorro", 50_000, "sql-t-0003")
    assert _rows(budget_engine, "SELECT status, achieved_on FROM savings_goals") == [
        ("lograda", TODAY)
    ]
    await _transfer(ledger, "Ahorro", "Gustos", 50_000, "sql-t-0004")
    assert _rows(budget_engine, "SELECT status FROM savings_goals") == [("lograda",)]  # RN-24
    assert _gap(store) == 0


async def test_vaciar_con_transferencia_y_archivar_con_su_meta(ledger, store, budget_engine):
    await _salary(ledger)
    await ledger.create_goal("Ahorro", "Viaje sintético", 900_000, "sql-meta-h8b")
    with pytest.raises(PocketNotEmpty):
        await ledger.archive_bolsa("Ahorro")
    await _transfer(ledger, "Ahorro", "Necesidades", 300_000, "sql-t-0005")
    preview = await ledger.archive_bolsa("Ahorro")
    await ledger.archive_bolsa(
        "Ahorro", confirm=True, operation_id="sql-arch-h8", preview_token=preview.preview_token
    )
    assert _rows(budget_engine, "SELECT active FROM pockets WHERE id = 2") == [(False,)]
    assert _rows(budget_engine, "SELECT archived_at IS NOT NULL FROM savings_goals") == [(True,)]
    with pytest.raises(DomainError, match="archivada"):
        await ledger.preview_transfer("Necesidades", "Ahorro", 1, "ajuste")
    assert _gap(store) == 0


def _run_in_threads(calls):
    barrier = threading.Barrier(len(calls))
    outcomes = []
    lock = threading.Lock()

    def worker(fn):
        barrier.wait()
        try:
            result = anyio.run(fn)
        except DomainError as exc:
            result = exc
        with lock:
            outcomes.append(result)

    threads = [threading.Thread(target=worker, args=(fn,)) for fn in calls]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)
    return outcomes


async def test_transferencias_concurrentes_no_sobregiran_el_origen(store, budget_engine):
    ledger = _service(store)
    await _salary(ledger)  # Necesidades: 500 000 disponibles
    slow = _service(SlowStore(budget_engine))
    targets = ("Gustos", "Ahorro", "Gustos")
    previews = [await slow.preview_transfer("Necesidades", t, 200_000, "ajuste") for t in targets]

    def confirm(i):
        return lambda: slow.transfer_between_bolsas(
            "Necesidades",
            targets[i],
            200_000,
            "ajuste",
            confirm=True,
            operation_id=f"sql-carrera-t{i}",
            preview_token=previews[i].preview_token,
        )

    outcomes = _run_in_threads([confirm(i) for i in range(3)])
    names = sorted(type(o).__name__ for o in outcomes)
    assert names == ["TransferExceedsAvailable", "TransferResult", "TransferResult"], outcomes
    assert _rows(budget_engine, "SELECT count(*), sum(amount) FROM transfers") == [(2, 400_000)]
    status = await ledger.get_bolsa_status("Necesidades")
    assert status.available == 100_000 and not status.negative
    assert _gap(store) == 0


async def test_transferencias_cruzadas_simultaneas_sin_interbloqueo(store, budget_engine):
    ledger = _service(store)
    await _salary(ledger)
    slow = _service(SlowStore(budget_engine))
    pairs = (("Necesidades", "Gustos"), ("Gustos", "Necesidades"))
    previews = [await slow.preview_transfer(a, b, 10_000, "ajuste") for a, b in pairs]

    def confirm(i):
        a, b = pairs[i]
        return lambda: slow.transfer_between_bolsas(
            a,
            b,
            10_000,
            "ajuste",
            confirm=True,
            operation_id=f"sql-cruce-t{i}",
            preview_token=previews[i].preview_token,
        )

    started = time.monotonic()
    outcomes = _run_in_threads([confirm(0), confirm(1)])
    assert all(type(o).__name__ == "TransferResult" for o in outcomes), outcomes
    assert time.monotonic() - started < 20
    assert _gap(store) == 0


async def test_archivar_y_transferir_hacia_ella_a_la_vez(store, budget_engine):
    """Una bolsa nunca queda archivada con dinero: gana una de las dos operaciones."""
    ledger = _service(store)
    await _salary(ledger)
    await _transfer(ledger, "Gustos", "Ahorro", 200_000, "sql-vaciar-gus")
    slow = _service(SlowStore(budget_engine))
    archive_preview = await slow.archive_bolsa("Gustos")
    transfer_preview = await slow.preview_transfer("Necesidades", "Gustos", 5_000, "ajuste")
    outcomes = _run_in_threads(
        [
            lambda: slow.archive_bolsa(
                "Gustos",
                confirm=True,
                operation_id="sql-arch-race",
                preview_token=archive_preview.preview_token,
            ),
            lambda: slow.transfer_between_bolsas(
                "Necesidades",
                "Gustos",
                5_000,
                "ajuste",
                confirm=True,
                operation_id="sql-t-race",
                preview_token=transfer_preview.preview_token,
            ),
        ]
    )
    failures = [o for o in outcomes if isinstance(o, DomainError)]
    assert len(failures) == 1, outcomes
    active = _rows(budget_engine, "SELECT active FROM pockets WHERE id = 3")[0][0]
    gustos_in = _rows(
        budget_engine, "SELECT coalesce(sum(amount), 0) FROM transfers WHERE to_pocket_id = 3"
    )[0][0]
    # Archivada ⇒ no entró dinero; si entró, sigue activa
    assert (not active and gustos_in == 0) or (active and gustos_in == 5_000)
    assert isinstance(failures[0], PocketNotEmpty | TransferExceedsAvailable | DomainError)
    assert _gap(store) == 0
