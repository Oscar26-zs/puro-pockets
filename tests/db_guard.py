"""Guardián de las pruebas de integración: solo se escribe en la base temporal que ellas crean.

Las pruebas crean `pp_test_<aleatorio>` en el Postgres local, la usan y la borran. Cualquier otra
base (la de desarrollo, la del homelab) se rechaza antes de tocar nada (FR-018).
"""

from __future__ import annotations

import secrets

from sqlalchemy.engine import make_url

TEST_DB_PREFIX = "pp_test_"
LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}


class UnsafeDatabaseError(RuntimeError):
    """La URL no apunta a la base temporal de las pruebas."""


def new_test_database_name() -> str:
    return f"{TEST_DB_PREFIX}{secrets.token_hex(6)}"


def assert_temp_database(url: str, expected_name: str) -> None:
    """Se niega a seguir si `url` no es la base temporal `expected_name` en este equipo."""
    parsed = make_url(url)
    name = parsed.database or ""
    if not expected_name.startswith(TEST_DB_PREFIX):
        raise UnsafeDatabaseError("La base esperada no es una base temporal de pruebas.")
    if name != expected_name or not name.startswith(TEST_DB_PREFIX):
        raise UnsafeDatabaseError(
            "Las pruebas de integración solo corren contra la base temporal que ellas crean; "
            "la URL apunta a otra base."
        )
    if parsed.host not in LOCAL_HOSTS:
        raise UnsafeDatabaseError(
            "Las pruebas de integración solo corren contra el Postgres local."
        )
