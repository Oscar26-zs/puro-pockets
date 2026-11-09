"""Caso de uso: comprobar el estado del servidor y de la base de datos."""

from __future__ import annotations

import logging
from collections.abc import Callable

import anyio

from puro_pockets.domain.health import HealthStatus

logger = logging.getLogger(__name__)

# Mensajes fijos: nunca se devuelve el texto de la excepción (puede contener datos de conexión)
CONNECTION_ERROR_MESSAGE = "No se pudo conectar con la base de datos."
TIMEOUT_MESSAGE = "La base de datos no respondió a tiempo."


class HealthService:
    """Comprueba la base con un tiempo límite total y arma el estado de salud."""

    def __init__(self, checker: Callable[[], None], timeout_seconds: float) -> None:
        self._checker = checker
        self._timeout_seconds = timeout_seconds

    async def check(self) -> HealthStatus:
        try:
            with anyio.fail_after(self._timeout_seconds):
                # La comprobación es bloqueante (driver síncrono): corre en un hilo
                await anyio.to_thread.run_sync(self._checker, abandon_on_cancel=True)
        except TimeoutError:
            logger.warning("La comprobación de la base superó %s s", self._timeout_seconds)
            return HealthStatus.database_error(TIMEOUT_MESSAGE)
        except Exception as exc:  # noqa: BLE001 - cualquier falla de la base se informa igual
            logger.warning("La comprobación de la base falló: %s", type(exc).__name__)
            return HealthStatus.database_error(CONNECTION_ERROR_MESSAGE)
        return HealthStatus.database_ok()
