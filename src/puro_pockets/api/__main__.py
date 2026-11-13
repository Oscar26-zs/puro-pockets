"""Punto de entrada: `python -m puro_pockets.api` arranca el dashboard (API + frontend).

Antes de servir comprueba que el rol de `DASHBOARD_DATABASE_URL` es de solo lectura y no lee
`oauth_*`; si no, sale con error. No hay respaldo al rol propietario (`DATABASE_URL`).
"""

from __future__ import annotations

import logging
import sys
from functools import partial

import uvicorn
from sqlalchemy import Engine, create_engine

from puro_pockets.api.access import AccessVerifier
from puro_pockets.api.app import build_app
from puro_pockets.api.config import DashboardSettings, load_dashboard_settings
from puro_pockets.api.readonly import UnsafeDatabaseRole, ensure_read_only
from puro_pockets.api.session import SessionManager
from puro_pockets.config import ConfigError
from puro_pockets.db.engine import check_database
from puro_pockets.db.ledger_store import SqlLedgerStore
from puro_pockets.domain.auth import LoginRateLimiter
from puro_pockets.domain.money import RateRange
from puro_pockets.services.budget import local_today
from puro_pockets.services.dashboard import DashboardService
from puro_pockets.services.ledger import LedgerService
from puro_pockets.services.passwords import PasswordVerifier

logger = logging.getLogger("puro_pockets.api")


def read_only_engine(settings: DashboardSettings) -> Engine:
    """Motor del dashboard: cada transacción es de solo lectura también en la sesión de Postgres."""
    return create_engine(
        settings.database_url,
        pool_pre_ping=True,
        pool_size=3,
        max_overflow=2,
        connect_args={
            "connect_timeout": settings.db_connect_timeout,
            "options": "-c default_transaction_read_only=on",
        },
    )


def build_from_settings(settings: DashboardSettings, engine: Engine):
    today = local_today(settings.app_timezone)
    store = SqlLedgerStore(engine)
    ledger = LedgerService(
        store, today=today, rate_range=RateRange(settings.usd_rate_min, settings.usd_rate_max)
    )
    return build_app(
        DashboardService(ledger, store, today),
        SessionManager(settings.session_secret, settings.session_ttl),
        PasswordVerifier(settings.owner_password_hash),
        LoginRateLimiter(),
        cookie_secure=settings.cookie_secure,
        static_dir=settings.static_dir,
        health=partial(check_database, engine),
        public_hostname=settings.public_hostname,
        access=AccessVerifier(settings.access_team_domain, settings.access_audience)
        if settings.public_hostname and settings.access_team_domain and settings.access_audience
        else None,
    )


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    try:
        settings = load_dashboard_settings()
    except ConfigError as exc:
        print(f"Error de configuración del dashboard: {exc}", file=sys.stderr)
        sys.exit(1)
    engine = read_only_engine(settings)
    try:
        ensure_read_only(engine)
    except UnsafeDatabaseRole as exc:
        print(f"El dashboard no arranca: {exc}", file=sys.stderr)
        sys.exit(2)
    except Exception as exc:  # noqa: BLE001 - sin base no hay dashboard; sin detalles de conexión
        print(
            f"El dashboard no arranca: no se pudo conectar a la base ({type(exc).__name__}).",
            file=sys.stderr,
        )
        sys.exit(3)
    if not (settings.static_dir / "index.html").is_file():
        logger.warning("No se encontró el frontend compilado: solo se sirve /api")
    logger.info(
        "Dashboard: rol de solo lectura comprobado; cookie Secure=%s; zona horaria=%s",
        settings.cookie_secure,
        settings.app_timezone,
    )
    if settings.public_hostname:
        logger.info(
            "Publicado por Cloudflare en %s, con Cloudflare Access obligatorio (equipo %s)",
            settings.public_hostname,
            settings.access_team_domain,
        )
        if not settings.cookie_secure:
            logger.warning("Publicado por Cloudflare con DASHBOARD_COOKIE_SECURE=false: usa true")
    else:
        logger.info("Sin nombre público: solo acceso local; peticiones de Cloudflare → 403")
    uvicorn.run(
        build_from_settings(settings, engine),
        host=settings.host,
        port=settings.port,
        access_log=False,  # la consulta lleva nombres de bolsa: registra el middleware
        proxy_headers=False,  # sin proxy delante: no se confía en X-Forwarded-For
        server_header=False,
        log_level="info",
    )


if __name__ == "__main__":
    main()
