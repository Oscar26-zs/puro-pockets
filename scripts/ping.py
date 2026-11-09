"""Cliente de prueba: llama a la tool ping del servidor MCP por Streamable HTTP.

Desde el Hito 3, /mcp exige un token OAuth. Sin token, el script solo comprueba que el servidor
responde y exige autenticación (401). Con token, llama a ping.

Uso:
    uv run python scripts/ping.py                  # sin token: comprueba que pide autenticación
    MCP_ACCESS_TOKEN=... uv run python scripts/ping.py --times 20

El token se lee SOLO de la variable de entorno MCP_ACCESS_TOKEN (nunca como argumento, para que no
quede en el historial) y nunca se imprime.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import urllib.error
import urllib.request

import httpx2
from mcp import Client
from mcp.client.streamable_http import streamable_http_client


def _root_cause(exc: BaseException) -> BaseException:
    """Desarma los ExceptionGroup de anyio para mostrar el error real."""
    while isinstance(exc, BaseExceptionGroup) and exc.exceptions:
        exc = exc.exceptions[0]
    return exc


def _default_url() -> str:
    return f"http://127.0.0.1:{os.environ.get('MCP_PORT', '8000')}/mcp"


def check_requires_auth(url: str) -> int:
    """Sin token: el servidor está vivo si responde 401 con WWW-Authenticate."""
    request = urllib.request.Request(
        url,
        data=b"{}",
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        },
    )
    try:
        urllib.request.urlopen(request, timeout=10)
    except urllib.error.HTTPError as exc:
        if exc.code == 401 and "resource_metadata" in exc.headers.get("WWW-Authenticate", ""):
            print(json.dumps({"server": "ok", "auth": "required"}))
            return 0
        print(f"Respuesta inesperada sin token: HTTP {exc.code}", file=sys.stderr)
        return 1
    print("El servidor respondió sin pedir autenticación.", file=sys.stderr)
    return 1


async def call_ping(url: str, token: str, times: int) -> int:
    http_client = httpx2.AsyncClient(headers={"Authorization": f"Bearer {token}"}, timeout=30)
    async with http_client, Client(streamable_http_client(url, http_client=http_client)) as client:
        for _ in range(times):
            result = await client.call_tool("ping", {})
            print(json.dumps(result.structured_content, ensure_ascii=False))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Llama a la tool ping del servidor MCP.")
    parser.add_argument("--url", default=_default_url(), help="URL del endpoint MCP")
    parser.add_argument("--times", type=int, default=1, help="Cantidad de llamadas (con token)")
    args = parser.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    token = os.environ.get("MCP_ACCESS_TOKEN", "").strip()
    try:
        if not token:
            return check_requires_auth(args.url)
        return asyncio.run(call_ping(args.url, token, args.times))
    except Exception as exc:  # noqa: BLE001 - mensaje claro para el usuario
        cause = _root_cause(exc)
        print(
            f"No se pudo llamar a ping en {args.url}: {type(cause).__name__}: {cause}",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
