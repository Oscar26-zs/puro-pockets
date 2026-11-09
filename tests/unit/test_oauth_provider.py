"""Proveedor OAuth con almacén en memoria (Hito 3)."""

import base64
import hashlib

import pytest
from mcp.server.auth.provider import (
    AuthorizationParams,
    AuthorizeError,
    RegistrationError,
    TokenError,
)
from mcp.shared.auth import OAuthClientInformationFull
from pydantic import AnyUrl

from puro_pockets.domain.auth import EventLimiter, hash_token
from puro_pockets.services.oauth import OAuthConfig, OwnerOAuthProvider
from tests.fakes import FakeClock, InMemoryOAuthStore

pytestmark = pytest.mark.anyio

CALLBACK = "https://claude.ai/api/mcp/auth_callback"
RESOURCE = "https://mcp.puropockets.space/mcp"
CONFIG = OAuthConfig(
    issuer_url="https://mcp.puropockets.space",
    resource_url=RESOURCE,
    allowed_redirect_uris=(CALLBACK, "https://claude.com/api/mcp/auth_callback"),
    max_clients=2,
    access_token_ttl=3600,
    refresh_token_ttl=30 * 24 * 3600,
    auth_code_ttl=300,
)


def _client(client_id="c1", redirect=CALLBACK, auth_method="none") -> OAuthClientInformationFull:
    return OAuthClientInformationFull(
        client_id=client_id,
        redirect_uris=[AnyUrl(redirect)],
        token_endpoint_auth_method=auth_method,
        grant_types=["authorization_code", "refresh_token"],
        response_types=["code"],
        client_name="Claude",
        scope="mcp offline_access",
    )


def _provider(clock=None, store=None) -> OwnerOAuthProvider:
    return OwnerOAuthProvider(
        store=store or InMemoryOAuthStore(),
        config=CONFIG,
        clock=clock or FakeClock(),
        registration_limiter=EventLimiter(max_events=100, window_seconds=3600),
    )


def _params(resource=RESOURCE) -> AuthorizationParams:
    verifier = "v" * 64
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=")
    return AuthorizationParams(
        state="estado",
        scopes=["mcp", "offline_access"],
        code_challenge=challenge.decode(),
        redirect_uri=AnyUrl(CALLBACK),
        redirect_uri_provided_explicitly=True,
        resource=resource,
    )


async def _tokens(provider: OwnerOAuthProvider, client):
    url = await provider.authorize(client, _params())
    request_id = url.split("request=")[1]
    redirect = await provider.complete_authorization(request_id)
    code = redirect.split("code=")[1].split("&")[0]
    loaded = await provider.load_authorization_code(client, code)
    return await provider.exchange_authorization_code(client, loaded)


# --- Registro ---


async def test_registro_valido():
    provider = _provider()
    await provider.register_client(_client())
    assert await provider.get_client("c1") is not None


async def test_registro_rechaza_retorno_no_permitido():
    provider = _provider()
    with pytest.raises(RegistrationError) as exc:
        await provider.register_client(_client(redirect="https://evil.example.com/callback"))
    assert exc.value.error == "invalid_redirect_uri"


async def test_registro_rechaza_cliente_confidencial():
    with pytest.raises(RegistrationError):
        await _provider().register_client(_client(auth_method="client_secret_post"))


async def test_registro_respeta_el_maximo_de_clientes():
    provider = _provider()
    await provider.register_client(_client("a"))
    await provider.register_client(_client("b"))
    with pytest.raises(RegistrationError):
        await provider.register_client(_client("c"))


async def test_registro_con_limite_de_intentos():
    provider = _provider()
    provider.registration_limiter = EventLimiter(max_events=1, window_seconds=3600)
    await provider.register_client(_client("a"))
    with pytest.raises(RegistrationError):
        await provider.register_client(_client("b"))


# --- Autorización y código ---


async def test_autorizacion_rechaza_otro_recurso():
    provider = _provider()
    client = _client()
    with pytest.raises(AuthorizeError) as exc:
        await provider.authorize(client, _params(resource="https://otro.example.com/mcp"))
    assert exc.value.error == "invalid_target"


async def test_codigo_de_un_solo_uso_y_solo_se_guarda_su_hash():
    store = InMemoryOAuthStore()
    provider = _provider(store=store)
    client = _client()
    url = await provider.authorize(client, _params())
    assert url.startswith("https://mcp.puropockets.space/login?request=")
    redirect = await provider.complete_authorization(url.split("request=")[1])
    assert redirect.startswith(CALLBACK) and "state=estado" in redirect
    code = redirect.split("code=")[1].split("&")[0]
    assert code not in store.codes and hash_token(code) in store.codes

    loaded = await provider.load_authorization_code(client, code)
    token = await provider.exchange_authorization_code(client, loaded)
    assert token.access_token.startswith("ppa_") and token.refresh_token.startswith("ppr_")
    assert token.access_token not in store.access
    assert await provider.load_authorization_code(client, code) is None
    with pytest.raises(TokenError):
        await provider.exchange_authorization_code(client, loaded)


async def test_codigo_vencido_no_se_canjea():
    clock = FakeClock()
    provider = _provider(clock=clock)
    client = _client()
    url = await provider.authorize(client, _params())
    redirect = await provider.complete_authorization(url.split("request=")[1])
    code = redirect.split("code=")[1].split("&")[0]
    loaded = await provider.load_authorization_code(client, code)
    clock.advance(301)
    with pytest.raises(TokenError):
        await provider.exchange_authorization_code(client, loaded)


# --- Tokens ---


async def test_token_de_acceso_valido_y_vencido():
    clock = FakeClock()
    provider = _provider(clock=clock)
    token = await _tokens(provider, _client())
    access = await provider.load_access_token(token.access_token)
    assert (
        access is not None
        and access.resource == RESOURCE
        and access.scopes
        == [
            "mcp",
            "offline_access",
        ]
    )
    assert await provider.load_access_token("ppa_inventado") is None
    clock.advance(3601)
    assert await provider.load_access_token(token.access_token) is None


async def test_refresco_rota_y_reutilizar_revoca_la_cadena():
    provider = _provider()
    client = _client()
    first = await _tokens(provider, client)

    old_refresh = await provider.load_refresh_token(client, first.refresh_token)
    second = await provider.exchange_refresh_token(client, old_refresh, old_refresh.scopes)
    assert second.refresh_token != first.refresh_token
    assert await provider.load_access_token(second.access_token) is not None

    # Reutilizar el refresco viejo: rechazado y toda la cadena revocada
    assert await provider.load_refresh_token(client, first.refresh_token) is None
    assert await provider.load_access_token(second.access_token) is None
    assert await provider.load_refresh_token(client, second.refresh_token) is None


async def test_refresco_de_otro_cliente_no_vale():
    provider = _provider()
    token = await _tokens(provider, _client("c1"))
    assert await provider.load_refresh_token(_client("c2"), token.refresh_token) is None


async def test_revocacion_corta_la_cadena():
    provider = _provider()
    client = _client()
    token = await _tokens(provider, client)
    access = await provider.load_access_token(token.access_token)
    await provider.revoke_token(access)
    assert await provider.load_access_token(token.access_token) is None
    assert await provider.load_refresh_token(client, token.refresh_token) is None
