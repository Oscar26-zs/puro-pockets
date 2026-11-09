"""Página de inicio de sesión del propietario (paso interactivo del flujo OAuth)."""

from __future__ import annotations

import html
import logging
import time
from collections.abc import Awaitable, Callable
from urllib.parse import urlsplit

from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse, Response

from puro_pockets.domain.auth import LoginRateLimiter
from puro_pockets.services.oauth import OwnerOAuthProvider, PendingAuthorization
from puro_pockets.services.passwords import PasswordVerifier

logger = logging.getLogger("puro_pockets.auth")


def client_ip(request: Request) -> str:
    """IP real del visitante: Cloudflare la envía en CF-Connecting-IP."""
    return request.headers.get("cf-connecting-ip") or (
        request.client.host if request.client else "desconocida"
    )


def _security_headers(allowed_redirect_uris: tuple[str, ...]) -> dict[str, str]:
    # form-action también controla la redirección posterior al envío: se permiten los orígenes de
    # retorno de la lista blanca
    origins = sorted(
        {f"{urlsplit(u).scheme}://{urlsplit(u).netloc}" for u in allowed_redirect_uris}
    )
    return {
        "Cache-Control": "no-store",
        "X-Frame-Options": "DENY",
        "Referrer-Policy": "no-referrer",
        "X-Content-Type-Options": "nosniff",
        "Content-Security-Policy": (
            "default-src 'none'; style-src 'unsafe-inline'; frame-ancestors 'none'; "
            f"form-action 'self' {' '.join(origins)}"
        ),
    }


def _page(title: str, body: str) -> str:
    return f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)} · Puro Pockets</title>
<style>
body{{font-family:system-ui,sans-serif;background:#f6f7f9;color:#1d2228;margin:0;padding:16px}}
main{{max-width:380px;margin:48px auto;background:#fff;border:1px solid #dde1e6;border-radius:10px;
padding:24px}}
h1{{font-size:1.25rem;margin:0 0 12px}} p{{line-height:1.45}}
.dest{{background:#eef4ff;border:1px solid #c9dafc;border-radius:8px;padding:10px 12px}}
label{{display:block;margin:16px 0 6px;font-weight:600}}
input[type=password]{{width:100%;box-sizing:border-box;padding:10px;font-size:1rem;
border:1px solid #b9c0c8;border-radius:6px}}
button{{margin-top:16px;width:100%;padding:10px;font-size:1rem;border:0;border-radius:6px;
background:#1f5fd6;color:#fff;cursor:pointer}}
.error{{color:#b3261e;font-weight:600}}
@media (prefers-color-scheme: dark){{body{{background:#111418;color:#e6e8eb}}
main{{background:#1a1e23;border-color:#2c323a}} .dest{{background:#16233a;border-color:#2a4069}}
input[type=password]{{background:#0f1215;color:#e6e8eb;border-color:#3a414a}}}}
</style></head><body><main>{body}</main></body></html>"""


def _form(pending: PendingAuthorization, request_id: str, error: str | None) -> str:
    client = html.escape(pending.client_name or "Cliente MCP")
    domain = html.escape(pending.redirect_domain)
    error_html = f'<p class="error">{html.escape(error)}</p>' if error else ""
    return _page(
        "Iniciar sesión",
        f"""<h1>Puro Pockets</h1>
<p><strong>{client}</strong> pide acceso a tu servidor MCP.</p>
<p class="dest">Al aceptar volverás a: <strong>{domain}</strong></p>
{error_html}
<form method="post" action="/login" autocomplete="off">
<input type="hidden" name="request" value="{html.escape(request_id)}">
<label for="password">Contraseña del propietario</label>
<input id="password" name="password" type="password" required autofocus>
<button type="submit">Iniciar sesión y permitir</button>
</form>""",
    )


def build_login_handler(
    provider: OwnerOAuthProvider,
    verifier: PasswordVerifier,
    limiter: LoginRateLimiter,
    clock: Callable[[], float] = time.time,
) -> Callable[[Request], Awaitable[Response]]:
    headers = _security_headers(provider.config.allowed_redirect_uris)

    def respond(title: str, message: str, status: int) -> Response:
        body = f"<h1>{html.escape(title)}</h1><p>{html.escape(message)}</p>"
        return HTMLResponse(_page(title, body), status_code=status, headers=headers)

    expired = (
        "Solicitud vencida",
        "La solicitud de inicio de sesión venció o no existe. "
        "Vuelve a Claude e inténtalo de nuevo.",
    )

    async def login(request: Request) -> Response:
        if request.method == "GET":
            request_id = request.query_params.get("request", "")
            pending = provider.get_pending(request_id)
            if pending is None:
                return respond(*expired, 400)
            return HTMLResponse(_form(pending, request_id, None), headers=headers)

        form = await request.form()
        request_id = str(form.get("request", ""))
        password = str(form.get("password", ""))
        ip = client_ip(request)
        now = clock()

        wait = limiter.retry_after(ip, now)
        if wait > 0:
            logger.warning("Inicio de sesión bloqueado por intentos: ip=%s", ip)
            minutes = max(1, round(wait / 60))
            return respond(
                "Demasiados intentos",
                f"Espera unos {minutes} minutos antes de volver a intentarlo.",
                429,
            )
        pending = provider.get_pending(request_id)
        if pending is None:
            return respond(*expired, 400)
        if not verifier.enabled:
            logger.error("Inicio de sesión deshabilitado: falta OWNER_PASSWORD_HASH válido")
            return respond(
                "Inicio de sesión deshabilitado",
                "El servidor no tiene configurada la contraseña del propietario "
                "(OWNER_PASSWORD_HASH).",
                503,
            )

        ok = await verifier.verify(password)
        del password  # no se conserva en memoria más de lo necesario
        if not ok:
            limiter.record_failure(ip, now)
            logger.warning(
                "Inicio de sesión fallido: ip=%s retorno=%s", ip, pending.redirect_domain
            )
            return HTMLResponse(
                _form(pending, request_id, "Contraseña incorrecta."),
                status_code=401,
                headers=headers,
            )

        limiter.record_success(ip)
        logger.info(
            "Inicio de sesión correcto: ip=%s client_id=%s retorno=%s",
            ip,
            pending.client_id,
            pending.redirect_domain,
        )
        return RedirectResponse(
            await provider.complete_authorization(request_id), status_code=302, headers=headers
        )

    return login
