"""Tools del presupuesto por HTTP, en proceso, detrás de OAuth (Hito 4; datos sintéticos).

Usa la aplicación ASGI real (SDK + OAuth + tools) con almacenes en memoria.
"""

import json
import logging
from datetime import date

import pytest
from starlette.testclient import TestClient

from puro_pockets.config import Settings
from puro_pockets.domain.auth import EventLimiter, LoginRateLimiter
from puro_pockets.mcp.server import AuthComponents, build_app, build_server
from puro_pockets.services.budget import BudgetService
from puro_pockets.services.health import HealthService
from puro_pockets.services.oauth import OAuthConfig, OwnerOAuthProvider
from puro_pockets.services.passwords import PasswordVerifier
from tests.fakes import InMemoryBudgetStore, InMemoryOAuthStore
from tests.unit.test_oauth_http import (
    BASE,
    CALLBACK,
    MCP_HEADERS,
    PASSWORD_HASH,
    RESOURCE,
    _full_flow,
    _mcp,
)

TOOLS = {
    "set_allocation",
    "get_allocation",
    "preview_initial_balance",
    "load_initial_balance",
    "list_bolsas",
}
SYNTH = [
    {"pocket": "Necesidades", "amount": 104_729},
    {"pocket": "gustos", "amount": 56_311},
    {"pocket": "AHORRO", "amount": 523_717},
]
SYNTH_AMOUNTS = ("104729", "56311", "523717", "684757")


@pytest.fixture
def store():
    return InMemoryBudgetStore()


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
    budget = BudgetService(store, today=lambda: date(2026, 11, 10))
    server = build_server(HealthService(lambda: None, timeout_seconds=2), auth, budget)
    with TestClient(build_app(server, settings), base_url=BASE, follow_redirects=False) as client:
        yield client


class Session:
    """Sesión MCP autenticada sobre el cliente de prueba."""

    def __init__(self, http: TestClient, token: str) -> None:
        self.http = http
        init = _mcp(http, token)
        assert init.status_code == 200, init.text
        self.headers = {
            **MCP_HEADERS,
            "Authorization": f"Bearer {token}",
            "mcp-session-id": init.headers["mcp-session-id"],
            "mcp-protocol-version": "2025-06-18",
        }
        http.post(
            "/mcp",
            json={"jsonrpc": "2.0", "method": "notifications/initialized"},
            headers=self.headers,
        )
        self._id = 1

    def request(self, method: str, params: dict | None = None) -> dict:
        self._id += 1
        body = {"jsonrpc": "2.0", "id": self._id, "method": method, "params": params or {}}
        response = self.http.post("/mcp", json=body, headers=self.headers)
        assert response.status_code == 200, response.text
        return next(
            json.loads(line[5:]) for line in response.text.splitlines() if line.startswith("data:")
        )

    def call(self, name: str, **arguments) -> dict:
        return self.request("tools/call", {"name": name, "arguments": arguments})["result"]


@pytest.fixture
def mcp(http):
    _, token = _full_flow(http)
    return Session(http, token["access_token"])


def _error_text(result: dict) -> str:
    assert result["isError"] is True, result
    return " ".join(c["text"] for c in result["content"] if c["type"] == "text")


# --- Autenticación ---


def test_sin_token_401_y_token_inventado_401(http):
    assert _mcp(http, None).status_code == 401
    assert _mcp(http, "ppa_inventado").status_code == 401


def test_las_tools_estan_publicadas_con_esquema_de_salida(mcp):
    tools = {t["name"]: t for t in mcp.request("tools/list")["result"]["tools"]}
    assert TOOLS <= set(tools)
    assert all("outputSchema" in tools[name] for name in TOOLS)


# --- Porcentajes ---


def test_definir_50_30_20_y_consultar(mcp):
    pcts = [
        {"pocket": "Necesidades", "percentage": 50},
        {"pocket": "Ahorro", "percentage": 30},
        {"pocket": "Gustos", "percentage": 20},
    ]
    saved = mcp.call("set_allocation", percentages=pcts)["structuredContent"]
    assert saved["month"] == "2026-11" and saved["source_month"] == "2026-11"
    got = mcp.call("get_allocation", month="2027-01")["structuredContent"]
    assert got["defined"] and got["source_month"] == "2026-11"
    assert [i["percentage"] for i in got["items"]] == [50, 30, 20]
    assert set(got["items"][0]) == {"pocket", "behavior", "percentage"}  # sin ids


def test_suma_110_rechazada_en_espanol(mcp, store):
    pcts = [
        {"pocket": "Necesidades", "percentage": 50},
        {"pocket": "Ahorro", "percentage": 30},
        {"pocket": "Gustos", "percentage": 30},
    ]
    text = _error_text(mcp.call("set_allocation", percentages=pcts))
    assert "deben sumar exactamente 100; suman 110" in text
    assert store.allocations == {}


def test_porcentaje_decimal_rechazado_en_espanol_sin_mostrar_el_valor(mcp):
    for value in (50.5, 50.0, "50", True):
        pcts = [{"pocket": "Necesidades", "percentage": value}]
        text = _error_text(mcp.call("set_allocation", percentages=pcts))
        assert "porcentaje de Necesidades debe ser un entero" in text
        assert "input_value" not in text and "50" not in text.replace("2026", "")


def test_monto_decimal_del_saldo_inicial_no_se_muestra(mcp):
    text = _error_text(
        mcp.call("load_initial_balance", amounts=[{"pocket": "Ahorro", "amount": 523_717.5}])
    )
    assert "monto de Ahorro" in text and "523717" not in text.replace(".", "").replace(",", "")


def test_mes_pasado_rechazado(mcp):
    pcts = [
        {"pocket": "Necesidades", "percentage": 50},
        {"pocket": "Ahorro", "percentage": 30},
        {"pocket": "Gustos", "percentage": 20},
    ]
    assert "mes pasado" in _error_text(
        mcp.call("set_allocation", percentages=pcts, month="2026-10")
    )


# --- Saldo inicial ---


def test_sin_confirm_no_guarda_y_con_confirm_carga_una_sola_vez(mcp, store):
    preview = mcp.call("preview_initial_balance", amounts=SYNTH)["structuredContent"]
    assert preview["total"] == 684_757 and not preview["saved"]
    unconfirmed = mcp.call("load_initial_balance", amounts=SYNTH)["structuredContent"]
    assert not unconfirmed["saved"] and store.incomes == []

    loaded = mcp.call("load_initial_balance", amounts=SYNTH, confirm=True)["structuredContent"]
    assert loaded["saved"] and loaded["month"] == "2026-11"

    listing = mcp.call("list_bolsas")["structuredContent"]
    assert [(p["name"], p["balance"], p["balance_kind"]) for p in listing["pockets"]] == [
        ("Necesidades", 104_729, "disponible_del_mes"),
        ("Ahorro", 523_717, "saldo"),
        ("Gustos", 56_311, "disponible_del_mes"),
    ]

    again = mcp.call("load_initial_balance", amounts=SYNTH, confirm=True)
    assert "ya fue cargado" in _error_text(again)
    assert len(store.incomes) == 1


def test_errores_y_registros_sin_montos(mcp, caplog):
    # Nivel de producción (configure_logging): INFO, con las bibliotecas de cuerpos fijadas en INFO
    caplog.set_level(logging.INFO)
    bad = [{"pocket": "Gustos", "amount": -56_311}, {"pocket": "Ahorro", "amount": 523_717}]
    text = _error_text(mcp.call("load_initial_balance", amounts=bad, confirm=True))
    assert "monto de Gustos" in text
    mcp.call("load_initial_balance", amounts=SYNTH, confirm=True)
    mcp.call("load_initial_balance", amounts=SYNTH, confirm=True)  # segunda: rechazada
    mcp.call("list_bolsas")
    logs = caplog.text.replace(".", "").replace(",", "")
    errors = text.replace(".", "").replace(",", "")
    for amount in SYNTH_AMOUNTS:
        assert amount not in logs, f"monto en registros: {amount}"
        assert amount not in errors, f"monto en mensaje de error: {amount}"


def test_bibliotecas_que_registran_cuerpos_quedan_en_info(monkeypatch):
    from puro_pockets import __main__ as entry

    monkeypatch.setattr(logging, "basicConfig", lambda **_: None)
    previous = {name: logging.getLogger(name).level for name in entry.BODY_LOGGERS}
    try:
        entry.configure_logging()
        for name in entry.BODY_LOGGERS:
            assert not logging.getLogger(name).isEnabledFor(logging.DEBUG), name
    finally:
        for name, level in previous.items():
            logging.getLogger(name).setLevel(level)
