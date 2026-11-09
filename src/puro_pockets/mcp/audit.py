"""Auditoría de rechazos en los endpoints OAuth (sin secretos).

El SDK rechaza muchas peticiones de /register, /authorize, /token y /revoke antes de llegar a
nuestro proveedor (validación de metadatos, scopes, URL de retorno, PKCE…) y no deja registro. Este
middleware ASGI observa la respuesta y, si es un rechazo, registra en INFO el motivo exacto que
devolvió el SDK y datos no sensibles de la petición (8 primeros caracteres del client_id, nombre del
cliente, dominios de retorno, método de autenticación y scopes pedidos). Nunca registra contraseñas,
códigos, tokens, verificadores PKCE ni secretos.
"""

from __future__ import annotations

import json
import logging
from typing import Any
from urllib.parse import parse_qs, urlsplit

from starlette.types import ASGIApp, Message, Receive, Scope, Send

logger = logging.getLogger("puro_pockets.auth")

AUDITED_PATHS = {"/register", "/authorize", "/token", "/revoke"}
MAX_CAPTURE = 64 * 1024


def short_id(client_id: str | None) -> str:
    return (client_id or "")[:8] or "-"


def _redact(text: str, client_id: str | None) -> str:
    """Acorta el client_id completo si aparece en un mensaje de error."""
    if client_id and len(client_id) > 8:
        text = text.replace(client_id, short_id(client_id) + "…")
    return text


def _request_summary(path: str, query: str, body: bytes, content_type: str) -> dict[str, Any]:
    """Datos no sensibles de la petición, para entender el rechazo."""
    summary: dict[str, Any] = {}
    params: dict[str, str] = {k: v[0] for k, v in parse_qs(query).items()}
    if body and "application/x-www-form-urlencoded" in content_type:
        params.update({k: v[0] for k, v in parse_qs(body.decode(errors="replace")).items()})
    if path == "/register" and body:
        try:
            data = json.loads(body)
        except ValueError:
            return {"cuerpo": "JSON inválido"}
        if isinstance(data, dict):
            uris = data.get("redirect_uris") or []
            summary["client_name"] = data.get("client_name")
            summary["retorno"] = sorted(
                {urlsplit(str(u)).hostname or "?" for u in uris if isinstance(u, str)}
            )
            summary["auth_method"] = data.get("token_endpoint_auth_method")
            summary["scope"] = data.get("scope")
            summary["grant_types"] = data.get("grant_types")
            summary["response_types"] = data.get("response_types")
            summary["application_type"] = data.get("application_type")
        return summary
    summary["client_id"] = short_id(params.get("client_id"))
    if path == "/authorize":
        redirect = params.get("redirect_uri")
        summary["retorno"] = urlsplit(redirect).hostname if redirect else None
        summary["scope"] = params.get("scope")
        summary["resource"] = params.get("resource")
        summary["pkce"] = params.get("code_challenge_method")
    if path == "/token":
        summary["grant_type"] = params.get("grant_type")
    return summary


class OAuthAuditMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["path"] not in AUDITED_PATHS:
            await self.app(scope, receive, send)
            return

        body = bytearray()
        status = 0
        location = ""
        response_body = bytearray()

        async def receive_wrapper() -> Message:
            message = await receive()
            if message["type"] == "http.request" and len(body) < MAX_CAPTURE:
                body.extend(message.get("body", b"")[: MAX_CAPTURE - len(body)])
            return message

        async def send_wrapper(message: Message) -> None:
            nonlocal status, location
            if message["type"] == "http.response.start":
                status = message["status"]
                for key, value in message.get("headers", []):
                    if key.lower() == b"location":
                        location = value.decode(errors="replace")
            elif message["type"] == "http.response.body" and status >= 400:
                if len(response_body) < MAX_CAPTURE:
                    response_body.extend(message.get("body", b""))
            await send(message)

        await self.app(scope, receive_wrapper, send_wrapper)

        try:
            self._log(scope, bytes(body), status, location, bytes(response_body))
        except Exception:  # noqa: BLE001 - la auditoría nunca debe romper la respuesta
            logger.exception("Fallo al auditar %s", scope["path"])

    def _log(
        self, scope: Scope, body: bytes, status: int, location: str, response_body: bytes
    ) -> None:
        path = scope["path"]
        query = scope.get("query_string", b"").decode(errors="replace")
        headers = {k.decode().lower(): v.decode(errors="replace") for k, v in scope["headers"]}
        error = description = None

        if status >= 400:
            try:
                data = json.loads(response_body) if response_body else {}
            except ValueError:
                data = {}
            error = data.get("error") if isinstance(data, dict) else None
            description = data.get("error_description") if isinstance(data, dict) else None
            if error is None:
                error = f"HTTP {status}"
        elif path == "/authorize" and status in (302, 303) and "error=" in location:
            # Rechazo devuelto al cliente por redirección (p. ej. invalid_scope)
            qs = parse_qs(urlsplit(location).query)
            error = qs.get("error", [None])[0]
            description = qs.get("error_description", [None])[0]
        else:
            return

        summary = _request_summary(path, query, body, headers.get("content-type", ""))
        client_id = parse_qs(query).get("client_id", [None])[0]
        logger.info(
            "Rechazo en %s: HTTP %s error=%s motivo=%r petición=%s",
            path,
            status,
            error,
            _redact(description or "", client_id) or None,
            summary,
        )
