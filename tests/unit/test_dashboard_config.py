"""Configuración, sesión y arranque del dashboard (Hito 10). Sin base de datos."""

import secrets

import pytest

from puro_pockets.api import __main__ as entry
from puro_pockets.api.config import load_dashboard_settings
from puro_pockets.api.readonly import UnsafeDatabaseRole
from puro_pockets.api.session import SessionManager
from puro_pockets.config import ConfigError

HASH = "$argon2id$v=19$m=8,t=1,p=1$c2FsdHNhbHQ$aGFzaGhhc2hoYXNo"
SECRET = "s" * 32
BASE_ENV = {
    "DASHBOARD_DATABASE_URL": "postgresql+psycopg://puro_dashboard:x@db:5432/puro_pockets",
    "DASHBOARD_SESSION_SECRET": SECRET,
    "OWNER_PASSWORD_HASH": HASH,
}


def test_valores_por_defecto_seguros():
    settings = load_dashboard_settings(BASE_ENV)
    assert settings.cookie_secure is True
    assert settings.host == "127.0.0.1" and settings.port == 8080
    assert settings.session_ttl == 12 * 3600
    assert settings.session_secret == SECRET.encode()


def test_sin_url_propia_no_cae_al_rol_propietario():
    env = {k: v for k, v in BASE_ENV.items() if k != "DASHBOARD_DATABASE_URL"}
    env["DATABASE_URL"] = "postgresql+psycopg://propietario:x@db:5432/puro_pockets"
    with pytest.raises(ConfigError, match="DASHBOARD_DATABASE_URL"):
        load_dashboard_settings(env)


@pytest.mark.parametrize("secret", ["", "corto", "x" * 31])
def test_secreto_de_al_menos_32_bytes(secret):
    with pytest.raises(ConfigError, match="DASHBOARD_SESSION_SECRET"):
        load_dashboard_settings({**BASE_ENV, "DASHBOARD_SESSION_SECRET": secret})


def test_el_secreto_no_aparece_en_el_error():
    with pytest.raises(ConfigError) as error:
        load_dashboard_settings({**BASE_ENV, "DASHBOARD_SESSION_SECRET": "valor-secreto"})
    assert "valor-secreto" not in str(error.value)


@pytest.mark.parametrize("value", ["", "texto-plano", "$2b$12$bcrypt"])
def test_exige_el_hash_argon2_del_hito_3(value):
    with pytest.raises(ConfigError, match="OWNER_PASSWORD_HASH"):
        load_dashboard_settings({**BASE_ENV, "OWNER_PASSWORD_HASH": value})


def test_hash_entre_comillas_simples_como_en_env():
    settings = load_dashboard_settings({**BASE_ENV, "OWNER_PASSWORD_HASH": f"'{HASH}'"})
    assert settings.owner_password_hash == HASH


def test_secure_y_ip_configurables():
    settings = load_dashboard_settings(
        {**BASE_ENV, "DASHBOARD_COOKIE_SECURE": "false", "DASHBOARD_HOST": "0.0.0.0"}
    )
    assert settings.cookie_secure is False and settings.host == "0.0.0.0"


def test_sesion_firmada_vence_y_se_revoca():
    now = [1000.0]
    manager = SessionManager(secrets.token_bytes(32), 60, clock=lambda: now[0])
    token = manager.issue()
    assert manager.valid(token)
    payload, signature = token.split(".")
    assert not manager.valid(f"{payload}x.{signature}")  # alterada
    manager.revoke(token)
    assert not manager.valid(token)
    other = manager.issue()
    now[0] += 61
    assert not manager.valid(other)  # vencida


def test_arranque_sale_si_falta_configuracion(monkeypatch, capsys):
    for name in BASE_ENV:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://propietario:x@db:5432/x")
    with pytest.raises(SystemExit) as stop:
        entry.main()
    assert stop.value.code == 1
    assert "DASHBOARD_DATABASE_URL" in capsys.readouterr().err


def test_arranque_se_niega_con_un_rol_que_puede_escribir(monkeypatch, capsys):
    for name, value in BASE_ENV.items():
        monkeypatch.setenv(name, value)

    def unsafe(_engine):
        raise UnsafeDatabaseRole("INSERT en la tabla expenses")

    served = []
    monkeypatch.setattr(entry, "ensure_read_only", unsafe)
    monkeypatch.setattr(entry.uvicorn, "run", lambda *a, **k: served.append(1))
    with pytest.raises(SystemExit) as stop:
        entry.main()
    assert stop.value.code == 2 and served == []
    assert "INSERT en la tabla expenses" in capsys.readouterr().err


def test_arranque_sin_base_no_muestra_la_url(monkeypatch, capsys):
    for name, value in BASE_ENV.items():
        monkeypatch.setenv(name, value)

    def unreachable(_engine):
        raise OSError("postgresql+psycopg://puro_dashboard:x@db:5432 no responde")

    monkeypatch.setattr(entry, "ensure_read_only", unreachable)
    with pytest.raises(SystemExit) as stop:
        entry.main()
    err = capsys.readouterr().err
    assert stop.value.code == 3 and "puro_dashboard:x" not in err
