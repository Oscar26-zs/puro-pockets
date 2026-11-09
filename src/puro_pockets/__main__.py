"""Punto de entrada: `python -m puro_pockets` arranca el servidor MCP (Streamable HTTP)."""

from __future__ import annotations

import logging
import sys
from functools import partial

from puro_pockets.config import ConfigError, load_settings
from puro_pockets.db.engine import check_database, create_engine_from_settings
from puro_pockets.mcp.server import build_server, run_server
from puro_pockets.services.health import HealthService


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    try:
        settings = load_settings()
    except ConfigError as exc:
        print(f"Error de configuración: {exc}", file=sys.stderr)
        sys.exit(1)

    engine = create_engine_from_settings(settings)
    # Límite total de la comprobación: tiempo de conexión + 1 s de margen (ping < 5 s)
    health = HealthService(
        partial(check_database, engine), timeout_seconds=settings.db_connect_timeout + 1
    )
    run_server(build_server(health), settings)


if __name__ == "__main__":
    main()
