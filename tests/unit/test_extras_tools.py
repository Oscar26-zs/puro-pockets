"""Tools de extras y gastos fijos por HTTP, en proceso, detrás de OAuth (Hito 6; datos sintéticos).

Usa la aplicación ASGI real (SDK + OAuth + tools) con almacenes en memoria; las fixtures `http`,
`mcp` y `store` vienen de test_ledger_tools.
"""

import json
import logging

from puro_pockets.domain.months import Month
from puro_pockets.mcp.server import SERVER_INSTRUCTIONS
from tests.unit.test_budget_tools import _error_text
from tests.unit.test_ledger_tools import http, mcp, store  # noqa: F401 - fixtures compartidas
from tests.unit.test_oauth_http import _full_flow, _mcp

TOOLS = {
    "register_extra_income",
    "get_allocation_context",
    "confirm_allocation",
    "manage_recurring",
    "list_pending_recurring",
}


def _manage(mcp, **arguments) -> dict:  # noqa: F811
    # Session.call usa "name" para la tool: se arma la llamada a mano
    params = {"name": "manage_recurring", "arguments": arguments}
    return mcp.request("tools/call", params)["result"]


def _ok(result: dict) -> dict:
    assert not result.get("isError"), result
    return result["structuredContent"]


def test_sin_credencial_401(http):  # noqa: F811
    assert _mcp(http, None).status_code == 401
    assert _mcp(http, "ppa_inventado").status_code == 401


def test_instrucciones_del_servidor_en_initialize(http):  # noqa: F811
    _, token = _full_flow(http)
    response = _mcp(http, token["access_token"])
    data = next(
        json.loads(line[5:]) for line in response.text.splitlines() if line.startswith("data:")
    )
    instructions = data["result"]["instructions"]
    assert instructions == SERVER_INSTRUCTIONS
    assert "aprobación explícita" in instructions and "confirm=false" in instructions
    assert "nunca lo asumas" in instructions


def test_tools_publicadas_con_esquema_de_salida(mcp):  # noqa: F811
    tools = {t["name"]: t for t in mcp.request("tools/list")["result"]["tools"]}
    assert TOOLS <= set(tools)
    assert all("outputSchema" in tools[name] for name in TOOLS)
    assert "operation_id" in tools["register_extra_income"]["inputSchema"]["required"]
    assert "preview_token" in tools["confirm_allocation"]["inputSchema"]["properties"]
    assert "recurring" in tools["add_expense"]["inputSchema"]["properties"]
    assert "amount" not in tools["add_expense"]["inputSchema"].get("required", [])
    assert "aprobación explícita" in tools["confirm_allocation"]["description"]


def test_flujo_completo_del_extra(mcp, store):  # noqa: F811
    store.replace_allocation(Month(2026, 11), {1: 50, 2: 30, 3: 20})
    extra = _ok(mcp.call("register_extra_income", amount=40_000, operation_id="tool-extra-01"))
    assert extra["reference"] == "I-1" and extra["allocation_status"] == "pendiente"
    summary = _ok(mcp.call("get_summary"))
    assert summary["unassigned"]["count"] == 1 and summary["unassigned"]["total_crc"] == 40_000

    context = _ok(mcp.call("get_allocation_context", extra="I-1"))
    assert [p["pocket"] for p in context["pockets"]] == ["Necesidades", "Ahorro", "Gustos"]

    shares = [{"pocket": "Ahorro", "percentage": 75}, {"pocket": "Gustos", "percentage": 25}]
    preview = _ok(mcp.call("confirm_allocation", extra="I-1", percentages=shares))
    assert not preview["saved"] and store.lines == []
    without_token = mcp.call(
        "confirm_allocation",
        extra="I-1",
        percentages=shares,
        confirm=True,
        operation_id="tool-reparto-1",
    )
    assert "vista previa" in _error_text(without_token) and store.lines == []
    saved = _ok(
        mcp.call(
            "confirm_allocation",
            extra="I-1",
            percentages=shares,
            confirm=True,
            operation_id="tool-reparto-1",
            preview_token=preview["preview_token"],
        )
    )
    assert saved["saved"] and [i["amount"] for i in saved["items"]] == [30_000, 10_000]
    twice = mcp.call(
        "confirm_allocation",
        extra="I-1",
        percentages=shares,
        confirm=True,
        operation_id="tool-reparto-2",
        preview_token=preview["preview_token"],
    )
    assert "ya se repartió" in _error_text(twice)
    assert _ok(mcp.call("get_summary"))["unassigned"]["count"] == 0


def test_reparto_que_no_suma_100_y_porcentaje_decimal(mcp, store):  # noqa: F811
    _ok(mcp.call("register_extra_income", amount=40_000, operation_id="tool-extra-02"))
    bad = [{"pocket": "Ahorro", "percentage": 60}, {"pocket": "Gustos", "percentage": 30}]
    assert "suman 90" in _error_text(mcp.call("confirm_allocation", extra="I-1", percentages=bad))
    decimal = [{"pocket": "Ahorro", "percentage": 99.5}, {"pocket": "Gustos", "percentage": 0.5}]
    text = _error_text(mcp.call("confirm_allocation", extra="I-1", percentages=decimal))
    assert "entero" in text and "99.5" not in text


def test_usd_sin_tipo_de_cambio_en_extra_y_en_fijo(mcp, store):  # noqa: F811
    no_rate = mcp.call(
        "register_extra_income", amount="10.00", currency="USD", operation_id="tool-extra-03"
    )
    assert "No se asume" in _error_text(no_rate) and store.incomes == []
    _ok(
        _manage(
            mcp,
            action="crear",
            operation_id="tool-fijo-001",
            name="Nube sintética",
            amount="9.99",
            currency="USD",
            day_of_month=31,
            pocket="Gustos",
        )
    )
    pending = _ok(mcp.call("list_pending_recurring"))
    assert pending["pending"][0]["amount"] == "9.99" and pending["pending"][0]["amount_crc"] is None
    assert pending["pending"][0]["due_date"] == "2026-11-30"
    pay = mcp.call("add_expense", operation_id="tool-pago-001", recurring="F-1")
    assert "No se asume" in _error_text(pay) and store.expenses == []
    paid = _ok(
        mcp.call("add_expense", operation_id="tool-pago-002", recurring="F-1", exchange_rate="500")
    )
    assert paid["amount_crc"] == 4_995 and paid["recurring"] == "F-1"
    again = mcp.call(
        "add_expense", operation_id="tool-pago-003", recurring="F-1", exchange_rate="500"
    )
    assert "ya tiene un pago vigente" in _error_text(again)


def test_registros_sin_montos_ni_descripciones(mcp, store, caplog):  # noqa: F811
    # Nivel de producción (configure_logging): INFO, con las bibliotecas de cuerpos fijadas en INFO
    caplog.set_level(logging.INFO)
    _ok(
        mcp.call(
            "register_extra_income",
            amount=77_777,
            operation_id="tool-extra-log",
            source="premio sintético confidencial",
        )
    )
    _ok(
        _manage(
            mcp,
            action="crear",
            operation_id="tool-fijo-log",
            name="Club confidencial",
            amount=33_333,
            day_of_month=5,
            pocket="Gustos",
        )
    )
    _ok(mcp.call("add_expense", operation_id="tool-pago-log", recurring="F-1"))
    mcp.call("register_extra_income", amount=12.5, operation_id="tool-extra-lo2")
    for secret in ("77777", "77.777", "33333", "12.5", "confidencial"):
        assert secret not in caplog.text, secret
