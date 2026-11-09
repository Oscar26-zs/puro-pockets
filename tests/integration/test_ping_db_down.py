"""Base inalcanzable con el driver real: error estructurado en menos de 5 s (T016, FR-007)."""

import time
from functools import partial

import pytest

from puro_pockets.config import Settings
from puro_pockets.db.engine import check_database, create_engine_from_settings
from puro_pockets.services.health import HealthService

pytestmark = [pytest.mark.integration, pytest.mark.anyio]

# Puerto 1 en 127.0.0.1: nadie escucha ahí
UNREACHABLE_URL = "postgresql+psycopg://usuario-secreto:clave-secreta@127.0.0.1:1/puro_pockets"


async def test_base_inalcanzable_responde_error_rapido_y_sin_datos_internos():
    settings = Settings(database_url=UNREACHABLE_URL, db_connect_timeout=2)
    engine = create_engine_from_settings(settings)
    service = HealthService(partial(check_database, engine), timeout_seconds=3)

    start = time.monotonic()
    status = await service.check()
    elapsed = time.monotonic() - start
    engine.dispose()

    assert status.server == "ok"
    assert status.database == "error"
    assert elapsed < 5
    assert status.detail
    for secreto in ("usuario-secreto", "clave-secreta", "127.0.0.1", "psycopg"):
        assert secreto not in status.detail
