"""Encabezados Host y Origin contra el servidor levantado (Hito 2, FR-005, FR-006, SC-004).

Simula lo que llega por el túnel: cloudflared reenvía el Host público `mcp.puropockets.space`.
"""

import http.client
import json
from urllib.parse import urlsplit

import pytest

pytestmark = pytest.mark.integration

PUBLIC_HOST = "mcp.puropockets.space"

INITIALIZE = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2025-06-18",
        "capabilities": {},
        "clientInfo": {"name": "prueba-encabezados", "version": "1"},
    },
}


def _post(mcp_url: str, extra_headers: dict[str, str]) -> int:
    # http.client respeta un encabezado Host explícito (así se simula el Host público del túnel)
    url = urlsplit(mcp_url)
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        **extra_headers,
    }
    connection = http.client.HTTPConnection(url.hostname, url.port, timeout=5)
    try:
        connection.request("POST", url.path, body=json.dumps(INITIALIZE), headers=headers)
        return connection.getresponse().status
    finally:
        connection.close()


@pytest.mark.parametrize(
    ("headers", "expected"),
    [
        ({"Host": PUBLIC_HOST}, 200),
        ({"Host": "127.0.0.1:8000"}, 200),
        ({"Host": "evil.example.com"}, 421),
        ({"Host": PUBLIC_HOST, "Origin": f"https://{PUBLIC_HOST}"}, 200),
        ({"Host": PUBLIC_HOST, "Origin": "https://claude.ai"}, 200),
        ({"Host": PUBLIC_HOST, "Origin": "https://evil.example.com"}, 403),
    ],
)
def test_encabezados(mcp_url, headers, expected):
    assert _post(mcp_url, headers) == expected
