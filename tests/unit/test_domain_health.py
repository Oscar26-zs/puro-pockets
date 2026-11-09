"""Estado de salud del dominio (T012)."""

import dataclasses

import pytest

from puro_pockets.domain.health import HealthStatus


def test_database_ok():
    status = HealthStatus.database_ok()
    assert status.server == "ok"
    assert status.database == "ok"
    assert status.detail is None


def test_database_error():
    status = HealthStatus.database_error("x")
    assert status.server == "ok"
    assert status.database == "error"
    assert status.detail == "x"


def test_es_inmutable():
    status = HealthStatus.database_ok()
    with pytest.raises(dataclasses.FrozenInstanceError):
        status.database = "error"  # type: ignore[misc]
