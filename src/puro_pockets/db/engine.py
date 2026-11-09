"""Conexión a la base de datos (SQLAlchemy + psycopg 3)."""

from __future__ import annotations

from sqlalchemy import Engine, create_engine, text

from puro_pockets.config import Settings


def create_engine_from_settings(settings: Settings) -> Engine:
    """Motor con reconexión automática y tiempo límite de conexión."""
    return create_engine(
        settings.database_url,
        pool_pre_ping=True,
        connect_args={"connect_timeout": settings.db_connect_timeout},
    )


def check_database(engine: Engine) -> None:
    """Ejecuta una consulta trivial. Deja propagar cualquier error de conexión."""
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
