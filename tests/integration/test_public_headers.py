"""Encabezados por el camino del túnel contra el servidor levantado (Hito 2; ajustado en el 3).

Desde el Hito 3 la autenticación se evalúa antes que Host/Origin: sin token, cualquier petición a
/mcp recibe 401. Las comprobaciones de Host y Origin con token válido están en
tests/unit/test_oauth_http.py::test_host_y_origin_con_token.
"""

import http.client
import json
from urllib.parse import urlsplit

import pytest

pytestmark = pytest.mark.integration

PUBLIC_HOST = "mcp.puropockets.space"


def _post(mcp_url: str, extra_headers: dict[str, str]) -> http.client.HTTPResponse:
    url = urlsplit(mcp_url)
    connection = http.client.HTTPConnection(url.hostname, url.port, timeout=5)
    connection.request(
        "POST",
        url.path,
        body=json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}),
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            **extra_headers,
        },
    )
    response = connection.getresponse()
    response.read()
    connection.close()
    return response


@pytest.mark.parametrize(
    "headers",
    [
        {"Host": PUBLIC_HOST},
        {"Host": "127.0.0.1:8000"},
        {"Host": "evil.example.com"},
        {"Host": PUBLIC_HOST, "Origin": "https://evil.example.com"},
    ],
)
def test_sin_token_siempre_401(mcp_url, headers):
    response = _post(mcp_url, headers)
    assert response.status == 401
    assert (
        f'resource_metadata="https://{PUBLIC_HOST}/.well-known/oauth-protected-resource/mcp"'
        in response.getheader("WWW-Authenticate")
    )
