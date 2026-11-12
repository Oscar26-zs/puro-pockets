"""Servicio de bolsas flexibles y metas (Hito 7) con almacén en memoria. Datos sintéticos."""

import logging
from datetime import date

import pytest

from puro_pockets.domain.balances import integrity_gap, pocket_balance
from puro_pockets.domain.errors import (
    DomainError,
    GoalAlreadyActive,
    GoalClosed,
    GoalNeedsSavingsPocket,
    IdempotencyConflict,
    MovementTouchesArchivedPocket,
    PocketAlreadyExists,
    PocketNotEmpty,
    PreviewRequired,
)
from puro_pockets.domain.goals import GoalStatus
from puro_pockets.domain.money import RateRange
from puro_pockets.domain.months import Month
from puro_pockets.services.budget import BudgetService
from puro_pockets.services.ledger import LedgerService
from tests.fakes import InMemoryLedgerStore

pytestmark = pytest.mark.anyio

TODAY = date(2026, 11, 11)
NOV, DEC, JAN = Month(2026, 11), Month(2026, 12), Month(2027, 1)
P_50_30_20 = {1: 50, 2: 30, 3: 20}


@pytest.fixture
def store():
    store = InMemoryLedgerStore()
    store.replace_allocation(NOV, P_50_30_20)
    return store


@pytest.fixture
def service(store):
    return LedgerService(store, today=lambda: TODAY, rate_range=RateRange(300, 1000))


def _balances(store):
    entries, expenses = store.allocation_entries(), store.expense_entries()
    return {p.id: pocket_balance(p, entries, NOV, expenses).balance for p in store.list_pockets()}


def _gap(store):
    return integrity_gap(
        store.distributed_income_total(),
        store.expense_total(),
        store.list_pockets(),
        store.allocation_entries(),
        store.expense_entries(),
    )


async def _create(service, name="Emergencia", share=10, op="op-bolsa-0001", **kw):
    kw.setdefault("behavior", "acumulable")
    preview = await service.create_bolsa(name, percentage=share, **kw)
    return await service.create_bolsa(
        name,
        percentage=share,
        confirm=True,
        operation_id=op,
        preview_token=preview.preview_token,
        **kw,
    )


async def _archive(service, name, op="op-archivo-01", **kw):
    preview = await service.archive_bolsa(name, **kw)
    return await service.archive_bolsa(
        name, confirm=True, operation_id=op, preview_token=preview.preview_token, **kw
    )


# --- preview_rebalance y create_bolsa (RN-13 a RN-15) ---


async def test_vista_previa_proporcional_del_mes_siguiente_sin_guardar(service, store):
    result = await service.preview_rebalance(
        "proporcional", new_pocket="Emergencia", new_percentage=10
    )
    month = result.months[0]
    assert month.month == "2026-12" and month.source_month == "2026-11"  # RN-15 y RN-03
    assert [(s.pocket, s.percentage) for s in month.previous] == [
        ("Necesidades", 50),
        ("Ahorro", 30),
        ("Gustos", 20),
    ]
    assert [(s.pocket, s.percentage) for s in month.new] == [
        ("Necesidades", 45),
        ("Ahorro", 27),
        ("Gustos", 18),
        ("Emergencia", 10),
    ]
    assert store.writes == 1 and len(store.pockets) == 3  # 1 = porcentajes del fixture


async def test_crear_bolsa_atomico_aplica_desde_el_mes_siguiente(service, store):
    preview = await service.create_bolsa("Emergencia", "acumulable", percentage=10)
    assert not preview.saved and preview.preview_token and len(store.pockets) == 3
    saved = await _create(service)
    assert saved.saved and saved.pocket.behavior == "acumulable"
    assert store.allocations[DEC] == {1: 45, 2: 27, 3: 18, 4: 10}
    assert sum(store.allocations[DEC].values()) == 100
    assert store.allocations[NOV] == P_50_30_20  # el mes en curso no cambia
    # el mes siguiente reparte con los porcentajes nuevos
    income = await service.add_income(100_000, confirm=True, operation_id="op-salario-dic")
    assert [(i.pocket, i.amount) for i in income.items][-1] == ("Emergencia", 10_000)


async def test_crear_desde_una_bolsa_y_en_el_mes_actual(service, store):
    await _create(
        service, "Viaje", 5, strategy="desde_una_bolsa", from_pocket="gustos", month="2026-11"
    )
    assert store.allocations[NOV] == {1: 50, 2: 30, 3: 15, 4: 5}


async def test_manual_completo_y_sin_porcentajes_previos(store):
    store.allocations.clear()
    service = LedgerService(store, today=lambda: TODAY, rate_range=RateRange(300, 1000))
    with pytest.raises(DomainError, match="estrategia manual"):
        await service.create_bolsa("Viaje", "acumulable", percentage=10)
    shares = [("Necesidades", 50), ("Ahorro", 20), ("Gustos", 20), ("Viaje", 10)]
    await _create(service, "Viaje", None, strategy="manual", percentages=shares)
    assert store.allocations[DEC] == {1: 50, 2: 20, 3: 20, 4: 10}


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        (
            {
                "strategy": "manual",
                "percentages": [("Necesidades", 50), ("Ahorro", 30), ("Gustos", 10), ("Viaje", 5)],
            },
            "suman 95",
        ),
        (
            {"strategy": "manual", "percentages": [("Necesidades", 70), ("Ahorro", 30)]},
            "todas las bolsas",
        ),
        ({"percentage": 101}, "entre 0 y 100"),
        ({"percentage": 25, "strategy": "desde_una_bolsa", "from_pocket": "Gustos"}, "no alcanza"),
        ({"month": "2026-10"}, "mes pasado"),
        ({"percentage": 10.5}, "entero"),
    ],
)
async def test_crear_bolsa_invalido_no_guarda(service, store, kwargs, message):
    args = {"percentage": 10, **kwargs}
    with pytest.raises(DomainError, match=message):
        await service.create_bolsa("Viaje", "acumulable", **args)
    assert len(store.pockets) == 3 and store.writes == 1  # 1 = porcentajes del fixture


async def test_nombre_duplicado_sin_distinguir_mayusculas(service, store):
    with pytest.raises(PocketAlreadyExists):
        await service.create_bolsa("  AHORRO ", "acumulable", percentage=10)
    await _create(service, "Viaje", 0)
    await _archive(service, "Viaje")
    with pytest.raises(PocketAlreadyExists):  # también contra una archivada
        await service.create_bolsa("viaje", "acumulable", percentage=0)


async def test_confirmar_sin_vista_previa(service, store):
    with pytest.raises(PreviewRequired):
        await service.create_bolsa(
            "Viaje", "acumulable", percentage=10, confirm=True, operation_id="op-bolsa-0002"
        )
    other = (await service.create_bolsa("Viaje", "acumulable", percentage=20)).preview_token
    with pytest.raises(PreviewRequired):
        await service.create_bolsa(
            "Viaje",
            "acumulable",
            percentage=10,
            confirm=True,
            operation_id="op-bolsa-0003",
            preview_token=other,
        )
    assert len(store.pockets) == 3


async def test_crear_bolsa_idempotente(service, store):
    first = await _create(service)
    again = await service.create_bolsa(
        "Emergencia", "acumulable", percentage=10, confirm=True, operation_id="op-bolsa-0001"
    )
    assert again == first and len(store.pockets) == 4
    with pytest.raises(IdempotencyConflict):
        await service.create_bolsa(
            "Emergencia", "acumulable", percentage=15, confirm=True, operation_id="op-bolsa-0001"
        )


async def test_cambiar_porcentajes_no_altera_meses_pasados_ni_repartos(service, store):
    await service.add_income(
        1_000_000, budget_month="2026-11", confirm=True, operation_id="op-sal-n1"
    )
    lines_before = list(store.lines)
    balances = _balances(store)
    await _create(service, "Viaje", 10, month="2026-11")
    assert store.lines == lines_before  # los repartos guardan el % que usaron
    assert {k: v for k, v in _balances(store).items() if k in balances} == balances
    assert _balances(store)[4] == 0 and _gap(store) == 0


# --- archive_bolsa (RN-16 a RN-18) ---


async def test_archivar_con_saldo_distinto_de_cero(service, store):
    await service.add_income(90_001, budget_month="2026-11", confirm=True, operation_id="op-sal-n2")
    with pytest.raises(PocketNotEmpty, match="saldo") as exc:
        await service.archive_bolsa("Ahorro")
    assert "27" not in exc.value.message and "transfer_between_bolsas" in exc.value.message
    with pytest.raises(PocketNotEmpty, match="disponible del mes"):
        await service.archive_bolsa("Gustos")


async def test_archivar_reescribe_el_mes_actual_y_los_futuros(service, store):
    await _create(service, "Viaje", 10, month="2026-11")  # Viaje en noviembre (sin dinero)
    store.replace_allocation(JAN, {1: 40, 2: 30, 3: 20, 4: 10})
    result = await _archive(service, "viaje", strategy="desde_una_bolsa", to_pocket="Ahorro")
    assert result.saved and [m.month for m in result.rebalance.months] == ["2026-11", "2027-01"]
    assert store.allocations[NOV] == {1: 45, 2: 37, 3: 18}  # Ahorro recibe el 10 %
    assert store.allocations[JAN] == {1: 40, 2: 40, 3: 20}
    for month in (NOV, JAN):
        assert 4 not in store.allocations[month] and sum(store.allocations[month].values()) == 100
    assert not next(p for p in store.pockets if p.id == 4).active  # nunca se borra (RN-16)
    # diciembre hereda de noviembre (RN-03): ningún mes futuro reparte a la archivada
    resolved = await BudgetService(store, today=lambda: TODAY).get_allocation("2026-12")
    assert "Viaje" not in [p.name for p, _ in resolved.items]


async def test_archivar_desde_un_mes_futuro_dejaria_el_actual_repartiendo(service, store):
    await _create(service, "Viaje", 10, month="2026-11")
    with pytest.raises(DomainError, match="Archivar es inmediato"):
        await service.archive_bolsa("Viaje", month="2026-12")
    with pytest.raises(DomainError, match="mes pasado"):
        await service.archive_bolsa("Viaje", month="2026-10")
    assert next(p for p in store.pockets if p.id == 4).active


async def test_bolsa_archivada_rechaza_gastos_repartos_y_porcentajes(service, store):
    await _create(service, "Viaje", 0, month="2026-11")
    await _archive(service, "Viaje")
    with pytest.raises(DomainError, match="archivada"):
        await service.add_expense(1_000, "op-gasto-arch", pocket="Viaje")
    extra = await service.register_extra_income(10_000, "op-extra-arch")
    with pytest.raises(DomainError, match="archivada"):
        await service.confirm_allocation(extra.reference, [("Viaje", 100)])
    with pytest.raises(DomainError, match="archivada"):
        await BudgetService(store, today=lambda: TODAY).set_allocation(
            [("Necesidades", 50), ("Ahorro", 30), ("Gustos", 10), ("Viaje", 10)]
        )
    with pytest.raises(DomainError, match="archivada"):
        await service.create_goal("Viaje", "Meta sintética", 1_000, "op-meta-arch1")
    salary = await service.add_income(
        100_000, budget_month="2026-11", confirm=True, operation_id="op-sal-arch"
    )
    assert (
        "Viaje" not in [i.pocket for i in salary.items]
        and sum(i.amount for i in salary.items) == 100_000
    )


async def test_no_se_anula_un_movimiento_de_una_bolsa_archivada(service, store):
    await _create(service, "Viaje", 10, month="2026-11")
    salary = await service.add_income(
        100_000, budget_month="2026-11", confirm=True, operation_id="op-sal-v1"
    )
    expense = await service.add_expense(10_000, "op-gasto-v1", pocket="Viaje")
    await _archive(service, "Viaje")
    for ref in (expense.reference, salary.reference):
        with pytest.raises(MovementTouchesArchivedPocket):
            await service.void_transaction(ref, "prueba sintética", f"op-void-{ref}", confirm=True)


# --- Metas (RN-19 a RN-25) ---


async def test_meta_en_bolsa_de_consumo_y_segunda_meta_activa(service, store):
    with pytest.raises(GoalNeedsSavingsPocket):
        await service.create_goal("Gustos", "Viaje sintético", 500_000, "op-meta-0001")
    first = await service.create_goal("Ahorro", "Viaje sintético", 500_000, "op-meta-0002")
    assert first.reference == "M-1" and first.status == "activa"
    with pytest.raises(GoalAlreadyActive, match="M-1"):
        await service.create_goal("ahorro", "Otra sintética", 100_000, "op-meta-0003")


async def test_crear_o_cambiar_metas_no_mueve_saldos(service, store):
    await service.add_income(
        1_000_000, budget_month="2026-11", confirm=True, operation_id="op-sal-m1"
    )
    before = _balances(store)
    goal = await service.create_goal("Ahorro", "Viaje sintético", 500_000, "op-meta-0004")
    await service.update_goal(goal.reference, "op-meta-upd1", target_amount=600_000)
    await service.update_goal(goal.reference, "op-meta-upd2", action="pausar")
    assert _balances(store) == before and _gap(store) == 0


async def test_avance_igual_al_saldo_y_lograda_al_cruzar(store):
    early = LedgerService(store, today=lambda: date(2026, 11, 2), rate_range=RateRange(300, 1000))
    service = LedgerService(store, today=lambda: TODAY, rate_range=RateRange(300, 1000))
    goal = await early.create_goal(
        "Ahorro", "Viaje sintético", 500_000, "op-meta-0005", target_date="2027-06-30"
    )
    assert goal.balance == 0 and goal.missing == 500_000 and goal.percent == 0
    await service.add_income(
        1_000_000,
        income_date="2026-11-05",
        budget_month="2026-11",
        confirm=True,
        operation_id="op-sal-m2",
    )
    progress = (await service.get_goal_progress()).items[0]
    status = await service.get_bolsa_status("Ahorro")
    assert progress.balance == status.balance == 300_000  # una sola fuente (11.2)
    assert (status.goal.reference, status.goal.percent, status.goal.missing) == ("M-1", 60, 200_000)
    assert progress.percent == 60 and progress.status == "activa"
    await service.add_income(
        1_000_000,
        income_date="2026-11-08",
        budget_month="2026-11",
        confirm=True,
        operation_id="op-sal-m3",
    )
    reached = (await service.get_goal_progress("Ahorro")).items[0]
    assert (
        reached.status == "lograda" and reached.achieved_on == "2026-11-08"
    )  # fecha del movimiento
    assert reached.excess == 100_000  # RN-29: se queda en la bolsa
    # gastar después no la revierte (RN-24)
    await service.add_expense(550_000, "op-gasto-m1", pocket="Ahorro")
    after = (await service.get_goal_progress("Ahorro")).items[0]
    assert after.status == "lograda" and after.balance == 50_000 and after.percent == 10
    # anular el ingreso que la cruzó tampoco la revierte ([PROPUESTO])
    await service.void_transaction("I-2", "prueba sintética", "op-void-m1", confirm=True)
    assert (await service.get_goal_progress("Ahorro")).items[0].status == "lograda"


async def test_la_fecha_de_logro_nunca_es_anterior_a_la_meta(service, store):
    await service.create_goal("Ahorro", "Viaje sintético", 100_000, "op-meta-0015")
    await service.add_income(
        1_000_000,
        income_date="2026-11-01",
        budget_month="2026-11",
        confirm=True,
        operation_id="op-sal-m8",
    )
    assert store.goals[0].achieved_on == TODAY  # el ingreso es anterior a la meta


async def test_lograda_al_crear_si_el_saldo_ya_alcanza(service, store):
    await service.add_income(
        1_000_000, budget_month="2026-11", confirm=True, operation_id="op-sal-m4"
    )
    goal = await service.create_goal("Ahorro", "Fondo sintético", 200_000, "op-meta-0006")
    assert (
        goal.status == "lograda" and goal.achieved_on == "2026-11-11" and "excedente" in goal.note
    )
    assert store.goals[0].status is GoalStatus.ACHIEVED


async def test_lograda_al_anular_un_gasto_y_al_bajar_el_objetivo(service, store):
    await service.add_income(
        1_000_000, budget_month="2026-11", confirm=True, operation_id="op-sal-m5"
    )
    await service.add_expense(250_000, "op-gasto-m2", pocket="Ahorro")
    goal = await service.create_goal("Ahorro", "Viaje sintético", 100_000, "op-meta-0007")
    assert goal.status == "activa"  # saldo 50 000
    await service.void_transaction("G-1", "gasto sintético mal", "op-void-m2", confirm=True)
    assert (await service.get_goal_progress()).items == []  # ya no está activa
    assert store.goals[0].status is GoalStatus.ACHIEVED and store.goals[0].achieved_on == TODAY
    other = await service.create_goal("Ahorro", "Otra sintética", 900_000, "op-meta-0008")
    lowered = await service.update_goal(other.reference, "op-meta-upd3", target_amount=250_000)
    assert lowered.status == "lograda"


async def test_pausar_reactivar_y_lograda_final(service, store):
    goal = await service.create_goal("Ahorro", "Viaje sintético", 500_000, "op-meta-0009")
    await service.update_goal(goal.reference, "op-meta-upd4", action="pausar")
    second = await service.create_goal("Ahorro", "Carro sintético", 900_000, "op-meta-0010")
    with pytest.raises(GoalAlreadyActive, match=second.reference):
        await service.update_goal(goal.reference, "op-meta-upd5", action="reactivar")
    await service.add_income(
        4_000_000, budget_month="2026-11", confirm=True, operation_id="op-sal-m6"
    )
    assert next(g for g in store.goals if g.id == 2).status is GoalStatus.ACHIEVED
    with pytest.raises(GoalClosed, match="lograda"):
        await service.update_goal(second.reference, "op-meta-upd6", action="pausar")
    with pytest.raises(GoalClosed, match="lograda"):
        await service.update_goal(second.reference, "op-meta-upd7", target_amount=1)
    # la pausada no se logró sola; al reactivarla sí (el saldo ya alcanza)
    assert next(g for g in store.goals if g.id == 1).status is GoalStatus.PAUSED
    revived = await service.update_goal(goal.reference, "op-meta-upd8", action="reactivar")
    assert revived.status == "lograda"


async def test_archivar_la_bolsa_archiva_su_meta(service, store):
    await _create(service, "Viaje", 0, month="2026-11")
    goal = await service.create_goal("Viaje", "Playa sintética", 300_000, "op-meta-0011")
    result = await _archive(service, "Viaje")
    assert result.archived_goals == [goal.reference]
    assert (await service.get_goal_progress()).items == []
    with pytest.raises(GoalClosed, match="archivada"):
        await service.update_goal(goal.reference, "op-meta-upd9", action="pausar")


async def test_variacion_neta_rn_28(store):
    service = LedgerService(store, today=lambda: date(2027, 2, 15), rate_range=RateRange(300, 1000))
    for month in ("2026-11", "2026-12", "2027-01", "2027-02"):
        await service.add_income(
            100_000,
            income_date="2026-11-01",
            budget_month=month,
            confirm=True,
            operation_id=f"op-sal-{month}",
        )
    await service.create_goal("Ahorro", "Viaje sintético", 900_000, "op-meta-0012")
    item = (await service.get_goal_progress()).items[0]
    assert (item.months_considered, item.avg_monthly_net_change, item.projectable) == (
        3,
        30_000,
        True,
    )


async def test_contexto_del_extra_incluye_metas_sin_ids(service, store):
    await service.add_income(
        1_000_000, budget_month="2026-11", confirm=True, operation_id="op-sal-m7"
    )
    await service.create_goal("Ahorro", "Viaje sintético", 600_000, "op-meta-0013")
    extra = await service.register_extra_income(40_000, "op-extra-ctx1")
    context = await service.get_allocation_context(extra.reference)
    assert [g.model_dump() for g in context.goals] == [
        {"pocket": "Ahorro", "target_amount": 600_000, "balance": 300_000, "percent": 50}
    ]


async def test_metas_idempotentes(service, store):
    first = await service.create_goal("Ahorro", "Viaje sintético", 500_000, "op-meta-0014")
    assert await service.create_goal("Ahorro", "Viaje sintético", 500_000, "op-meta-0014") == first
    assert len(store.goals) == 1
    with pytest.raises(IdempotencyConflict):
        await service.create_goal("Ahorro", "Viaje sintético", 400_000, "op-meta-0014")


async def test_registros_y_errores_sin_montos_ni_nombres(service, store, caplog):
    caplog.set_level(logging.DEBUG)
    await service.add_income(
        777_777, budget_month="2026-11", confirm=True, operation_id="op-sal-log"
    )
    await _create(service, "Bolsa secreta", 10, month="2026-11")
    await service.create_goal("Ahorro", "Meta confidencial", 654_321, "op-meta-log1")
    errors = []
    for call in (
        service.create_goal("Ahorro", "Meta confidencial", 654_321, "op-meta-log2"),
        service.archive_bolsa("Ahorro"),
        service.create_goal("Gustos", "Meta confidencial", 111_111, "op-meta-log3"),
    ):
        with pytest.raises(DomainError) as exc:
            await call
        errors.append(exc.value.message)
    text = caplog.text + " ".join(errors)
    for secret in ("777777", "777.777", "654321", "654.321", "111111", "confidencial", "secreta"):
        assert secret not in text, secret
