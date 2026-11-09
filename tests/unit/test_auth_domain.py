"""Reglas puras de autenticación (Hito 3)."""

from puro_pockets.domain.auth import (
    EventLimiter,
    LoginRateLimiter,
    hash_token,
    redirect_domain,
    redirect_uri_allowed,
)

ALLOWLIST = (
    "https://claude.ai/api/mcp/auth_callback",
    "https://claude.com/api/mcp/auth_callback",
)


def test_hash_token_es_sha256_estable_y_no_revela_el_token():
    h = hash_token("ppa_secreto")
    assert h == hash_token("ppa_secreto")
    assert h != hash_token("ppa_otro")
    assert len(h) == 64
    assert "secreto" not in h


def test_lista_blanca_exacta():
    assert redirect_uri_allowed("https://claude.ai/api/mcp/auth_callback", ALLOWLIST)
    assert redirect_uri_allowed("https://claude.com/api/mcp/auth_callback", ALLOWLIST)
    for uri in (
        "https://claude.ai/api/mcp/auth_callback/",
        "https://claude.ai/api/mcp/auth_callback?x=1",
        "http://claude.ai/api/mcp/auth_callback",
        "https://evil.example.com/api/mcp/auth_callback",
        "https://claude.ai.evil.com/api/mcp/auth_callback",
        "http://localhost:3118/callback",
    ):
        assert not redirect_uri_allowed(uri, ALLOWLIST), uri


def test_redirect_domain():
    assert redirect_domain("https://claude.ai/api/mcp/auth_callback") == "claude.ai"
    assert redirect_domain("https://claude.com/api/mcp/auth_callback") == "claude.com"


def test_bloqueo_por_ip_tras_cinco_fallos_y_reinicio_al_acertar():
    limiter = LoginRateLimiter(
        per_key_max=5, window_seconds=900, global_max=100, global_lock_seconds=300
    )
    for _ in range(4):
        limiter.record_failure("1.1.1.1", now=0)
    assert limiter.retry_after("1.1.1.1", now=1) == 0
    limiter.record_failure("1.1.1.1", now=2)
    assert limiter.retry_after("1.1.1.1", now=3) > 0
    assert limiter.retry_after("2.2.2.2", now=3) == 0  # otra IP no se bloquea
    assert limiter.retry_after("1.1.1.1", now=903) == 0  # pasa la ventana
    limiter.record_failure("3.3.3.3", now=0)
    limiter.record_success("3.3.3.3")
    for _ in range(4):
        limiter.record_failure("3.3.3.3", now=1)
    assert limiter.retry_after("3.3.3.3", now=2) == 0


def test_bloqueo_global_corto():
    limiter = LoginRateLimiter(
        per_key_max=100, window_seconds=900, global_max=20, global_lock_seconds=300
    )
    for i in range(20):
        limiter.record_failure(f"10.0.0.{i}", now=10)
    assert limiter.retry_after("99.99.99.99", now=11) > 0  # bloqueo global
    assert limiter.retry_after("99.99.99.99", now=311) == 0  # dura poco


def test_limitador_de_eventos():
    limiter = EventLimiter(max_events=2, window_seconds=3600)
    assert limiter.allow(now=0)
    assert limiter.allow(now=1)
    assert not limiter.allow(now=2)
    assert limiter.allow(now=3601)
