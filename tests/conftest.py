"""Configuración común de pytest."""

import pytest


@pytest.fixture
def anyio_backend() -> str:
    # Pruebas asíncronas con el plugin de anyio (incluido con mcp), sobre asyncio
    return "asyncio"
