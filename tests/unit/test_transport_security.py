"""Hosts y orígenes permitidos por la protección contra DNS rebinding (Hito 2, FR-005 a FR-007)."""

from puro_pockets.config import Settings
from puro_pockets.mcp.server import build_transport_security

DB_URL = "postgresql+psycopg://u:p@127.0.0.1:5432/x"
LOCAL_HOSTS = {"127.0.0.1:*", "localhost:*", "[::1]:*"}


def test_solo_local_sin_nombre_publico():
    security = build_transport_security(Settings(database_url=DB_URL))
    assert security.enable_dns_rebinding_protection is True
    assert set(security.allowed_hosts) == LOCAL_HOSTS
    assert all("puropockets" not in origin for origin in security.allowed_origins)


def test_nombre_publico_y_origenes_extra():
    settings = Settings(
        database_url=DB_URL,
        public_hostname="mcp.puropockets.space",
        allowed_origins=("https://claude.ai",),
    )
    security = build_transport_security(settings)
    assert security.enable_dns_rebinding_protection is True
    assert LOCAL_HOSTS <= set(security.allowed_hosts)
    assert "mcp.puropockets.space" in security.allowed_hosts
    assert "mcp.puropockets.space:*" in security.allowed_hosts
    assert "https://mcp.puropockets.space" in security.allowed_origins
    assert "https://claude.ai" in security.allowed_origins


def test_sin_comodines_abiertos():
    settings = Settings(database_url=DB_URL, public_hostname="mcp.puropockets.space")
    security = build_transport_security(settings)
    assert "*" not in security.allowed_hosts
    assert "*" not in security.allowed_origins
