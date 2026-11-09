"""Migraciones reversibles contra la base levantada (T017, FR-005, SC-003)."""

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

from .conftest import REPO_ROOT

pytestmark = pytest.mark.integration


def _alembic_config(database_url: str) -> Config:
    config = Config(str(REPO_ROOT / "alembic.ini"))
    config.attributes["database_url"] = database_url
    return config


def _current_revision(database_url: str) -> str | None:
    engine = create_engine(database_url)
    try:
        with engine.connect() as connection:
            exists = connection.execute(
                text("SELECT to_regclass('public.alembic_version')")
            ).scalar()
            if exists is None:
                return None
            return connection.execute(text("SELECT version_num FROM alembic_version")).scalar()
    finally:
        engine.dispose()


def test_subir_dos_veces_bajar_y_volver_a_subir(database_url):
    config = _alembic_config(database_url)

    command.upgrade(config, "head")
    command.upgrade(config, "head")  # la segunda vez no hace nada y no falla
    assert _current_revision(database_url) == "0002_oauth"

    command.downgrade(config, "base")
    assert _current_revision(database_url) is None

    command.upgrade(config, "head")
    assert _current_revision(database_url) == "0002_oauth"
