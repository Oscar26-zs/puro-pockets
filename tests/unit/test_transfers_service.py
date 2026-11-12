"""Servicio de transferencias (Hito 8) con almacén en memoria. Datos sintéticos.

Incluye las pruebas pendientes del Hito 7 (vaciar una bolsa con una transferencia y archivarla).
La concurrencia real (dos transferencias simultáneas) se prueba contra Postgres en
tests/integration/test_transfers_sql_store.py.
"""

import logging
from datetime import date

import pytest

from puro_pockets.domain.balances import integrity_gap, pocket_figures
from puro_pockets.domain.errors import (
    DomainError,
    IdempotencyConflict,
    PocketNotEmpty,
    PreviewRequired,
    TransferExceedsAvailable,
    TransferFromNegative,
    TransferSamePocket,
    TransfersAreFinal,
)
from puro_pockets.domain.goals import GoalStatus
from puro_pockets.domain.money import RateRange
from puro_pockets.domain.months import Month
from puro_pockets.services.ledger import LedgerService
from tests.fakes import InMemoryLedgerStore

pytestmark = pytest.mark.anyio

TODAY = date(2026, 11, 11)
NOV = Month(2026, 11)
SALARY = 1_000_000  # Necesidades 500 000, Ahorro 300 000, Gustos 200 000 en noviembre
NOTE = "nota privada sintética"


@pytest.fixture
def store():
    store = InMemoryLedgerStore()
    store.replace_allocation(NOV, {1: 50, 2: 30, 3: 20})
    return store


@pytest.fixture
def service(store):
    return LedgerService(store, today=lambda: TODAY, rate_range=RateRange(300, 1000))


async def _salary(service, op="op-salario-01"):
    await service.add_income(
        SALARY, income_date="2026-10-31", budget_month="2026-11", confirm=True, operation_id=op
    )


async def _transfer(
    service, source, target, amount, reason="reasignacion", op="op-transf-01", **kw
):
    preview = await service.preview_transfer(source, target, amount, reason, **kw)
    return await service.transfer_between_bolsas(
        source,
        target,
        amount,
        reason,
        confirm=True,
        operation_id=op,
        preview_token=preview.preview_token,
        **kw,
    )


def _amounts(store):
    data = (store.allocation_entries(), store.expense_entries(), store.transfer_entries())
    return {p.name: pocket_figures(p, NOV, *data).amount for p in store.list_pockets()}


def _gap(store):
    return integrity_gap(
        store.distributed_income_total(),
        store.expense_total(),
        store.list_pockets(),
        store.allocation_entries(),
        store.expense_entries(),
        store.transfer_entries(),
    )


# --- Vista previa y confirmación ---


async def test_vista_previa_no_guarda_nada_y_muestra_ambas_bolsas(service, store):
    await _salary(service)
    writes = store.writes
    preview = await service.preview_transfer("necesidades", "GUSTOS", 50_000, "ajuste", NOTE)
    assert store.transfers == [] and store.writes == writes
    assert preview.saved is False and preview.reference is None and preview.preview_token
    assert (preview.date, preview.month, preview.note) == ("2026-11-11", "2026-11", NOTE)
    src, dst = preview.from_pocket, preview.to_pocket
    assert (src.pocket, src.balance_kind, src.before, src.after) == (
        "Necesidades",
        "disponible_del_mes",
        500_000,
        450_000,
    )
    assert (src.adjusted_budget_before, src.adjusted_budget_after) == (500_000, 450_000)
    assert (dst.before, dst.after, dst.adjusted_budget_after) == (200_000, 250_000, 250_000)
    # transfer_between_bolsas sin confirm devuelve la misma vista previa
    same = await service.transfer_between_bolsas("Necesidades", "Gustos", 50_000, "ajuste", NOTE)
    assert same.preview_token == preview.preview_token and store.transfers == []


async def test_acumulable_muestra_saldo_sin_presupuesto_ajustado(service):
    await _salary(service)
    preview = await service.preview_transfer("Ahorro", "Gustos", 1_000, "reasignacion")
    side = preview.from_pocket
    assert (side.balance_kind, side.before, side.after) == ("saldo", 300_000, 299_000)
    assert side.adjusted_budget_before is None and side.adjusted_budget_after is None


async def test_confirmar_guarda_t1_sin_crear_ni_destruir_dinero(service, store):
    await _salary(service)
    before = _amounts(store)
    result = await _transfer(service, "Necesidades", "Ahorro", 120_000, note=NOTE)
    assert result.saved and result.reference == "T-1" and result.preview_token is None
    assert len(store.transfers) == 1 and store.transfers[0].note == NOTE
    after = _amounts(store)
    assert after["Necesidades"] == before["Necesidades"] - 120_000
    assert after["Ahorro"] == before["Ahorro"] + 120_000
    assert sum(after.values()) == sum(before.values()) and _gap(store) == 0


async def test_confirm_sin_vista_previa_u_otra_ficha_se_rechaza(service, store):
    await _salary(service)
    with pytest.raises(PreviewRequired, match="datos de la transferencia"):
        await service.transfer_between_bolsas(
            "Necesidades", "Gustos", 1_000, "ajuste", confirm=True, operation_id="op-sin-ficha"
        )
    other = await service.preview_transfer("Necesidades", "Gustos", 2_000, "ajuste")
    with pytest.raises(PreviewRequired):
        await service.transfer_between_bolsas(
            "Necesidades",
            "Gustos",
            1_000,
            "ajuste",
            confirm=True,
            operation_id="op-otra-ficha",
            preview_token=other.preview_token,
        )
    assert store.transfers == []


async def test_idempotencia_misma_clave(service, store):
    await _salary(service)
    first = await _transfer(service, "Necesidades", "Gustos", 10_000, op="op-idem-0001")
    again = await _transfer(service, "Necesidades", "Gustos", 10_000, op="op-idem-0001")
    assert again == first and len(store.transfers) == 1
    with pytest.raises(IdempotencyConflict):
        await _transfer(service, "Necesidades", "Gustos", 10_001, op="op-idem-0001")
    with pytest.raises(IdempotencyConflict):
        await _transfer(service, "Necesidades", "Gustos", 10_000, "ajuste", op="op-idem-0001")
    assert len(store.transfers) == 1


# --- "Terminado cuando" del Hito 8 y RN-37 ---


async def test_gustos_en_negativo_se_cubre_desde_necesidades(service, store):
    await _salary(service)
    spent = await service.add_expense(230_000, "op-gasto-0001", pocket="Gustos")
    assert spent.overspent and spent.pocket_balance.balance == -30_000
    assert [f.pocket for f in spent.available_pockets] == ["Necesidades", "Ahorro"]
    assert "preview_transfer" in spent.warning and "cubrir_sobregasto" in spent.warning
    result = await _transfer(service, "Necesidades", "Gustos", 30_000, "cubrir_sobregasto")
    assert result.to_pocket.after == 0 and result.warning is None
    status = await service.get_bolsa_status("Gustos")
    assert (status.assigned, status.transfers_in, status.adjusted_budget) == (
        200_000,
        30_000,
        230_000,
    )
    assert status.available == 0 and status.negative is False
    assert status.percent_used == 100 and status.percent_used_original == 115
    listed = await service.list_transactions(type="transferencia")
    assert [(i.reference, i.from_pocket, i.to_pocket, i.reason) for i in listed.items] == [
        ("T-1", "Necesidades", "Gustos", "cubrir_sobregasto")
    ]


async def test_advertencia_de_sobregasto_usa_los_calculos_con_transferencias(service):
    await _salary(service)
    await _transfer(service, "Necesidades", "Ahorro", 500_000, op="op-vaciar-nec")
    spent = await service.add_expense(250_000, "op-gasto-0002", pocket="Gustos")
    # Necesidades quedó en 0 por la transferencia: ya no es candidata
    assert [f.pocket for f in spent.available_pockets] == ["Ahorro"]


async def test_destino_que_sigue_en_negativo_se_avisa(service):
    await _salary(service)
    await service.add_expense(260_000, "op-gasto-0003", pocket="Gustos")
    result = await service.preview_transfer("Necesidades", "Gustos", 10_000, "cubrir_sobregasto")
    assert result.to_pocket.after == -50_000 and "sigue en negativo" in result.warning


# --- Negativas ---


async def test_origen_igual_al_destino(service):
    await _salary(service)
    with pytest.raises(TransferSamePocket):
        await service.preview_transfer("Gustos", "gustos", 1_000, "ajuste")


@pytest.mark.parametrize("amount", [0, -5_000, 1.5, "1000", True])
async def test_monto_cero_negativo_o_no_entero(service, amount):
    await _salary(service)
    with pytest.raises(DomainError, match="colones|mayor que 0"):
        await service.preview_transfer("Necesidades", "Gustos", amount, "ajuste")


async def test_mas_de_lo_disponible_en_consumo_y_en_acumulable(service):
    await _salary(service)
    with pytest.raises(TransferExceedsAvailable, match="disponible del mes"):
        await service.preview_transfer("Necesidades", "Gustos", 500_001, "ajuste")
    with pytest.raises(TransferExceedsAvailable, match="saldo"):
        await service.preview_transfer("Ahorro", "Gustos", 300_001, "ajuste")
    # exactamente lo disponible sí se puede
    await service.preview_transfer("Ahorro", "Gustos", 300_000, "ajuste")


async def test_origen_en_negativo(service):
    await _salary(service)
    await service.add_expense(210_000, "op-gasto-0004", pocket="Gustos")
    with pytest.raises(TransferFromNegative):
        await service.preview_transfer("Gustos", "Necesidades", 1, "ajuste")


async def test_bolsa_archivada_o_inexistente(service, store):
    await _salary(service)
    created = await service.create_bolsa("Viaje", "consumo", percentage=0)
    await service.create_bolsa(
        "Viaje",
        "consumo",
        percentage=0,
        confirm=True,
        operation_id="op-viaje-001",
        preview_token=created.preview_token,
    )
    archive = await service.archive_bolsa("Viaje")
    await service.archive_bolsa(
        "Viaje", confirm=True, operation_id="op-viaje-arch", preview_token=archive.preview_token
    )
    for source, target in (("Viaje", "Gustos"), ("Gustos", "Viaje"), ("Inexistente", "Gustos")):
        with pytest.raises(DomainError, match="no existe o está archivada"):
            await service.preview_transfer(source, target, 1_000, "ajuste")
    assert store.transfers == []


@pytest.mark.parametrize("reason", ["cierre_de_mes", "regalo", ""])
async def test_motivo_invalido_o_reservado(service, reason):
    await _salary(service)
    with pytest.raises(DomainError, match="cubrir_sobregasto"):
        await service.preview_transfer("Necesidades", "Gustos", 1_000, reason)


@pytest.mark.parametrize("day", ["2026-11-10", "2026-11-12", "2026-10-31"])
async def test_fecha_pasada_o_futura(service, day):
    await _salary(service)
    with pytest.raises(DomainError, match="fecha de hoy"):
        await service.preview_transfer("Necesidades", "Gustos", 1_000, "ajuste", transfer_date=day)
    ok = await service.preview_transfer(
        "Necesidades", "Gustos", 1_000, "ajuste", transfer_date="2026-11-11"
    )
    assert ok.date == "2026-11-11"


async def test_nota_de_mas_de_140(service):
    await _salary(service)
    with pytest.raises(DomainError, match="140"):
        await service.preview_transfer("Necesidades", "Gustos", 1_000, "ajuste", "n" * 141)


async def test_se_vuelve_a_validar_al_confirmar(service, store):
    """Entre la vista previa y la confirmación cambió el disponible del origen: RN-42 se valida otra
    vez con lo que hay en ese momento (en Postgres, además, con las bolsas bloqueadas)."""
    await _salary(service)
    preview = await service.preview_transfer("Necesidades", "Gustos", 400_000, "ajuste")
    await service.add_expense(200_000, "op-gasto-0005", pocket="Necesidades")
    with pytest.raises(TransferExceedsAvailable):
        await service.transfer_between_bolsas(
            "Necesidades",
            "Gustos",
            400_000,
            "ajuste",
            confirm=True,
            operation_id="op-revalida-1",
            preview_token=preview.preview_token,
        )
    assert store.transfers == []


async def test_las_transferencias_no_se_anulan(service):
    await _salary(service)
    await _transfer(service, "Necesidades", "Gustos", 1_000)
    with pytest.raises(TransfersAreFinal, match="sentido contrario"):
        await service.void_transaction("T-1", "me equivoqué", "op-void-t1")


async def test_un_error_se_corrige_con_una_transferencia_inversa(service, store):
    await _salary(service)
    before = _amounts(store)
    await _transfer(service, "Necesidades", "Gustos", 75_000, op="op-ida-00001")
    await _transfer(service, "Gustos", "Necesidades", 75_000, op="op-vuelta-001")
    assert _amounts(store) == before and len(store.transfers) == 2 and _gap(store) == 0


# --- RN-58 y metas ---


async def _goal(service, target=1_000_000):
    return await service.create_goal("Ahorro", "Viaje sintético", target, "op-meta-0001")


async def test_rn58_mover_fuera_de_una_bolsa_con_meta_avisa_el_efecto(service, store):
    await _salary(service)
    await _goal(service)  # saldo 300 000 → 30 %
    preview = await service.preview_transfer("Ahorro", "Gustos", 60_000, "reasignacion")
    [effect] = preview.goal_effects
    assert (effect.reference, effect.pocket) == ("M-1", "Ahorro")
    assert (effect.percent_before, effect.percent_after) == (30, 24)
    assert (effect.missing_before, effect.missing_after) == (700_000, 760_000)
    assert not effect.completes
    assert "baja de 30 % a 24 %" in preview.warning and "Viaje sintético" not in preview.warning
    assert store.goals[0].status is GoalStatus.ACTIVE


async def test_transferencia_que_completa_la_meta_la_marca_lograda(service, store):
    await _salary(service)
    await _goal(service, target=400_000)
    preview = await service.preview_transfer("Necesidades", "Ahorro", 100_000, "reasignacion")
    assert preview.goal_effects[0].completes and "lograda" in preview.warning
    await _transfer(service, "Necesidades", "Ahorro", 100_000)
    goal = store.goals[0]
    assert goal.status is GoalStatus.ACHIEVED and goal.achieved_on == TODAY
    # sacar dinero después no la revierte (RN-24)
    await _transfer(service, "Ahorro", "Necesidades", 100_000, op="op-sacar-0001")
    assert store.goals[0].status is GoalStatus.ACHIEVED
    progress = await service.get_goal_progress("Ahorro")
    assert progress.items[0].balance == 300_000  # el avance es el saldo, con transferencias


async def test_rn28_y_avance_incluyen_transferencias(service):
    await _salary(service)
    await _goal(service)
    await _transfer(service, "Necesidades", "Ahorro", 50_000)
    progress = await service.get_goal_progress()
    status = await service.get_bolsa_status("Ahorro")
    assert progress.items[0].balance == status.balance == 350_000
    assert status.goal is not None and status.goal.percent == 35


# --- Consultas con presupuesto ajustado ---


async def test_resumen_y_contexto_muestran_el_presupuesto_ajustado(service):
    await _salary(service)
    await service.add_expense(20_000, "op-gasto-0006", pocket="Necesidades")
    await _transfer(service, "Necesidades", "Gustos", 80_000)
    summary = await service.get_summary()
    by_name = {p.pocket: p for p in summary.pockets}
    nec, gus, aho = by_name["Necesidades"], by_name["Gustos"], by_name["Ahorro"]
    assert (nec.assigned, nec.transfers_out, nec.adjusted_budget) == (500_000, 80_000, 420_000)
    assert (nec.spent, nec.available, nec.percent_used, nec.percent_used_original) == (
        20_000,
        400_000,
        4,
        4,
    )
    assert (gus.transfers_in, gus.adjusted_budget, gus.available) == (80_000, 280_000, 280_000)
    assert aho.balance == 300_000
    extra = await service.register_extra_income(50_000, "op-extra-0001", income_date="2026-11-11")
    context = await service.get_allocation_context(extra.reference)
    ctx = {p.pocket: p for p in context.pockets}
    assert (ctx["Gustos"].budget, ctx["Gustos"].transfers_in, ctx["Gustos"].adjusted_budget) == (
        200_000,
        80_000,
        280_000,
    )
    assert ctx["Necesidades"].available == 400_000


async def test_listado_filtra_por_tipo_y_bolsa_con_el_mismo_limite(service):
    await _salary(service)
    await service.add_expense(1_000, "op-gasto-0007", pocket="Gustos")
    await _transfer(service, "Necesidades", "Ahorro", 1_000, op="op-t-a-00001")
    await _transfer(service, "Gustos", "Necesidades", 500, op="op-t-b-00001")
    everything = await service.list_transactions()
    assert {i.type for i in everything.items} == {"ingreso", "gasto", "transferencia"}
    gustos = await service.list_transactions(pocket="Gustos")
    assert [i.reference for i in gustos.items] == ["T-2", "G-1"]
    only = await service.list_transactions(type="transferencia", limit=1)
    assert [i.reference for i in only.items] == ["T-2"] and only.has_more
    with pytest.raises(DomainError, match="gastos y transferencias"):
        await service.list_transactions(type="ingreso", pocket="Gustos")
    with pytest.raises(DomainError, match="transferencia"):
        await service.list_transactions(type="ajuste")


async def test_anular_un_salario_tras_transferir_avisa_negativos(service):
    """RN-59 con transferencias: el negativo se calcula con las cifras oficiales."""
    await _salary(service)
    await _transfer(service, "Ahorro", "Gustos", 300_000)
    preview = await service.void_transaction("I-1", "salario mal cargado", "op-void-sal1")
    assert {n.pocket: n.balance for n in preview.negative_pockets} == {"Ahorro": -300_000}


# --- Pruebas pendientes del Hito 7: vaciar con una transferencia y archivar (RN-18) ---


async def _archive(service, name, op="op-archivo-01"):
    preview = await service.archive_bolsa(name)
    return await service.archive_bolsa(
        name, confirm=True, operation_id=op, preview_token=preview.preview_token
    )


async def test_acumulable_con_meta_se_vacia_y_se_archiva_con_su_meta(service, store):
    await _salary(service)
    await _goal(service)
    with pytest.raises(PocketNotEmpty, match="transfer_between_bolsas") as exc:
        await service.archive_bolsa("Ahorro")
    assert "300" not in exc.value.message
    preview = await service.preview_transfer("Ahorro", "Necesidades", 300_000, "reasignacion")
    assert preview.goal_effects[0].percent_after == 0  # RN-58: aviso del efecto en la meta
    await _transfer(service, "Ahorro", "Necesidades", 300_000)
    result = await _archive(service, "Ahorro")
    assert result.saved and result.archived_goals == ["M-1"]
    assert not next(p for p in store.pockets if p.name == "Ahorro").active
    assert store.goals[0].archived and _gap(store) == 0


async def test_consumo_con_disponible_se_vacia_y_se_archiva(service, store):
    await _salary(service)
    with pytest.raises(PocketNotEmpty, match="disponible del mes"):
        await service.archive_bolsa("Gustos")
    await _transfer(service, "Gustos", "Ahorro", 200_000)
    await _archive(service, "Gustos")
    assert not next(p for p in store.pockets if p.name == "Gustos").active
    with pytest.raises(DomainError, match="no existe o está archivada"):
        await service.preview_transfer("Ahorro", "Gustos", 1, "ajuste")


async def test_consumo_en_negativo_se_cubre_y_luego_se_archiva(service, store):
    await _salary(service)
    await service.add_expense(250_000, "op-gasto-0008", pocket="Gustos")
    with pytest.raises(PocketNotEmpty, match="negativo"):
        await service.archive_bolsa("Gustos")
    await _transfer(service, "Necesidades", "Gustos", 50_000, "cubrir_sobregasto")
    await _archive(service, "Gustos")
    assert _gap(store) == 0


async def test_archivar_revalida_el_saldo_dentro_de_la_operacion(service, store):
    """Entre la vista previa del archivado y su confirmación entró dinero: se rechaza."""
    await _salary(service)
    await _transfer(service, "Gustos", "Ahorro", 200_000, op="op-vaciar-gus")
    preview = await service.archive_bolsa("Gustos")
    await _transfer(service, "Necesidades", "Gustos", 1_000, op="op-entra-gus")
    with pytest.raises(PocketNotEmpty):
        await service.archive_bolsa(
            "Gustos", confirm=True, operation_id="op-arch-gus1", preview_token=preview.preview_token
        )
    assert next(p for p in store.pockets if p.name == "Gustos").active


# --- Registros y errores ---


async def test_registros_y_errores_sin_montos_notas_ni_nombres_de_metas(service, caplog):
    caplog.set_level(logging.DEBUG)
    await _salary(service)
    await _goal(service)
    await _transfer(service, "Ahorro", "Gustos", 123_457, note=NOTE)
    errors = []
    for args in (
        ("Ahorro", "Gustos", 987_654, "ajuste", NOTE),
        ("Ahorro", "Ahorro", 5_555, "ajuste", NOTE),
        ("Ahorro", "Gustos", 5_555, "cierre_de_mes", NOTE),
        ("Ahorro", "Gustos", 5_555, "ajuste", NOTE + "x" * 140),
    ):
        with pytest.raises(DomainError) as exc:
            await service.preview_transfer(*args)
        errors.append(exc.value.message)
    text = caplog.text + " ".join(errors)
    assert "Transferencia registrada: ref=T-1" in caplog.text
    for secret in ("123457", "123 457", "123.457", "987654", "5555", NOTE, "Viaje sintético"):
        assert secret not in text, secret
