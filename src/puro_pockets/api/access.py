"""Verificación del token de Cloudflare Access (Hito 10, publicación por Cloudflare).

Cuando el dashboard se publica en un nombre propio (p. ej. `dash.puropockets.space`) por el túnel,
Cloudflare Access exige identidad antes de dejar pasar la petición y agrega un JWT firmado
(`Cf-Access-Jwt-Assertion`, también en la cookie `CF_Authorization`). El dashboard no confía en que
Access esté bien configurado: verifica la firma RS256 con las claves públicas del equipo, la
audiencia (AUD de la aplicación), el emisor y el vencimiento. Sin token válido → 403.

Las claves se descargan de `https://<equipo>.cloudflareaccess.com/cdn-cgi/access/certs` y se
guardan en caché. Si no se pueden obtener, se rechaza (falla cerrada). Los registros nunca incluyen
el token ni el correo.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

import anyio
import jwt

logger = logging.getLogger("puro_pockets.api")

ACCESS_HEADER = "cf-access-jwt-assertion"
ACCESS_COOKIE = "CF_Authorization"

# Recibe el token sin verificar y devuelve la clave pública con que se firmó
KeyProvider = Callable[[str], object]


def jwks_key_provider(team_domain: str) -> KeyProvider:
    client = jwt.PyJWKClient(
        f"https://{team_domain}/cdn-cgi/access/certs", cache_keys=True, lifespan=3600, timeout=5
    )
    return lambda token: client.get_signing_key_from_jwt(token).key


class AccessVerifier:
    def __init__(
        self, team_domain: str, audience: str, key_provider: KeyProvider | None = None
    ) -> None:
        self.issuer = f"https://{team_domain}"
        self.audience = audience
        self._keys = key_provider or jwks_key_provider(team_domain)

    def _verify(self, token: str) -> bool:
        try:
            jwt.decode(
                token,
                self._keys(token),
                algorithms=["RS256"],
                audience=self.audience,
                issuer=self.issuer,
                options={"require": ["exp", "iat", "aud", "iss"]},
            )
        except jwt.PyJWTError as exc:
            logger.warning("Token de Cloudflare Access rechazado: %s", type(exc).__name__)
            return False
        except Exception as exc:  # noqa: BLE001 - sin claves no se deja pasar (falla cerrada)
            logger.error("No se pudo verificar Cloudflare Access: %s", type(exc).__name__)
            return False
        return True

    async def verify(self, token: str | None) -> bool:
        if not token:
            return False
        return await anyio.to_thread.run_sync(self._verify, token)
