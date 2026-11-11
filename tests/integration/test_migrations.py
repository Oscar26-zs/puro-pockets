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

HEAD = "0004_movements"


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
        "INSERT INTO incomes (income_date, kind, budget_month, amount, original_amount, "
        "allocation_status) VALUES ('2026-11-10', 'saldo_inicial', '2026-11', 1000, 1000, "
        "'repartido')"
    )
    _execute(url, initial)
    with pytest.raises(IntegrityError, match="ux_incomes_single_initial_balance"):
        _execute(url, initial)


# --- Hito 5: 0004_movements ---

HITO4_DATA = (
    "INSERT INTO budget_month_allocations (month, pocket_id, percentage) "
    "SELECT '2026-11', id, CASE name WHEN 'Necesidades' THEN 50 WHEN 'Ahorro' THEN 30 ELSE 20 END "
    "FROM pockets",
    "INSERT INTO incomes (income_date, kind, budget_month, amount, allocation_status) "
    "VALUES ('2026-11-10', 'saldo_inicial', '2026-11', 684757, 'repartido')",
    "INSERT INTO income_allocations (income_id, pocket_id, percentage, amount) "
    "SELECT 1, id, NULL, CASE name WHEN 'Necesidades' THEN 104729 WHEN 'Ahorro' THEN 523717 "
    "ELSE 56311 END FROM pockets",
)
CRC_EXPENSE = (
    "INSERT INTO expenses (expense_date, month, pocket_id, original_amount, amount) "
    "VALUES ('2026-11-10', '2026-11', 1, 4321, 4321)"
)


def _rows(url: str, sql: str) -> list[tuple]:
    engine = create_engine(url)
    try:
        with engine.connect() as connection:
            return [tuple(r) for r in connection.execute(text(sql)).all()]
    finally:
        engine.dispose()


def test_0004_conserva_los_datos_del_hito_4(empty_database):
    url, name = empty_database
    assert_temp_database(url, name)
    config = alembic_config(url)
    command.upgrade(config, "0003_budget")
    for sql in HITO4_DATA:
        _execute(url, sql)

    command.upgrade(config, "head")
    assert _current_revision(url) == HEAD
    assert _rows(
        url,
        "SELECT kind, budget_month, amount, currency, original_amount, exchange_rate, voided, "
        "voided_at, void_reason, allocation_status FROM incomes",
    ) == [("saldo_inicial", "2026-11", 684757, "CRC", 684757, None, False, None, None, "repartido")]
    assert _rows(
        url, "SELECT pocket_id, percentage, amount FROM income_allocations ORDER BY 1"
    ) == [
        (1, None, 104729),
        (2, None, 523717),
        (3, None, 56311),
    ]
    assert _scalar(url, "SELECT count(*) FROM budget_month_allocations") == 3


def test_0004_downgrade_con_gastos_se_niega_salvo_con_la_variable(empty_database, monkeypatch):
    url, _ = empty_database
    config = alembic_config(url)
    command.upgrade(config, "head")
    _execute(url, CRC_EXPENSE)
    monkeypatch.delenv("ALLOW_DESTRUCTIVE_DOWNGRADE", raising=False)
    with pytest.raises(RuntimeError, match="0004_movements cancelado"):
        command.downgrade(config, "0003_budget")
    assert _current_revision(url) == HEAD
    assert _scalar(url, "SELECT count(*) FROM expenses") == 1

    monkeypatch.setenv("ALLOW_DESTRUCTIVE_DOWNGRADE", "true")
    command.downgrade(config, "0003_budget")
    assert _current_revision(url) == "0003_budget"


def test_0004_downgrade_se_niega_con_un_ingreso_anulado(empty_database, monkeypatch):
    url, _ = empty_database
    config = alembic_config(url)
    command.upgrade(config, "head")
    _execute(
        url,
        "INSERT INTO incomes (income_date, kind, budget_month, amount, original_amount, "
        "allocation_status, voided, voided_at, void_reason) VALUES ('2026-11-10', 'base', "
        "'2026-12', 5000, 5000, 'repartido', TRUE, now(), 'prueba sintética')",
    )
    monkeypatch.delenv("ALLOW_DESTRUCTIVE_DOWNGRADE", raising=False)
    with pytest.raises(RuntimeError, match="ALLOW_DESTRUCTIVE_DOWNGRADE=true"):
        command.downgrade(config, "0003_budget")


def test_0004_restricciones_de_moneda_y_anulacion(empty_database):
    url, _ = empty_database
    command.upgrade(alembic_config(url), "head")
    expense = (
        "INSERT INTO expenses (expense_date, month, pocket_id, currency, original_amount, "
        "exchange_rate, amount{extra_cols}) VALUES ('2026-11-10', '2026-11', 1, {values}{extra})"
    )
    bad = [
        expense.format(extra_cols="", values="'CRC', 100, 51234, 100", extra=""),  # CRC con tasa
        expense.format(extra_cols="", values="'USD', 1000, NULL, 5123", extra=""),  # USD sin tasa
        expense.format(extra_cols="", values="'EUR', 1000, 51234, 5123", extra=""),  # moneda
        expense.format(extra_cols="", values="'CRC', 100, NULL, 99", extra=""),  # CRC distinto
        expense.format(extra_cols=", voided", values="'CRC', 100, NULL, 100", extra=", TRUE"),
        "INSERT INTO expenses (expense_date, month, pocket_id, original_amount, amount, "
        "description) VALUES ('2026-11-10', '2026-11', 1, 1, 1, repeat('x', 121))",
        "INSERT INTO expenses (expense_date, month, pocket_id, original_amount, amount) "
        "VALUES ('2026-11-10', '2026-13', 1, 1, 1)",
    ]
    for sql in bad:
        with pytest.raises(IntegrityError):
            _execute(url, sql)
    _execute(url, expense.format(extra_cols="", values="'USD', 1000, 51234, 5123", extra=""))


def test_0004_el_libro_mayor_no_se_borra_ni_se_edita(empty_database):
    url, _ = empty_database
    command.upgrade(alembic_config(url), "head")
    _execute(url, CRC_EXPENSE)
    _execute(
        url,
        "INSERT INTO incomes (income_date, kind, budget_month, amount, original_amount, "
        "allocation_status) VALUES ('2026-11-10', 'base', '2026-12', 9000, 9000, 'repartido')",
    )
    _execute(
        url,
        "INSERT INTO income_allocations (income_id, pocket_id, percentage, amount) "
        "VALUES (1, 1, 100, 9000)",
    )
    forbidden = [
        "DELETE FROM expenses",
        "DELETE FROM incomes",
        "DELETE FROM income_allocations",
        "UPDATE income_allocations SET amount = 1",
        "UPDATE expenses SET amount = 1, original_amount = 1",
        "UPDATE expenses SET pocket_id = 2",
        "UPDATE incomes SET budget_month = '2027-01'",
    ]
    for sql in forbidden:
        with pytest.raises(IntegrityError, match="RN-53|inmutable"):
            _execute(url, sql)

    void = "UPDATE expenses SET voided = TRUE, voided_at = now(), void_reason = 'motivo sintético'"
    _execute(url, void)
    with pytest.raises(IntegrityError, match="no se deshace"):
        _execute(url, "UPDATE expenses SET voided = FALSE, voided_at = NULL, void_reason = NULL")
    with pytest.raises(IntegrityError, match="no se deshace"):
        _execute(url, "UPDATE expenses SET void_reason = 'otro motivo'")
    assert _scalar(url, "SELECT count(*) FROM expenses") == 1


def test_0004_nuevo_saldo_inicial_tras_anular(empty_database):
    url, _ = empty_database
    command.upgrade(alembic_config(url), "head")
    initial = (
        "INSERT INTO incomes (income_date, kind, budget_month, amount, original_amount, "
        "allocation_status) VALUES ('2026-11-10', 'saldo_inicial', '2026-11', 777, 777, "
        "'repartido')"
    )
    _execute(url, initial)
    with pytest.raises(IntegrityError, match="ux_incomes_single_initial_balance"):
        _execute(url, initial)
    _execute(
        url,
        "UPDATE incomes SET voided = TRUE, voided_at = now(), void_reason = 'mal cargado' "
        "WHERE kind = 'saldo_inicial'",
    )
    _execute(url, initial)
    assert _scalar(url, "SELECT count(*) FROM incomes WHERE kind = 'saldo_inicial'") == 2
