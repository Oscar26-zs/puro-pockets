"""Servicio de movimientos (Hito 5) con almacén en memoria. Datos sintéticos."""

import logging
from datetime import date

import pytest

from puro_pockets.domain.errors import DomainError, IdempotencyConflict
from puro_pockets.domain.money import RateRange
from puro_pockets.domain.months import Month
from puro_pockets.services.budget import BudgetService
from puro_pockets.services.ledger import LedgerService
from tests.fakes import InMemoryLedgerStore

pytestmark = pytest.mark.anyio

TODAY = date(2026, 11, 10)
NOV, DEC = Month(2026, 11), Month(2026, 12)
RANGE = RateRange(300, 1000)
P_50_30_20 = {1: 50, 2: 30, 3: 20}


@pytest.fixture
def store():
    return InMemoryLedgerStore()


@pytest.fixture
def service(store):
    return LedgerService(store, today=lambda: TODAY, rate_range=RANGE)


@pytest.fixture
def budget(store):
    return BudgetService(store, today=lambda: TODAY)


def _amounts(result):
    return [(i.pocket, i.percentage, i.amount) for i in result.items]


# --- US1: salario ---


async def test_salario_va_al_mes_siguiente_y_se_reparte_con_residuo(service, store):
    store.replace_allocation(DEC, P_50_30_20)
    result = await service.add_income(
        1_000_001, income_date="2026-11-10", confirm=True, operation_id="op-salario-1"
    )
    assert result.saved and result.reference == "I-1"
    assert result.budget_month == "2026-12" and result.allocation_source_month == "2026-12"
    assert _amounts(result) == [
        ("Necesidades", 50, 500_000),
        ("Ahorro", 30, 300_000),
        ("Gustos", 20, 200_001),  # RN-08: la última absorbe el residuo
    ]
    assert [(line.percentage, line.amount) for _, line in store.lines] == [
        (50, 500_000),
        (30, 300_000),
        (20, 200_001),
    ]


async def test_salario_hereda_porcentajes_e_indica_el_origen(service, store):
    store.replace_allocation(NOV, P_50_30_20)
    result = await service.add_income(90_000, confirm=True, operation_id="op-salario-2")
    assert result.budget_month == "2026-12"
    assert result.allocation_source_month == "2026-11"  # RN-03


async def test_mes_explicito(service, store):
    store.replace_allocation(NOV, P_50_30_20)
    result = await service.add_income(
        90_000, budget_month="2026-11", confirm=True, operation_id="op-salario-3"
    )
    assert result.budget_month == "2026-11"


async def test_sin_porcentajes_error_claro_y_nada_guardado(service, store):
    with pytest.raises(DomainError, match="set_allocation"):
        await service.add_income(90_000, confirm=True, operation_id="op-salario-4")
    assert store.incomes == [] and store.operations == {}


async def test_vista_previa_y_sin_confirm_no_guardan(service, store):
    store.replace_allocation(DEC, P_50_30_20)
    preview = await service.preview_income(10_001)
    unconfirmed = await service.add_income(10_001)
    assert not preview.saved and preview.reference is None
    assert not unconfirmed.saved
    assert _amounts(preview) == [
        ("Necesidades", 50, 5_000),
        ("Ahorro", 30, 3_000),
        ("Gustos", 20, 2_001),
    ]
    assert store.incomes == [] and store.writes == 1  # solo replace_allocation


async def test_salario_en_dolares_se_convierte_una_vez(service, store):
    store.replace_allocation(DEC, P_50_30_20)
    result = await service.add_income(
        "1000.00", currency="USD", exchange_rate="512.34", confirm=True, operation_id="op-usd-1"
    )
    assert (result.currency, result.original_amount, result.exchange_rate, result.amount_crc) == (
        "USD",
        "1000.00",
        "512.34",
        512_340,
    )
    row = store.incomes[0]
    assert (row.original_amount, row.exchange_rate, row.amount) == (100_000, 51_234, 512_340)


async def test_salario_usd_sin_tipo_de_cambio_y_fecha_futura(service, store):
    store.replace_allocation(DEC, P_50_30_20)
    with pytest.raises(DomainError, match="Falta el tipo de cambio"):
        await service.add_income("10.00", currency="USD", confirm=True, operation_id="op-usd-2")
    with pytest.raises(DomainError, match="futura"):
        await service.add_income(
            1_000, income_date="2026-11-11", confirm=True, operation_id="op-fut-1"
        )
    assert store.incomes == []


async def test_confirmar_sin_clave_es_error(service, store):
    store.replace_allocation(DEC, P_50_30_20)
    with pytest.raises(DomainError, match="operation_id"):
        await service.add_income(1_000, confirm=True)


async def test_porcentaje_cero_al_final_no_recibe_el_residuo(service, store):
    store.replace_allocation(DEC, {1: 50, 2: 50, 3: 0})
    result = await service.preview_income(10_001)
    assert _amounts(result) == [("Necesidades", 50, 5_000), ("Ahorro", 50, 5_001), ("Gustos", 0, 0)]


# --- US2 / US3: gastos y sobregasto ---


async def test_gasto_en_colones_en_el_mes_de_su_fecha(service, store):
    store.replace_allocation(NOV, P_50_30_20)
    await service.add_income(
        100_000, budget_month="2026-11", confirm=True, operation_id="op-inc-10"
    )
    result = await service.add_expense(
        12_500, "op-gasto-1", pocket="gustos", expense_date="2026-11-03"
    )
    assert result.reference == "G-1" and result.month == "2026-11"
    assert result.category == "pendiente de clasificar"  # RN-34
    assert (result.pocket_balance.balance, result.pocket_balance.balance_kind) == (
        7_500,
        "disponible_del_mes",
    )
    assert not result.overspent and result.warning is None and result.available_pockets == []


async def test_gasto_en_dolares_redondeo_half_up(service):
    result = await service.add_expense(
        "10.00", "op-gasto-usd", pocket="Necesidades", currency="USD", exchange_rate="512.34"
    )
    assert (result.original_amount, result.exchange_rate, result.amount_crc) == (
        "10.00",
        "512.34",
        5_123,
    )


async def test_gasto_contra_acumulable_baja_su_saldo(service, budget, store):
    await budget.load_initial_balance([("Ahorro", 50_000)], confirm=True)
    result = await service.add_expense(8_000, "op-gasto-aho", pocket="Ahorro")  # RN-33
    assert (result.pocket_balance.balance, result.pocket_balance.balance_kind) == (42_000, "saldo")


async def test_sobregasto_se_guarda_y_advierte_con_bolsas_disponibles(service, budget, store):
    await budget.load_initial_balance(
        [("Necesidades", 40_000), ("Ahorro", 90_000), ("Gustos", 10_000)], confirm=True
    )
    result = await service.add_expense(15_000, "op-sobre-1", pocket="Gustos")
    assert result.overspent and len(store.expenses) == 1  # RN-37: no se bloquea
    assert result.pocket_balance.balance == -5_000
    assert [(p.pocket, p.balance) for p in result.available_pockets] == [
        ("Necesidades", 40_000),
        ("Ahorro", 90_000),
    ]
    assert "Gustos queda en negativo" in result.warning
    summary = await service.get_summary()
    assert summary.negative_pockets == ["Gustos"]  # RN-38


async def test_categoria_y_bolsa_por_defecto(service, store):
    await service.create_category("Restaurantes", "gustos")
    result = await service.add_expense(3_000, "op-cat-1", category="restaurantes")
    assert (result.pocket, result.category) == ("Gustos", "Restaurantes")
    other = await service.add_expense(
        2_000, "op-cat-2", category="Restaurantes", pocket="Necesidades"
    )
    assert other.pocket == "Necesidades"  # RN-33: cualquier bolsa


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"amount": 0, "pocket": "Gustos"}, "mayor que 0"),
        ({"amount": -5, "pocket": "Gustos"}, "mayor que 0"),
        ({"amount": 100, "pocket": "Viaje"}, "no existe"),
        ({"amount": 100}, "Indica la bolsa"),
        ({"amount": 100, "category": "Cine"}, "create_category"),
        ({"amount": 100, "pocket": "Gustos", "expense_date": "2026-11-11"}, "futura"),
        ({"amount": "10", "pocket": "Gustos", "currency": "USD"}, "Falta el tipo de cambio"),
        ({"amount": 100, "pocket": "Gustos", "description": "x" * 121}, "120"),
    ],
)
async def test_gastos_invalidos_no_guardan(service, store, kwargs, message):
    amount = kwargs.pop("amount")
    with pytest.raises(DomainError, match=message):
        await service.add_expense(amount, "op-invalido", **kwargs)
    assert store.expenses == [] and store.operations == {}


async def test_categoria_unica_sin_distinguir_mayusculas(service):
    await service.create_category("Restaurantes", "Gustos")
    with pytest.raises(DomainError, match="Ya existe"):
        await service.create_category("restaurantes", "Necesidades")
    listing = await service.list_categories()
    assert [(c.name, c.pocket) for c in listing.items] == [("Restaurantes", "Gustos")]


# --- US5: anulación ---


async def test_anular_gasto_lo_saca_de_los_calculos_pero_sigue_en_el_historial(service, store):
    store.replace_allocation(NOV, P_50_30_20)
    await service.add_income(
        100_000, budget_month="2026-11", confirm=True, operation_id="op-inc-20"
    )
    await service.add_expense(9_000, "op-gasto-20", pocket="Gustos")
    preview = await service.void_transaction("g-1", "monto equivocado", "op-void-0")
    assert not preview.saved and not store.expenses[0].voided
    result = await service.void_transaction("G-1", "monto equivocado", "op-void-1", confirm=True)
    assert result.saved and result.movement == "gasto" and result.voided_on == "2026-11-10"
    status = await service.get_bolsa_status("Gustos")
    assert status.spent == 0 and status.available == 20_000
    listing = await service.list_transactions(type="gasto")
    assert listing.items[0].voided and listing.items[0].void_reason == "monto equivocado"
    assert len(store.expenses) == 1  # nada se borra


async def test_anular_salario_revierte_y_advierte_negativos(service, store):
    store.replace_allocation(NOV, P_50_30_20)
    await service.add_income(
        100_000, budget_month="2026-11", confirm=True, operation_id="op-inc-30"
    )
    await service.add_expense(15_000, "op-gasto-30", pocket="Gustos")
    result = await service.void_transaction("I-1", "salario duplicado", "op-void-30", confirm=True)
    assert result.movement == "ingreso"
    assert [(p.pocket, p.balance) for p in result.negative_pockets] == [("Gustos", -15_000)]
    assert "RN-59" in result.warning
    status = await service.get_bolsa_status("Necesidades")
    assert status.assigned == 0  # sus asignaciones dejan de contar


async def test_anular_saldo_inicial_permite_una_nueva_carga(service, budget, store):
    await budget.load_initial_balance([("Ahorro", 1_000)], confirm=True)
    result = await service.void_transaction("I-1", "monto mal cargado", "op-void-ini", confirm=True)
    assert result.movement == "saldo_inicial" and result.initial_balance_reloadable
    reloaded = await budget.load_initial_balance([("Ahorro", 2_000)], confirm=True)
    assert reloaded.saved
    listing = await budget.list_pockets()
    assert [b.balance for b in listing.pockets if b.pocket.name == "Ahorro"] == [2_000]


async def test_anular_dos_veces_y_referencias_invalidas(service, store):
    await service.add_expense(1_000, "op-gasto-40", pocket="Gustos")
    await service.void_transaction("G-1", "error de prueba", "op-void-40", confirm=True)
    with pytest.raises(DomainError, match="ya está anulado"):
        await service.void_transaction("G-1", "error de prueba", "op-void-41", confirm=True)
    with pytest.raises(DomainError, match="No existe"):
        await service.void_transaction("G-99", "error de prueba", "op-void-42", confirm=True)
    with pytest.raises(DomainError, match="G-12"):
        await service.void_transaction("12", "error de prueba", "op-void-43", confirm=True)
    with pytest.raises(DomainError, match="motivo"):
        await service.void_transaction("G-1", "", "op-void-44", confirm=True)


# --- Idempotencia ---


async def test_misma_clave_y_contenido_devuelve_lo_mismo_sin_duplicar(service, store):
    store.replace_allocation(DEC, P_50_30_20)
    first = await service.add_income(50_000, confirm=True, operation_id="op-idem-1")
    again = await service.add_income(50_000, confirm=True, operation_id="op-idem-1")
    assert first == again and len(store.incomes) == 1

    g1 = await service.add_expense(7_000, "op-idem-2", pocket="gustos", description="almuerzo")
    g2 = await service.add_expense(7_000, "op-idem-2", pocket="GUSTOS", description=" almuerzo ")
    assert g1 == g2 and len(store.expenses) == 1

    v1 = await service.void_transaction("G-1", "duplicado", "op-idem-3", confirm=True)
    v2 = await service.void_transaction("g-1", "duplicado", "op-idem-3", confirm=True)
    assert v1 == v2  # aunque ya esté anulado, devuelve el resultado original


async def test_reintento_al_dia_siguiente_sin_fecha_devuelve_lo_original(store):
    clock = {"today": TODAY}
    service = LedgerService(store, today=lambda: clock["today"], rate_range=RANGE)
    first = await service.add_expense(7_000, "op-idem-dia", pocket="Gustos")
    clock["today"] = date(2026, 11, 11)
    again = await service.add_expense(7_000, "op-idem-dia", pocket="Gustos")
    assert again == first and again.expense_date == "2026-11-10" and len(store.expenses) == 1


async def test_misma_clave_con_otro_contenido_o_en_otra_tool_es_error(service, store):
    store.replace_allocation(DEC, P_50_30_20)
    await service.add_expense(7_000, "op-idem-4", pocket="Gustos")
    with pytest.raises(IdempotencyConflict):
        await service.add_expense(7_001, "op-idem-4", pocket="Gustos")
    with pytest.raises(IdempotencyConflict):
        await service.add_income(7_000, confirm=True, operation_id="op-idem-4")
    assert len(store.expenses) == 1 and store.incomes == []


async def test_carrera_con_la_misma_clave_devuelve_el_resultado_guardado(
    service, store, monkeypatch
):
    first = await service.add_expense(7_000, "op-carrera", pocket="Gustos")
    real = store.get_operation
    calls = {"n": 0}

    def late_view(
        operation_id,
    ):  # la primera consulta no ve la clave (otra llamada aún no hizo commit)
        calls["n"] += 1
        return None if calls["n"] == 1 else real(operation_id)

    monkeypatch.setattr(store, "get_operation", late_view)
    again = await service.add_expense(7_000, "op-carrera", pocket="Gustos")
    assert again == first and len(store.expenses) == 1


# --- US4: consultas ---


async def test_estado_resumen_top_y_listado_cuadran(service, budget, store):
    await budget.load_initial_balance([("Ahorro", 100_000)], confirm=True)
    store.replace_allocation(NOV, P_50_30_20)
    await service.add_income(
        200_000, budget_month="2026-11", confirm=True, operation_id="op-query-1"
    )
    await service.create_category("Súper", "Necesidades")
    await service.add_expense(30_000, "op-query-2", category="Súper")
    await service.add_expense(20_000, "op-query-3", category="súper")
    await service.add_expense(5_000, "op-query-4", pocket="Gustos")
    await service.add_expense(1_000, "op-query-5", pocket="Ahorro", expense_date="2026-10-20")

    nec = await service.get_bolsa_status("necesidades")
    assert (nec.assigned, nec.adjusted_budget, nec.spent, nec.available, nec.percent_used) == (
        100_000,
        100_000,
        50_000,
        50_000,
        50,
    )
    assert (nec.transfers_in, nec.transfers_out, nec.balance) == (0, 0, None)
    aho = await service.get_bolsa_status("Ahorro")
    assert (aho.balance, aho.available, aho.percent_used) == (100_000 + 60_000 - 1_000, None, None)

    summary = await service.get_summary("2026-11")
    assert summary.income_total == 200_000  # sin el saldo inicial (RN-54)
    assert summary.expense_total == 55_000
    assert [p.pocket for p in summary.pockets] == ["Necesidades", "Ahorro", "Gustos"]

    top = await service.top_categories()
    assert [(i.category, i.amount_crc, i.count, i.percent) for i in top.items] == [
        ("Súper", 50_000, 2, 90),
        ("pendiente de clasificar", 5_000, 1, 9),
    ]

    listing = await service.list_transactions(limit=3)
    assert len(listing.items) == 3 and listing.has_more
    assert all("id" not in item.model_dump() for item in listing.items)
    everything = await service.list_transactions(limit=100)
    assert [i.reference for i in everything.items][-1] == "G-4"  # el más antiguo (octubre) al final
    only_ahorro = await service.list_transactions(pocket="ahorro")
    assert [i.reference for i in only_ahorro.items] == ["G-4"]


@pytest.mark.parametrize("limit", [0, 101, "20", True, 2.0])
async def test_limite_del_listado(service, limit):
    with pytest.raises(DomainError, match="entre 1 y 100"):
        await service.list_transactions(limit=limit)


async def test_filtro_por_bolsa_solo_para_gastos(service):
    with pytest.raises(DomainError, match="solo aplica a gastos"):
        await service.list_transactions(type="ingreso", pocket="Gustos")


# --- Registros ---


async def test_registros_sin_montos_ni_descripciones(service, store, caplog):
    caplog.set_level(logging.DEBUG, logger="puro_pockets")
    store.replace_allocation(DEC, P_50_30_20)
    await service.add_income(734_219, confirm=True, operation_id="op-log-1")
    await service.add_expense(
        "19.87",
        "op-log-2",
        pocket="Gustos",
        currency="USD",
        exchange_rate="611.23",
        description="regalo secreto",
    )
    await service.add_expense(93_417, "op-log-3", pocket="Gustos")  # sobregasto
    await service.void_transaction("G-1", "motivo privado", "op-log-4", confirm=True)
    text = caplog.text.replace(".", "").replace(",", "")
    for secret in ("734219", "1987", "61123", "12145", "93417", "regalo secreto"):
        assert secret not in text, secret
