"""Tools del cierre de mes por HTTP, en proceso, detrás de OAuth (Hito 9; datos sintéticos).

Las fixtures `http`, `mcp` y `store` vienen de test_ledger_tools (hoy = 2026-11-10): octubre ya
terminó y se puede cerrar.
"""

import json
import logging

from puro_pockets.domain.months import Month
from tests.unit.test_budget_tools import _error_text
from tests.unit.test_ledger_tools import http, mcp, store  # noqa: F401 - fixtures compartidas
from tests.unit.test_oauth_http import _full_flow, _mcp

TOOLS = {"preview_month_close", "close_month", "set_surplus_destination"}
COVERS = [{"from_pocket": "Necesidades", "to_pocket": "Gustos", "amount": 13_579}]
DESTS = [{"from_pocket": "Necesidades", "to_pocket": "Ahorro", "amount": 6_421}]


def _ok(result: dict) -> dict:
    assert not result.get("isError"), result
    return result["structuredContent"]


def _call(mcp, tool, **arguments):  # noqa: F811
    return mcp.request("tools/call", {"name": tool, "arguments": arguments})["result"]


def test_sin_credencial_401(http):  # noqa: F811
    assert _mcp(http, None).status_code == 401


def test_instrucciones_explican_el_ritual(http):  # noqa: F811
    _, token = _full_flow(http)
    init = _mcp(http, token["access_token"])
    data = next(json.loads(x[5:]) for x in init.text.splitlines() if x.startswith("data:"))
    instructions = data["result"]["instructions"]
    assert "RN-51" in instructions and "preview_month_close" in instructions
    assert "close_month" in instructions and "add_income" in instructions
    assert "pending_closure" in instructions
    assert "confirm=true no garantiza" in instructions


def test_esquemas_y_descripciones(mcp):  # noqa: F811
    tools = {t["name"]: t for t in mcp.request("tools/list")["result"]["tools"]}
    assert TOOLS <= set(tools)
    assert all("outputSchema" in tools[name] for name in TOOLS)
    assert "aprobación EXPLÍCITA" in tools["close_month"]["description"]
    assert "RN-58" in tools["preview_month_close"]["description"]
    covers = tools["close_month"]["inputSchema"]["properties"]["covers"]
    assert covers["items"]["properties"]["amount"]["type"] == "integer"
    dest = tools["close_month"]["inputSchema"]["properties"]["destinations"]
    assert "null" in dest["items"]["properties"]["to_pocket"]["type"]
    listed = tools["list_bolsas"]["outputSchema"]["properties"]
    assert "pending_closure" in listed and "month_closed" in listed


def test_ritual_completo_por_http(mcp, store, caplog):  # noqa: F811
    caplog.set_level(logging.INFO)  # nivel de producción
    store.replace_allocation(Month(2026, 10), {1: 50, 2: 30, 3: 20})
    _ok(
        mcp.call(
            "add_income",
            amount=1_000_000,
            income_date="2026-09-30",
            budget_month="2026-10",
            confirm=True,
            operation_id="tool-sal-h9",
        )
    )
    _ok(
        mcp.call(
            "add_expense",
            amount=213_579,
            pocket="Gustos",
            expense_date="2026-10-20",
            operation_id="tool-g-h9-1",
        )
    )
    _ok(
        mcp.call(
            "add_expense",
            amount=480_000,
            pocket="Necesidades",
            expense_date="2026-10-21",
            operation_id="tool-g-h9-2",
        )
    )
    pending = _ok(mcp.call("list_bolsas"))["pending_closure"]
    assert pending == [{"month": "2026-10", "has_movements": True}]
    _ok(_call(mcp, "set_surplus_destination", pocket="Necesidades",
              destination_pocket="Ahorro", operation_id="tool-dest-h9"))  # fmt: skip

    data = _ok(_call(mcp, "preview_month_close"))
    assert data["month"] == "2026-10" and data["preview_token"] is None
    nec = next(c for c in data["consumption"] if c["pocket"] == "Necesidades")
    assert nec["available"] == 20_000 and nec["suggested_destination"] == "Ahorro"

    args = {"month": "2026-10", "covers": COVERS, "destinations": DESTS}
    preview = _ok(_call(mcp, "preview_month_close", **args))
    assert preview["unassigned_surplus_total"] == 0 and preview["preview_token"]
    refused = _call(mcp, "close_month", **args, confirm=True, operation_id="tool-close-h9")
    assert "vista previa" in _error_text(refused) and store.closures == {}
    closed = _ok(
        _call(
            mcp,
            "close_month",
            **args,
            confirm=True,
            operation_id="tool-close-h9",
            preview_token=preview["preview_token"],
        )
    )
    assert closed["saved"] and [t["reference"] for t in closed["transfers"]] == ["T-1", "T-2"]

    late = _call(
        mcp,
        "add_expense",
        amount=1_234,
        pocket="Gustos",
        expense_date="2026-10-31",
        operation_id="tool-g-h9-3",
    )
    void = _call(mcp, "void_transaction", reference="G-1", reason="error", operation_id="tool-v-h9")
    again = _call(mcp, "preview_month_close", month="2026-10")
    decimal = _call(
        mcp,
        "preview_month_close",
        month="2026-11",
        covers=[{"from_pocket": "Necesidades", "to_pocket": "Gustos", "amount": 1.5}],
    )
    for result in (late, void):
        assert "2026-10 está cerrado" in _error_text(result)
    assert "ya está cerrado" in _error_text(again)
    assert decimal.get("isError")
    summary = _ok(mcp.call("get_summary", month="2026-10"))
    assert summary["month_closed"] and summary["pending_closure"] == []

    texts = " ".join(_error_text(r) for r in (late, void, again)) + caplog.text
    for secret in ("13579", "13 579", "6421", "1234", "1 234", "213579"):
        assert secret not in texts
    assert "Cierre registrado: mes=2026-10" in caplog.text
