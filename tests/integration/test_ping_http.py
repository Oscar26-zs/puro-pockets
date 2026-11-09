"""ping por Streamable HTTP contra los servicios levantados (T015, SC-004)."""

import time

import pytest
from mcp import Client

pytestmark = [pytest.mark.integration, pytest.mark.anyio]


async def test_ping_por_http_con_base_operativa(mcp_url):
    async with Client(mcp_url) as client:
        start = time.monotonic()
        result = await client.call_tool("ping", {})
        elapsed = time.monotonic() - start
    assert result.structured_content == {"server": "ok", "database": "ok", "detail": None}
    assert elapsed < 2
