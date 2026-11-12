"""Servicio del cierre de mes (Hito 9) con almacén en memoria. Datos sintéticos.

Octubre de 2026: salario 1 000 000 (Necesidades 500 000, Ahorro 300 000, Gustos 200 000), gastos
que dejan Necesidades con sobrante 20 000 y Gustos con déficit 5 000. Ahorro tiene una meta de
1 000 000 y Viaje es otra acumulable. La atomicidad real (fallo a mitad) y la concurrencia se
prueban contra Postgres en tests/integration/test_closing_sql_store.py.
"""

import logging
from dataclasses import replace
from datetime import date

import pytest

from puro_pockets.domain.balances import IncomeKind, integrity_gap
from puro_pockets.domain.closures import is_closed
from puro_pockets.domain.errors import (
    ClosureProposalInvalid,
    ClosureStateChanged,
    DomainError,
    ExtrasPendingBlock,
    IdempotencyConflict,
    MonthClosed,
    MonthNotClosable,
    PreviewRequired,
)
from puro_pockets.domain.money import Converted, Currency, RateRange
from puro_pockets.domain.months import Month
from puro_pockets.domain.pockets import Behavior, Pocket
from puro_pockets.domain.recurring import RecurringTemplate
from puro_pockets.domain.transfers import TransferReason
from puro_pockets.services.budget import BudgetService
from puro_pockets.services.ledger import ExpenseRow, IncomeRow, LedgerService
from tests.fakes import InMemoryLedgerStore

pytestmark = pytest.mark.anyio

OCT, NOV = Month(2026, 10), Month(2026, 11)
GOAL_NAME = "meta privada sintética"
POCKETS = [
    Pocket(1, "Necesidades", Behavior.CONSUMO),
    Pocket(2, "Ahorro", Behavior.ACUMULABLE),
    Pocket(3, "Gustos", Behavior.CONSUMO),
    Pocket(4, "Viaje", Behavior.ACUMULABLE),
]
COVERS = [{"from_pocket": "Necesidades", "to_pocket": "Gustos", "amount": 5_000}]
DESTS = [{"from_pocket": "Necesidades", "to_pocket": "Ahorro", "amount": 10_000}]


class Clock:
    def __init__(self, day: date) -> None:
        self.day = day

    def __call__(self) -> date:
        return self.day


@pytest.fixture
def clock():
    return Clock(date(2026, 10, 31))


@pytest.fixture
def store():
    store = InMemoryLedgerStore(list(POCKETS))
    store.replace_allocation(OCT, {1: 50, 2: 30, 3: 20, 4: 0})
    return store


@pytest.fixture
async def service(store, clock):
    ledger = LedgerService(store, today=clock, rate_range=RateRange(300, 1000))
    await ledger.add_income(
        1_000_000,
        income_date="2026-09-30",
        budget_month="2026-10",
        confirm=True,
        operation_id="svc-op-sal",
    )
    await ledger.add_expense(
        480_000, "svc-op-g-nec", pocket="Necesidades", expense_date="2026-10-10"
    )
    await ledger.add_expense(205_000, "svc-op-g-gus", pocket="Gustos", expense_date="2026-10-12")
    await ledger.create_goal("Ahorro", GOAL_NAME, 1_000_000, "svc-op-meta")
    return ledger


async def _close(service, month="2026-10", covers=COVERS, dests=DESTS, op="svc-op-close"):
    preview = await service.preview_month_close(month, covers, dests)
    return await service.close_month(
        month, covers, dests, confirm=True, preview_token=preview.preview_token, operation_id=op
    )


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


# --- Vista previa ---


async def test_vista_previa_sin_propuesta_solo_datos(service, store):
    writes = store.writes
    data = await service.preview_month_close()  # el mes más antiguo cerrable: octubre
    assert data.month == "2026-10" and data.closable and data.preview_token is None
    lines = {c.pocket: (c.available, c.situation) for c in data.consumption}
    assert lines == {"Necesidades": (20_000, "sobrante"), "Gustos": (-5_000, "deficit")}
    ahorro = next(a for a in data.accumulable if a.pocket == "Ahorro")
    assert ahorro.balance == 300_000 and ahorro.goal.percent == 30
    assert any("no admitirá más movimientos" in w for w in data.warnings)
    assert store.writes == writes and store.closures == {}


async def test_vista_previa_con_propuesta_muestra_todo_y_la_ficha(service, store):
    preview = await service.preview_month_close("2026-10", COVERS, DESTS)
    after = {o.pocket: o.after for o in preview.outcomes}
    assert after["Gustos"] == 0 and after["Ahorro"] == 310_000 and after["Necesidades"] == 5_000
    assert preview.unassigned_surplus_total == 5_000 and preview.uncovered_overspend_total == 0
    assert [e.percent_after for e in preview.goal_effects] == [31]
    assert len(preview.preview_token) == 64 and len(preview.transfers) == 2
    assert store.transfers == [] and store.closures == {}


async def test_sin_mes_para_cerrar_responde_sin_error(store, clock):
    ledger = LedgerService(store, today=clock, rate_range=RateRange(300, 1000))
    data = await ledger.preview_month_close()
    assert data.month is None and not data.closable


# --- Cierre ---


async def test_cerrar_cubre_destina_y_registra_el_resto(service, store, clock, caplog):
    caplog.set_level(logging.INFO)
    result = await _close(service)
    assert result.saved and result.month == "2026-10" and "add_income" in result.next_steps
    assert [t.reference for t in result.transfers] == ["T-1", "T-2"]
    assert all(t.reason is TransferReason.MONTH_CLOSE for t in store.transfers)
    assert all(t.month == OCT and t.transfer_date == clock.day for t in store.transfers)
    assert [(a.pocket_id, a.kind, a.amount) for a in store.adjustments] == [
        (1, "sobrante_no_destinado", 5_000)
    ]
    assert OCT in store.closures and _gap(store) == 0
    status = await service.get_bolsa_status("Necesidades", "2026-10")
    assert status.month_closed and status.closure_adjustment.amount == 5_000
    summary = await service.get_summary("2026-10")
    assert summary.month_closed and summary.closure_adjustments[0].kind == "sobrante_no_destinado"
    # Registros sin montos ni nombres de metas
    for secret in ("5000", "10000", "5 000", GOAL_NAME):
        assert secret not in caplog.text
    assert "Cierre registrado: mes=2026-10" in caplog.text


async def test_el_mes_siguiente_empieza_en_cero(service, store):
    await _close(service)
    for name in ("Necesidades", "Gustos"):
        status = await service.get_bolsa_status(name, "2026-11")
        assert status.available == 0 and status.assigned == 0
    store.replace_allocation(NOV, {1: 50, 2: 30, 3: 20, 4: 0})
    await service.add_income(  # el salario del 31 de octubre es del mes siguiente (5.1)
        100_000, income_date="2026-10-31", confirm=True, operation_id="svc-op-sal-nov"
    )
    status = await service.get_bolsa_status("Gustos", "2026-11")
    assert status.available == 20_000  # cero más lo que recibe


async def test_cobertura_desde_acumulable_es_opcional(service, store):
    await service.add_expense(
        20_000, "svc-op-g-nec2", pocket="Necesidades", expense_date="2026-10-20"
    )
    # Ahora Necesidades está en 0 y Gustos en −5 000: solo Ahorro podría cubrir
    with_balance = [{"from_pocket": "Ahorro", "to_pocket": "Gustos", "amount": 5_000}]
    preview = await service.preview_month_close("2026-10", with_balance, [])
    assert preview.covers[0].from_balance and preview.goal_effects[0].percent_after == 29
    declined = await _close(service, covers=[], dests=[], op="svc-op-close-2b")
    assert declined.uncovered_overspend_total == -5_000
    assert store.adjustments[0].kind == "sobregasto_no_cubierto" and _gap(store) == 0


async def test_misma_clave_reintenta_y_otra_propuesta_choca(service, store):
    first = await _close(service)
    again = await service.close_month(
        "2026-10", COVERS, DESTS, confirm=True, preview_token="x" * 64, operation_id="svc-op-close"
    )
    assert again == first and len(store.transfers) == 2
    with pytest.raises(IdempotencyConflict):
        await service.close_month(
            "2026-10", COVERS, [], confirm=True, preview_token="x" * 64, operation_id="svc-op-close"
        )


# --- Negativas ---


async def test_antes_del_ultimo_dia_no_se_cierra(service, clock):
    clock.day = date(2026, 10, 30)
    preview = await service.preview_month_close("2026-10", COVERS, DESTS)
    assert not preview.closable and preview.preview_token is None
    assert preview.next_closable_on == "2026-10-31"
    with pytest.raises(MonthNotClosable, match="último día"):
        await service.close_month(
            "2026-10", COVERS, DESTS, confirm=True, preview_token="x" * 64, operation_id="svc-op-c1"
        )


async def test_futuro_fuera_de_orden_y_ya_cerrado(service, clock):
    with pytest.raises(MonthNotClosable, match="futuro"):
        await service.preview_month_close("2026-11")
    clock.day = date(2026, 11, 30)
    with pytest.raises(MonthNotClosable, match="antes hay que cerrar 2026-10"):
        await service.preview_month_close("2026-11")
    await _close(service)
    with pytest.raises(MonthNotClosable, match="ya está cerrado"):
        await service.preview_month_close("2026-10")


async def test_extra_pendiente_bloquea_y_fijo_pendiente_avisa(service, store):
    extra = await service.register_extra_income(40_000, "svc-op-extra", income_date="2026-10-15")
    store.recurring.append(
        RecurringTemplate(1, "fijo sintético", Currency.CRC, 5, 1, None, OCT, True, ((OCT, 9_000),))
    )
    preview = await service.preview_month_close("2026-10", COVERS, DESTS)
    assert preview.blocked_by == [extra.reference] and preview.preview_token is None
    assert preview.pending_recurring.references == ["F-1"]
    with pytest.raises(ExtrasPendingBlock, match="confirm_allocation"):
        await service.close_month(
            "2026-10", COVERS, DESTS, confirm=True, preview_token="x" * 64, operation_id="svc-op-c2"
        )
    await service.void_transaction(extra.reference, "error sintético", "svc-op-vx", confirm=True)
    assert (await _close(service)).saved  # el fijo pendiente no bloquea


@pytest.mark.parametrize(
    ("covers", "dests", "match"),
    [
        (COVERS, [{"from_pocket": "Necesidades", "to_pocket": "Gustos", "amount": 1}], "10.2"),
        (
            COVERS,
            [{"from_pocket": "Necesidades", "to_pocket": "Ahorro", "amount": 15_001}],
            "RN-47",
        ),
        ([{"from_pocket": "Ahorro", "to_pocket": "Gustos", "amount": 5_000}], [], "primero"),
    ],
)
async def test_propuestas_invalidas_se_rechazan(service, covers, dests, match):
    with pytest.raises(ClosureProposalInvalid, match=match):
        await service.preview_month_close("2026-10", covers, dests)


async def test_confirmar_sin_vista_previa_o_con_ficha_vencida(service, store):
    with pytest.raises(PreviewRequired):
        await service.close_month("2026-10", COVERS, DESTS, confirm=True, operation_id="svc-op-c3")
    preview = await service.preview_month_close("2026-10", COVERS, DESTS)
    other = await service.preview_month_close("2026-10", COVERS, [])
    with pytest.raises(PreviewRequired):  # ficha de otra propuesta
        await service.close_month(
            "2026-10",
            COVERS,
            DESTS,
            confirm=True,
            preview_token=other.preview_token,
            operation_id="svc-op-c4",
        )
    await service.add_expense(1_000, "svc-op-g-tarde", pocket="Gustos", expense_date="2026-10-31")
    with pytest.raises(ClosureStateChanged, match="repite preview_month_close"):
        await service.close_month(
            "2026-10",
            COVERS,
            DESTS,
            confirm=True,
            preview_token=preview.preview_token,
            operation_id="svc-op-c5",
        )
    assert store.closures == {} and store.transfers == []


async def test_cambio_dentro_de_la_transaccion_se_detecta(service, store):
    """Un gasto que entra entre la comprobación del servicio y la transacción del cierre."""
    preview = await service.preview_month_close("2026-10", COVERS, DESTS)
    original = store.record_closure

    def racing(month, closed_at, day, operation, verify):
        store.expenses.append(
            ExpenseRow(99, day, OCT, 3, None, None, Currency.CRC, 1, None, 1, False, None, None)
        )
        return original(month, closed_at, day, operation, verify)

    store.record_closure = racing
    with pytest.raises(ClosureStateChanged):
        await service.close_month(
            "2026-10",
            COVERS,
            DESTS,
            confirm=True,
            preview_token=preview.preview_token,
            operation_id="svc-op-c6",
        )
    assert store.closures == {}


async def test_mes_cerrado_rechaza_todo_lo_que_le_pertenece(service, store):
    await _close(service)
    rejected = [
        service.add_expense(1_000, "svc-neg-1", pocket="Gustos", expense_date="2026-10-31"),
        service.add_expense(1_000, "svc-neg-2", pocket="Gustos", expense_date="2026-09-15"),
        service.add_income(1_000, budget_month="2026-10", confirm=True, operation_id="svc-neg-3"),
        service.preview_income(1_000, budget_month="2026-10"),
        service.register_extra_income(1_000, "svc-neg-4", income_date="2026-10-31"),
        service.preview_transfer("Necesidades", "Ahorro", 1, "reasignacion"),
        service.void_transaction("G-1", "error sintético", "svc-neg-5"),
        service.void_transaction("I-1", "error sintético", "svc-neg-6", confirm=True),
    ]
    for call in rejected:
        with pytest.raises(MonthClosed):
            await call
    # Un extra del mes cerrado que hubiera quedado pendiente tampoco se reparte
    money = Converted(Currency.CRC, 1_000, None, 1_000)
    store.incomes.append(
        IncomeRow(
            99,
            IncomeKind.EXTRA,
            date(2026, 10, 5),
            OCT,
            money.currency,
            1_000,
            None,
            1_000,
            False,
            None,
            True,
            None,
        )
    )
    with pytest.raises(MonthClosed):
        await service.confirm_allocation("I-99", [("Ahorro", 100)])
    budget = BudgetService(store, today=lambda: date(2026, 10, 31))
    with pytest.raises(MonthClosed):
        await budget.set_allocation([("Necesidades", 100)])
    with pytest.raises(MonthClosed):
        await budget.preview_initial_balance([("Ahorro", 1)])
    # El salario de hoy pertenece al mes siguiente (abierto): se acepta
    store.replace_allocation(NOV, {1: 50, 2: 30, 3: 20, 4: 0})
    ok = await service.add_income(
        1_000, income_date="2026-10-31", confirm=True, operation_id="svc-neg-7"
    )
    assert ok.budget_month == "2026-11"


async def test_pendiente_de_cierre_en_resumen_y_lista(service, store, clock):
    clock.day = date(2026, 11, 11)
    summary = await service.get_summary()
    assert [(p.month, p.has_movements) for p in summary.pending_closure] == [("2026-10", True)]
    view = await BudgetService(store, today=clock).list_pockets()
    assert [p.month for p in view.pending_closure] == ["2026-10"] and not view.month_closed
    await _close(service)
    assert (await service.get_summary()).pending_closure == []


async def test_bolsa_nueva_y_archivado_con_el_mes_actual_cerrado(service, store):
    await _close(service)
    preview = await service.create_bolsa("Emergencia", "acumulable", 10, month="2026-10")
    assert preview.rebalance.months[0].month == "2026-11"
    assert "2026-10 ya está cerrado" in preview.rebalance.note
    store.surplus[3] = 4  # Gustos sugiere Viaje
    archive = await service.archive_bolsa("Viaje")
    assert archive.rebalance.months[0].month == "2026-11"
    assert "ya está cerrado" in archive.rebalance.note
    await service.archive_bolsa(
        "Viaje", confirm=True, operation_id="svc-op-arch", preview_token=archive.preview_token
    )
    assert store.surplus == {}  # una acumulable archivada deja de ser destino sugerido
    assert OCT not in {m for m in store.allocations if store.allocations[m].get(4) is None}


async def test_destino_de_sobrante_sugerido(service, store):
    saved = await service.set_surplus_destination("Gustos", "Viaje", "svc-op-dest-1")
    assert saved.suggested_destination == "Viaje" and store.surplus == {3: 4}
    data = await service.preview_month_close("2026-10")
    assert (
        next(c for c in data.consumption if c.pocket == "Gustos").suggested_destination == "Viaje"
    )
    with pytest.raises(DomainError, match="acumulable activa"):
        await service.set_surplus_destination("Gustos", "Necesidades", "svc-op-dest-2")
    with pytest.raises(DomainError, match="no es de consumo"):
        await service.set_surplus_destination("Ahorro", "Viaje", "svc-op-dest-3")
    cleared = await service.set_surplus_destination("Gustos", None, "svc-op-dest-4")
    assert cleared.suggested_destination is None and store.surplus == {}


async def test_metas_se_evaluan_en_el_cierre(service, store):
    store.goals = [replace(g, target_amount=310_000) for g in store.goals]
    result = await _close(service)
    assert result.goals_achieved == ["M-1"]
    assert store.goals[0].status.value == "lograda"
