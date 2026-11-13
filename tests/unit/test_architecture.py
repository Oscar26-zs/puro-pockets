"""Arquitectura en capas (FR-010, gobernanza: regla no negociable 2).

La capa de dominio no puede depender de MCP, de la base de datos ni de las capas exteriores.
"""

import ast
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[2] / "src"
DOMAIN_DIR = SRC / "puro_pockets" / "domain"

FORBIDDEN_IN_DOMAIN = (
    "mcp",
    "sqlalchemy",
    "psycopg",
    "alembic",
    "puro_pockets.db",
    "puro_pockets.mcp",
    "puro_pockets.services",
    "puro_pockets.api",
    "fastapi",
    "starlette",
)


def imported_modules(source: str, module_name: str) -> set[str]:
    """Módulos importados por un archivo, resolviendo los imports relativos."""
    package_parts = module_name.split(".")[:-1]
    modules: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = package_parts[: len(package_parts) - node.level + 1]
                prefix = ".".join(base + ([node.module] if node.module else []))
            else:
                prefix = node.module or ""
            modules.add(prefix)
            # `from paquete import modulo` también importa submódulos (p. ej. `from .. import db`)
            modules.update(f"{prefix}.{alias.name}" for alias in node.names if prefix)
    return modules


def forbidden_imports(source: str, module_name: str) -> set[str]:
    return {
        mod
        for mod in imported_modules(source, module_name)
        for forbidden in FORBIDDEN_IN_DOMAIN
        if mod == forbidden or mod.startswith(forbidden + ".")
    }


def _module_name(path: Path) -> str:
    # src/puro_pockets/domain/health.py -> puro_pockets.domain.health
    return ".".join(path.relative_to(SRC).with_suffix("").parts)


def test_domain_no_importa_mcp_ni_base_de_datos():
    files = sorted(DOMAIN_DIR.rglob("*.py"))
    assert files, "No se encontraron módulos en domain/"
    violations = {
        str(path.relative_to(SRC)): sorted(found)
        for path in files
        if (found := forbidden_imports(path.read_text(encoding="utf-8"), _module_name(path)))
    }
    assert not violations, f"domain/ importa capas prohibidas: {violations}"


@pytest.mark.parametrize(
    "source",
    [
        "import sqlalchemy",
        "from sqlalchemy.orm import Session",
        "import mcp",
        "from mcp.server.mcpserver import MCPServer",
        "import psycopg",
        "from puro_pockets.db.engine import check_database",
        "from ..db import engine",
        "from ..mcp.server import build_server",
        "from .. import services",
    ],
)
def test_el_detector_reconoce_imports_prohibidos(source):
    # Comprueba que la prueba de arquitectura realmente fallaría ante una violación
    assert forbidden_imports(source, "puro_pockets.domain.ejemplo")


@pytest.mark.parametrize(
    "source",
    [
        "from dataclasses import dataclass",
        "from typing import Literal",
        "from puro_pockets.domain.health import HealthStatus",
        "from .health import HealthStatus",
    ],
)
def test_el_detector_permite_imports_validos(source):
    assert not forbidden_imports(source, "puro_pockets.domain.ejemplo")
