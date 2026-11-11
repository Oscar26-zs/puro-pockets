"""Utilidades de las pruebas de integración (requieren `docker compose up`).

Las pruebas que tocan la base usan una base temporal propia (`pp_test_<aleatorio>`) en el Postgres
local, creada y borrada aquí. `DATABASE_URL` solo se usa para llegar al servidor y crear/borrar esa
base: nunca se escribe en la base de desarrollo, y el guardián rechaza cualquier otra (FR-018).
"""

import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import make_url

from tests.db_guard import assert_temp_database, new_test_database_name

REPO_ROOT = Path(__file__).resolve().parents[2]
SEED_POCKETS = (("Necesidades", "consumo"), ("Ahorro", "acumulable"), ("Gustos", "consumo"))


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


def _server_url() -> str:
    url = _env_value("DATABASE_URL")
    if not url:
        pytest.fail("Falta DATABASE_URL (en el entorno o en .env) para las pruebas de integración.")
    return url


def alembic_config(database_url: str) -> Config:
    config = Config(str(REPO_ROOT / "alembic.ini"))
    config.attributes["database_url"] = database_url
    return config


@contextmanager
def temporary_database(migrate: bool) -> Iterator[tuple[str, str]]:
    """Crea una base temporal vacía (y opcionalmente migrada); la borra al terminar."""
    server = make_url(_server_url())
    name = new_test_database_name()
    url = server.set(database=name).render_as_string(hide_password=False)
    assert_temp_database(url, name)
    admin = create_engine(server.set(database="postgres"), isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as conn:
            conn.execute(text(f'CREATE DATABASE "{name}"'))
        try:
            if migrate:
                command.upgrade(alembic_config(url), "head")
            yield url, name
        finally:
            with admin.connect() as conn:
                conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
    finally:
        admin.dispose()


@pytest.fixture(scope="session")
def _session_database() -> Iterator[tuple[str, str]]:
    with temporary_database(migrate=True) as created:
        yield created


@pytest.fixture
def database_url(_session_database) -> str:
    """URL de la base temporal de la sesión, ya migrada."""
    url, name = _session_database
    assert_temp_database(url, name)
    return url


@pytest.fixture
def empty_database() -> Iterator[tuple[str, str]]:
    """Base temporal propia y vacía (sin migrar), para las pruebas de migraciones."""
    with temporary_database(migrate=False) as created:
        yield created


@pytest.fixture
def budget_engine(_session_database) -> Iterator[Engine]:
    """Motor sobre la base temporal con las tablas del presupuesto en su estado inicial."""
    url, name = _session_database
    assert_temp_database(url, name)
    engine = create_engine(url)
    reset_budget(engine, name)
    try:
        yield engine
    finally:
        engine.dispose()


def reset_budget(engine: Engine, expected_name: str, pockets=SEED_POCKETS) -> None:
    """Vacía las tablas del presupuesto y deja las bolsas indicadas (por defecto, las iniciales)."""
    assert_temp_database(engine.url.render_as_string(hide_password=False), expected_name)
    with engine.begin() as conn:
        conn.execute(
            text(
                "TRUNCATE income_allocations, incomes, budget_month_allocations, categories, "
                "pockets RESTART IDENTITY CASCADE"
            )
        )
        for pocket_name, behavior in pockets:
            conn.execute(
                text("INSERT INTO pockets (name, behavior) VALUES (:n, :b)"),
                {"n": pocket_name, "b": str(behavior)},
            )


@pytest.fixture
def mcp_url() -> str:
    port = _env_value("MCP_PORT") or "8000"
    return f"http://127.0.0.1:{port}/mcp"
