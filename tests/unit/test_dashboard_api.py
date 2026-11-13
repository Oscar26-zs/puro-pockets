"""API del dashboard (Hito 10) en proceso, con almacén en memoria y datos sintéticos.

Comprueba la sesión, los verbos, las cabeceras, los registros sin datos privados y que resumen,
bolsas, metas y movimientos sean IDÉNTICOS a lo que devuelven las tools por MCP (mismo almacén).
La contraseña de prueba se genera aquí y nunca se imprime.
"""

import logging
import secrets
from functools import partial

import anyio
import pytest
from argon2 import PasswordHasher
from starlette.testclient import TestClient

from puro_pockets.api.app import CONTENT_SECURITY_POLICY, build_app
from puro_pockets.api.session import COOKIE_NAME, SessionManager
from puro_pockets.config import Settings
from puro_pockets.domain.auth import EventLimiter, LoginRateLimiter
from puro_pockets.domain.money import RateRange
from puro_pockets.mcp.server import AuthComponents, build_server
from puro_pockets.mcp.server import build_app as build_mcp_app
from puro_pockets.services.budget import BudgetService
from puro_pockets.services.dashboard import DashboardService
from puro_pockets.services.health import HealthService
from puro_pockets.services.ledger import LedgerService
from puro_pockets.services.oauth import OAuthConfig, OwnerOAuthProvider
from puro_pockets.services.passwords import PasswordVerifier
from tests.dashboard_world import (
    EXPECTED,
    GOAL_NAME,
    SECRET_DESCRIPTION,
    SECRET_NOTE,
    TODAY,
    build_world,
)
from tests.fakes import InMemoryLedgerStore, InMemoryOAuthStore
from tests.unit.test_budget_tools import Session
from tests.unit.test_oauth_http import BASE, CALLBACK, RESOURCE, _full_flow

PASSWORD = secrets.token_urlsafe(16)
PASSWORD_HASH = PasswordHasher(time_cost=1, memory_cost=8, parallelism=1).hash(PASSWORD)
SECRET = secrets.token_bytes(48)
DASHBOARD = "https://127.0.0.1:8080"
GET_ROUTES = [
    "/api/session",
    "/api/summary",
    "/api/pockets",
    "/api/movements",
    "/api/categories",
    "/api/history",
    "/api/fixed",
    "/api/closures/pending",
]


class Clock:
    """Reloj de prueba: la fecha (mes actual) y los segundos (sesión y límite de intentos)."""

    def __init__(self) -> None:
        self.day = TODAY
        self.seconds = 1_000_000.0

    def __call__(self):
        return self.day

    def time(self) -> float:
        return self.seconds


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def store():
    return InMemoryLedgerStore()


@pytest.fixture
def ledger(store, clock):
    service = LedgerService(store, today=clock, rate_range=RateRange(300, 1000))
    anyio.run(partial(build_world, store, service))
    return service


def _dashboard(store, ledger, clock, *, secure=True, static_dir=None, health=None, per_key=5):
    app = build_app(
        DashboardService(ledger, store, clock),
        SessionManager(SECRET, 12 * 3600, clock=clock.time),
        PasswordVerifier(PASSWORD_HASH),
        LoginRateLimiter(per_key_max=per_key, window_seconds=900, global_max=50),
        cookie_secure=secure,
        static_dir=static_dir,
        health=health,
        clock=clock.time,
    )
    return TestClient(app, base_url=DASHBOARD, follow_redirects=False)


@pytest.fixture
def api(store, ledger, clock):
    with _dashboard(store, ledger, clock) as client:
        yield client


def _login(client: TestClient, password: str = PASSWORD):
    return client.post("/api/session/login", json={"password": password})


@pytest.fixture
def auth(api):
    assert _login(api).status_code == 204
    return api


@pytest.fixture
def mcp(store, ledger, clock):
    """Las tools reales por MCP (OAuth incluido) sobre el MISMO almacén."""
    provider = OwnerOAuthProvider(
        store=InMemoryOAuthStore(),
        config=OAuthConfig(
            issuer_url=BASE, resource_url=RESOURCE, allowed_redirect_uris=(CALLBACK,)
        ),
        registration_limiter=EventLimiter(max_events=100, window_seconds=3600),
    )
    from tests.unit.test_oauth_http import PASSWORD_HASH as MCP_HASH

    components = AuthComponents(
        provider=provider,
        verifier=PasswordVerifier(MCP_HASH),
        limiter=LoginRateLimiter(),
        registration_enabled=True,
    )
    server = build_server(
        HealthService(lambda: None, timeout_seconds=2),
        components,
        BudgetService(store, today=clock),
        ledger,
    )
    settings = Settings(
        database_url="postgresql+psycopg://u:p@127.0.0.1:1/x",
        public_hostname="mcp.puropockets.space",
    )
    with TestClient(build_mcp_app(server, settings), base_url=BASE, follow_redirects=False) as http:
        _, token = _full_flow(http)
        yield Session(http, token["access_token"])


def _tool(mcp, name, **arguments) -> dict:
    result = mcp.call(name, **arguments)
    assert not result.get("isError"), result
    return result["structuredContent"]


# --- Sesión y acceso ---


@pytest.mark.parametrize("path", [*GET_ROUTES, "/api", "/api/no-existe"])
def test_sin_sesion_todo_api_responde_401(api, path):
    response = api.get(path)
    assert response.status_code == 401
    assert response.json() == {"detail": "Inicia sesión para ver el dashboard."}


def test_cierre_de_sesion_sin_sesion_tambien_401(api):
    assert api.post("/api/session/logout").status_code == 401


@pytest.mark.parametrize(
    "value",
    ["", "basura", "a.b", "a.b.c", "eyJzaWQiOiJ4IiwiZXhwIjo5OTk5OTk5OTk5fQ.firma-falsa"],
)
def test_cookie_falsa_o_alterada_401(api, value):
    api.cookies.set(COOKIE_NAME, value)
    assert api.get("/api/summary").status_code == 401


def test_cookie_firmada_con_otro_secreto_401(api, clock):
    forged = SessionManager(secrets.token_bytes(48), 3600, clock=clock.time).issue()
    api.cookies.set(COOKIE_NAME, forged)
    assert api.get("/api/summary").status_code == 401


def test_contraseña_mala_401_y_limite_de_intentos_429(api):
    for _ in range(5):
        response = _login(api, "contraseña-equivocada")
        assert response.status_code == 401
        assert COOKIE_NAME not in response.cookies
    blocked = _login(api)  # incluso la correcta queda bloqueada para esa IP
    assert blocked.status_code == 429
    assert int(blocked.headers["Retry-After"]) > 0
    assert api.get("/api/summary").status_code == 401


def test_el_bloqueo_vence_con_la_ventana(api, clock):
    for _ in range(5):
        _login(api, "mala")
    clock.seconds += 901
    assert _login(api).status_code == 204


def test_cookie_httponly_samesite_strict_secure_12h(api):
    response = _login(api)
    assert response.status_code == 204
    header = response.headers["set-cookie"]
    assert header.startswith(f"{COOKIE_NAME}=")
    lowered = header.lower()
    assert "httponly" in lowered
    assert "samesite=strict" in lowered
    assert "secure" in lowered
    assert "max-age=43200" in lowered
    assert "path=/" in lowered


def test_secure_configurable(store, ledger, clock):
    with _dashboard(store, ledger, clock, secure=False) as client:
        header = _login(client).headers["set-cookie"].lower()
    assert "httponly" in header and "samesite=strict" in header
    assert "secure" not in header


def test_sesion_valida_permite_leer_y_vence_a_las_12_horas(auth, clock):
    assert auth.get("/api/session").json() == {"current_month": "2026-11"}
    clock.seconds += 12 * 3600 + 1
    assert auth.get("/api/session").status_code == 401


def test_cerrar_sesion_borra_la_cookie_y_la_revoca(auth):
    token = auth.cookies.get(COOKIE_NAME)
    response = auth.post("/api/session/logout")
    assert response.status_code == 204
    assert "max-age=0" in response.headers["set-cookie"].lower()
    auth.cookies.set(COOKIE_NAME, token)  # reusar la cookie anterior
    assert auth.get("/api/summary").status_code == 401


def test_login_exige_json_y_mismo_origen(api):
    assert api.post("/api/session/login", data={"password": PASSWORD}).status_code == 400
    assert (
        api.post(
            "/api/session/login", content=b"{", headers={"content-type": "application/json"}
        ).status_code
        == 400
    )
    other = api.post(
        "/api/session/login",
        json={"password": PASSWORD},
        headers={"Origin": "https://mcp.puropockets.space"},
    )
    assert other.status_code == 403
    same = api.post(
        "/api/session/login", json={"password": PASSWORD}, headers={"Origin": DASHBOARD}
    )
    assert same.status_code == 204


# --- Verbos ---


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
@pytest.mark.parametrize("path", [*GET_ROUTES, "/", "/healthz", "/cualquier-cosa"])
def test_verbos_no_permitidos_405(auth, method, path):
    response = auth.request(method, path)
    assert response.status_code == 405
    assert response.headers["allow"] == "GET"


@pytest.mark.parametrize("path", ["/api/session/login", "/api/session/logout"])
@pytest.mark.parametrize("method", ["GET", "PUT", "DELETE"])
def test_sesion_solo_por_post(api, path, method):
    response = api.request(method, path)
    assert response.status_code == 405
    assert response.headers["allow"] == "POST"


# --- Cabeceras ---


def test_cabeceras_de_seguridad_y_sin_cors(auth):
    for path in ["/api/summary", "/api/no-existe", "/healthz"]:
        response = auth.get(path, headers={"Origin": "https://otro.example"})
        assert response.headers["content-security-policy"] == CONTENT_SECURITY_POLICY
        assert "default-src 'self'" in response.headers["content-security-policy"]
        assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
        assert response.headers["x-content-type-options"] == "nosniff"
        assert response.headers["referrer-policy"] == "no-referrer"
        assert "access-control-allow-origin" not in response.headers
    assert auth.get("/api/summary").headers["cache-control"] == "no-store"
    assert auth.options("/api/summary").status_code == 405  # sin preflight de CORS


def test_cabeceras_tambien_en_401(api):
    response = api.get("/api/summary")
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["content-security-policy"] == CONTENT_SECURITY_POLICY


# --- Identidad con las tools (SC-001) ---


@pytest.mark.parametrize("month", ["2026-11", "2026-10"])
def test_resumen_identico_a_get_summary(auth, mcp, month):
    api = auth.get("/api/summary", params={"month": month}).json()
    tool = _tool(mcp, "get_summary", month=month)
    assert api["month"] == tool["month"]
    assert api["income"] == tool["income_total"]
    assert api["extra_income"] == tool["extra_income_total"]
    assert api["spent"] == tool["expense_total"]
    assert api["month_closed"] == tool["month_closed"]
    assert api["closure_adjustments"] == tool["closure_adjustments"]
    assert api["pending_closure"] == tool["pending_closure"]
    for key in ("count", "total_crc", "usd_count", "usd_total"):
        assert api["unassigned"][key] == tool["unassigned"][key]
    consumo = [p["available"] for p in tool["pockets"] if p["behavior"] == "consumo"]
    assert api["available"] == sum(consumo)


@pytest.mark.parametrize("month", ["2026-11", "2026-10"])
def test_bolsas_identicas_a_get_bolsa_status_y_metas_a_get_goal_progress(auth, mcp, month):
    api = auth.get("/api/pockets", params={"month": month}).json()
    names = [p["pocket"] for p in _tool(mcp, "get_summary", month=month)["pockets"]]
    assert [p["name"] for p in api["items"]] == names
    goals = {g["pocket"]: g for g in _tool(mcp, "get_goal_progress")["items"]}
    for item in api["items"]:
        tool = _tool(mcp, "get_bolsa_status", pocket=item["name"], month=month)
        assert item["kind"] == tool["behavior"]
        assert item["assigned"] == tool["assigned"]
        assert item["received"] == tool["transfers_in"]
        assert item["sent"] == tool["transfers_out"]
        assert item["adjusted"] == tool["adjusted_budget"]
        assert item["spent"] == tool["spent"]
        assert item["available"] == tool["available"]
        assert item["used"] == tool["percent_used"]
        assert item["used_original"] == tool["percent_used_original"]
        assert item["balance"] == tool["balance"]
        assert item["negative"] == tool["negative"]
        assert api["month_closed"] == tool["month_closed"]
        if tool["goal"] is None:
            assert item["goal"] is None
            continue
        goal, progress = item["goal"], goals[item["name"]]
        assert goal["reference"] == tool["goal"]["reference"] == progress["reference"]
        assert goal["target"] == tool["goal"]["target_amount"] == progress["target_amount"]
        assert goal["progress"] == tool["goal"]["percent"] == progress["percent"]
        assert goal["remaining"] == tool["goal"]["missing"] == progress["missing"]
        assert goal["name"] == progress["name"]
        assert goal["status"] == progress["status"]
        assert goal["balance"] == progress["balance"]
        assert goal["excess"] == progress["excess"]
        assert goal["monthly_average"] == progress["avg_monthly_net_change"]
        assert goal["projectable"] == progress["projectable"]


@pytest.mark.parametrize(
    "filters",
    [
        {},
        {"month": "2026-11"},
        {"month": "2026-10"},
        {"type": "gasto", "include_voided": True},
        {"type": "transferencia"},
        {"type": "ingreso", "month": "2026-11"},
        {"pocket": "Gustos", "include_voided": True},
        {"pocket": "Necesidades", "month": "2026-11", "type": "gasto"},
    ],
)
def test_movimientos_identicos_a_list_transactions(auth, mcp, filters):
    params = {"include_voided": False, **filters}
    api = auth.get("/api/movements", params=params).json()
    tool = _tool(mcp, "list_transactions", limit=10, **params)
    assert len(api["items"]) == len(tool["items"])
    assert api["has_more"] == tool["has_more"]
    for mine, theirs in zip(api["items"], tool["items"], strict=True):
        assert mine["ref"] == theirs["reference"]
        for key in (
            "type",
            "kind",
            "date",
            "month",
            "description",
            "pocket",
            "from_pocket",
            "to_pocket",
            "category",
            "currency",
            "original_amount",
            "amount_crc",
            "voided",
            "void_reason",
            "reason",
            "note",
            "recurring",
        ):
            assert mine[key] == theirs.get(key), key
        assert mine["pending"] == (theirs["allocation_status"] == "pendiente")


def test_categorias_identicas_a_top_categories(auth, mcp):
    api = auth.get("/api/categories", params={"month": "2026-11"}).json()
    tool = _tool(mcp, "top_categories", month="2026-11", limit=20)
    assert api["total"] == tool["total_spent"] == 310_000
    assert [(c["name"], c["value"], c["percent"]) for c in api["items"]] == [
        (c["category"], c["amount_crc"], c["percent"]) for c in tool["items"]
    ]


# --- Anulados, mes cerrado, evolución y ahorrado ---


def test_anulados_no_suman_y_se_marcan(auth):
    summary = auth.get("/api/summary").json()
    assert summary["spent"] == EXPECTED["nov"]["spent"]  # sin los 35 000 anulados
    hidden = auth.get("/api/movements", params={"type": "gasto"}).json()["items"]
    assert all(not m["voided"] for m in hidden)
    shown = auth.get("/api/movements", params={"type": "gasto", "include_voided": True}).json()
    voided = [m for m in shown["items"] if m["voided"]]
    assert len(voided) == 1 and voided[0]["void_reason"] == "registro duplicado"
    gustos = next(p for p in auth.get("/api/pockets").json()["items"] if p["name"] == "Gustos")
    assert gustos["spent"] == 112_000


def test_mes_cerrado_marcado_con_sus_ajustes(auth):
    october = auth.get("/api/summary", params={"month": "2026-10"}).json()
    assert october["month_closed"] is True
    assert october["closure_adjustments"] == [
        {"pocket": "Necesidades", "kind": "sobrante_no_destinado", "amount": 5_000}
    ]
    assert auth.get("/api/pockets", params={"month": "2026-10"}).json()["month_closed"] is True
    november = auth.get("/api/summary").json()
    assert november["month_closed"] is False


def test_resumen_de_noviembre_a_mano(auth):
    summary = auth.get("/api/summary").json()
    for key, value in EXPECTED["nov"].items():
        assert summary[key] == value, key
    assert summary["saved_breakdown"] == {
        "base": 150_000,
        "extra": 0,
        "transfers_in": 0,
        "transfers_out": 0,
        "closure_surplus": 0,
    }
    assert summary["unassigned"] == {
        "count": 1,
        "total_crc": 13_000,
        "crc_count": 0,
        "crc_total": 0,
        "usd_count": 1,
        "usd_total": "25.00",
    }


def test_evolucion_de_seis_meses_con_ahorrado(auth):
    months = auth.get("/api/history").json()["months"]
    assert [m["month"] for m in months] == [
        "2026-06",
        "2026-07",
        "2026-08",
        "2026-09",
        "2026-10",
        "2026-11",
    ]
    assert months[0] == {"month": "2026-06", "income": 0, "spent": 0, "saved": 0}
    assert months[4] == {"month": "2026-10", **EXPECTED["oct"]}
    nov = {k: v for k, v in EXPECTED["nov"].items() if k != "available"}
    assert months[5] == {"month": "2026-11", **nov}


def test_evolucion_coincide_con_get_summary_cada_mes(auth, mcp):
    for row in auth.get("/api/history").json()["months"]:
        tool = _tool(mcp, "get_summary", month=row["month"])
        assert row["income"] == tool["income_total"]
        assert row["spent"] == tool["expense_total"]


def test_meta_con_fecha_estimada(auth):
    ahorro = next(p for p in auth.get("/api/pockets").json()["items"] if p["name"] == "Ahorro")
    goal = ahorro["goal"]
    assert goal["progress"] == 92 and goal["remaining"] == 40_000
    assert goal["monthly_average"] == 310_000 and goal["projectable"] is True
    assert goal["estimated_month"] == "2026-12"  # ⌈40 000 ÷ 310 000⌉ = 1 mes


def test_alertas_de_bolsas_y_extras(auth):
    pockets = {p["name"]: p for p in auth.get("/api/pockets").json()["items"]}
    assert pockets["Necesidades"]["alert"] == "warning"  # 81 %
    assert pockets["Gustos"]["alert"] == "danger"  # 104 %, −4 500
    assert pockets["Ahorro"]["alert"] is None
    alerts = auth.get("/api/summary").json()["alerts"]
    assert {"kind": "overspent", "pocket": "Gustos", "amount": 4_500} in [
        {k: v for k, v in a.items() if v is not None} for a in alerts
    ]
    assert any(a["kind"] == "high_usage" and a["percent"] == 81 for a in alerts)
    assert any(a["kind"] == "unassigned" and a["usd_total"] == "25.00" for a in alerts)


def test_cierre_pendiente_en_avisos(auth, clock, mcp):
    from datetime import date

    clock.day = date(2026, 12, 2)  # noviembre terminó sin cerrar (RN-49)
    summary = auth.get("/api/summary", params={"month": "2026-11"}).json()
    assert {"month": "2026-11", "has_movements": True} in summary["pending_closure"]
    assert any(a["kind"] == "close_pending" and a["month"] == "2026-11" for a in summary["alerts"])
    pending = auth.get("/api/closures/pending").json()["items"]
    assert pending == _tool(mcp, "get_summary")["pending_closure"]


def test_gastos_fijos_pagados_pendientes_y_atrasados(auth):
    fixed = auth.get("/api/fixed").json()
    status = {f["name"]: f["status"] for f in fixed["items"]}
    assert status == {"Alquiler": "paid", "Internet": "pending", "Video": "overdue"}
    video = next(f for f in fixed["items"] if f["name"] == "Video")
    assert video["currency"] == "USD" and video["amount"] == "12.99" and video["amount_crc"] is None
    assert fixed["pending_count"] == 2 and fixed["overdue_count"] == 1


def test_paginacion_con_tope(auth):
    first = auth.get("/api/movements", params={"include_voided": True}).json()
    assert first["page"] == 1 and first["page_size"] == 10 and len(first["items"]) == 10
    second = auth.get("/api/movements", params={"include_voided": True, "page": 2}).json()
    refs = {m["ref"] for m in first["items"]}
    assert second["items"] and refs.isdisjoint(m["ref"] for m in second["items"])
    assert auth.get("/api/movements", params={"page": 11}).status_code == 400
    assert auth.get("/api/movements", params={"page": 0}).status_code == 400


def test_parametros_invalidos_400_sin_repetir_la_entrada(auth):
    bad = auth.get("/api/movements", params={"type": "privado-xyz"})
    assert bad.status_code == 400 and "privado-xyz" not in bad.text
    month = auth.get("/api/summary", params={"month": "2026-13"})
    assert month.status_code == 400 and "AAAA-MM" in month.json()["detail"]


# --- Registros sin datos privados (FR-008) ---


def test_registros_sin_montos_ni_descripciones(auth, caplog):
    caplog.set_level(logging.DEBUG)
    for path in GET_ROUTES:
        auth.get(path)
    auth.get("/api/movements", params={"pocket": "Necesidades", "include_voided": True})
    auth.get("/api/summary", params={"month": "2026-10"})
    _login(auth, "mala")
    # Registros del servidor (el cliente de pruebas, httpx, registra su propia URL)
    server = [r for r in caplog.records if not r.name.startswith(("httpx", "httpcore"))]
    text = "\n".join(record.getMessage() for record in server)
    assert "GET /api/summary 200" in text  # sí se registra la petición
    for secret in (
        SECRET_DESCRIPTION,
        SECRET_NOTE,
        GOAL_NAME,
        "Necesidades",
        "168000",
        "168 000",
        "168.000",
        "310000",
        "44500",
        "4500",
        PASSWORD,
    ):
        assert secret not in text, secret


# --- Salud, estáticos y el MCP sin rutas del dashboard ---


def test_salud_sin_sesion(store, ledger, clock):
    with _dashboard(store, ledger, clock, health=lambda: None) as client:
        assert client.get("/healthz").json() == {"status": "ok"}

    def broken():
        raise OSError("sin base")

    with _dashboard(store, ledger, clock, health=broken) as client:
        assert client.get("/healthz").status_code == 503


def test_frontend_compilado_y_rutas_de_la_spa(store, ledger, clock, tmp_path):
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text("<!doctype html><title>Puro Pockets</title>")
    (tmp_path / "assets" / "app.js").write_text("console.log(1)")
    with _dashboard(store, ledger, clock, static_dir=tmp_path) as client:
        index = client.get("/")
        assert index.status_code == 200 and "Puro Pockets" in index.text
        assert index.headers["cache-control"] == "no-store"
        assert index.headers["content-security-policy"] == CONTENT_SECURITY_POLICY
        assert client.get("/bolsas").text == index.text  # la SPA atiende sus rutas
        assert client.get("/assets/app.js").text == "console.log(1)"
        assert client.get("/api/summary").status_code == 401  # /api nunca cae al index
        _login(client)
        assert client.get("/api/no-existe").status_code == 404


@pytest.mark.parametrize("path", ["/", "/api", "/api/summary", "/api/session", "/index.html"])
def test_el_mcp_no_sirve_rutas_del_dashboard(path):
    settings = Settings(
        database_url="postgresql+psycopg://u:p@127.0.0.1:1/x",
        public_hostname="mcp.puropockets.space",
    )
    server = build_server(HealthService(lambda: None, timeout_seconds=2))
    with TestClient(build_mcp_app(server, settings), base_url="https://mcp.puropockets.space") as c:
        response = c.get(path)
    assert response.status_code == 404
    assert "Puro Pockets" not in response.text and "income" not in response.text
