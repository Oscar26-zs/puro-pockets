"""Migraciones reversibles y protegidas, sobre una base temporal propia (FR-005, Hito 4 FR-017).

Nunca corren contra la base de desarrollo ni la del homelab: la fixture `empty_database` crea y
borra `pp_test_<aleatorio>`.
"""

import pytest
from alembic import command
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError

from tests.db_guard import assert_temp_database

from .conftest import alembic_config

pytestmark = pytest.mark.integration

HEAD = "0003_budget"


def _scalar(url: str, sql: str, **params):
    engine = create_engine(url)
    try:
        with engine.connect() as connection:
            return connection.execute(text(sql), params).scalar()
    finally:
        engine.dispose()


def _execute(url: str, sql: str, **params) -> None:
    engine = create_engine(url)
    try:
        with engine.begin() as connection:
            connection.execute(text(sql), params)
    finally:
        engine.dispose()


def _current_revision(url: str) -> str | None:
    if _scalar(url, "SELECT to_regclass('public.alembic_version')") is None:
        return None
    return _scalar(url, "SELECT version_num FROM alembic_version")


def test_subir_dos_veces_bajar_y_volver_a_subir(empty_database, monkeypatch):
    url, name = empty_database
    assert_temp_database(url, name)
    monkeypatch.delenv("ALLOW_DESTRUCTIVE_DOWNGRADE", raising=False)
    config = alembic_config(url)

    command.upgrade(config, "head")
    command.upgrade(config, "head")  # la segunda vez no hace nada y no falla
    assert _current_revision(url) == HEAD

    command.downgrade(config, "base")  # sin datos propios: solo las bolsas iniciales
    assert _current_revision(url) is None

    command.upgrade(config, "head")
    assert _current_revision(url) == HEAD


def test_datos_iniciales_solo_las_tres_bolsas(empty_database):
    url, _ = empty_database
    command.upgrade(alembic_config(url), "head")
    engine = create_engine(url)
    try:
        with engine.connect() as connection:
            rows = connection.execute(
                text("SELECT name, behavior, active FROM pockets ORDER BY id")
            ).all()
            allocations = connection.execute(
                text("SELECT count(*) FROM budget_month_allocations")
            ).scalar()
    finally:
        engine.dispose()
    assert [tuple(r) for r in rows] == [
        ("Necesidades", "consumo", True),
        ("Ahorro", "acumulable", True),
        ("Gustos", "consumo", True),
    ]
    assert allocations == 0  # el 50/30/20 lo guarda el propietario


def test_downgrade_con_datos_se_niega_salvo_con_la_variable(empty_database, monkeypatch):
    url, _ = empty_database
    config = alembic_config(url)
    command.upgrade(config, "head")
    _execute(
        url,
        "INSERT INTO budget_month_allocations (month, pocket_id, percentage) "
        "SELECT '2026-11', id, CASE name WHEN 'Necesidades' THEN 50 WHEN 'Ahorro' THEN 30 "
        "ELSE 20 END FROM pockets",
    )

    monkeypatch.delenv("ALLOW_DESTRUCTIVE_DOWNGRADE", raising=False)
    with pytest.raises(RuntimeError, match="ALLOW_DESTRUCTIVE_DOWNGRADE=true"):
        command.downgrade(config, "0002_oauth")
    assert _current_revision(url) == HEAD
    assert _scalar(url, "SELECT count(*) FROM budget_month_allocations") == 3

    monkeypatch.setenv("ALLOW_DESTRUCTIVE_DOWNGRADE", "true")
    command.downgrade(config, "0002_oauth")
    assert _current_revision(url) == "0002_oauth"


def test_downgrade_se_niega_si_las_bolsas_cambiaron(empty_database, monkeypatch):
    url, _ = empty_database
    config = alembic_config(url)
    command.upgrade(config, "head")
    _execute(url, "UPDATE pockets SET name = 'Necesidades del hogar' WHERE name = 'Necesidades'")
    monkeypatch.delenv("ALLOW_DESTRUCTIVE_DOWNGRADE", raising=False)
    with pytest.raises(RuntimeError, match="tienen datos"):
        command.downgrade(config, "0002_oauth")


def test_restricciones_de_la_base(empty_database):
    url, _ = empty_database
    command.upgrade(alembic_config(url), "head")
    bad = [
        "INSERT INTO pockets (name, behavior) VALUES ('AHORRO', 'acumulable')",  # nombre repetido
        "INSERT INTO pockets (name, behavior) VALUES ('Viaje', 'gasto')",  # comportamiento inválido
        "INSERT INTO budget_month_allocations VALUES ('2026-13', 1, 10)",  # mes inválido
        "INSERT INTO budget_month_allocations VALUES ('2026-11', 1, 101)",  # porcentaje > 100
        "INSERT INTO incomes (income_date, kind, budget_month, amount) "
        "VALUES ('2026-11-10', 'base', '2026-11', 0)",  # monto 0
    ]
    for sql in bad:
        with pytest.raises(IntegrityError):
            _execute(url, sql)
    initial = (
        "INSERT INTO incomes (income_date, kind, budget_month, amount, allocation_status) "
        "VALUES ('2026-11-10', 'saldo_inicial', '2026-11', 1000, 'repartido')"
    )
    _execute(url, initial)
    with pytest.raises(IntegrityError, match="ux_incomes_single_initial_balance"):
        _execute(url, initial)
