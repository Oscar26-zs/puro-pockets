"""Configuración de la aplicación a partir de variables de entorno."""

from __future__ import annotations

import os
import zoneinfo
from collections.abc import Mapping
from dataclasses import dataclass

DEFAULT_REDIRECT_URIS = (
    "https://claude.ai/api/mcp/auth_callback",
    "https://claude.com/api/mcp/auth_callback",
)

# Duraciones (segundos): normales y modo corto para probar el refresco (OAUTH_SHORT_LIFETIMES=true)
NORMAL_LIFETIMES = {"access": 3600, "refresh": 30 * 24 * 3600, "code": 300}
SHORT_LIFETIMES = {"access": 120, "refresh": 900, "code": 300}

# Zona del propietario: define el "mes actual" (Hito 4)
DEFAULT_TIMEZONE = "America/Costa_Rica"

# Rango razonable del tipo de cambio, en colones por dólar (Hito 5, decisión #12)
DEFAULT_USD_RATE_MIN = 300
DEFAULT_USD_RATE_MAX = 1000


class ConfigError(RuntimeError):
    """Configuración faltante o inválida. El mensaje nunca incluye valores."""


@dataclass(frozen=True)
class Settings:
    database_url: str
    mcp_host: str = "127.0.0.1"
    mcp_port: int = 8000
    db_connect_timeout: int = 2
    # Acceso público por el túnel (Hito 2): nombre público aceptado y orígenes extra permitidos
    public_hostname: str | None = None
    allowed_origins: tuple[str, ...] = ()
    # OAuth (Hito 3)
    owner_password_hash: str | None = None
    oauth_issuer_url: str = "http://127.0.0.1:8000"
    oauth_resource_url: str = "http://127.0.0.1:8000/mcp"
    oauth_allowed_redirect_uris: tuple[str, ...] = DEFAULT_REDIRECT_URIS
    oauth_registration_enabled: bool = False
    oauth_max_clients: int = 10
    oauth_access_token_ttl: int = NORMAL_LIFETIMES["access"]
    oauth_refresh_token_ttl: int = NORMAL_LIFETIMES["refresh"]
    oauth_auth_code_ttl: int = NORMAL_LIFETIMES["code"]
    # Presupuesto (Hito 4)
    app_timezone: str = DEFAULT_TIMEZONE
    # Movimientos (Hito 5): rango aceptado del tipo de cambio, colones por dólar (inclusivo)
    usd_rate_min: int = DEFAULT_USD_RATE_MIN
    usd_rate_max: int = DEFAULT_USD_RATE_MAX


def _required(env: Mapping[str, str], name: str) -> str:
    value = env.get(name, "").strip()
    if not value:
        raise ConfigError(
            f"Falta la variable de entorno obligatoria {name}. "
            "Revisa tu archivo .env (ver .env.example)."
        )
    return value


def _int(env: Mapping[str, str], name: str, default: int) -> int:
    raw = env.get(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        raise ConfigError(f"La variable {name} debe ser un número entero.") from None


def _bool(env: Mapping[str, str], name: str, default: bool) -> bool:
    raw = env.get(name, "").strip().lower()
    if not raw:
        return default
    if raw in ("true", "1", "yes", "si", "sí"):
        return True
    if raw in ("false", "0", "no"):
        return False
    raise ConfigError(f"La variable {name} debe ser true o false.")


def _timezone(env: Mapping[str, str], name: str) -> str:
    value = env.get(name, "").strip() or DEFAULT_TIMEZONE
    try:
        zoneinfo.ZoneInfo(value)
    except (zoneinfo.ZoneInfoNotFoundError, ValueError):
        raise ConfigError(
            f"La variable {name} debe ser una zona horaria válida (por ejemplo {DEFAULT_TIMEZONE})."
        ) from None
    return value


def _rate_range(env: Mapping[str, str]) -> tuple[int, int]:
    low = _int(env, "USD_RATE_MIN", DEFAULT_USD_RATE_MIN)
    high = _int(env, "USD_RATE_MAX", DEFAULT_USD_RATE_MAX)
    if low <= 0 or low >= high:
        raise ConfigError(
            "USD_RATE_MIN y USD_RATE_MAX deben ser enteros positivos, con USD_RATE_MIN menor que "
            "USD_RATE_MAX (colones por dólar)."
        )
    return low, high


def _csv(env: Mapping[str, str], name: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in env.get(name, "").split(",") if item.strip())


def load_settings(env: Mapping[str, str] | None = None) -> Settings:
    """Lee la configuración. Si `env` es None, usa las variables del proceso."""
    env = os.environ if env is None else env
    mcp_port = _int(env, "MCP_PORT", 8000)
    public_hostname = env.get("MCP_PUBLIC_HOSTNAME", "").strip() or None

    issuer = env.get("OAUTH_ISSUER_URL", "").strip().rstrip("/") or (
        f"https://{public_hostname}" if public_hostname else f"http://127.0.0.1:{mcp_port}"
    )
    resource = env.get("OAUTH_RESOURCE_URL", "").strip() or f"{issuer}/mcp"
    lifetimes = SHORT_LIFETIMES if _bool(env, "OAUTH_SHORT_LIFETIMES", False) else NORMAL_LIFETIMES
    rate_min, rate_max = _rate_range(env)

    return Settings(
        database_url=_required(env, "DATABASE_URL"),
        mcp_host=env.get("MCP_HOST", "").strip() or "127.0.0.1",
        mcp_port=mcp_port,
        db_connect_timeout=_int(env, "DB_CONNECT_TIMEOUT", 2),
        public_hostname=public_hostname,
        allowed_origins=_csv(env, "MCP_ALLOWED_ORIGINS"),
        owner_password_hash=env.get("OWNER_PASSWORD_HASH", "").strip() or None,
        oauth_issuer_url=issuer,
        oauth_resource_url=resource,
        oauth_allowed_redirect_uris=_csv(env, "OAUTH_ALLOWED_REDIRECT_URIS")
        or DEFAULT_REDIRECT_URIS,
        oauth_registration_enabled=_bool(env, "OAUTH_REGISTRATION_ENABLED", False),
        oauth_max_clients=_int(env, "OAUTH_MAX_CLIENTS", 10),
        oauth_access_token_ttl=_int(env, "OAUTH_ACCESS_TOKEN_TTL_SECONDS", lifetimes["access"]),
        oauth_refresh_token_ttl=_int(env, "OAUTH_REFRESH_TOKEN_TTL_SECONDS", lifetimes["refresh"]),
        oauth_auth_code_ttl=_int(env, "OAUTH_AUTH_CODE_TTL_SECONDS", lifetimes["code"]),
        app_timezone=_timezone(env, "APP_TIMEZONE"),
        usd_rate_min=rate_min,
        usd_rate_max=rate_max,
    )
