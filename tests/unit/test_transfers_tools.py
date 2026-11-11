"""Tools de transferencias por HTTP, en proceso, detrás de OAuth (Hito 8; datos sintéticos).

Las fixtures `http`, `mcp` y `store` vienen de test_ledger_tools (hoy = 2026-11-10).
"""

import json
import logging

from puro_pockets.domain.months import Month
from tests.unit.test_budget_tools import _error_text
from tests.unit.test_ledger_tools import http, mcp, store  # noqa: F401 - fixtures compartidas
from tests.unit.test_oauth_http import _full_flow, _mcp

TOOLS = {"preview_transfer", "transfer_between_bolsas"}
NOTE = "nota reservada sintética"


def _ok(result: dict) -> dict:
    assert not result.get("isError"), result
    return result["structuredContent"]


def _call(mcp, tool, **arguments):  # noqa: F811
    return mcp.request("tools/call", {"name": tool, "arguments": arguments})["result"]


def test_sin_credencial_401(http):  # noqa: F811
    assert _mcp(http, None).status_code == 401


def test_instrucciones_explican_el_flujo(http):  # noqa: F811
    _, token = _full_flow(http)
    init = _mcp(http, token["access_token"])
    data = next(json.loads(x[5:]) for x in init.text.splitlines() if x.startswith("data:"))
    instructions = data["result"]["instructions"]
    assert "preview_transfer" in instructions and "transfer_between_bolsas" in instructions
    assert "cubrir_sobregasto" in instructions and "T-n" in instructions


def test_esquemas_y_descripciones(mcp):  # noqa: F811
    tools = {t["name"]: t for t in mcp.request("tools/list")["result"]["tools"]}
    assert TOOLS <= set(tools)
    assert all("outputSchema" in tools[name] for name in TOOLS)
    assert "aprobación EXPLÍCITA" in tools["transfer_between_bolsas"]["description"]
    assert "RN-58" in tools["preview_transfer"]["description"]
    reason = tools["preview_transfer"]["inputSchema"]["properties"]["reason"]
    assert reason["enum"] == ["cubrir_sobregasto", "reasignacion", "ajuste"]
    assert tools["preview_transfer"]["inputSchema"]["properties"]["amount"]["type"] == "integer"
    # Tras un sobregasto, add_expense guía a Claude hacia la transferencia con aprobación
    assert "preview_transfer" in tools["add_expense"]["description"]
    assert "aprobación EXPLÍCITA" in tools["add_expense"]["description"]
    assert (
        "transferencia"
        in tools["list_transactions"]["inputSchema"]["properties"]["type"]["anyOf"][0]["enum"]
    )
    assert "T-n" in tools["void_transaction"]["description"]


def test_flujo_sobregasto_y_transferencia(mcp, store, caplog):  # noqa: F811
    caplog.set_level(logging.INFO)  # nivel de producción
    store.replace_allocation(Month(2026, 11), {1: 50, 2: 30, 3: 20})
    _ok(
        mcp.call(
            "add_income",
            amount=1_000_000,
            budget_month="2026-11",
            confirm=True,
            operation_id="tool-sal-h8",
        )
    )
    spent = _ok(mcp.call("add_expense", amount=213_579, pocket="Gustos", operation_id="tool-g-h8"))
    assert spent["overspent"] and "preview_transfer" in spent["warning"]
    args = {
        "from_pocket": "Necesidades",
        "to_pocket": "Gustos",
        "amount": 13_579,
        "reason": "cubrir_sobregasto",
        "note": NOTE,
    }
    preview = _ok(_call(mcp, "preview_transfer", **args))
    assert preview["to_pocket"]["after"] == 0 and store.transfers == []
    refused = _call(mcp, "transfer_between_bolsas", **args, confirm=True, operation_id="tool-t-01")
    assert "vista previa" in _error_text(refused) and store.transfers == []
    saved = _ok(
        _call(
            mcp,
            "transfer_between_bolsas",
            **args,
            confirm=True,
            operation_id="tool-t-01",
            preview_token=preview["preview_token"],
        )
    )
    assert saved["reference"] == "T-1" and len(store.transfers) == 1
    status = _ok(mcp.call("get_bolsa_status", pocket="Gustos"))
    assert status["available"] == 0 and status["transfers_in"] == 13_579
    listed = _ok(mcp.call("list_transactions", type="transferencia"))
    assert listed["items"][0]["reference"] == "T-1"
    voided = _call(mcp, "void_transaction", reference="T-1", reason="error", operation_id="tool-v1")
    assert "sentido contrario" in _error_text(voided)

    too_much = _call(mcp, "preview_transfer", **{**args, "amount": 9_999_999})
    decimal = _call(mcp, "preview_transfer", **{**args, "amount": 100.5})
    reserved = _call(mcp, "preview_transfer", **{**args, "reason": "cierre_de_mes"})
    for result in (too_much, decimal, reserved):
        assert result.get("isError")
    assert "reservado" in _error_text(reserved)  # mensaje del dominio, en español
    invalid = _call(mcp, "preview_transfer", **{**args, "reason": "regalo"})
    assert "cubrir_sobregasto, reasignacion o ajuste" in _error_text(invalid)
    texts = " ".join(_error_text(r) for r in (too_much, decimal)) + caplog.text
    for secret in ("213579", "213.579", "13579", "13.579", "9999999", "100.5", NOTE):
        assert secret not in texts, secret
