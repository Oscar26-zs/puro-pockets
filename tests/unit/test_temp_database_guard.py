"""El guardián impide que las pruebas de integración escriban fuera de su base temporal (FR-018)."""

import pytest

from tests.db_guard import (
    TEST_DB_PREFIX,
    UnsafeDatabaseError,
    assert_temp_database,
    new_test_database_name,
)

LOCAL = "postgresql+psycopg://u:p@127.0.0.1:5432/"


def test_acepta_la_base_temporal_creada():
    name = new_test_database_name()
    assert name.startswith(TEST_DB_PREFIX)
    assert_temp_database(LOCAL + name, name)


@pytest.mark.parametrize(
    "url, expected",
    [
        (LOCAL + "puro_pockets", "pp_test_abc"),  # la base de desarrollo
        (LOCAL + "pp_test_otra", "pp_test_abc"),  # otra base temporal
        (LOCAL + "puro_pockets", "puro_pockets"),  # "esperada" sin el prefijo
        ("postgresql+psycopg://u:p@db:5432/pp_test_abc", "pp_test_abc"),  # host del contenedor
        ("postgresql+psycopg://u:p@192.168.1.50:5432/pp_test_abc", "pp_test_abc"),  # otra máquina
    ],
)
def test_rechaza_cualquier_otra_base(url, expected):
    with pytest.raises(UnsafeDatabaseError):
        assert_temp_database(url, expected)


def test_los_nombres_son_unicos():
    assert len({new_test_database_name() for _ in range(50)}) == 50
