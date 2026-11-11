"""Tools de movimientos por HTTP, en proceso, detrás de OAuth (Hito 5; datos sintéticos).

Usa la aplicación ASGI real (SDK + OAuth + tools) con almacenes en memoria.
"""

import logging
from datetime import date

import pytest
from starlette.testclient import TestClient

from puro_pockets.config import Settings
from puro_pockets.domain.auth import EventLimiter, LoginRateLimiter
from puro_pockets.domain.money import RateRange
from puro_pockets.domain.months import Month
from puro_pockets.mcp.server import AuthComponents, build_app, build_server
from puro_pockets.services.budget import BudgetService
from puro_pockets.services.health import HealthService
from puro_pockets.services.ledger import LedgerService
from puro_pockets.services.oauth import OAuthConfig, OwnerOAuthProvider
from puro_pockets.services.passwords import PasswordVerifier
from tests.fakes import InMemoryLedgerStore, InMemoryOAuthStore
from tests.unit.test_budget_tools import Session, _error_text
from tests.unit.test_oauth_http import BASE, CALLBACK, PASSWORD_HASH, RESOURCE, _full_flow, _mcp

TOOLS = {
    "preview_income",
    "add_income",
    "add_expense",
    "void_transaction",
    "get_bolsa_status",
    "list_transactions",
    "get_summary",
    "top_categories",
    "create_category",
    "list_categories",
}
P_50_30_20 = {1: 50, 2: 30, 3: 20}


@pytest.fixture
def store():
    return InMemoryLedgerStore()


@pytest.fixture
def http(store):
    settings = Settings(
        database_url="postgresql+psycopg://u:p@127.0.0.1:1/x",
        public_hostname="mcp.puropockets.space",
    )
    provider = OwnerOAuthProvider(
        store=InMemoryOAuthStore(),
        config=OAuthConfig(
            issuer_url=BASE, resource_url=RESOURCE, allowed_redirect_uris=(CALLBACK,)
        ),
        registration_limiter=EventLimiter(max_events=100, window_seconds=3600),
    )
    auth = AuthComponents(
        provider=provider,
        verifier=PasswordVerifier(PASSWORD_HASH),
        limiter=LoginRateLimiter(),
        registration_enabled=True,
    )
    today = lambda: date(2026, 11, 10)  # noqa: E731
    budget = BudgetService(store, today=today)
    ledger = LedgerService(store, today=today, rate_range=RateRange(300, 1000))
    server = build_server(HealthService(lambda: None, timeout_seconds=2), auth, budget, ledger)
    with TestClient(build_app(server, settings), base_url=BASE, follow_redirects=False) as client:
        yield client


@pytest.fixture
def mcp(http):
    _, token = _full_flow(http)
    return Session(http, token["access_token"])


def _ok(result: dict) -> dict:
    assert not result.get("isError"), result
    return result["structuredContent"]


def test_sin_token_401(http):
    assert _mcp(http, None).status_code == 401
    assert _mcp(http, "ppa_inventado").status_code == 401


def test_tools_publicadas_con_esquema_de_salida(mcp):
    tools = {t["name"]: t for t in mcp.request("tools/list")["result"]["tools"]}
    assert TOOLS <= set(tools)
    assert all("outputSchema" in tools[name] for name in TOOLS)
    assert "operation_id" in tools["add_expense"]["inputSchema"]["required"]


def test_salario_50_30_20_en_el_mes_siguiente(mcp, store):
    store.replace_allocation(Month(2026, 12), P_50_30_20)
    preview = _ok(mcp.call("add_income", amount=1_000_001, income_date="2026-11-01"))
    assert not preview["saved"] and preview["budget_month"] == "2026-12" and store.incomes == []
    with_tool = _ok(mcp.call("preview_income", amount=1_000_001, income_date="2026-11-01"))
    assert with_tool == preview
    saved = _ok(
        mcp.call(
            "add_income",
            amount=1_000_001,
            income_date="2026-10-30",
            budget_month="2026-12",
            confirm=True,
            operation_id="tool-salario-1",
        )
    )
    assert saved["saved"] and saved["reference"] == "I-1" and saved["budget_month"] == "2026-12"
    assert [(i["pocket"], i["percentage"], i["amount"]) for i in saved["items"]] == [
        ("Necesidades", 50, 500_000),
        ("Ahorro", 30, 300_000),
        ("Gustos", 20, 200_001),
    ]


def test_gasto_en_dolares_convertido_y_texto_obligatorio_para_decimales(mcp, store):
    result = _ok(
        mcp.call(
            "add_expense",
            amount="10.00",
            currency="USD",
            exchange_rate="512.34",
            pocket="Necesidades",
            operation_id="tool-gasto-usd",
        )
    )
    assert (result["original_amount"], result["exchange_rate"], result["amount_crc"]) == (
        "10.00",
        "512.34",
        5_123,
    )
    as_number = mcp.call(
        "add_expense",
        amount=10.5,
        currency="USD",
        exchange_rate="512.34",
        pocket="Necesidades",
        operation_id="tool-gasto-float",
    )
    assert "como texto" in _error_text(as_number)
    rate_number = mcp.call(
        "add_expense",
        amount="10.50",
        currency="USD",
        exchange_rate=512.34,
        pocket="Necesidades",
        operation_id="tool-gasto-float-2",
    )
    assert "como texto" in _error_text(rate_number)
    assert len(store.expenses) == 1


def test_usd_sin_tipo_de_cambio_es_error(mcp, store):
    result = mcp.call(
        "add_expense", amount="10.00", currency="USD", pocket="Gustos", operation_id="tool-sin-tc"
    )
    assert "Falta el tipo de cambio" in _error_text(result)
    assert store.expenses == []


def test_porcentajes_que_no_suman_100_y_entero_con_decimales(mcp, store):
    bad = [
        {"pocket": "Necesidades", "percentage": 50},
        {"pocket": "Ahorro", "percentage": 30},
        {"pocket": "Gustos", "percentage": 30},
    ]
    assert "suman 110" in _error_text(mcp.call("set_allocation", percentages=bad))
    as_float = [{"pocket": "Necesidades", "percentage": 50.0}]
    assert "entero" in _error_text(mcp.call("set_allocation", percentages=as_float))
    assert store.allocations == {}


def test_sobregasto_idempotencia_y_anulacion(mcp, store):
    store.replace_allocation(Month(2026, 11), P_50_30_20)
    _ok(
        mcp.call(
            "add_income",
            amount=50_000,
            budget_month="2026-11",
            confirm=True,
            operation_id="tool-salario-2",
        )
    )
    args = {"amount": 12_000, "pocket": "gustos", "operation_id": "tool-sobregasto"}
    first = _ok(mcp.call("add_expense", **args))
    assert first["overspent"] and first["pocket_balance"]["balance"] == -2_000
    assert [p["pocket"] for p in first["available_pockets"]] == ["Necesidades", "Ahorro"]
    again = _ok(mcp.call("add_expense", **args))
    assert again == first and len(store.expenses) == 1  # la misma llamada no duplica
    conflict = mcp.call("add_expense", **{**args, "amount": 12_001})
    assert "ya se usó con otros datos" in _error_text(conflict)

    voided = _ok(
        mcp.call(
            "void_transaction",
            reference="G-1",
            reason="gasto duplicado",
            operation_id="tool-void-1",
            confirm=True,
        )
    )
    assert voided["saved"] and voided["movement"] == "gasto"
    status = _ok(mcp.call("get_bolsa_status", pocket="Gustos"))
    assert status["spent"] == 0 and status["available"] == 10_000
    listing = _ok(mcp.call("list_transactions"))
    assert listing["items"][0]["reference"] == "G-1" and listing["items"][0]["voided"]


def _create_category(mcp, name: str, pocket: str) -> dict:
    # Session.call usa "name" para la tool: se arma la llamada a mano
    params = {"name": "create_category", "arguments": {"name": name, "pocket": pocket}}
    return mcp.request("tools/call", params)["result"]


def test_resumen_categorias_y_listado(mcp):
    _ok(_create_category(mcp, "Súper", "Necesidades"))
    dup = _create_category(mcp, "súper", "Gustos")
    assert "Ya existe" in _error_text(dup)
    _ok(mcp.call("add_expense", amount=3_000, category="Súper", operation_id="tool-cat-1"))
    assert _ok(mcp.call("list_categories"))["items"] == [{"name": "Súper", "pocket": "Necesidades"}]
    top = _ok(mcp.call("top_categories"))
    assert top["items"][0]["category"] == "Súper"
    summary = _ok(mcp.call("get_summary", month="2026-11"))
    assert summary["expense_total"] == 3_000 and summary["negative_pockets"] == ["Necesidades"]
    too_many = mcp.call("list_transactions", limit=150)
    assert "entre 1 y 100" in _error_text(too_many)


def test_registros_y_errores_sin_montos_ni_descripciones(mcp, store, caplog):
    # Nivel de producción (configure_logging): INFO, con las bibliotecas de cuerpos fijadas en INFO
    caplog.set_level(logging.INFO)
    store.replace_allocation(Month(2026, 12), P_50_30_20)
    mcp.call("add_income", amount=834_517, confirm=True, operation_id="tool-log-1")
    mcp.call(
        "add_expense",
        amount=71_939,
        pocket="Gustos",
        description="cena confidencial",
        operation_id="tool-log-2",
    )
    errors = [
        mcp.call("add_expense", amount=-71_939, pocket="Gustos", operation_id="tool-log-3"),
        mcp.call("add_expense", amount=71_939.5, pocket="Gustos", operation_id="tool-log-3b"),
        mcp.call(
            "add_expense",
            amount="19.87",
            currency="USD",
            exchange_rate=1234.56,
            pocket="Gustos",
            operation_id="tool-log-3c",
        ),
        mcp.call("add_expense", amount=[71_939], pocket="Gustos", operation_id="tool-log-3d"),
        mcp.call(
            "add_expense",
            amount="19.87",
            currency="USD",
            exchange_rate="1234.56",
            pocket="Gustos",
            operation_id="tool-log-4",
        ),
        mcp.call(
            "add_expense",
            amount=71_939,
            pocket="Gustos",
            description="x" * 130,
            operation_id="tool-log-5",
        ),
        mcp.call("add_expense", amount=71_940, pocket="Gustos", operation_id="tool-log-2"),
    ]
    mcp.call(
        "void_transaction",
        reference="G-1",
        reason="motivo",
        operation_id="tool-log-6",
        confirm=True,
    )
    texts = " ".join(_error_text(e) for e in errors).replace(".", "").replace(",", "")
    logs = caplog.text.replace(".", "").replace(",", "")
    for secret in ("834517", "71939", "71940", "1987", "123456", "cena confidencial"):
        assert secret not in logs, f"en registros: {secret}"
        assert secret not in texts, f"en errores: {secret}"
