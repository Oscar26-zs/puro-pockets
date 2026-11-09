"""Registro → autorización (también tras reiniciar), réplicas con bases distintas y auditoría.

Reproduce el fallo reportado en el Hito 3 ("Client ID … not found" para un cliente existente).
"""

import logging
from urllib.parse import parse_qs, urlsplit

from tests.fakes import InMemoryOAuthStore
from tests.unit.test_oauth_http import (
    CALLBACK,
    PASSWORD,
    RESOURCE,
    _authorize,
    _login,
    _make_client,
    _mcp,
    _pkce,
    _register,
)

SECRETS_THAT_MUST_NOT_BE_LOGGED = ("ppa_", "ppr_", "ppc_", "$argon2")


def test_registrar_por_http_y_autorizar(caplog):
    with _make_client() as http:
        client_id = _register(http).json()["client_id"]
        _, challenge = _pkce()
        response = _authorize(http, client_id, challenge)
    assert response.status_code == 302
    assert "/login?request=" in response.headers["location"]


def test_registrar_reiniciar_y_autorizar_con_la_misma_base():
    store = InMemoryOAuthStore()  # la "base" sobrevive al reinicio; la app y el proveedor no
    with _make_client(store=store) as http:
        client_id = _register(http).json()["client_id"]
    with _make_client(store=store, registration_enabled=False) as http:
        _, challenge = _pkce()
        response = _authorize(http, client_id, challenge)
        assert response.status_code == 302
        location = _login(http, response.headers["location"], PASSWORD).headers["location"]
    assert location.startswith(CALLBACK) and "code=" in location


def test_replica_con_otra_base_reproduce_client_not_found(caplog):
    """Dos réplicas del túnel con bases distintas: el registro cae en una y /authorize en otra."""
    with _make_client() as homelab:
        client_id = _register(homelab).json()["client_id"]
    caplog.set_level(logging.INFO, logger="puro_pockets.auth")
    with _make_client() as otra_maquina:  # otra base, como el equipo de desarrollo
        _, challenge = _pkce()
        response = _authorize(otra_maquina, client_id, challenge)
    assert response.status_code == 400
    assert "not found" in response.json()["error_description"]
    logs = caplog.text
    assert f"Cliente no encontrado en esta base: client_id={client_id[:8]}" in logs
    assert "Rechazo en /authorize: HTTP 400 error=invalid_request" in logs
    assert client_id not in logs  # solo los 8 primeros caracteres


def test_auditoria_de_registro_rechazado_por_el_sdk(caplog):
    """Un scope no admitido lo rechaza el SDK antes del proveedor: igual debe quedar el motivo."""
    caplog.set_level(logging.INFO, logger="puro_pockets.auth")
    with _make_client() as http:
        response = http.post(
            "/register",
            json={
                "redirect_uris": [CALLBACK],
                "token_endpoint_auth_method": "none",
                "grant_types": ["authorization_code", "refresh_token"],
                "response_types": ["code"],
                "client_name": "Claude",
                "scope": "claudeai",
            },
        )
    assert response.status_code == 400
    logs = caplog.text
    assert "Rechazo en /register: HTTP 400 error=invalid_client_metadata" in logs
    assert "claudeai" in logs  # el motivo exacto y el scope pedido
    assert "'client_name': 'Claude'" in logs


def test_auditoria_de_registro_rechazado_por_el_proveedor(caplog):
    caplog.set_level(logging.INFO, logger="puro_pockets.auth")
    with _make_client() as http:
        _register(http, redirect="https://evil.example.com/callback")
    logs = caplog.text
    assert "Registro rechazado: URL de retorno no permitida (evil.example.com)" in logs
    assert "Rechazo en /register: HTTP 400 error=invalid_redirect_uri" in logs


def test_auditoria_de_token_rechazado_sin_secretos(caplog):
    caplog.set_level(logging.INFO, logger="puro_pockets.auth")
    with _make_client() as http:
        client_id = _register(http).json()["client_id"]
        _, challenge = _pkce()
        login_url = _authorize(http, client_id, challenge).headers["location"]
        code = parse_qs(urlsplit(_login(http, login_url, PASSWORD).headers["location"]).query)[
            "code"
        ][0]
        response = http.post(
            "/token",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": CALLBACK,
                "client_id": client_id,
                "code_verifier": "verificador-incorrecto-" + "x" * 30,
                "resource": RESOURCE,
            },
        )
    assert response.status_code == 400
    logs = caplog.text
    assert "Rechazo en /token: HTTP 400 error=invalid_grant" in logs
    assert "grant_type': 'authorization_code'" in logs
    assert code not in logs
    assert "verificador-incorrecto" not in logs
    assert PASSWORD not in logs
    for secret in SECRETS_THAT_MUST_NOT_BE_LOGGED:
        assert secret not in logs


def test_flujo_completo_tras_reinicio_con_token_y_refresco():
    """Extremo a extremo: /authorize + login, /token, /mcp con el token y refresco, con reinicio."""
    store = InMemoryOAuthStore()
    with _make_client(store=store) as http:
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
        ).json()
        assert _mcp(http, token["access_token"]).status_code == 200

    # Reinicio: el token y el refresco siguen valiendo (están en la base, no en memoria)
    with _make_client(store=store, registration_enabled=False) as http:
        assert _mcp(http, token["access_token"]).status_code == 200
        refreshed = http.post(
            "/token",
            data={
                "grant_type": "refresh_token",
                "refresh_token": token["refresh_token"],
                "client_id": client_id,
                "resource": RESOURCE,
            },
        )
        assert refreshed.status_code == 200, refreshed.text
        assert _mcp(http, refreshed.json()["access_token"]).status_code == 200


def test_reinicio_entre_authorize_y_login_da_solicitud_vencida_y_queda_registrado(caplog):
    """Las solicitudes viven en memoria: un reinicio (u otra réplica) las pierde."""
    caplog.set_level(logging.INFO, logger="puro_pockets.auth")
    store = InMemoryOAuthStore()
    with _make_client(store=store) as http:
        client_id = _register(http).json()["client_id"]
        _, challenge = _pkce()
        login_url = _authorize(http, client_id, challenge).headers["location"]
    request_id = parse_qs(urlsplit(login_url).query)["request"][0]
    with _make_client(store=store) as http:  # otro proceso
        response = _login(http, login_url, PASSWORD)
    assert response.status_code == 400
    assert "Solicitud vencida" in response.text
    logs = caplog.text
    assert f"Solicitud de inicio de sesión creada: solicitud={request_id[:6]}" in logs
    assert f"Solicitud de inicio de sesión no encontrada: solicitud={request_id[:6]}" in logs
    assert request_id not in logs  # solo 6 caracteres


def test_envio_doble_del_formulario_devuelve_la_misma_redireccion(caplog):
    """Caso real del homelab: login correcto y un segundo envío del mismo formulario."""
    caplog.set_level(logging.INFO, logger="puro_pockets.auth")
    with _make_client() as http:
        client_id = _register(http).json()["client_id"]
        verifier, challenge = _pkce()
        login_url = _authorize(http, client_id, challenge).headers["location"]
        first = _login(http, login_url, PASSWORD)
        second = _login(http, login_url, PASSWORD)  # Enter + clic, doble clic…
        assert first.status_code == second.status_code == 302
        assert second.headers["location"] == first.headers["location"]

        # El código sigue siendo de un solo uso
        code = parse_qs(urlsplit(first.headers["location"]).query)["code"][0]
        exchange = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": CALLBACK,
            "client_id": client_id,
            "code_verifier": verifier,
            "resource": RESOURCE,
        }
        assert http.post("/token", data=exchange).status_code == 200
        assert http.post("/token", data=exchange).status_code == 400
    assert "Envío repetido del inicio de sesión" in caplog.text
    assert code not in caplog.text


def test_envio_repetido_exige_la_contrasena_correcta():
    with _make_client() as http:
        client_id = _register(http).json()["client_id"]
        _, challenge = _pkce()
        login_url = _authorize(http, client_id, challenge).headers["location"]
        assert _login(http, login_url, PASSWORD).status_code == 302
        repeated = _login(http, login_url, "incorrecta")
        assert repeated.status_code == 400
        assert "location" not in repeated.headers
