"""Proveedor OAuth 2.1 para un único usuario (el propietario), sobre el módulo de auth del SDK.

El SDK implementa los endpoints, PKCE y la validación Bearer; aquí se decide qué se guarda (solo
hashes), quién puede registrarse, cuánto duran los tokens y cómo se rotan y revocan.
"""

from __future__ import annotations

import logging
import secrets
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from functools import partial
from typing import Protocol, TypeVar

import anyio
from mcp.server.auth.provider import (
    AccessToken,
    AuthorizationCode,
    AuthorizationParams,
    AuthorizeError,
    RefreshToken,
    RegistrationError,
    TokenError,
    construct_redirect_uri,
)
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken
from pydantic import AnyUrl

from puro_pockets.domain.auth import EventLimiter, hash_token, redirect_domain, redirect_uri_allowed

logger = logging.getLogger("puro_pockets.auth")

T = TypeVar("T")

SCOPE_MCP = "mcp"
SCOPE_OFFLINE = "offline_access"
VALID_SCOPES = [SCOPE_MCP, SCOPE_OFFLINE]
OWNER_SUBJECT = "owner"
PENDING_TTL_SECONDS = 600  # tiempo para completar el inicio de sesión


@dataclass(frozen=True)
class CodeRecord:
    code_hash: str
    client_id: str
    redirect_uri: str
    redirect_uri_provided_explicitly: bool
    code_challenge: str
    scopes: tuple[str, ...]
    resource: str
    expires_at: float
    used_at: float | None = None


@dataclass(frozen=True)
class TokenRecord:
    token_hash: str
    client_id: str
    family_id: str
    scopes: tuple[str, ...]
    resource: str
    expires_at: float
    revoked_at: float | None = None
    used_at: float | None = None  # solo tokens de refresco


class OAuthStore(Protocol):
    """Almacén de clientes, códigos y tokens. Métodos síncronos (se llaman en un hilo)."""

    def count_clients(self) -> int: ...
    def get_client(self, client_id: str) -> str | None: ...
    def save_client(self, client_id: str, metadata_json: str) -> None: ...
    def save_code(self, record: CodeRecord) -> None: ...
    def get_code(self, code_hash: str) -> CodeRecord | None: ...
    def consume_code(self, code_hash: str, now: float) -> bool: ...
    def save_token_pair(self, access: TokenRecord, refresh: TokenRecord) -> None: ...
    def get_access_token(self, token_hash: str) -> TokenRecord | None: ...
    def get_refresh_token(self, token_hash: str) -> TokenRecord | None: ...
    def consume_refresh_token(self, token_hash: str, now: float) -> bool: ...
    def revoke_family(self, family_id: str, now: float) -> None: ...
    def revoke_all(self, now: float) -> int: ...


@dataclass(frozen=True)
class OAuthConfig:
    issuer_url: str
    resource_url: str
    allowed_redirect_uris: tuple[str, ...]
    max_clients: int = 10
    access_token_ttl: int = 3600
    refresh_token_ttl: int = 30 * 24 * 3600
    auth_code_ttl: int = 300
    login_path: str = "/login"


@dataclass
class PendingAuthorization:
    client_id: str
    client_name: str | None
    redirect_uri: str
    redirect_uri_provided_explicitly: bool
    code_challenge: str
    state: str | None
    scopes: tuple[str, ...]
    created_at: float

    @property
    def redirect_domain(self) -> str:
        return redirect_domain(self.redirect_uri)


@dataclass
class OwnerOAuthProvider:
    store: OAuthStore
    config: OAuthConfig
    clock: Callable[[], float] = time.time
    registration_limiter: EventLimiter = field(
        default_factory=lambda: EventLimiter(max_events=5, window_seconds=3600)
    )
    _pending: dict[str, PendingAuthorization] = field(default_factory=dict)

    async def _db(self, fn: Callable[..., T], *args: object) -> T:
        return await anyio.to_thread.run_sync(partial(fn, *args))

    # --- Clientes (RFC 7591) ---

    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        try:
            raw = await self._db(self.store.get_client, client_id)
            if not raw:
                # Nota: si varias réplicas del túnel apuntan a bases distintas, el cliente puede
                # existir en otra máquina (ver README, "Problemas frecuentes").
                logger.info("Cliente no encontrado en esta base: client_id=%s", client_id[:8])
                return None
            return OAuthClientInformationFull.model_validate_json(raw)
        except Exception:
            # No se oculta como "no encontrado": se registra la excepción real y se propaga
            logger.exception("Error al leer el cliente client_id=%s", client_id[:8])
            raise

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        if not self.registration_limiter.allow(self.clock()):
            logger.warning("Registro rechazado: demasiados intentos")
            raise RegistrationError(
                "invalid_client_metadata", "Demasiados registros. Espera e inténtalo de nuevo."
            )
        if client_info.token_endpoint_auth_method != "none":
            logger.warning("Registro rechazado: cliente confidencial no permitido")
            raise RegistrationError(
                "invalid_client_metadata", "Solo se aceptan clientes públicos (sin secreto)."
            )
        uris = [str(uri) for uri in client_info.redirect_uris or []]
        rejected = [
            u for u in uris if not redirect_uri_allowed(u, self.config.allowed_redirect_uris)
        ]
        if not uris or rejected:
            logger.warning(
                "Registro rechazado: URL de retorno no permitida (%s)",
                ", ".join(sorted({redirect_domain(u) or "?" for u in rejected})) or "ninguna",
            )
            raise RegistrationError("invalid_redirect_uri", "URL de retorno no permitida.")
        if await self._db(self.store.count_clients) >= self.config.max_clients:
            logger.warning("Registro rechazado: máximo de %s clientes", self.config.max_clients)
            raise RegistrationError("invalid_client_metadata", "Se alcanzó el máximo de clientes.")
        await self._db(self.store.save_client, client_info.client_id, client_info.model_dump_json())
        logger.info(
            "Cliente registrado: client_id=%s nombre=%r retorno=%s",
            client_info.client_id[:8],
            client_info.client_name,
            ", ".join(sorted({redirect_domain(u) for u in uris})),
        )

    # --- Autorización: el SDK valida la petición; el propietario inicia sesión en /login ---

    async def authorize(
        self, client: OAuthClientInformationFull, params: AuthorizationParams
    ) -> str:
        redirect = str(params.redirect_uri)
        if not redirect_uri_allowed(redirect, self.config.allowed_redirect_uris):
            raise AuthorizeError("invalid_request", "URL de retorno no permitida.")
        if params.resource and params.resource.rstrip("/") != self.config.resource_url.rstrip("/"):
            raise AuthorizeError("invalid_target", "Recurso desconocido.")
        self._purge_pending()
        request_id = secrets.token_urlsafe(24)
        self._pending[request_id] = PendingAuthorization(
            client_id=client.client_id,
            client_name=client.client_name,
            redirect_uri=redirect,
            redirect_uri_provided_explicitly=params.redirect_uri_provided_explicitly,
            code_challenge=params.code_challenge,
            state=params.state,
            scopes=tuple(params.scopes or VALID_SCOPES),
            created_at=self.clock(),
        )
        return f"{self.config.issuer_url}{self.config.login_path}?request={request_id}"

    def _purge_pending(self) -> None:
        limit = self.clock() - PENDING_TTL_SECONDS
        for key in [k for k, p in self._pending.items() if p.created_at < limit]:
            del self._pending[key]

    def get_pending(self, request_id: str) -> PendingAuthorization | None:
        self._purge_pending()
        return self._pending.get(request_id)

    async def complete_authorization(self, request_id: str) -> str:
        """Tras un inicio de sesión correcto: emite el código y devuelve la URL de retorno."""
        pending = self._pending.pop(request_id)
        code = "ppc_" + secrets.token_urlsafe(32)
        await self._db(
            self.store.save_code,
            CodeRecord(
                code_hash=hash_token(code),
                client_id=pending.client_id,
                redirect_uri=pending.redirect_uri,
                redirect_uri_provided_explicitly=pending.redirect_uri_provided_explicitly,
                code_challenge=pending.code_challenge,
                scopes=pending.scopes,
                resource=self.config.resource_url,
                expires_at=self.clock() + self.config.auth_code_ttl,
            ),
        )
        logger.info(
            "Código emitido: client_id=%s retorno=%s",
            pending.client_id[:8],
            pending.redirect_domain,
        )
        return construct_redirect_uri(pending.redirect_uri, code=code, state=pending.state)

    async def load_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: str
    ) -> AuthorizationCode | None:
        record = await self._db(self.store.get_code, hash_token(authorization_code))
        if record is None or record.client_id != client.client_id or record.used_at is not None:
            return None
        return AuthorizationCode(
            code=authorization_code,
            scopes=list(record.scopes),
            expires_at=record.expires_at,
            client_id=record.client_id,
            code_challenge=record.code_challenge,
            redirect_uri=AnyUrl(record.redirect_uri),
            redirect_uri_provided_explicitly=record.redirect_uri_provided_explicitly,
            resource=record.resource,
            subject=OWNER_SUBJECT,
        )

    async def exchange_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: AuthorizationCode
    ) -> OAuthToken:
        now = self.clock()
        if not await self._db(self.store.consume_code, hash_token(authorization_code.code), now):
            logger.warning("Código reutilizado o vencido: client_id=%s", client.client_id[:8])
            raise TokenError("invalid_grant", "El código ya se usó.")
        family_id = str(uuid.uuid4())
        logger.info("Tokens emitidos: client_id=%s cadena=%s", client.client_id[:8], family_id[:8])
        return await self._issue_pair(
            client.client_id, family_id, tuple(authorization_code.scopes), now
        )

    # --- Tokens ---

    async def _issue_pair(
        self, client_id: str, family_id: str, scopes: tuple[str, ...], now: float
    ) -> OAuthToken:
        access = "ppa_" + secrets.token_urlsafe(32)
        refresh = "ppr_" + secrets.token_urlsafe(32)
        base = TokenRecord(
            token_hash="",
            client_id=client_id,
            family_id=family_id,
            scopes=scopes,
            resource=self.config.resource_url,
            expires_at=0,
        )
        await self._db(
            self.store.save_token_pair,
            replace(
                base, token_hash=hash_token(access), expires_at=now + self.config.access_token_ttl
            ),
            replace(
                base, token_hash=hash_token(refresh), expires_at=now + self.config.refresh_token_ttl
            ),
        )
        return OAuthToken(
            access_token=access,
            token_type="Bearer",
            expires_in=self.config.access_token_ttl,
            scope=" ".join(scopes),
            refresh_token=refresh,
        )

    async def load_refresh_token(
        self, client: OAuthClientInformationFull, refresh_token: str
    ) -> RefreshToken | None:
        record = await self._db(self.store.get_refresh_token, hash_token(refresh_token))
        if record is None or record.client_id != client.client_id:
            return None
        now = self.clock()
        if record.revoked_at is not None or record.expires_at <= now:
            return None
        if record.used_at is not None:
            # Reutilización de un refresco ya rotado: posible robo; se revoca toda la cadena
            await self._db(self.store.revoke_family, record.family_id, now)
            logger.warning(
                "Refresco reutilizado: cadena %s revocada (client_id=%s)",
                record.family_id[:8],
                client.client_id[:8],
            )
            return None
        return RefreshToken(
            token=refresh_token,
            client_id=record.client_id,
            scopes=list(record.scopes),
            expires_at=int(record.expires_at),
            resource=record.resource,
            subject=OWNER_SUBJECT,
        )

    async def exchange_refresh_token(
        self,
        client: OAuthClientInformationFull,
        refresh_token: RefreshToken,
        scopes: list[str],
    ) -> OAuthToken:
        now = self.clock()
        token_hash = hash_token(refresh_token.token)
        record = await self._db(self.store.get_refresh_token, token_hash)
        if record is None or not await self._db(self.store.consume_refresh_token, token_hash, now):
            if record is not None:
                await self._db(self.store.revoke_family, record.family_id, now)
            raise TokenError("invalid_grant", "El token de refresco ya no es válido.")
        logger.info("Refresco: client_id=%s cadena=%s", client.client_id[:8], record.family_id[:8])
        return await self._issue_pair(client.client_id, record.family_id, tuple(scopes), now)

    async def load_access_token(self, token: str) -> AccessToken | None:
        record = await self._db(self.store.get_access_token, hash_token(token))
        if record is None or record.revoked_at is not None or record.expires_at <= self.clock():
            return None
        return AccessToken(
            token=token,
            client_id=record.client_id,
            scopes=list(record.scopes),
            expires_at=int(record.expires_at),
            resource=record.resource,
            subject=OWNER_SUBJECT,
        )

    async def revoke_token(self, token: AccessToken | RefreshToken) -> None:
        token_hash = hash_token(token.token)
        record = await self._db(self.store.get_access_token, token_hash) or await self._db(
            self.store.get_refresh_token, token_hash
        )
        if record is not None:
            await self._db(self.store.revoke_family, record.family_id, self.clock())
            logger.info(
                "Revocación: cadena %s (client_id=%s)", record.family_id[:8], record.client_id[:8]
            )
