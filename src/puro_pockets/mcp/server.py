"""Servidor MCP y sus tools. Las tools son delgadas: validan y llaman a services."""

from __future__ import annotations

from typing import Literal

from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from pydantic import BaseModel, Field

from puro_pockets.config import Settings
from puro_pockets.services.health import HealthService

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


def build_server(health_service: HealthService) -> MCPServer:
    server = MCPServer("puro-pockets")

    @server.tool()
    async def ping() -> PingResult:
        """Indica si el servidor MCP y la base de datos están operativos."""
        status = await health_service.check()
        return PingResult(server=status.server, database=status.database, detail=status.detail)

    return server


def run_server(server: MCPServer, settings: Settings) -> None:
    server.run(
        transport="streamable-http",
        host=settings.mcp_host,
        port=settings.mcp_port,
        transport_security=build_transport_security(settings),
    )
