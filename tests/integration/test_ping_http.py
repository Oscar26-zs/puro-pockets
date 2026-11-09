"""/mcp por Streamable HTTP contra los servicios levantados.

Desde el Hito 3, /mcp exige token: sin él responde 401 con el puntero a los metadatos (la llamada a
ping con token se prueba en test_oauth_sql_store.py).
"""

import json
import time
import urllib.error
import urllib.request

import pytest

pytestmark = pytest.mark.integration


def test_mcp_sin_token_responde_401_rapido(mcp_url):
    request = urllib.request.Request(
        mcp_url,
        data=b"{}",
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        },
    )
    start = time.monotonic()
    with pytest.raises(urllib.error.HTTPError) as exc:
        urllib.request.urlopen(request, timeout=5)
    assert time.monotonic() - start < 2
    assert exc.value.code == 401
    assert "resource_metadata=" in exc.value.headers["WWW-Authenticate"]


def test_metadatos_publicos(mcp_url):
    base = mcp_url.removesuffix("/mcp")
    with urllib.request.urlopen(f"{base}/.well-known/oauth-protected-resource/mcp") as response:
        resource = json.load(response)
    assert resource["resource"] == "https://mcp.puropockets.space/mcp"
    with urllib.request.urlopen(f"{base}/.well-known/oauth-authorization-server") as response:
        server = json.load(response)
    assert server["code_challenge_methods_supported"] == ["S256"]
    assert "offline_access" in server["scopes_supported"]
    # Registro cerrado por defecto
    assert "registration_endpoint" not in server
