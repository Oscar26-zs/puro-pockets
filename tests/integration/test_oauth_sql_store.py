"""Almacén SQL real + aplicación completa (Hito 3).

Emite tokens con el proveedor sobre Postgres (base temporal de las pruebas) y llama a ping, con el
token, en la aplicación ASGI real levantada en proceso sobre la misma base, con su propio proveedor
(como otra instancia del servidor). Comprueba que solo se guardan hashes, el refresco con rotación,
la reutilización y la revocación. Desde el Hito 4 no escribe en la base del contenedor (FR-018); el
401 del contenedor sin token sigue cubierto en test_ping_http.py.
"""

import base64
import hashlib
import json
import uuid
from functools import partial

import pytest
from mcp.server.auth.provider import AuthorizationParams
from mcp.shared.auth import OAuthClientInformationFull
from pydantic import AnyUrl
from sqlalchemy import delete, select
from starlette.testclient import TestClient

from puro_pockets.config import Settings
from puro_pockets.db.engine import check_database, create_engine_from_settings
from puro_pockets.db.oauth_store import (
    SqlOAuthStore,
    oauth_access_tokens,
    oauth_authorization_codes,
    oauth_clients,
)
from puro_pockets.domain.auth import EventLimiter, LoginRateLimiter, hash_token
from puro_pockets.mcp.server import AuthComponents, build_app, build_server
from puro_pockets.services.health import HealthService
from puro_pockets.services.oauth import OAuthConfig, OwnerOAuthProvider
from puro_pockets.services.passwords import PasswordVerifier

pytestmark = [pytest.mark.integration, pytest.mark.anyio]

CALLBACK = "https://claude.ai/api/mcp/auth_callback"
BASE = "https://mcp.puropockets.space"
RESOURCE = f"{BASE}/mcp"
MCP_HEADERS = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}


def _app_client(engine) -> TestClient:
    """Aplicación real con su propio proveedor sobre la misma base (otra "instancia")."""
    provider = OwnerOAuthProvider(
        store=SqlOAuthStore(engine),
        config=OAuthConfig(
            issuer_url=BASE, resource_url=RESOURCE, allowed_redirect_uris=(CALLBACK,)
        ),
    )
    auth = AuthComponents(
        provider=provider, verifier=PasswordVerifier(None), limiter=LoginRateLimiter()
    )
    health = HealthService(partial(check_database, engine), timeout_seconds=3)
    settings = Settings(database_url="unused", public_hostname="mcp.puropockets.space")
    return TestClient(build_app(build_server(health, auth), settings), base_url=BASE)


def _ping_status(http: TestClient, access_token: str) -> dict | int:
    """Llama a ping con el token; devuelve el contenido o el código HTTP de error."""
    headers = {**MCP_HEADERS, "Authorization": f"Bearer {access_token}"}
    init = http.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "prueba", "version": "1"},
            },
        },
        headers=headers,
    )
    if init.status_code != 200:
        return init.status_code
    headers |= {
        "mcp-session-id": init.headers["mcp-session-id"],
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
    if call.status_code != 200:
        return call.status_code
    data = next(json.loads(line[5:]) for line in call.text.splitlines() if line.startswith("data:"))
    return data["result"]["structuredContent"]


async def test_flujo_sql_y_ping_con_la_app_real(database_url):
    engine = create_engine_from_settings(Settings(database_url=database_url))
    http = _app_client(engine).__enter__()
    provider = OwnerOAuthProvider(
        store=SqlOAuthStore(engine),
        config=OAuthConfig(
            issuer_url="https://mcp.puropockets.space",
            resource_url=RESOURCE,
            allowed_redirect_uris=(CALLBACK,),
            max_clients=1000,
        ),
        registration_limiter=EventLimiter(max_events=100, window_seconds=3600),
    )
    client = OAuthClientInformationFull(
        client_id=f"prueba-{uuid.uuid4()}",
        client_name="Prueba de integración",
        redirect_uris=[AnyUrl(CALLBACK)],
        token_endpoint_auth_method="none",
        grant_types=["authorization_code", "refresh_token"],
        response_types=["code"],
        scope="mcp offline_access",
    )
    try:
        await provider.register_client(client)
        verifier = "v" * 64
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(
            b"="
        )
        url = await provider.authorize(
            client,
            AuthorizationParams(
                state="s",
                scopes=["mcp", "offline_access"],
                code_challenge=challenge.decode(),
                redirect_uri=AnyUrl(CALLBACK),
                redirect_uri_provided_explicitly=True,
                resource=RESOURCE,
            ),
        )
        redirect = await provider.complete_authorization(url.split("request=")[1])
        code = redirect.split("code=")[1].split("&")[0]
        tokens = await provider.exchange_authorization_code(
            client, await provider.load_authorization_code(client, code)
        )

        # En la base solo hay hashes
        with engine.connect() as conn:
            codes = (
                conn.execute(
                    select(oauth_authorization_codes.c.code_hash).where(
                        oauth_authorization_codes.c.client_id == client.client_id
                    )
                )
                .scalars()
                .all()
            )
            access_hashes = (
                conn.execute(
                    select(oauth_access_tokens.c.token_hash).where(
                        oauth_access_tokens.c.client_id == client.client_id
                    )
                )
                .scalars()
                .all()
            )
        assert codes == [hash_token(code)]
        assert access_hashes == [hash_token(tokens.access_token)]

        # La otra instancia valida el token contra la misma base
        assert _ping_status(http, tokens.access_token) == {
            "server": "ok",
            "database": "ok",
            "detail": None,
        }
        assert _ping_status(http, "ppa_inventado") == 401

        # Refresco con rotación; reutilizar el viejo revoca la cadena
        old = await provider.load_refresh_token(client, tokens.refresh_token)
        rotated = await provider.exchange_refresh_token(client, old, old.scopes)
        assert _ping_status(http, rotated.access_token) != 401
        assert await provider.load_refresh_token(client, tokens.refresh_token) is None
        assert _ping_status(http, rotated.access_token) == 401

        # Revocación de una cadena nueva
        url = await provider.authorize(
            client,
            AuthorizationParams(
                state=None,
                scopes=["mcp"],
                code_challenge=challenge.decode(),
                redirect_uri=AnyUrl(CALLBACK),
                redirect_uri_provided_explicitly=True,
                resource=RESOURCE,
            ),
        )
        redirect = await provider.complete_authorization(url.split("request=")[1])
        code = redirect.split("code=")[1].split("&")[0]
        fresh = await provider.exchange_authorization_code(
            client, await provider.load_authorization_code(client, code)
        )
        assert _ping_status(http, fresh.access_token) != 401
        await provider.revoke_token(await provider.load_access_token(fresh.access_token))
        assert _ping_status(http, fresh.access_token) == 401
    finally:
        http.__exit__(None, None, None)
        with engine.begin() as conn:
            conn.execute(delete(oauth_clients).where(oauth_clients.c.client_id == client.client_id))
        engine.dispose()
