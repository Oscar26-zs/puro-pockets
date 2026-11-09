"""Configuración de la aplicación a partir de variables de entorno."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass


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


def _csv(env: Mapping[str, str], name: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in env.get(name, "").split(",") if item.strip())


def load_settings(env: Mapping[str, str] | None = None) -> Settings:
    """Lee la configuración. Si `env` es None, usa las variables del proceso."""
    env = os.environ if env is None else env
    return Settings(
        database_url=_required(env, "DATABASE_URL"),
        mcp_host=env.get("MCP_HOST", "").strip() or "127.0.0.1",
        mcp_port=_int(env, "MCP_PORT", 8000),
        db_connect_timeout=_int(env, "DB_CONNECT_TIMEOUT", 2),
        public_hostname=env.get("MCP_PUBLIC_HOSTNAME", "").strip() or None,
        allowed_origins=_csv(env, "MCP_ALLOWED_ORIGINS"),
    )
