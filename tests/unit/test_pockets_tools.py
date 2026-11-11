"""Tools de bolsas flexibles y metas por HTTP, en proceso, detrás de OAuth (Hito 7; sintéticos).

Las fixtures `http`, `mcp` y `store` vienen de test_ledger_tools (hoy = 2026-11-10).
"""

import json
import logging

from puro_pockets.domain.months import Month
from tests.unit.test_budget_tools import _error_text
from tests.unit.test_ledger_tools import http, mcp, store  # noqa: F401 - fixtures compartidas
from tests.unit.test_oauth_http import _full_flow, _mcp

TOOLS = {
    "preview_rebalance",
    "create_bolsa",
    "archive_bolsa",
    "create_goal",
    "get_goal_progress",
    "update_goal",
}


def _ok(result: dict) -> dict:
    assert not result.get("isError"), result
    return result["structuredContent"]


def _call(mcp, tool, **arguments):  # noqa: F811
    # Session.call usa "name" para la tool: se arma la llamada a mano
    return mcp.request("tools/call", {"name": tool, "arguments": arguments})["result"]


def test_sin_credencial_401(http):  # noqa: F811
    assert _mcp(http, None).status_code == 401


def test_tools_publicadas_e_instrucciones(http):  # noqa: F811
    _, token = _full_flow(http)
    init = _mcp(http, token["access_token"])
    data = next(json.loads(x[5:]) for x in init.text.splitlines() if x.startswith("data:"))
    assert "create_bolsa" in data["result"]["instructions"]
    assert "no tiene dinero propio" in data["result"]["instructions"]


def test_esquemas(mcp):  # noqa: F811
    tools = {t["name"]: t for t in mcp.request("tools/list")["result"]["tools"]}
    assert TOOLS <= set(tools)
    assert all("outputSchema" in tools[name] for name in TOOLS)
    assert "aprobación EXPLÍCITA" in tools["create_bolsa"]["description"]
    assert "aprobación EXPLÍCITA" in tools["archive_bolsa"]["description"]
    assert "operation_id" in tools["create_goal"]["inputSchema"]["required"]


def test_flujo_crear_bolsa_y_meta(mcp, store):  # noqa: F811
    store.replace_allocation(Month(2026, 11), {1: 50, 2: 30, 3: 20})
    args = {"name": "Emergencia", "behavior": "acumulable", "percentage": 10}
    preview = _ok(_call(mcp, "create_bolsa", **args))
    assert preview["rebalance"]["months"][0]["month"] == "2026-12" and len(store.pockets) == 3
    no_token = _call(mcp, "create_bolsa", **args, confirm=True, operation_id="tool-bolsa-01")
    assert "vista previa" in _error_text(no_token) and len(store.pockets) == 3
    saved = _ok(
        _call(
            mcp,
            "create_bolsa",
            **args,
            confirm=True,
            operation_id="tool-bolsa-01",
            preview_token=preview["preview_token"],
        )
    )
    assert saved["saved"] and sum(store.allocations[Month(2026, 12)].values()) == 100
    dup = _call(mcp, "create_bolsa", name="emergencia", behavior="consumo", percentage=0)
    assert "Ya existe" in _error_text(dup)
    bad = _call(
        mcp,
        "preview_rebalance",
        strategy="manual",
        new_pocket="Viaje",
        percentages=[{"pocket": "Necesidades", "percentage": 99}],
    )
    assert "todas las bolsas" in _error_text(bad)

    consumo = _call(
        mcp, "create_goal", pocket="Gustos", name="X", target_amount=1, operation_id="tool-meta-01"
    )
    assert "acumulable" in _error_text(consumo)
    goal = _ok(
        _call(
            mcp,
            "create_goal",
            pocket="Emergencia",
            name="Fondo sintético",
            target_amount=500_000,
            operation_id="tool-meta-02",
        )
    )
    assert goal["reference"] == "M-1" and goal["balance"] == 0
    progress = _ok(_call(mcp, "get_goal_progress"))
    assert progress["items"][0]["missing"] == 500_000
    decimal = _call(
        mcp,
        "create_goal",
        pocket="Ahorro",
        name="Y",
        target_amount=100.5,
        operation_id="tool-meta-03",
    )
    assert "entero" in _error_text(decimal) and "100.5" not in _error_text(decimal)


def test_archivar_con_saldo_y_registros_sin_montos(mcp, store, caplog):  # noqa: F811
    caplog.set_level(logging.INFO)  # nivel de producción (configure_logging)
    store.replace_allocation(Month(2026, 11), {1: 50, 2: 30, 3: 20})
    _ok(
        mcp.call(
            "add_income",
            amount=432_101,
            budget_month="2026-11",
            confirm=True,
            operation_id="tool-sal-h7",
        )
    )
    refused = _call(mcp, "archive_bolsa", name="Ahorro")
    assert "no es cero" in _error_text(refused) and "129" not in _error_text(refused)
    _ok(
        _call(
            mcp,
            "create_goal",
            pocket="Ahorro",
            name="Meta confidencial",
            target_amount=987_654,
            operation_id="tool-meta-log",
        )
    )
    for secret in ("432101", "432.101", "987654", "987.654", "confidencial"):
        assert secret not in caplog.text, secret
