"""Alternativa al registro dinámico: crea un "cliente propio" para el conector de claude.ai.

Úsalo solo si el registro automático (DCR) falla. Crea un cliente público (sin secreto) con las URL
de retorno de OAUTH_ALLOWED_REDIRECT_URIS e imprime su client_id, que no es secreto. En claude.ai,
al agregar el conector, elige "Use your own OAuth client", pega el client_id y deja el secreto
vacío.

Uso (en el homelab): docker compose exec mcp python scripts/register_client.py
"""

from __future__ import annotations

import sys
import uuid

from mcp.shared.auth import OAuthClientInformationFull
from pydantic import AnyUrl

from puro_pockets.config import ConfigError, load_settings
from puro_pockets.db.engine import create_engine_from_settings
from puro_pockets.db.oauth_store import SqlOAuthStore
from puro_pockets.services.oauth import VALID_SCOPES


def main() -> int:
    try:
        settings = load_settings()
    except ConfigError as exc:
        print(f"Error de configuración: {exc}", file=sys.stderr)
        return 1
    engine = create_engine_from_settings(settings)
    store = SqlOAuthStore(engine)
    if store.count_clients() >= settings.oauth_max_clients:
        print(f"Ya hay {settings.oauth_max_clients} clientes (máximo).", file=sys.stderr)
        return 1
    client = OAuthClientInformationFull(
        client_id=str(uuid.uuid4()),
        client_name="Claude (cliente propio)",
        redirect_uris=[AnyUrl(uri) for uri in settings.oauth_allowed_redirect_uris],
        token_endpoint_auth_method="none",
        grant_types=["authorization_code", "refresh_token"],
        response_types=["code"],
        scope=" ".join(VALID_SCOPES),
    )
    store.save_client(client.client_id, client.model_dump_json())
    engine.dispose()
    print(f"client_id: {client.client_id}")
    print("Retornos permitidos: " + ", ".join(settings.oauth_allowed_redirect_uris))
    return 0


if __name__ == "__main__":
    sys.exit(main())
