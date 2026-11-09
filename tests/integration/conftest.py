"""Utilidades de las pruebas de integración (requieren `docker compose up`)."""

import os
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


def _env_value(name: str) -> str | None:
    """Lee una variable del entorno o, si no está, del archivo .env de la raíz."""
    if os.environ.get(name):
        return os.environ[name]
    env_file = REPO_ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                if key.strip() == name:
                    return value.strip()
    return None


@pytest.fixture
def database_url() -> str:
    url = _env_value("DATABASE_URL")
    if not url:
        pytest.fail("Falta DATABASE_URL (en el entorno o en .env) para las pruebas de integración.")
    return url


@pytest.fixture
def mcp_url() -> str:
    port = _env_value("MCP_PORT") or "8000"
    return f"http://127.0.0.1:{port}/mcp"
