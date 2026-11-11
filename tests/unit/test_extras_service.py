"""Servicio de extras y gastos fijos (Hito 6) con almacén en memoria. Datos sintéticos."""

import logging
from datetime import date

import pytest

from puro_pockets.domain.balances import integrity_gap
from puro_pockets.domain.errors import (
    DomainError,
    ExtraAlreadyDistributed,
    IdempotencyConflict,
    MovementVoided,
    NotAnExtra,
    PreviewRequired,
    RecurringAlreadyPaid,
    RecurringInactive,
    RecurringNameTaken,
)
from puro_pockets.domain.money import RateRange
from puro_pockets.domain.months import Month
from puro_pockets.services.ledger import LedgerService
from tests.fakes import InMemoryLedgerStore

pytestmark = pytest.mark.anyio

TODAY = date(2026, 11, 10)
NOV = Month(2026, 11)
P_50_30_20 = {1: 50, 2: 30, 3: 20}
SECRET_AMOUNTS = ("40000", "40.000", "27999", "12001", "55555", "123.45")


@pytest.fixture
def store():
    store = InMemoryLedgerStore()
    store.replace_allocation(NOV, P_50_30_20)
    return store


@pytest.fixture
def service(store):
    return LedgerService(store, today=lambda: TODAY, rate_range=RateRange(300, 1000))


def _gap(store):
    return integrity_gap(
        store.distributed_income_total(),
        store.expense_total(),
        store.list_pockets(),
        store.allocation_entries(),
        store.expense_entries(),
    )


async def _extra(service, amount=40_000, op="op-extra-0001", **kw):
    return await service.register_extra_income(amount, op, **kw)


async def _preview(service, ref, shares):
    return await service.confirm_allocation(ref, shares)


async def _confirm(service, ref, shares, op="op-reparto-001", token=None):
    if token is None:
        token = (await _preview(service, ref, shares)).preview_token
    return await service.confirm_allocation(
        ref, shares, confirm=True, operation_id=op, preview_token=token
    )


# --- Ingreso extra (RN-04 a RN-09) ---


async def test_extra_queda_pendiente_en_el_mes_de_su_fecha_y_no_suma_a_bolsas(service, store):
    result = await _extra(service, income_date="2026-10-31", source="venta sintética")
    assert result.reference == "I-1" and result.kind == "extra"
    assert result.budget_month == "2026-10"  # RN-09: el mes en que entra (no el siguiente)
    assert result.allocation_status == "pendiente"
    assert store.lines == [] and store.allocation_entries() == []
    assert store.distributed_income_total() == 0  # fuera del invariante (11.4)
    summary = await service.get_summary("2026-10")
    assert summary.income_total == 0 and summary.extra_income_total == 0
    assert summary.unassigned.count == 1 and summary.unassigned.total_crc == 40_000
    assert summary.unassigned.references == ["I-1"]
    assert all(p.assigned == 0 for p in summary.pockets)
    listing = await service.list_transactions()
    assert listing.items[0].allocation_status == "pendiente"
    assert listing.items[0].description == "venta sintética"
    assert listing.unassigned.count == 1


async def test_extra_en_dolares_exige_tipo_de_cambio_y_aparte_en_sin_asignar(service, store):
    with pytest.raises(DomainError, match="Falta el tipo de cambio"):
        await _extra(service, "100.00", currency="USD")
    assert store.incomes == []
    await _extra(service, "100.00", "op-extra-usd1", currency="USD", exchange_rate="512.34")
    await _extra(service, 1_000, "op-extra-crc1")
    unassigned = (await service.get_summary()).unassigned
    assert unassigned.count == 2 and unassigned.total_crc == 51_234 + 1_000
    assert unassigned.usd_count == 1 and unassigned.usd_total == "100.00"


async def test_extra_fecha_futura_y_sin_clave(service):
    with pytest.raises(DomainError, match="futura"):
        await _extra(service, income_date="2026-11-11")
    with pytest.raises(DomainError, match="operation_id"):
        await service.register_extra_income(40_000, None)


async def test_extra_idempotente(service, store):
    first = await _extra(service)
    assert await _extra(service) == first
    assert len(store.incomes) == 1
    with pytest.raises(IdempotencyConflict):
        await _extra(service, 40_001)


# --- Contexto (RN-05, RN-36) ---


async def test_contexto_solo_agregados_con_fijos_y_extras_previos(service, store):
    await service.add_income(
        1_000_000, budget_month="2026-11", confirm=True, operation_id="op-sal-1"
    )
    await service.add_expense(30_000, "op-gasto-001", pocket="Gustos", description="cine sintético")
    await service.manage_recurring(
        "crear",
        "op-fijo-0001",
        name="Alquiler sintético",
        amount=300_000,
        day_of_month=1,
        pocket="Necesidades",
    )
    await service.manage_recurring(
        "crear",
        "op-fijo-0002",
        name="Nube sintética",
        amount="12.50",
        currency="USD",
        day_of_month=28,
        pocket="Gustos",
    )
    old = await _extra(service, 10_000, "op-extra-old1", income_date="2026-11-01")
    await _confirm(service, old.reference, [("Ahorro", 70), ("Gustos", 30)], "op-reparto-old")
    new = await _extra(service, 40_000, "op-extra-new1")

    context = await service.get_allocation_context(new.reference)
    assert context.extra.reference == new.reference and context.month == "2026-11"
    assert context.extra.allocation_status == "pendiente"
    assert context.percentages_source_month == "2026-11"
    by_name = {p.pocket: p for p in context.pockets}
    assert by_name["Gustos"].percentage == 20 and by_name["Gustos"].spent == 30_000
    assert by_name["Gustos"].budget == 200_000 + 3_000  # salario + extra repartido, no el pendiente
    assert by_name["Gustos"].available == 173_000
    assert by_name["Ahorro"].balance == 300_000 + 7_000 and by_name["Ahorro"].available is None
    recurring = context.recurring_pending
    assert recurring.count == 2 and recurring.overdue_count == 1  # el del día 1 ya venció
    assert recurring.total_crc == 300_000  # el de USD no se convierte
    assert recurring.usd_count == 1 and recurring.usd_total == "12.50"
    assert [r.model_dump() for r in context.recent_extras] == [
        {
            "budget_month": "2026-11",
            "shares": [
                {"pocket": "Ahorro", "percentage": 70},
                {"pocket": "Gustos", "percentage": 30},
            ],
        }
    ]
    dumped = context.model_dump_json()
    assert "cine sintético" not in dumped and '"id"' not in dumped  # sin descripciones ni ids


async def test_contexto_de_algo_que_no_es_extra(service, store):
    await service.add_income(90_000, confirm=True, operation_id="op-sal-0002")
    with pytest.raises(NotAnExtra):
        await service.get_allocation_context("I-1")
    with pytest.raises(NotAnExtra):
        await service.get_allocation_context("G-1")
    with pytest.raises(DomainError, match="No existe"):
        await service.get_allocation_context("I-99")


# --- confirm_allocation (RN-01, RN-07, RN-08) ---


async def test_vista_previa_no_guarda_y_confirmar_reparte_con_residuo(service, store):
    extra = await _extra(service, 40_001)
    preview = await _preview(service, extra.reference, [("Necesidades", 50), ("Ahorro", 50)])
    assert not preview.saved and preview.preview_token and store.lines == []
    assert [(i.pocket, i.percentage, i.amount) for i in preview.items] == [
        ("Necesidades", 50, 20_000),
        ("Ahorro", 50, 20_001),  # RN-08: la última que recibe absorbe el residuo
    ]
    saved = await _confirm(service, extra.reference, [("Necesidades", 50), ("Ahorro", 50)])
    assert saved.saved and saved.allocation_status == "repartido" and saved.preview_token is None
    assert sum(i.amount for i in saved.items) == 40_001
    assert [(line.percentage, line.amount) for _, line in store.lines] == [
        (50, 20_000),
        (50, 20_001),
    ]
    summary = await service.get_summary()
    assert summary.unassigned.count == 0 and summary.extra_income_total == 40_001
    assert _gap(store) == 0


async def test_cien_por_ciento_a_una_bolsa_personalizada(store):
    from puro_pockets.domain.pockets import Behavior, Pocket

    store.pockets.append(Pocket(4, "Emergencia", Behavior.ACUMULABLE))
    service = LedgerService(store, today=lambda: TODAY, rate_range=RateRange(300, 1000))
    extra = await _extra(service, 25_000)
    saved = await _confirm(service, extra.reference, [("emergencia", 100)])
    assert [(i.pocket, i.amount) for i in saved.items] == [("Emergencia", 25_000)]  # RN-07


@pytest.mark.parametrize(
    ("shares", "message"),
    [
        ([("Ahorro", 60), ("Gustos", 30)], "suman 90"),
        ([("Inventada", 100)], "no existe o está archivada"),
        ([("Ahorro", 99.5), ("Gustos", 0.5)], "entero entre 0 y 100"),
    ],
)
async def test_reparto_invalido_no_guarda(service, store, shares, message):
    extra = await _extra(service)
    with pytest.raises(DomainError, match=message):
        await _preview(service, extra.reference, shares)
    with pytest.raises(DomainError, match=message):
        await service.confirm_allocation(
            extra.reference, shares, confirm=True, operation_id="op-reparto-bad", preview_token="x"
        )
    assert store.lines == [] and store.operations.keys() == {"op-extra-0001"}


async def test_bolsa_inactiva_no_recibe(store):
    from dataclasses import replace

    store.pockets[2] = replace(store.pockets[2], active=False)  # Gustos archivada
    service = LedgerService(store, today=lambda: TODAY, rate_range=RateRange(300, 1000))
    extra = await _extra(service)
    with pytest.raises(DomainError, match="no existe o está archivada"):
        await _preview(service, extra.reference, [("Gustos", 100)])


async def test_confirmar_sin_vista_previa_o_con_otra_ficha_se_rechaza(service, store):
    extra = await _extra(service)
    shares = [("Ahorro", 100)]
    with pytest.raises(PreviewRequired):
        await service.confirm_allocation(
            extra.reference, shares, confirm=True, operation_id="op-reparto-001"
        )
    other = (await _preview(service, extra.reference, [("Gustos", 100)])).preview_token
    with pytest.raises(PreviewRequired):
        await _confirm(service, extra.reference, shares, token=other)
    with pytest.raises(DomainError, match="operation_id"):
        await service.confirm_allocation(extra.reference, shares, confirm=True)
    assert store.lines == [] and store.pending_extras()


async def test_repartir_dos_veces_el_mismo_extra(service, store):
    extra = await _extra(service)
    first = await _confirm(service, extra.reference, [("Ahorro", 100)])
    # Reintento con la misma clave: misma respuesta, sin duplicar
    again = await service.confirm_allocation(
        extra.reference, [("Ahorro", 100)], True, "op-reparto-001", "ignorada-en-reintento"
    )
    assert again == first and len(store.lines) == 1
    with pytest.raises(ExtraAlreadyDistributed, match="anúlalo"):
        await _preview(service, extra.reference, [("Gustos", 100)])
    with pytest.raises(ExtraAlreadyDistributed):
        await service.confirm_allocation(
            extra.reference, [("Gustos", 100)], True, "op-reparto-002", "x"
        )
    assert len(store.lines) == 1


async def test_anular_extra_repartido_revierte_y_se_registra_de_nuevo(service, store):
    extra = await _extra(service)
    await _confirm(service, extra.reference, [("Gustos", 100)])
    await service.add_expense(39_000, "op-gasto-gus1", pocket="Gustos")
    preview = await service.void_transaction(extra.reference, "monto mal", "op-void-00001")
    assert preview.movement == "extra" and [n.pocket for n in preview.negative_pockets] == [
        "Gustos"
    ]
    await service.void_transaction(extra.reference, "monto mal", "op-void-00001", confirm=True)
    assert store.allocation_entries() == [] and _gap(store) == 0
    with pytest.raises(MovementVoided):
        await _preview(service, extra.reference, [("Gustos", 100)])
    fixed = await _extra(service, 45_000, "op-extra-0002")
    await _confirm(service, fixed.reference, [("Gustos", 100)], "op-reparto-002")
    assert (await service.get_bolsa_status("Gustos")).available == 6_000


async def test_anular_extra_pendiente_lo_quita_de_sin_asignar(service, store):
    extra = await _extra(service)
    result = await service.void_transaction(
        extra.reference, "duplicado", "op-void-00002", confirm=True
    )
    assert "sin asignar" in result.warning and result.negative_pockets == []
    assert (await service.get_summary()).unassigned.count == 0


# --- Gastos fijos (RN-35, RN-36) ---


async def _fixed(service, op="op-fijo-0001", **kw):
    data = {
        "name": "Internet sintético",
        "amount": 25_000,
        "day_of_month": 15,
        "pocket": "Necesidades",
    }
    data.update(kw)
    return await service.manage_recurring("crear", op, **data)


async def test_crear_listar_y_pagar_con_el_monto_de_la_plantilla(service, store):
    created = await _fixed(service)
    item = created.items[0]
    assert created.saved and item.reference == "F-1" and item.start_month == "2026-11"
    pending = await service.list_pending_recurring()
    assert [(p.reference, p.amount_crc, p.due_date, p.overdue) for p in pending.pending] == [
        ("F-1", 25_000, "2026-11-15", False)
    ]
    paid = await service.add_expense(operation_id="op-pago-0001", recurring="f-1")
    assert paid.recurring == "F-1" and paid.amount_crc == 25_000 and paid.pocket == "Necesidades"
    after = await service.list_pending_recurring()
    assert after.pending == [] and after.paid[0].expense_reference == paid.reference
    listing = await service.list_transactions(type="gasto")
    assert listing.items[0].recurring == "F-1"


async def test_pago_con_otro_monto_y_por_nombre(service):
    await _fixed(service)
    paid = await service.add_expense(26_500, "op-pago-0002", recurring="internet SINTÉTICO")
    assert paid.amount_crc == 26_500 and paid.recurring == "F-1"


async def test_dos_pagos_vigentes_del_mismo_fijo_en_un_mes(service, store):
    await _fixed(service)
    await service.add_expense(operation_id="op-pago-0001", recurring="F-1")
    with pytest.raises(RecurringAlreadyPaid, match="F-1.*2026-11"):
        await service.add_expense(operation_id="op-pago-0002", recurring="F-1")
    assert len(store.expenses) == 1
    # Anulado el pago, vuelve a figurar como pendiente y se puede pagar de nuevo
    voided = await service.void_transaction("G-1", "pago duplicado", "op-void-00003", confirm=True)
    assert "vuelve a quedar pendiente" in voided.warning
    assert [p.reference for p in (await service.list_pending_recurring()).pending] == ["F-1"]
    await service.add_expense(operation_id="op-pago-0003", recurring="F-1")


async def test_fijo_en_usd_exige_el_tipo_de_cambio_de_cada_pago(service, store):
    await _fixed(service, name="Nube sintética", amount="12.50", currency="USD")
    pending = (await service.list_pending_recurring()).pending[0]
    assert pending.amount == "12.50" and pending.amount_crc is None  # no se convierte
    with pytest.raises(DomainError, match="Falta el tipo de cambio"):
        await service.add_expense(operation_id="op-pago-usd1", recurring="F-1")
    first = await service.add_expense(
        operation_id="op-pago-usd2", recurring="F-1", exchange_rate="500.00"
    )
    assert first.amount_crc == 6_250
    # el mes siguiente no reutiliza el tipo de cambio anterior: sigue exigiéndolo
    later = LedgerService(store, today=lambda: date(2026, 12, 2), rate_range=RateRange(300, 1000))
    with pytest.raises(DomainError, match="Falta el tipo de cambio"):
        await later.add_expense(operation_id="op-pago-usd3", recurring="F-1")


async def test_fijo_dia_31_vence_el_ultimo_dia_de_febrero(store):
    service = LedgerService(store, today=lambda: date(2027, 3, 1), rate_range=RateRange(300, 1000))
    await service.manage_recurring(
        "crear",
        "op-fijo-0031",
        name="Seguro sintético",
        amount=8_000,
        day_of_month=31,
        pocket="Necesidades",
        start_month="2027-01",
    )
    feb = (await service.list_pending_recurring("2027-02")).pending[0]
    assert feb.due_date == "2027-02-28" and feb.overdue


async def test_plantilla_desactivada(service, store):
    await _fixed(service)
    result = await service.manage_recurring("desactivar", "op-fijo-off1", recurring="F-1")
    assert result.saved and not result.items[0].active
    assert (await service.list_pending_recurring()).pending == []
    with pytest.raises(RecurringInactive):
        await service.add_expense(operation_id="op-pago-0004", recurring="F-1")
    with pytest.raises(RecurringInactive):
        await service.manage_recurring("actualizar", "op-fijo-upd9", recurring="F-1", amount=1)
    with pytest.raises(RecurringInactive):
        await service.manage_recurring("desactivar", "op-fijo-off2", recurring="F-1")
    assert (await service.manage_recurring("listar")).items == []
    assert len((await service.manage_recurring("listar", include_inactive=True)).items) == 1
    # el nombre queda libre para una plantilla nueva
    await _fixed(service, "op-fijo-0002")


async def test_nombre_unico_sin_distinguir_mayusculas(service):
    await _fixed(service)
    with pytest.raises(RecurringNameTaken):
        await _fixed(service, "op-fijo-0002", name="INTERNET sintético")


async def test_cambiar_el_monto_afecta_solo_meses_futuros(service, store):
    await _fixed(service)
    result = await service.manage_recurring(
        "actualizar", "op-fijo-upd1", recurring="F-1", amount=30_000, day_of_month=20
    )
    item = result.items[0]
    assert item.amount == "25000" and item.day_of_month == 20
    assert item.scheduled_change.model_dump() == {"from_month": "2026-12", "amount": "30000"}
    assert "2026-12" in result.note
    assert (await service.list_pending_recurring()).pending[0].amount_crc == 25_000
    assert (await service.list_pending_recurring("2026-12")).pending[0].amount_crc == 30_000
    with pytest.raises(DomainError, match="moneda"):
        await service.manage_recurring(
            "actualizar", "op-fijo-upd2", recurring="F-1", currency="USD"
        )
    with pytest.raises(DomainError, match="Indica qué cambiar"):
        await service.manage_recurring("actualizar", "op-fijo-upd3", recurring="F-1")


async def test_pago_antes_del_mes_de_inicio(service):
    await _fixed(service, start_month="2026-12")
    with pytest.raises(DomainError, match="empieza en 2026-12"):
        await service.add_expense(operation_id="op-pago-0005", recurring="F-1")


async def test_escrituras_de_plantillas_idempotentes(service, store):
    first = await _fixed(service)
    assert await _fixed(service) == first and len(store.recurring) == 1
    with pytest.raises(IdempotencyConflict):
        await _fixed(service, amount=99)
    with pytest.raises(DomainError, match="operation_id"):
        await service.manage_recurring("crear", None, name="X sintético", amount=1, day_of_month=1)
    with pytest.raises(DomainError, match="acción"):
        await service.manage_recurring("borrar", "op-fijo-0009")


async def test_registros_y_errores_sin_montos_ni_descripciones(service, caplog):
    caplog.set_level(logging.DEBUG)
    extra = await _extra(service, 55_555, "op-extra-log1", source="herencia sintética secreta")
    await _confirm(service, extra.reference, [("Ahorro", 100)], "op-reparto-log")
    await service.manage_recurring(
        "crear",
        "op-fijo-log1",
        name="Gimnasio secreto",
        amount=27_999,
        day_of_month=3,
        pocket="Gustos",
    )
    await service.add_expense(12_001, "op-pago-log1", recurring="F-1", description="nota secreta")
    errors = []
    for call in (
        service.add_expense(12_001, "op-pago-log2", recurring="F-1"),
        _extra(service, "123.45", "op-extra-log2", currency="USD"),
        service.manage_recurring(
            "crear",
            "op-fijo-log2",
            name="gimnasio SECRETO",
            amount=1,
            day_of_month=3,
            pocket="Gustos",
        ),
    ):
        with pytest.raises(DomainError) as exc:
            await call
        errors.append(exc.value.message)
    text = caplog.text + " ".join(errors)
    for secret in (*SECRET_AMOUNTS, "secret", "herencia", "Gimnasio"):
        assert secret not in text, secret
