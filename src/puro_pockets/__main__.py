"""Punto de entrada: `python -m puro_pockets` arranca el servidor MCP (Streamable HTTP + OAuth)."""

from __future__ import annotations

import logging
import sys
from functools import partial

from sqlalchemy import Engine

from puro_pockets.config import ConfigError, Settings, load_settings
from puro_pockets.db.budget_store import SqlBudgetStore
from puro_pockets.db.engine import check_database, create_engine_from_settings
from puro_pockets.db.oauth_store import SqlOAuthStore
from puro_pockets.domain.auth import LoginRateLimiter
from puro_pockets.mcp.server import AuthComponents, build_server, run_server
from puro_pockets.services.budget import BudgetService, local_today
from puro_pockets.services.health import HealthService
from puro_pockets.services.oauth import OAuthConfig, OwnerOAuthProvider
from puro_pockets.services.passwords import PasswordVerifier

logger = logging.getLogger("puro_pockets")

# Bibliotecas que en DEBUG registran los cuerpos completos de las respuestas (montos y saldos):
# se fijan en INFO aunque se suba el nivel general (FR-014, principio 3.10)
BODY_LOGGERS = ("sse_starlette", "mcp.server.streamable_http")


def configure_logging() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    for name in BODY_LOGGERS:
        logging.getLogger(name).setLevel(logging.INFO)


def oauth_config(settings: Settings) -> OAuthConfig:
    return OAuthConfig(
        issuer_url=settings.oauth_issuer_url,
        resource_url=settings.oauth_resource_url,
        allowed_redirect_uris=settings.oauth_allowed_redirect_uris,
        max_clients=settings.oauth_max_clients,
        access_token_ttl=settings.oauth_access_token_ttl,
        refresh_token_ttl=settings.oauth_refresh_token_ttl,
        auth_code_ttl=settings.oauth_auth_code_ttl,
    )


def build_auth(settings: Settings, engine: Engine) -> AuthComponents:
    verifier = PasswordVerifier(settings.owner_password_hash)
    if not verifier.enabled:
        logger.warning(
            "OWNER_PASSWORD_HASH vacío o inválido: el inicio de sesión está deshabilitado "
            "y nadie puede obtener tokens (ver README, Hito 3)."
        )
    if settings.oauth_registration_enabled:
        logger.warning(
            "Registro de clientes ABIERTO (OAUTH_REGISTRATION_ENABLED=true). "
            "Ciérralo después de agregar el conector."
        )
    logger.info(
        "OAuth: emisor=%s recurso=%s acceso=%ss refresco=%ss código=%ss retornos=%s",
        settings.oauth_issuer_url,
        settings.oauth_resource_url,
        settings.oauth_access_token_ttl,
        settings.oauth_refresh_token_ttl,
        settings.oauth_auth_code_ttl,
        ", ".join(settings.oauth_allowed_redirect_uris),
    )
    return AuthComponents(
        provider=OwnerOAuthProvider(store=SqlOAuthStore(engine), config=oauth_config(settings)),
        verifier=verifier,
        limiter=LoginRateLimiter(),
        registration_enabled=settings.oauth_registration_enabled,
    )


def main() -> None:
    configure_logging()
    try:
        settings = load_settings()
    except ConfigError as exc:
        print(f"Error de configuración: {exc}", file=sys.stderr)
        sys.exit(1)

    engine = create_engine_from_settings(settings)
    # Límite total de la comprobación: tiempo de conexión + 1 s de margen (ping < 5 s)
    health = HealthService(
        partial(check_database, engine), timeout_seconds=settings.db_connect_timeout + 1
    )
    budget = BudgetService(SqlBudgetStore(engine), today=local_today(settings.app_timezone))
    logger.info("Presupuesto: zona horaria=%s", settings.app_timezone)
    run_server(build_server(health, build_auth(settings, engine), budget), settings)


if __name__ == "__main__":
    main()
