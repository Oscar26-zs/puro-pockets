"""Dashboard contra Postgres real con un rol de solo lectura (Hito 10; datos sintéticos).

Base temporal propia y un rol único `pp_test_dash_<aleatorio>` creado con el mismo
`scripts/create_dashboard_role.sql` (solo cambia el nombre). El rol es del servidor (no de la base),
así que se borra al final, después de la base. Nunca toca la base de desarrollo ni la del homelab.
"""

import secrets
from functools import partial

import anyio
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError
from starlette.testclient import TestClient

from puro_pockets.api.__main__ import build_from_settings, read_only_engine
from puro_pockets.api.config import DashboardSettings
from puro_pockets.api.readonly import UnsafeDatabaseRole, ensure_read_only, role_problems
from puro_pockets.db.ledger_store import SqlLedgerStore
from puro_pockets.domain.money import RateRange
from puro_pockets.services.dashboard import DashboardService
from puro_pockets.services.ledger import LedgerService
from tests.dashboard_world import EXPECTED, TODAY, build_world
from tests.integration.conftest import REPO_ROOT, reset_budget, temporary_database

pytestmark = pytest.mark.integration

SCRIPT = (REPO_ROOT / "scripts" / "create_dashboard_role.sql").read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def world():
    """Base temporal con el mundo sintético y el rol de solo lectura creado por el script."""
    role = f"pp_test_dash_{secrets.token_hex(4)}"
    password = secrets.token_urlsafe(24)
    with temporary_database(migrate=True) as (url, name):
        owner = create_engine(url)
        reset_budget(owner, name)
        store = SqlLedgerStore(owner)
        ledger = LedgerService(store, today=lambda: TODAY, rate_range=RateRange(300, 1000))
        anyio.run(partial(build_world, store, ledger))
        raw = owner.raw_connection()
        try:
            with raw.cursor() as cur:
                cur.execute(SCRIPT.replace("puro_dashboard", role))
                cur.execute(f"ALTER ROLE \"{role}\" PASSWORD '{password}'")
            raw.commit()
        finally:
            raw.close()
        role_url = make_url(url).set(username=role, password=password)
        try:
            yield {
                "owner": owner,
                "ledger": ledger,
                "store": store,
                "role": role,
                "role_url": role_url.render_as_string(hide_password=False),
            }
        finally:
            owner.dispose()
    # La base ya no existe: el rol queda sin permisos y se puede borrar
    admin = create_engine(make_url(url).set(database="postgres"), isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as conn:
            conn.execute(text(f'DROP ROLE IF EXISTS "{role}"'))
    finally:
        admin.dispose()


def _settings(world, **overrides) -> DashboardSettings:
    values = {
        "database_url": world["role_url"],
        "session_secret": secrets.token_bytes(48),
        "owner_password_hash": "$argon2id$v=19$m=8,t=1,p=1$c2FsdHNhbHQ$aGFzaGhhc2hoYXNo",
        "static_dir": REPO_ROOT / "no-existe",
    }
    return DashboardSettings(**{**values, **overrides})


def _grant(world, sql: str) -> None:
    with world["owner"].begin() as conn:
        conn.execute(text(sql.format(role=f'"{world["role"]}"')))


def test_el_rol_del_script_es_de_solo_lectura(world):
    engine = read_only_engine(_settings(world))
    try:
        assert role_problems(engine) == []
        ensure_read_only(engine)
    finally:
        engine.dispose()


def test_el_rol_no_puede_escribir_ni_leer_oauth(world):
    engine = create_engine(world["role_url"])
    try:
        with engine.connect() as conn:
            with pytest.raises(DBAPIError):
                conn.execute(text("INSERT INTO categories (name, pocket_id) VALUES ('x', 1)"))
            conn.rollback()
            with pytest.raises(DBAPIError):
                conn.execute(text("SELECT count(*) FROM oauth_clients"))
            conn.rollback()
            with pytest.raises(DBAPIError):
                conn.execute(text("SELECT count(*) FROM idempotency_keys"))
            conn.rollback()
            assert conn.execute(text("SELECT count(*) FROM pockets")).scalar() == 3
    finally:
        engine.dispose()


def test_se_niega_con_el_rol_propietario(world):
    with pytest.raises(UnsafeDatabaseRole) as error:
        ensure_read_only(world["owner"])
    message = str(error.value)
    assert "INSERT en la tabla expenses" in message
    assert "SELECT en la tabla oauth_clients" in message


@pytest.mark.parametrize(
    ("grant", "revoke", "expected"),
    [
        (
            "GRANT SELECT ON oauth_clients TO {role}",
            "REVOKE SELECT ON oauth_clients FROM {role}",
            "SELECT en la tabla oauth_clients",
        ),
        (
            "GRANT SELECT ON oauth_access_tokens TO {role}",
            "REVOKE SELECT ON oauth_access_tokens FROM {role}",
            "SELECT en la tabla oauth_access_tokens",
        ),
        (
            "GRANT INSERT ON expenses TO {role}",
            "REVOKE INSERT ON expenses FROM {role}",
            "INSERT en la tabla expenses",
        ),
        (
            "GRANT UPDATE ON pockets TO {role}",
            "REVOKE UPDATE ON pockets FROM {role}",
            "UPDATE en la tabla pockets",
        ),
        (
            "GRANT USAGE ON SEQUENCE expenses_id_seq TO {role}",
            "REVOKE USAGE ON SEQUENCE expenses_id_seq FROM {role}",
            "secuencia expenses_id_seq",
        ),
        (
            "GRANT CREATE ON SCHEMA public TO {role}",
            "REVOKE CREATE ON SCHEMA public FROM {role}",
            "crear objetos en el esquema public",
        ),
    ],
)
def test_se_niega_si_el_rol_tiene_un_permiso_de_mas(world, grant, revoke, expected):
    engine = create_engine(world["role_url"])
    _grant(world, grant)
    try:
        with pytest.raises(UnsafeDatabaseRole) as error:
            ensure_read_only(engine)
        assert expected in str(error.value)
    finally:
        _grant(world, revoke)
        engine.dispose()
    engine = create_engine(world["role_url"])
    try:
        ensure_read_only(engine)  # vuelve a estar bien
    finally:
        engine.dispose()


async def _owner_tools(world):
    ledger = world["ledger"]
    return (
        await ledger.get_summary("2026-11"),
        await ledger.list_transactions("2026-11", None, None, False, 10),
    )


def test_la_api_con_el_rol_devuelve_lo_mismo_que_las_tools(world):
    summary, movements = anyio.run(partial(_owner_tools, world))
    engine = read_only_engine(_settings(world))
    try:
        app = build_from_settings(_settings(world), engine)
        # El reloj real no es el de la prueba: se fija el mes en la consulta
        with TestClient(app, base_url="https://127.0.0.1:8080") as client:
            assert client.get("/api/summary").status_code == 401
            assert client.get("/healthz").json() == {"status": "ok"}
        store = SqlLedgerStore(engine)
        ledger = LedgerService(store, today=lambda: TODAY, rate_range=RateRange(300, 1000))
        service = DashboardService(ledger, store, lambda: TODAY)
        data = anyio.run(service.summary, "2026-11")
        assert data.income == summary.income_total == EXPECTED["nov"]["income"]
        assert data.spent == summary.expense_total == EXPECTED["nov"]["spent"]
        assert data.saved == EXPECTED["nov"]["saved"]
        assert data.available == EXPECTED["nov"]["available"]
        listed = anyio.run(service.movements, "2026-11", None, None, False, 1)
        assert [m.ref for m in listed.items] == [m.reference for m in movements.items]
        history = anyio.run(service.history, "2026-11")
        assert history.months[-2].saved == EXPECTED["oct"]["saved"]
        pockets = anyio.run(service.pockets, "2026-11")
        assert {p.name for p in pockets.items} == {"Necesidades", "Ahorro", "Gustos"}
        fixed = anyio.run(service.fixed, "2026-11")
        assert {f.status for f in fixed.items} == {"paid", "pending", "overdue"}
        assert anyio.run(service.categories, "2026-11").total == 310_000
    finally:
        engine.dispose()


def test_las_lecturas_corren_en_transacciones_de_solo_lectura(world):
    engine = read_only_engine(_settings(world))
    try:
        with engine.connect() as conn:
            assert conn.execute(text("SHOW transaction_read_only")).scalar() == "on"
    finally:
        engine.dispose()
