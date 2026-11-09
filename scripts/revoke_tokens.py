"""Revoca TODOS los tokens de acceso y de refresco emitidos (corta el acceso de cualquier conector).

Uso (en el homelab): docker compose exec mcp python scripts/revoke_tokens.py --yes
Después, el conector de claude.ai pedirá iniciar sesión de nuevo.
"""

from __future__ import annotations

import argparse
import sys
import time

from puro_pockets.config import ConfigError, load_settings
from puro_pockets.db.engine import create_engine_from_settings
from puro_pockets.db.oauth_store import SqlOAuthStore


def main() -> int:
    parser = argparse.ArgumentParser(description="Revoca todos los tokens OAuth emitidos.")
    parser.add_argument("--yes", action="store_true", help="confirmar la revocación")
    args = parser.parse_args()
    if not args.yes:
        print("Esto revoca todos los tokens. Repite con --yes para confirmar.", file=sys.stderr)
        return 1
    try:
        settings = load_settings()
    except ConfigError as exc:
        print(f"Error de configuración: {exc}", file=sys.stderr)
        return 1
    engine = create_engine_from_settings(settings)
    revoked = SqlOAuthStore(engine).revoke_all(time.time())
    engine.dispose()
    print(f"Tokens revocados: {revoked}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
