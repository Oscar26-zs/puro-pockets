"""Configuración del dashboard (Hito 10) a partir de variables de entorno.

Variables propias `DASHBOARD_*` más las compartidas con el MCP (`OWNER_PASSWORD_HASH`,
`APP_TIMEZONE`, `USD_RATE_MIN`, `USD_RATE_MAX`). `DASHBOARD_DATABASE_URL` es obligatoria y
**no** cae a `DATABASE_URL`: el dashboard nunca usa el rol propietario. Los mensajes nunca incluyen
valores.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from puro_pockets.config import ConfigError, _bool, _int, _rate_range, _required, _timezone

MIN_SECRET_BYTES = 32
SESSION_TTL_SECONDS = 12 * 3600
DEFAULT_STATIC_DIR = Path(__file__).resolve().parents[3] / "web" / "dist"


@dataclass(frozen=True)
class DashboardSettings:
    database_url: str
    session_secret: bytes
    owner_password_hash: str
    cookie_secure: bool = True
    host: str = "127.0.0.1"
    port: int = 8080
    static_dir: Path = DEFAULT_STATIC_DIR
    db_connect_timeout: int = 2
    app_timezone: str = "America/Costa_Rica"
    usd_rate_min: int = 300
    usd_rate_max: int = 1000
    session_ttl: int = SESSION_TTL_SECONDS


def _secret(env: Mapping[str, str]) -> bytes:
    raw = _required(env, "DASHBOARD_SESSION_SECRET").encode("utf-8")
    if len(raw) < MIN_SECRET_BYTES:
        raise ConfigError(
            f"DASHBOARD_SESSION_SECRET debe tener al menos {MIN_SECRET_BYTES} bytes "
            '(genéralo con: python -c "import secrets; print(secrets.token_urlsafe(48))").'
        )
    return raw


def _password_hash(env: Mapping[str, str]) -> str:
    value = env.get("OWNER_PASSWORD_HASH", "").strip().strip("'\"")
    if not value.startswith("$argon2"):
        raise ConfigError(
            "OWNER_PASSWORD_HASH falta o no es un hash argon2: genéralo con "
            "scripts/hash_password.py (Hito 3). Sin él nadie podría entrar al dashboard."
        )
    return value


def load_dashboard_settings(env: Mapping[str, str] | None = None) -> DashboardSettings:
    """Lee la configuración del dashboard. Si `env` es None, usa las variables del proceso."""
    env = os.environ if env is None else env
    rate_min, rate_max = _rate_range(env)
    static = env.get("DASHBOARD_STATIC_DIR", "").strip()
    return DashboardSettings(
        database_url=_required(env, "DASHBOARD_DATABASE_URL"),
        session_secret=_secret(env),
        owner_password_hash=_password_hash(env),
        cookie_secure=_bool(env, "DASHBOARD_COOKIE_SECURE", True),
        host=env.get("DASHBOARD_HOST", "").strip() or "127.0.0.1",
        port=_int(env, "DASHBOARD_PORT", 8080),
        static_dir=Path(static) if static else DEFAULT_STATIC_DIR,
        db_connect_timeout=_int(env, "DB_CONNECT_TIMEOUT", 2),
        app_timezone=_timezone(env, "APP_TIMEZONE"),
        usd_rate_min=rate_min,
        usd_rate_max=rate_max,
    )
