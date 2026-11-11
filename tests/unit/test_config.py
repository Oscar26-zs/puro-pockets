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


# --- OAuth (Hito 3) ---

CLAUDE_CALLBACKS = (
    "https://claude.ai/api/mcp/auth_callback",
    "https://claude.com/api/mcp/auth_callback",
)


def test_oauth_valores_por_defecto():
    settings = load_settings(
        {"DATABASE_URL": DB_URL, "MCP_PUBLIC_HOSTNAME": "mcp.puropockets.space"}
    )
    assert settings.owner_password_hash is None
    assert settings.oauth_issuer_url == "https://mcp.puropockets.space"
    assert settings.oauth_resource_url == "https://mcp.puropockets.space/mcp"
    assert settings.oauth_allowed_redirect_uris == CLAUDE_CALLBACKS
    assert settings.oauth_registration_enabled is False
    assert settings.oauth_max_clients == 10
    assert settings.oauth_access_token_ttl == 3600
    assert settings.oauth_refresh_token_ttl == 30 * 24 * 3600
    assert settings.oauth_auth_code_ttl == 300


def test_oauth_sin_nombre_publico_usa_loopback():
    settings = load_settings({"DATABASE_URL": DB_URL})
    assert settings.oauth_issuer_url == "http://127.0.0.1:8000"
    assert settings.oauth_resource_url == "http://127.0.0.1:8000/mcp"


def test_oauth_registro_y_lista_blanca_configurables():
    settings = load_settings(
        {
            "DATABASE_URL": DB_URL,
            "OAUTH_REGISTRATION_ENABLED": "true",
            "OAUTH_ALLOWED_REDIRECT_URIS": "https://claude.ai/api/mcp/auth_callback",
            "OAUTH_MAX_CLIENTS": "3",
            "OWNER_PASSWORD_HASH": "$argon2id$v=19$m=65536,t=3,p=4$abc$def",
        }
    )
    assert settings.oauth_registration_enabled is True
    assert settings.oauth_allowed_redirect_uris == ("https://claude.ai/api/mcp/auth_callback",)
    assert settings.oauth_max_clients == 3
    assert settings.owner_password_hash.startswith("$argon2id$")


def test_oauth_duraciones_cortas_para_pruebas():
    settings = load_settings({"DATABASE_URL": DB_URL, "OAUTH_SHORT_LIFETIMES": "true"})
    assert settings.oauth_access_token_ttl == 120
    assert settings.oauth_refresh_token_ttl == 900
    assert settings.oauth_auth_code_ttl == 300


def test_oauth_duracion_explicita_gana():
    settings = load_settings(
        {
            "DATABASE_URL": DB_URL,
            "OAUTH_SHORT_LIFETIMES": "true",
            "OAUTH_ACCESS_TOKEN_TTL_SECONDS": "60",
        }
    )
    assert settings.oauth_access_token_ttl == 60
    assert settings.oauth_refresh_token_ttl == 900


def test_oauth_booleano_invalido_no_muestra_el_valor():
    with pytest.raises(ConfigError) as exc:
        load_settings({"DATABASE_URL": DB_URL, "OAUTH_REGISTRATION_ENABLED": "quizas"})
    assert "OAUTH_REGISTRATION_ENABLED" in str(exc.value)
    assert "quizas" not in str(exc.value)


def test_zona_horaria_por_defecto_y_configurable():
    assert load_settings({"DATABASE_URL": "x"}).app_timezone == "America/Costa_Rica"
    settings = load_settings({"DATABASE_URL": "x", "APP_TIMEZONE": "America/Mexico_City"})
    assert settings.app_timezone == "America/Mexico_City"


def test_zona_horaria_invalida_da_error_claro():
    with pytest.raises(ConfigError, match="APP_TIMEZONE"):
        load_settings({"DATABASE_URL": "x", "APP_TIMEZONE": "Marte/Olympus"})
