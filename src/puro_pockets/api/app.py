"""API del dashboard (Hito 10): FastAPI de solo lectura y el frontend compilado.

- Solo `GET`, salvo `POST /api/session/login` y `POST /api/session/logout`; otro verbo → 405.
- Sin sesión, todo `/api` responde 401 (también las rutas que no existen, para no revelarlas).
- Cabeceras de seguridad en todas las respuestas y `Cache-Control: no-store` en `/api`. Sin CORS.
- Registros: método, ruta sin consulta, estado y duración. Nunca montos, notas, descripciones ni
  nombres de metas (la consulta puede llevar nombres de bolsa, por eso no se registra).
- Las cifras salen de `DashboardService`, que reutiliza `LedgerService` (las mismas de las tools).
"""

from __future__ import annotations

import logging
import math
import time
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Literal

import anyio
from fastapi import FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

from puro_pockets.api.session import COOKIE_NAME, SessionManager
from puro_pockets.domain.auth import LoginRateLimiter
from puro_pockets.domain.errors import DomainError
from puro_pockets.services.dashboard import (
    CategoriesOut,
    DashboardService,
    FixedOut,
    HistoryOut,
    MovementsOut,
    PendingClosuresOut,
    PocketsOut,
    SummaryOut,
)
from puro_pockets.services.passwords import PasswordVerifier

logger = logging.getLogger("puro_pockets.api")

LOGIN_PATH = "/api/session/login"
LOGOUT_PATH = "/api/session/logout"
POST_PATHS = frozenset({LOGIN_PATH, LOGOUT_PATH})

CONTENT_SECURITY_POLICY = (
    "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
    "script-src 'self'; connect-src 'self'; font-src 'self'; object-src 'none'; "
    "base-uri 'none'; form-action 'self'; frame-ancestors 'none'"
)
SECURITY_HEADERS = {
    "Content-Security-Policy": CONTENT_SECURITY_POLICY,
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "X-Frame-Options": "DENY",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=(), interest-cohort=()",
}

MonthParam = Query(default=None, description="Mes AAAA-MM; por defecto el actual.")


class LoginBody(BaseModel):
    password: str


class SessionOut(BaseModel):
    current_month: str


def _is_api(path: str) -> bool:
    return path == "/api" or path.startswith("/api/")


def _error(status: int, detail: str, headers: dict[str, str] | None = None) -> JSONResponse:
    return JSONResponse({"detail": detail}, status_code=status, headers=headers)


def build_app(
    service: DashboardService,
    sessions: SessionManager,
    verifier: PasswordVerifier,
    limiter: LoginRateLimiter,
    *,
    cookie_secure: bool = True,
    static_dir: Path | None = None,
    health: Callable[[], None] | None = None,
    clock: Callable[[], float] = time.monotonic,
) -> FastAPI:
    app = FastAPI(
        title="Puro Pockets: dashboard",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )

    # --- Middleware: verbos, sesión, cabeceras y registro ---

    @app.middleware("http")
    async def guard(request: Request, call_next: Callable[[Request], Awaitable[Response]]):
        started = time.perf_counter()
        path, method = request.url.path, request.method
        api = _is_api(path)
        allowed = ("POST",) if path in POST_PATHS else ("GET",)
        if method not in allowed:
            response: Response = _error(405, "Método no permitido.", {"Allow": ", ".join(allowed)})
        elif api and path != LOGIN_PATH and not sessions.valid(request.cookies.get(COOKIE_NAME)):
            response = _error(401, "Inicia sesión para ver el dashboard.")
        else:
            response = await call_next(request)
        for name, value in SECURITY_HEADERS.items():
            response.headers.setdefault(name, value)
        if (
            api
            or path in ("/", "/index.html")
            or response.headers.get("content-type", "").startswith("text/html")
        ):
            response.headers["Cache-Control"] = "no-store"
        elapsed = (time.perf_counter() - started) * 1000
        logger.info("%s %s %s %.0fms", method, path, response.status_code, elapsed)
        return response

    # --- Errores: sin repetir lo que llegó en la petición ---

    @app.exception_handler(DomainError)
    async def domain_error(_request: Request, exc: DomainError) -> JSONResponse:
        return _error(400, exc.message)

    @app.exception_handler(RequestValidationError)
    async def invalid_request(_request: Request, _exc: RequestValidationError) -> JSONResponse:
        return _error(400, "Parámetros inválidos.")

    @app.exception_handler(StarletteHTTPException)
    async def http_error(_request: Request, exc: StarletteHTTPException) -> JSONResponse:
        detail = {404: "No encontrado.", 405: "Método no permitido."}.get(
            exc.status_code, "Solicitud inválida."
        )
        return _error(exc.status_code, detail)

    @app.exception_handler(Exception)
    async def unexpected(_request: Request, exc: Exception) -> JSONResponse:
        # Solo el tipo: el mensaje de un error de la base puede llevar parámetros de la consulta
        logger.error("Error interno del dashboard: %s", type(exc).__name__)
        return _error(500, "No pudimos cargar tus datos.")

    # --- Salud (fuera de /api, sin sesión, sin datos) ---

    @app.get("/healthz", include_in_schema=False)
    async def healthz() -> JSONResponse:
        if health is None:
            return JSONResponse({"status": "ok"})
        try:
            with anyio.fail_after(5):
                await anyio.to_thread.run_sync(health)
        except Exception:  # noqa: BLE001 - cualquier fallo de la base es "no sano"
            return JSONResponse({"status": "error"}, status_code=503)
        return JSONResponse({"status": "ok"})

    # --- Sesión ---

    @app.post(LOGIN_PATH, status_code=204)
    async def login(request: Request) -> Response:
        origin = request.headers.get("origin")
        if origin is not None and origin != f"{request.url.scheme}://{request.url.netloc}":
            return _error(403, "Origen no permitido.")
        if not request.headers.get("content-type", "").startswith("application/json"):
            return _error(400, "Solicitud inválida.")
        key = request.client.host if request.client else "desconocido"
        wait = limiter.retry_after(key, clock())
        if wait > 0:
            logger.warning("Inicio de sesión del dashboard bloqueado por intentos")
            return _error(
                429,
                "Demasiados intentos. Espera unos minutos.",
                {"Retry-After": str(math.ceil(wait))},
            )
        try:
            body = LoginBody.model_validate(await request.json())
        except Exception:  # noqa: BLE001 - cuerpo ilegible: misma respuesta para todo
            return _error(400, "Solicitud inválida.")
        if not await verifier.verify(body.password):
            limiter.record_failure(key, clock())
            logger.warning("Inicio de sesión del dashboard fallido")
            return _error(401, "Contraseña incorrecta.")
        limiter.record_success(key)
        logger.info("Inicio de sesión del dashboard correcto")
        response = Response(status_code=204)
        response.set_cookie(
            COOKIE_NAME,
            sessions.issue(),
            max_age=sessions.ttl_seconds,
            path="/",
            secure=cookie_secure,
            httponly=True,
            samesite="strict",
        )
        return response

    @app.post(LOGOUT_PATH, status_code=204)
    async def logout(request: Request) -> Response:
        sessions.revoke(request.cookies.get(COOKIE_NAME))
        logger.info("Cierre de sesión del dashboard")
        response = Response(status_code=204)
        response.delete_cookie(
            COOKIE_NAME, path="/", secure=cookie_secure, httponly=True, samesite="strict"
        )
        return response

    @app.get("/api/session")
    async def session() -> SessionOut:
        return SessionOut(current_month=str(service.current_month()))

    # --- Datos (solo lectura) ---

    @app.get("/api/summary")
    async def summary(month: str | None = MonthParam) -> SummaryOut:
        return await service.summary(month)

    @app.get("/api/pockets")
    async def pockets(month: str | None = MonthParam) -> PocketsOut:
        return await service.pockets(month)

    @app.get("/api/movements")
    async def movements(
        month: str | None = MonthParam,
        type: Literal["gasto", "ingreso", "transferencia"] | None = None,  # noqa: A002
        pocket: str | None = Query(default=None, max_length=60),
        include_voided: bool = False,
        page: int = Query(default=1, ge=1, le=10),
    ) -> MovementsOut:
        return await service.movements(month, type, pocket, include_voided, page)

    @app.get("/api/categories")
    async def categories(month: str | None = MonthParam) -> CategoriesOut:
        return await service.categories(month)

    @app.get("/api/history")
    async def history(month: str | None = MonthParam) -> HistoryOut:
        return await service.history(month)

    @app.get("/api/fixed")
    async def fixed(month: str | None = MonthParam) -> FixedOut:
        return await service.fixed(month)

    @app.get("/api/closures/pending")
    async def pending_closures() -> PendingClosuresOut:
        return await service.pending_closures()

    # --- Frontend compilado (si existe) ---

    if static_dir is not None and (static_dir / "index.html").is_file():
        root = static_dir.resolve()
        if (root / "assets").is_dir():
            app.mount("/assets", StaticFiles(directory=root / "assets"), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        async def frontend(path: str) -> Response:
            if _is_api("/" + path):
                return _error(404, "No encontrado.")
            candidate = (root / path).resolve()
            if path and candidate.is_file() and candidate.is_relative_to(root):
                return FileResponse(candidate)
            return FileResponse(root / "index.html")  # aplicación de una sola página

    return app
