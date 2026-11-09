"""Extremo a extremo con Postgres real: /register, reinicio de la app, /authorize + login, /token,
/mcp con el token y refresco (reproduce el escenario del fallo "Client ID … not found")."""

from urllib.parse import parse_qs, urlsplit

import pytest
from sqlalchemy import delete
from starlette.testclient import TestClient

from puro_pockets.config import Settings
from puro_pockets.db.engine import create_engine_from_settings
from puro_pockets.db.oauth_store import SqlOAuthStore, oauth_clients
from puro_pockets.domain.auth import EventLimiter, LoginRateLimiter
from puro_pockets.mcp.server import AuthComponents, build_app, build_server
from puro_pockets.services.health import HealthService
from puro_pockets.services.oauth import OAuthConfig, OwnerOAuthProvider
from puro_pockets.services.passwords import PasswordVerifier
from tests.unit.test_oauth_http import (
    BASE,
    CALLBACK,
    PASSWORD,
    PASSWORD_HASH,
    RESOURCE,
    _authorize,
    _login,
    _mcp,
    _pkce,
    _register,
)

pytestmark = pytest.mark.integration


def _app(engine, registration_enabled: bool) -> TestClient:
    provider = OwnerOAuthProvider(
        store=SqlOAuthStore(engine),
        config=OAuthConfig(
            issuer_url=BASE, resource_url=RESOURCE, allowed_redirect_uris=(CALLBACK,)
        ),
        registration_limiter=EventLimiter(max_events=100, window_seconds=3600),
    )
    auth = AuthComponents(
        provider=provider,
        verifier=PasswordVerifier(PASSWORD_HASH),
        limiter=LoginRateLimiter(),
        registration_enabled=registration_enabled,
    )
    settings = Settings(database_url="unused", public_hostname="mcp.puropockets.space")
    app = build_app(build_server(HealthService(lambda: None, 2), auth), settings)
    return TestClient(app, base_url=BASE, follow_redirects=False)


def test_registro_reinicio_autorizacion_token_mcp_y_refresco(database_url):
    engine = create_engine_from_settings(Settings(database_url=database_url))
    client_id = None
    try:
        with _app(engine, registration_enabled=True) as http:
            client_id = _register(http).json()["client_id"]

        # "Reinicio": app y proveedor nuevos, misma base; registro ya cerrado
        with _app(engine, registration_enabled=False) as http:
            verifier, challenge = _pkce()
            authorize = _authorize(http, client_id, challenge)
            assert authorize.status_code == 302, authorize.text
            location = _login(http, authorize.headers["location"], PASSWORD).headers["location"]
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
            token = token.json()
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
            assert _mcp(http, "ppa_inventado").status_code == 401
    finally:
        if client_id:
            with engine.begin() as conn:
                conn.execute(delete(oauth_clients).where(oauth_clients.c.client_id == client_id))
        engine.dispose()
