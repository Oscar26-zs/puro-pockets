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

HEAD = "0007_transfers"


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


# --- Hito 6: 0005_extras_recurring ---

HITO5_DATA = (
    HITO4_DATA[0],
    "INSERT INTO incomes (income_date, kind, budget_month, amount, original_amount, "
    "allocation_status) VALUES ('2026-11-10', 'saldo_inicial', '2026-11', 684757, 684757, "
    "'repartido')",
    HITO4_DATA[2],
    "INSERT INTO incomes (income_date, kind, budget_month, amount, currency, original_amount, "
    "exchange_rate, allocation_status) VALUES ('2026-11-01', 'base', '2026-12', 512340, 'USD', "
    "100000, 51234, 'repartido')",
    "INSERT INTO income_allocations (income_id, pocket_id, percentage, amount) "
    "VALUES (2, 1, 100, 512340)",
    "INSERT INTO incomes (income_date, kind, budget_month, amount, original_amount, "
    "allocation_status, voided, voided_at, void_reason) VALUES ('2026-11-02', 'base', '2026-12', "
    "7000, 7000, 'repartido', TRUE, '2026-11-03T10:00:00Z', 'prueba sintética')",
    "INSERT INTO expenses (expense_date, month, pocket_id, description, currency, "
    "original_amount, exchange_rate, amount) VALUES ('2026-11-05', '2026-11', 3, 'cena sintética', "
    "'USD', 1000, 51234, 5123)",
    "INSERT INTO idempotency_keys (operation_id, tool, fingerprint, response) "
    "VALUES ('op-sintetica-1', 'add_expense', repeat('a', 64), '{}')",
)
TEMPLATE = (
    "INSERT INTO recurring_expenses (name, currency, day_of_month, pocket_id, start_month) "
    "VALUES ('Internet sintético', 'CRC', 31, 1, '2026-11')"
)
PENDING_EXTRA = (
    "INSERT INTO incomes (income_date, kind, budget_month, amount, original_amount, "
    "allocation_status) VALUES ('2026-11-10', 'extra', '2026-11', 4000, 4000, 'pendiente')"
)


def test_0005_conserva_los_datos_del_hito_5(empty_database):
    url, name = empty_database
    assert_temp_database(url, name)
    config = alembic_config(url)
    command.upgrade(config, "0004_movements")
    for sql in HITO5_DATA:
        _execute(url, sql)
    tables = ("incomes", "income_allocations", "expenses", "idempotency_keys")
    before = {table: _rows(url, f"SELECT * FROM {table} ORDER BY 1") for table in tables}

    command.upgrade(config, "head")
    assert _current_revision(url) == HEAD
    for table in ("incomes", "income_allocations", "idempotency_keys"):
        assert _rows(url, f"SELECT * FROM {table} ORDER BY 1") == before[table], table
    # expenses gana la columna recurring_id (NULL) y conserva todo lo demás
    after = _rows(url, "SELECT * FROM expenses ORDER BY 1")
    assert [row[:-1] for row in after] == before["expenses"]
    assert [row[-1] for row in after] == [None]


def test_0005_se_niega_si_hay_un_ingreso_no_extra_pendiente(empty_database):
    url, _ = empty_database
    config = alembic_config(url)
    command.upgrade(config, "0004_movements")
    _execute(
        url,
        "INSERT INTO incomes (income_date, kind, budget_month, amount, original_amount, "
        "allocation_status) VALUES ('2026-11-10', 'base', '2026-12', 9000, 9000, 'pendiente')",
    )
    with pytest.raises(RuntimeError, match="0005 cancelada"):
        command.upgrade(config, "head")
    assert _current_revision(url) == "0004_movements"


def test_0005_downgrade_protegido(empty_database, monkeypatch):
    url, _ = empty_database
    config = alembic_config(url)
    command.upgrade(config, "head")
    _execute(url, TEMPLATE)
    monkeypatch.delenv("ALLOW_DESTRUCTIVE_DOWNGRADE", raising=False)
    with pytest.raises(RuntimeError, match="0005_extras_recurring cancelado"):
        command.downgrade(config, "0004_movements")
    assert _current_revision(url) == HEAD
    assert _scalar(url, "SELECT count(*) FROM recurring_expenses") == 1

    monkeypatch.setenv("ALLOW_DESTRUCTIVE_DOWNGRADE", "true")
    command.downgrade(config, "0004_movements")
    assert _current_revision(url) == "0004_movements"
    assert _scalar(url, "SELECT to_regclass('public.recurring_expenses')") is None
    command.upgrade(config, "head")  # y vuelve a subir
    assert _current_revision(url) == HEAD


def test_0005_downgrade_se_niega_con_un_extra(empty_database, monkeypatch):
    url, _ = empty_database
    config = alembic_config(url)
    command.upgrade(config, "head")
    _execute(url, PENDING_EXTRA)
    monkeypatch.delenv("ALLOW_DESTRUCTIVE_DOWNGRADE", raising=False)
    with pytest.raises(RuntimeError, match="ALLOW_DESTRUCTIVE_DOWNGRADE=true"):
        command.downgrade(config, "0004_movements")


def test_0005_restricciones_y_disparadores(empty_database):
    url, _ = empty_database
    command.upgrade(alembic_config(url), "head")
    _execute(url, TEMPLATE)
    _execute(
        url,
        "INSERT INTO recurring_expense_amounts (recurring_id, from_month, original_amount) "
        "VALUES (1, '2026-11', 25000)",
    )
    payment = (
        "INSERT INTO expenses (expense_date, month, pocket_id, original_amount, amount, "
        "recurring_id) VALUES ('2026-11-10', '2026-11', 1, 25000, 25000, 1)"
    )
    _execute(url, payment)
    bad = [
        payment,  # segundo pago vigente del mismo fijo en el mes
        TEMPLATE,  # nombre repetido entre los activos
        "INSERT INTO recurring_expenses (name, currency, day_of_month, pocket_id, start_month) "
        "VALUES ('Otro', 'CRC', 32, 1, '2026-11')",  # día 32
        "INSERT INTO recurring_expenses (name, currency, day_of_month, pocket_id, start_month) "
        "VALUES ('Otro', 'EUR', 1, 1, '2026-11')",  # moneda
        "INSERT INTO recurring_expense_amounts VALUES (1, '2026-12', 0)",  # monto 0
        "INSERT INTO incomes (income_date, kind, budget_month, amount, original_amount, "
        "allocation_status) VALUES ('2026-11-10', 'base', '2026-12', 1, 1, 'pendiente')",
        "INSERT INTO incomes (income_date, kind, budget_month, amount, original_amount, "
        "allocation_status, source) VALUES ('2026-11-10', 'extra', '2026-11', 1, 1, "
        "'pendiente', repeat('x', 121))",
    ]
    for sql in bad:
        with pytest.raises(IntegrityError):
            _execute(url, sql)
    forbidden = [
        "DELETE FROM recurring_expenses",
        "DELETE FROM recurring_expense_amounts",
        "UPDATE recurring_expenses SET currency = 'USD'",
        "UPDATE recurring_expenses SET start_month = '2027-01'",
        "UPDATE expenses SET recurring_id = NULL",
    ]
    for sql in forbidden:
        with pytest.raises(IntegrityError, match="no se borran|no se cambian|RN-53"):
            _execute(url, sql)
    # Anulado el pago, el fijo admite otro en el mes
    _execute(url, "UPDATE expenses SET voided = TRUE, voided_at = now(), void_reason = 'duplicado'")
    _execute(url, payment)
    # Desactivado, no se reactiva
    _execute(url, "UPDATE recurring_expenses SET active = FALSE, deactivated_at = now()")
    with pytest.raises(IntegrityError, match="no se reactiva"):
        _execute(url, "UPDATE recurring_expenses SET active = TRUE, deactivated_at = NULL")
    # Un reparto no vuelve a pendiente ni se hace sobre un ingreso anulado
    # (los INSERT rechazados arriba consumieron valores de la secuencia: se usa el último id)
    last = "WHERE id = (SELECT max(id) FROM incomes)"
    _execute(url, PENDING_EXTRA)
    _execute(url, f"UPDATE incomes SET allocation_status = 'repartido' {last}")
    with pytest.raises(IntegrityError, match="reparto no se deshace"):
        _execute(url, f"UPDATE incomes SET allocation_status = 'pendiente' {last}")
    _execute(url, PENDING_EXTRA)
    _execute(
        url,
        f"UPDATE incomes SET voided = TRUE, voided_at = now(), void_reason = 'duplicado' {last}",
    )
    with pytest.raises(IntegrityError, match="reparto no se deshace"):
        _execute(url, f"UPDATE incomes SET allocation_status = 'repartido' {last}")


# --- Hito 7: 0006_pockets_goals ---

HITO6_DATA = (
    *HITO5_DATA,
    TEMPLATE,
    "INSERT INTO recurring_expense_amounts (recurring_id, from_month, original_amount) "
    "VALUES (1, '2026-11', 25000)",
    "INSERT INTO expenses (expense_date, month, pocket_id, original_amount, amount, recurring_id) "
    "VALUES ('2026-11-10', '2026-11', 1, 25000, 25000, 1)",
    PENDING_EXTRA,
)
GOAL = (
    "INSERT INTO savings_goals (pocket_id, name, target_amount, created_on) "
    "VALUES (2, 'Viaje sintético', 500000, '2026-11-11')"
)


def test_0006_conserva_los_datos_del_hito_6(empty_database):
    url, name = empty_database
    assert_temp_database(url, name)
    config = alembic_config(url)
    command.upgrade(config, "0005_extras_recurring")
    for sql in HITO6_DATA:
        _execute(url, sql)
    tables = (
        "incomes",
        "income_allocations",
        "expenses",
        "idempotency_keys",
        "recurring_expenses",
        "recurring_expense_amounts",
        "budget_month_allocations",
    )
    before = {table: _rows(url, f"SELECT * FROM {table} ORDER BY 1, 2") for table in tables}
    pockets_before = _rows(url, "SELECT * FROM pockets ORDER BY 1")

    command.upgrade(config, "head")
    assert _current_revision(url) == HEAD
    for table in tables:
        assert _rows(url, f"SELECT * FROM {table} ORDER BY 1, 2") == before[table], table
    # pockets gana archived_at (NULL en las activas) y conserva todo lo demás
    after = _rows(url, "SELECT * FROM pockets ORDER BY 1")
    assert [row[:-1] for row in after] == pockets_before
    assert {row[-1] for row in after} == {None}


def test_0006_downgrade_protegido(empty_database, monkeypatch):
    url, _ = empty_database
    config = alembic_config(url)
    command.upgrade(config, "head")
    _execute(url, GOAL)
    monkeypatch.delenv("ALLOW_DESTRUCTIVE_DOWNGRADE", raising=False)
    with pytest.raises(RuntimeError, match="0006_pockets_goals cancelado"):
        command.downgrade(config, "0005_extras_recurring")
    assert _current_revision(url) == HEAD
    assert _scalar(url, "SELECT count(*) FROM savings_goals") == 1

    monkeypatch.setenv("ALLOW_DESTRUCTIVE_DOWNGRADE", "true")
    command.downgrade(config, "0005_extras_recurring")
    assert _scalar(url, "SELECT to_regclass('public.savings_goals')") is None
    command.upgrade(config, "head")
    assert _current_revision(url) == HEAD


def test_0006_downgrade_se_niega_con_una_bolsa_archivada(empty_database, monkeypatch):
    url, _ = empty_database
    config = alembic_config(url)
    command.upgrade(config, "head")
    _execute(url, "UPDATE pockets SET active = FALSE, archived_at = now() WHERE name = 'Gustos'")
    monkeypatch.delenv("ALLOW_DESTRUCTIVE_DOWNGRADE", raising=False)
    with pytest.raises(RuntimeError, match="ALLOW_DESTRUCTIVE_DOWNGRADE=true"):
        command.downgrade(config, "0005_extras_recurring")


def test_0006_restricciones_y_disparadores(empty_database):
    url, _ = empty_database
    command.upgrade(alembic_config(url), "head")
    _execute(url, GOAL)
    bad = [
        GOAL,  # segunda meta activa en la misma bolsa (RN-22)
        "INSERT INTO savings_goals (pocket_id, name, target_amount, created_on) "
        "VALUES (2, 'Cero', 0, '2026-11-11')",  # objetivo 0
        "INSERT INTO savings_goals (pocket_id, name, target_amount, status, created_on) "
        "VALUES (2, 'X', 1, 'lograda', '2026-11-11')",  # lograda sin fecha de logro
        "INSERT INTO savings_goals (pocket_id, name, target_amount, status, created_on) "
        "VALUES (2, 'X', 1, 'cancelada', '2026-11-11')",  # estado inválido
        "UPDATE pockets SET active = FALSE WHERE name = 'Gustos'",  # archivada sin archived_at
    ]
    for sql in bad:
        with pytest.raises(IntegrityError):
            _execute(url, sql)
    # una pausada libera el cupo: otra activa en la misma bolsa
    _execute(url, "UPDATE savings_goals SET status = 'pausada' WHERE id = 1")
    _execute(url, GOAL)
    forbidden = [
        ("DELETE FROM pockets WHERE name = 'Gustos'", "no se borra"),
        ("DELETE FROM savings_goals", "no se borra"),
        ("UPDATE pockets SET behavior = 'acumulable' WHERE name = 'Gustos'", "comportamiento"),
        ("UPDATE savings_goals SET pocket_id = 1", "no cambian"),
    ]
    for sql, message in forbidden:
        with pytest.raises(IntegrityError, match=message):
            _execute(url, sql)
    last = "WHERE id = (SELECT max(id) FROM savings_goals)"
    _execute(url, f"UPDATE savings_goals SET status = 'lograda', achieved_on = '2026-11-12' {last}")
    with pytest.raises(IntegrityError, match="se queda lograda"):
        _execute(url, f"UPDATE savings_goals SET status = 'activa', achieved_on = NULL {last}")
    _execute(url, "UPDATE pockets SET active = FALSE, archived_at = now() WHERE name = 'Gustos'")
    with pytest.raises(IntegrityError, match="no se reactiva"):
        _execute(url, "UPDATE pockets SET active = TRUE, archived_at = NULL WHERE name = 'Gustos'")


# --- Hito 8: 0007_transfers ---

HITO7_DATA = (
    *HITO6_DATA,
    GOAL,
    "INSERT INTO pockets (name, behavior) VALUES ('Viaje sintético', 'consumo')",
    "UPDATE pockets SET active = FALSE, archived_at = '2026-11-11T12:00:00Z' "
    "WHERE name = 'Viaje sintético'",
)
TRANSFER = (
    "INSERT INTO transfers (transfer_date, month, from_pocket_id, to_pocket_id, amount, reason) "
    "VALUES ('2026-11-11', '2026-11', 1, 3, 5000, 'cubrir_sobregasto')"
)


def test_0007_conserva_los_datos_del_hito_7(empty_database):
    url, name = empty_database
    assert_temp_database(url, name)
    config = alembic_config(url)
    command.upgrade(config, "0006_pockets_goals")
    for sql in HITO7_DATA:
        _execute(url, sql)
    tables = (
        "pockets",
        "savings_goals",
        "incomes",
        "income_allocations",
        "expenses",
        "idempotency_keys",
        "recurring_expenses",
        "recurring_expense_amounts",
        "budget_month_allocations",
        "categories",
    )
    before = {table: _rows(url, f"SELECT * FROM {table} ORDER BY 1, 2") for table in tables}
    assert before["savings_goals"] and before["expenses"]  # hay datos que conservar

    command.upgrade(config, "head")
    assert _current_revision(url) == HEAD
    for table in tables:
        assert _rows(url, f"SELECT * FROM {table} ORDER BY 1, 2") == before[table], table
    assert _scalar(url, "SELECT count(*) FROM transfers") == 0


def test_0007_downgrade_protegido(empty_database, monkeypatch):
    url, _ = empty_database
    config = alembic_config(url)
    command.upgrade(config, "head")
    _execute(url, TRANSFER)
    monkeypatch.delenv("ALLOW_DESTRUCTIVE_DOWNGRADE", raising=False)
    with pytest.raises(RuntimeError, match="0007_transfers cancelado"):
        command.downgrade(config, "0006_pockets_goals")
    assert _current_revision(url) == HEAD
    assert _scalar(url, "SELECT count(*) FROM transfers") == 1

    monkeypatch.setenv("ALLOW_DESTRUCTIVE_DOWNGRADE", "true")
    command.downgrade(config, "0006_pockets_goals")
    assert _scalar(url, "SELECT to_regclass('public.transfers')") is None
    command.upgrade(config, "head")
    assert _current_revision(url) == HEAD


def test_0007_downgrade_sin_transferencias_no_pide_la_variable(empty_database, monkeypatch):
    url, _ = empty_database
    config = alembic_config(url)
    command.upgrade(config, "head")
    monkeypatch.delenv("ALLOW_DESTRUCTIVE_DOWNGRADE", raising=False)
    command.downgrade(config, "0006_pockets_goals")
    assert _current_revision(url) == "0006_pockets_goals"


def test_0007_restricciones_y_disparador(empty_database):
    url, _ = empty_database
    command.upgrade(alembic_config(url), "head")
    columns = "transfer_date, month, from_pocket_id, to_pocket_id, amount, reason, note"

    def row(values: str) -> str:
        return f"INSERT INTO transfers ({columns}) VALUES ({values})"

    _execute(url, TRANSFER)
    _execute(url, row("'2026-11-11', '2026-11', 2, 1, 1, 'cierre_de_mes', NULL"))  # reservado: sí
    _execute(url, row(f"'2026-11-11', '2026-11', 1, 2, 1, 'ajuste', '{'n' * 140}'"))
    bad = [
        row("'2026-11-11', '2026-11', 1, 3, 0, 'ajuste', NULL"),  # monto 0
        row("'2026-11-11', '2026-11', 1, 3, -5, 'ajuste', NULL"),  # negativo
        row("'2026-11-11', '2026-11', 2, 2, 5, 'ajuste', NULL"),  # mismo origen y destino
        row("'2026-11-11', '2026-11', 1, 3, 5, 'regalo', NULL"),  # motivo inválido
        row("'2026-11-11', '2026-13', 1, 3, 5, 'ajuste', NULL"),  # mes inválido
        row("'2026-11-11', '26-11', 1, 3, 5, 'ajuste', NULL"),  # formato de mes
        row(f"'2026-11-11', '2026-11', 1, 3, 5, 'ajuste', '{'n' * 141}'"),  # nota de 141
        row("'2026-11-11', '2026-11', 1, 999, 5, 'ajuste', NULL"),  # bolsa inexistente (FK)
    ]
    for sql in bad:
        with pytest.raises(IntegrityError):
            _execute(url, sql)
    for sql in ("UPDATE transfers SET amount = 1", "DELETE FROM transfers WHERE id = 1"):
        with pytest.raises(IntegrityError, match="no se edita ni se borra"):
            _execute(url, sql)
    assert _scalar(url, "SELECT count(*) FROM transfers") == 3
    rules = _rows(
        url,
        "SELECT confdeltype FROM pg_constraint WHERE conrelid = 'transfers'::regclass "
        "AND contype = 'f'",
    )
    assert rules == [("r",), ("r",)]  # ON DELETE RESTRICT en las dos claves foráneas
