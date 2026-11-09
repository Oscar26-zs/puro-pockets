"""Almacén SQL real + servidor levantado (Hito 3).

Emite tokens con el proveedor sobre Postgres (la misma base que usa el contenedor) y llama a ping en
el contenedor con un cliente MCP real y el token. Comprueba que solo se guardan hashes, el refresco
con rotación, la reutilización y la revocación.
"""

import base64
import hashlib
import uuid

import httpx2
import pytest
from mcp import Client
from mcp.client.streamable_http import streamable_http_client
from mcp.server.auth.provider import AuthorizationParams
from mcp.shared.auth import OAuthClientInformationFull
from pydantic import AnyUrl
from sqlalchemy import delete, select

from puro_pockets.config import Settings
from puro_pockets.db.engine import create_engine_from_settings
from puro_pockets.db.oauth_store import (
    SqlOAuthStore,
    oauth_access_tokens,
    oauth_authorization_codes,
    oauth_clients,
)
from puro_pockets.domain.auth import EventLimiter, hash_token
from puro_pockets.services.oauth import OAuthConfig, OwnerOAuthProvider

pytestmark = [pytest.mark.integration, pytest.mark.anyio]

CALLBACK = "https://claude.ai/api/mcp/auth_callback"
RESOURCE = "https://mcp.puropockets.space/mcp"  # el mismo que valida el contenedor


async def _ping_status(mcp_url: str, access_token: str) -> dict | int:
    """Llama a ping con un cliente MCP real; devuelve el contenido o el código HTTP de error."""
    headers = {"Authorization": f"Bearer {access_token}"}
    async with httpx2.AsyncClient(headers=headers, timeout=10) as http_client:
        probe = await http_client.post(
            mcp_url,
            json={"jsonrpc": "2.0", "id": 0, "method": "ping"},
            headers={"Accept": "application/json, text/event-stream"},
        )
        if probe.status_code == 401:
            return 401
        async with Client(streamable_http_client(mcp_url, http_client=http_client)) as client:
            return (await client.call_tool("ping", {})).structured_content


async def test_flujo_sql_y_ping_en_el_contenedor(database_url, mcp_url):
    engine = create_engine_from_settings(Settings(database_url=database_url))
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

        # El contenedor valida el token contra la misma base
        assert await _ping_status(mcp_url, tokens.access_token) == {
            "server": "ok",
            "database": "ok",
            "detail": None,
        }
        assert await _ping_status(mcp_url, "ppa_inventado") == 401

        # Refresco con rotación; reutilizar el viejo revoca la cadena
        old = await provider.load_refresh_token(client, tokens.refresh_token)
        rotated = await provider.exchange_refresh_token(client, old, old.scopes)
        assert await _ping_status(mcp_url, rotated.access_token) != 401
        assert await provider.load_refresh_token(client, tokens.refresh_token) is None
        assert await _ping_status(mcp_url, rotated.access_token) == 401

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
        assert await _ping_status(mcp_url, fresh.access_token) != 401
        await provider.revoke_token(await provider.load_access_token(fresh.access_token))
        assert await _ping_status(mcp_url, fresh.access_token) == 401
    finally:
        with engine.begin() as conn:
            conn.execute(delete(oauth_clients).where(oauth_clients.c.client_id == client.client_id))
        engine.dispose()
