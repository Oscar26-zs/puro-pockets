"""Tool ping en memoria, con la comprobación de base simulada (T014, contrato contracts/ping.md)."""

import time

import pytest
from mcp import Client

from puro_pockets.mcp.server import build_server
from puro_pockets.services.health import HealthService

pytestmark = pytest.mark.anyio

SECRET_URL = "postgresql+psycopg://usuario-secreto:clave-secreta@host-interno:5432/x"


def _ok() -> None:
    return None


def _falla() -> None:
    raise RuntimeError(f"connection failed for {SECRET_URL}")


def _lenta() -> None:
    time.sleep(3)


async def _ping(checker, timeout_seconds: float = 2) -> dict:
    server = build_server(HealthService(checker, timeout_seconds=timeout_seconds))
    async with Client(server) as client:
        result = await client.call_tool("ping", {})
        assert result.structured_content is not None
        return result.structured_content


async def test_ping_esta_registrada_con_esquema_de_salida():
    server = build_server(HealthService(_ok, timeout_seconds=2))
    async with Client(server) as client:
        tools = (await client.list_tools()).tools
    ping = next(t for t in tools if t.name == "ping")
    assert ping.output_schema is not None


async def test_base_operativa():
    assert await _ping(_ok) == {"server": "ok", "database": "ok", "detail": None}


async def test_base_con_error_responde_estructurado_y_sin_datos_internos():
    result = await _ping(_falla)
    assert result["server"] == "ok"
    assert result["database"] == "error"
    detail = result["detail"]
    assert detail
    for secreto in ("usuario-secreto", "clave-secreta", "host-interno", "postgresql"):
        assert secreto not in detail


async def test_base_lenta_corta_por_tiempo_limite():
    start = time.monotonic()
    result = await _ping(_lenta, timeout_seconds=1)
    elapsed = time.monotonic() - start
    assert result["database"] == "error"
    assert elapsed < 5
