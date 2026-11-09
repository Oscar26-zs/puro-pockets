"""Cliente de prueba: llama a la tool ping del servidor MCP por Streamable HTTP.

Uso:
    uv run python scripts/ping.py             # una llamada
    uv run python scripts/ping.py --times 20  # 20 llamadas (medición de memoria)
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys

from mcp import Client


def _root_cause(exc: BaseException) -> BaseException:
    """Desarma los ExceptionGroup de anyio para mostrar el error real."""
    while isinstance(exc, BaseExceptionGroup) and exc.exceptions:
        exc = exc.exceptions[0]
    return exc


def _default_url() -> str:
    return f"http://127.0.0.1:{os.environ.get('MCP_PORT', '8000')}/mcp"


async def _run(url: str, times: int) -> int:
    async with Client(url) as client:
        for _ in range(times):
            result = await client.call_tool("ping", {})
            print(json.dumps(result.structured_content, ensure_ascii=False))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Llama a la tool ping del servidor MCP.")
    parser.add_argument("--url", default=_default_url(), help="URL del endpoint MCP")
    parser.add_argument("--times", type=int, default=1, help="Cantidad de llamadas")
    args = parser.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    try:
        return asyncio.run(_run(args.url, args.times))
    except Exception as exc:  # noqa: BLE001 - mensaje claro para el usuario
        cause = _root_cause(exc)
        print(
            f"No se pudo llamar a ping en {args.url}: {type(cause).__name__}: {cause}",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
