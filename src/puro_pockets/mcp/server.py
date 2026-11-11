"""Servidor MCP y sus tools. Las tools son delgadas: validan y llaman a services."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import uvicorn
from mcp.server.auth.settings import AuthSettings, ClientRegistrationOptions, RevocationOptions
from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from pydantic import BaseModel, Field
from starlette.applications import Starlette
from starlette.types import ASGIApp

from puro_pockets.config import Settings
from puro_pockets.domain.auth import LoginRateLimiter
from puro_pockets.mcp.audit import OAuthAuditMiddleware
from puro_pockets.mcp.budget_tools import register_budget_tools
from puro_pockets.mcp.login import build_login_handler
from puro_pockets.services.budget import BudgetService
from puro_pockets.services.health import HealthService
from puro_pockets.services.oauth import SCOPE_MCP, VALID_SCOPES, OwnerOAuthProvider
from puro_pockets.services.passwords import PasswordVerifier

# Protección contra DNS rebinding. El SDK valida Host (si no está permitido: 421) y Origin (solo si
# viene; si no está permitido: 403). Dentro del contenedor el servidor escucha en 0.0.0.0 y el SDK
# solo la activa por su cuenta para 127.0.0.1, así que se configura siempre de forma explícita.
LOCAL_HOSTS = ["127.0.0.1:*", "localhost:*", "[::1]:*"]
LOCAL_ORIGINS = ["http://127.0.0.1:*", "http://localhost:*", "http://[::1]:*"]


def build_transport_security(settings: Settings) -> TransportSecuritySettings:
    """Hosts locales siempre; el nombre público del túnel y los orígenes extra si se configuran."""
    hosts = list(LOCAL_HOSTS)
    origins = list(LOCAL_ORIGINS)
    if settings.public_hostname:
        # cloudflared reenvía el Host público original
        hosts += [settings.public_hostname, f"{settings.public_hostname}:*"]
        origins.append(f"https://{settings.public_hostname}")
    origins += list(settings.allowed_origins)
    return TransportSecuritySettings(
        enable_dns_rebinding_protection=True, allowed_hosts=hosts, allowed_origins=origins
    )


class PingResult(BaseModel):
    """Estado de salud que devuelve ping (contrato: specs/001-cimientos/contracts/ping.md)."""

    server: Literal["ok"] = Field(description="Estado del servidor MCP.")
    database: Literal["ok", "error"] = Field(description="Estado de la base de datos.")
    detail: str | None = Field(
        default=None, description="Motivo breve en español cuando la base está en error."
    )


@dataclass
class AuthComponents:
    """Piezas del servidor de autorización propio (Hito 3)."""

    provider: OwnerOAuthProvider
    verifier: PasswordVerifier
    limiter: LoginRateLimiter
    registration_enabled: bool = False


def build_auth_settings(provider: OwnerOAuthProvider, registration_enabled: bool) -> AuthSettings:
    return AuthSettings(
        issuer_url=provider.config.issuer_url,
        resource_server_url=provider.config.resource_url,
        # Rechaza tokens emitidos para otro recurso (RFC 8707)
        validate_token_resource=True,
        required_scopes=[SCOPE_MCP],
        # valid_scopes también define los scopes anunciados (incluye offline_access) aunque el
        # registro esté cerrado; el endpoint /register solo existe con registration_enabled
        client_registration_options=ClientRegistrationOptions(
            enabled=registration_enabled,
            valid_scopes=VALID_SCOPES,
            default_scopes=VALID_SCOPES,
        ),
        revocation_options=RevocationOptions(enabled=True),
    )


def build_server(
    health_service: HealthService,
    auth: AuthComponents | None = None,
    budget: BudgetService | None = None,
) -> MCPServer:
    if auth is None:
        server = MCPServer("puro-pockets")
    else:
        server = MCPServer(
            "puro-pockets",
            auth=build_auth_settings(auth.provider, auth.registration_enabled),
            auth_server_provider=auth.provider,
        )
        server.custom_route("/login", methods=["GET", "POST"])(
            build_login_handler(auth.provider, auth.verifier, auth.limiter)
        )

    @server.tool()
    async def ping() -> PingResult:
        """Indica si el servidor MCP y la base de datos están operativos."""
        status = await health_service.check()
        return PingResult(server=status.server, database=status.database, detail=status.detail)

    if budget is not None:
        # Presupuesto (Hito 4). Con auth, todas las tools quedan detrás del token
        register_budget_tools(server, budget)

    return server


def build_app(server: MCPServer, settings: Settings) -> ASGIApp:
    """Aplicación ASGI completa (MCP + OAuth) con auditoría de rechazos OAuth.

    La usan el arranque (run_server) y las pruebas en proceso, así que prueban lo mismo.
    """
    app: Starlette = server.streamable_http_app(
        transport_security=build_transport_security(settings), host=settings.mcp_host
    )
    return OAuthAuditMiddleware(app)


def run_server(server: MCPServer, settings: Settings) -> None:
    # Igual que MCPServer.run(transport="streamable-http"), pero con la app envuelta en la auditoría
    uvicorn.run(
        build_app(server, settings),
        host=settings.mcp_host,
        port=settings.mcp_port,
        log_level="info",
    )
