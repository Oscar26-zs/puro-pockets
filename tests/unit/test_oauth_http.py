"""Flujo OAuth completo por HTTP, en proceso, con un cliente de prueba (Hito 3).

Usa la aplicación ASGI real (SDK + proveedor + página de inicio de sesión) con almacén en memoria.
La contraseña de prueba se genera aquí y nunca se imprime.
"""

import base64
import hashlib
import json
import secrets
from urllib.parse import parse_qs, urlsplit

import pytest
from argon2 import PasswordHasher
from starlette.testclient import TestClient

from puro_pockets.config import Settings
from puro_pockets.domain.auth import EventLimiter, LoginRateLimiter
from puro_pockets.mcp.server import AuthComponents, build_app, build_server
from puro_pockets.services.health import HealthService
from puro_pockets.services.oauth import OAuthConfig, OwnerOAuthProvider
from puro_pockets.services.passwords import PasswordVerifier
from tests.fakes import InMemoryOAuthStore

BASE = "https://mcp.puropockets.space"
RESOURCE = f"{BASE}/mcp"
CALLBACK = "https://claude.ai/api/mcp/auth_callback"
PASSWORD = secrets.token_urlsafe(16)
# Parámetros mínimos solo para que las pruebas sean rápidas
PASSWORD_HASH = PasswordHasher(time_cost=1, memory_cost=8, parallelism=1).hash(PASSWORD)
MCP_HEADERS = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}
INITIALIZE = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2025-06-18",
        "capabilities": {},
        "clientInfo": {"name": "cliente-de-prueba", "version": "1"},
    },
}


def _make_client(
    registration_enabled: bool = True,
    password_hash: str | None = PASSWORD_HASH,
    store=None,
):
    """App completa nueva. Pasar el mismo `store` a dos llamadas simula un reinicio del servidor."""
    settings = Settings(
        database_url="postgresql+psycopg://u:p@127.0.0.1:1/x",
        public_hostname="mcp.puropockets.space",
        allowed_origins=("https://claude.ai",),
    )
    provider = OwnerOAuthProvider(
        store=store if store is not None else InMemoryOAuthStore(),
        config=OAuthConfig(
            issuer_url=BASE,
            resource_url=RESOURCE,
            allowed_redirect_uris=(CALLBACK, "https://claude.com/api/mcp/auth_callback"),
            max_clients=10,
        ),
        registration_limiter=EventLimiter(max_events=100, window_seconds=3600),
    )
    auth = AuthComponents(
        provider=provider,
        verifier=PasswordVerifier(password_hash),
        limiter=LoginRateLimiter(per_key_max=5, window_seconds=900, global_max=50),
        registration_enabled=registration_enabled,
    )
    app = build_app(build_server(HealthService(lambda: None, timeout_seconds=2), auth), settings)
    return TestClient(app, base_url=BASE, follow_redirects=False)


@pytest.fixture
def http():
    with _make_client() as client:
        yield client


def _register(http: TestClient, redirect: str = CALLBACK):
    return http.post(
        "/register",
        json={
            "redirect_uris": [redirect],
            "token_endpoint_auth_method": "none",
            "grant_types": ["authorization_code", "refresh_token"],
            "response_types": ["code"],
            "client_name": "Claude",
            "scope": "mcp offline_access",
        },
    )


def _pkce() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=")
    return verifier, challenge.decode()


def _authorize(http: TestClient, client_id: str, challenge: str):
    return http.get(
        "/authorize",
        params={
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": CALLBACK,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "state": "estado-123",
            "scope": "mcp offline_access",
            "resource": RESOURCE,
        },
    )


def _login(http: TestClient, login_url: str, password: str, ip: str = "203.0.113.7"):
    request_id = parse_qs(urlsplit(login_url).query)["request"][0]
    return http.post(
        "/login",
        data={"request": request_id, "password": password},
        headers={"CF-Connecting-IP": ip},
    )


def _full_flow(http: TestClient) -> tuple[str, dict]:
    client_id = _register(http).json()["client_id"]
    verifier, challenge = _pkce()
    login_url = _authorize(http, client_id, challenge).headers["location"]
    location = _login(http, login_url, PASSWORD).headers["location"]
    code = parse_qs(urlsplit(location).query)["code"][0]
    token = http.post(
        "/token",
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": CALLBACK,
            "client_id": client_id,
            "code_verifier": verifier,
            "resource": RESOURCE,
        },
    )
    assert token.status_code == 200, token.text
    return client_id, token.json()


def _mcp(http: TestClient, access_token: str | None, **headers: str):
    auth = {"Authorization": f"Bearer {access_token}"} if access_token else {}
    return http.post("/mcp", json=INITIALIZE, headers={**MCP_HEADERS, **auth, **headers})


# --- 401 ---


def test_sin_token_401_con_resource_metadata(http):
    response = _mcp(http, None)
    assert response.status_code == 401
    header = response.headers["www-authenticate"]
    assert header.startswith("Bearer ")
    assert f'resource_metadata="{BASE}/.well-known/oauth-protected-resource/mcp"' in header


def test_token_invalido_401(http):
    assert _mcp(http, "ppa_inventado").status_code == 401


# --- Metadatos ---


def test_metadatos_del_recurso_y_del_servidor(http):
    resource = http.get("/.well-known/oauth-protected-resource/mcp").json()
    assert resource["resource"] == RESOURCE
    assert resource["authorization_servers"][0].rstrip("/") == BASE
    server = http.get("/.well-known/oauth-authorization-server").json()
    assert server["code_challenge_methods_supported"] == ["S256"]
    assert "offline_access" in server["scopes_supported"]
    assert server["registration_endpoint"] == f"{BASE}/register"
    assert server["revocation_endpoint"] == f"{BASE}/revoke"


# --- Flujo completo ---


def test_flujo_completo_y_ping_con_token(http):
    client_id, token = _full_flow(http)
    assert token["token_type"].lower() == "bearer"
    assert token["expires_in"] == 3600
    assert token["refresh_token"]

    init = _mcp(http, token["access_token"])
    assert init.status_code == 200, init.text
    session = init.headers["mcp-session-id"]
    headers = {
        **MCP_HEADERS,
        "Authorization": f"Bearer {token['access_token']}",
        "mcp-session-id": session,
        "mcp-protocol-version": "2025-06-18",
    }
    http.post(
        "/mcp", json={"jsonrpc": "2.0", "method": "notifications/initialized"}, headers=headers
    )
    call = http.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "ping"}},
        headers=headers,
    )
    assert call.status_code == 200
    data = next(json.loads(line[5:]) for line in call.text.splitlines() if line.startswith("data:"))
    assert data["result"]["structuredContent"] == {
        "server": "ok",
        "database": "ok",
        "detail": None,
    }


def test_pagina_de_inicio_muestra_el_dominio_de_retorno(http):
    client_id = _register(http).json()["client_id"]
    _, challenge = _pkce()
    login_url = _authorize(http, client_id, challenge).headers["location"]
    assert login_url.startswith(f"{BASE}/login?request=")
    page = http.get(login_url)
    assert page.status_code == 200
    assert "claude.ai" in page.text
    assert (
        "form-action 'self' https://claude.ai https://claude.com"
        in page.headers["content-security-policy"]
    )


def test_contrasena_incorrecta_no_emite_codigo(http):
    client_id = _register(http).json()["client_id"]
    _, challenge = _pkce()
    login_url = _authorize(http, client_id, challenge).headers["location"]
    response = _login(http, login_url, "incorrecta")
    assert response.status_code == 401
    assert "location" not in response.headers


def test_limite_de_intentos_de_inicio_de_sesion(http):
    client_id = _register(http).json()["client_id"]
    _, challenge = _pkce()
    login_url = _authorize(http, client_id, challenge).headers["location"]
    for _ in range(5):
        assert _login(http, login_url, "incorrecta").status_code == 401
    # Bloqueada incluso con la contraseña correcta; otra IP no
    assert _login(http, login_url, PASSWORD).status_code == 429
    assert _login(http, login_url, PASSWORD, ip="198.51.100.9").status_code == 302


def test_el_bloqueo_de_login_no_afecta_a_mcp_con_token(http):
    _, token = _full_flow(http)
    client_id = _register(http).json()["client_id"]
    _, challenge = _pkce()
    login_url = _authorize(http, client_id, challenge).headers["location"]
    for _ in range(6):
        _login(http, login_url, "incorrecta")
    assert _mcp(http, token["access_token"]).status_code == 200


# --- Registro ---


def test_registro_con_retorno_no_permitido_rechazado(http):
    response = _register(http, redirect="https://evil.example.com/callback")
    assert response.status_code == 400
    assert response.json()["error"] == "invalid_redirect_uri"


def test_registro_cerrado_por_defecto():
    with _make_client(registration_enabled=False) as http:
        assert _register(http).status_code == 404
        assert (
            "registration_endpoint"
            not in http.get("/.well-known/oauth-authorization-server").json()
        )


def test_sin_hash_configurado_el_login_queda_deshabilitado():
    with _make_client(password_hash=None) as http:
        client_id = _register(http).json()["client_id"]
        _, challenge = _pkce()
        login_url = _authorize(http, client_id, challenge).headers["location"]
        assert _login(http, login_url, "lo-que-sea").status_code == 503


# --- Refresco y revocación ---


def test_refresco_con_rotacion_y_reutilizacion(http):
    client_id, first = _full_flow(http)
    refresh = {"grant_type": "refresh_token", "client_id": client_id, "resource": RESOURCE}

    second = http.post("/token", data={**refresh, "refresh_token": first["refresh_token"]})
    assert second.status_code == 200, second.text
    second = second.json()
    assert second["refresh_token"] != first["refresh_token"]
    assert _mcp(http, second["access_token"]).status_code == 200

    reuse = http.post("/token", data={**refresh, "refresh_token": first["refresh_token"]})
    assert reuse.status_code == 400
    assert reuse.json()["error"] == "invalid_grant"
    # La reutilización revocó toda la cadena
    assert _mcp(http, second["access_token"]).status_code == 401


def test_revocacion(http):
    client_id, token = _full_flow(http)
    # Defecto del SDK mcp==2.3.0: RevocationRequest declara `client_secret: str | None` sin valor
    # por defecto: un cliente público que (como pide RFC 7009) no lo envía recibe 400. Si esta
    # aserción falla tras actualizar el SDK, el defecto se corrigió: quitar el client_secret vacío.
    sdk_defect = http.post("/revoke", data={"token": token["access_token"], "client_id": client_id})
    assert sdk_defect.status_code == 400
    assert _mcp(http, token["access_token"]).status_code == 200

    revoke = http.post(
        "/revoke",
        data={"token": token["access_token"], "client_id": client_id, "client_secret": ""},
    )
    assert revoke.status_code == 200
    assert _mcp(http, token["access_token"]).status_code == 401


# --- Host y Origin con token válido (protección contra DNS rebinding) ---


def test_host_y_origin_con_token(http):
    _, token = _full_flow(http)
    access = token["access_token"]
    assert _mcp(http, access, Host="evil.example.com").status_code == 421
    assert _mcp(http, access, Origin="https://evil.example.com").status_code == 403
    assert _mcp(http, access, Origin="https://claude.ai").status_code == 200
