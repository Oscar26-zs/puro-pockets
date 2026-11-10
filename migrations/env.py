"""Entorno de Alembic: toma la URL de la base de la variable DATABASE_URL."""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

from puro_pockets.config import load_settings

config = context.config

if config.config_file_name is not None:
    # disable_existing_loggers=False: no silenciar los loggers de la aplicación (p. ej. la
    # auditoría de OAuth) cuando Alembic corre en el mismo proceso
    fileConfig(config.config_file_name, disable_existing_loggers=False)

# Todavía no hay modelos (el Hito 1 no crea tablas de negocio)
target_metadata = None


def _database_url() -> str:
    # Permite que las pruebas pasen la URL explícitamente sin tocar el entorno
    return config.attributes.get("database_url") or load_settings().database_url


def run_migrations_offline() -> None:
    context.configure(url=_database_url(), target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(_database_url(), poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
