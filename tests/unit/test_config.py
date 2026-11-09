"""Configuración desde variables de entorno (caso borde: variable obligatoria faltante)."""

import pytest

from puro_pockets.config import ConfigError, load_settings

DB_URL = "postgresql+psycopg://usuario:secreto@localhost:5432/puro_pockets"


def test_falta_database_url_da_error_que_nombra_la_variable():
    with pytest.raises(ConfigError) as exc:
        load_settings({})
    assert "DATABASE_URL" in str(exc.value)


def test_valores_por_defecto():
    settings = load_settings({"DATABASE_URL": DB_URL})
    assert settings.database_url == DB_URL
    assert settings.mcp_host == "127.0.0.1"
    assert settings.mcp_port == 8000
    assert settings.db_connect_timeout == 2


def test_valores_explicitos():
    settings = load_settings(
        {
            "DATABASE_URL": DB_URL,
            "MCP_HOST": "0.0.0.0",
            "MCP_PORT": "9000",
            "DB_CONNECT_TIMEOUT": "3",
        }
    )
    assert settings.mcp_host == "0.0.0.0"
    assert settings.mcp_port == 9000
    assert settings.db_connect_timeout == 3


def test_numero_invalido_no_muestra_el_valor():
    with pytest.raises(ConfigError) as exc:
        load_settings({"DATABASE_URL": DB_URL, "MCP_PORT": "no-es-numero"})
    assert "MCP_PORT" in str(exc.value)
    assert "no-es-numero" not in str(exc.value)


def test_acceso_publico_por_defecto_desactivado():
    settings = load_settings({"DATABASE_URL": DB_URL})
    assert settings.public_hostname is None
    assert settings.allowed_origins == ()


def test_nombre_publico_y_origenes():
    settings = load_settings(
        {
            "DATABASE_URL": DB_URL,
            "MCP_PUBLIC_HOSTNAME": " mcp.puropockets.space ",
            "MCP_ALLOWED_ORIGINS": "https://claude.ai, https://claude.com,,",
        }
    )
    assert settings.public_hostname == "mcp.puropockets.space"
    assert settings.allowed_origins == ("https://claude.ai", "https://claude.com")


def test_el_error_nunca_muestra_la_url():
    with pytest.raises(ConfigError) as exc:
        load_settings({"DATABASE_URL": DB_URL, "DB_CONNECT_TIMEOUT": "x"})
    assert "secreto" not in str(exc.value)
