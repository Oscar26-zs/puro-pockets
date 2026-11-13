"""Sesión del dashboard: cookie firmada con HMAC-SHA256, sin tablas (Hito 10).

El valor es `base64url(json{sid, exp}).base64url(firma)`. La firma usa `DASHBOARD_SESSION_SECRET`;
se compara en tiempo constante. Cerrar sesión revoca el `sid` en memoria hasta que vence (un
reinicio olvida las revocaciones; rotar el secreto invalida todas las sesiones) [PROPUESTO].
La cookie no lleva datos financieros ni del propietario.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import secrets
import time
from collections.abc import Callable
from dataclasses import dataclass, field

COOKIE_NAME = "pp_session"


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


@dataclass
class SessionManager:
    secret: bytes
    ttl_seconds: int
    clock: Callable[[], float] = time.time
    _revoked: dict[str, float] = field(default_factory=dict)

    def _sign(self, payload: str) -> str:
        return _b64(hmac.new(self.secret, payload.encode("ascii"), hashlib.sha256).digest())

    def issue(self) -> str:
        body = {"sid": secrets.token_hex(16), "exp": int(self.clock()) + self.ttl_seconds}
        payload = _b64(json.dumps(body, separators=(",", ":")).encode("utf-8"))
        return f"{payload}.{self._sign(payload)}"

    def _claims(self, token: str | None) -> dict | None:
        if not token or token.count(".") != 1:
            return None
        payload, signature = token.split(".")
        if not hmac.compare_digest(signature, self._sign(payload)):
            return None
        try:
            claims = json.loads(_unb64(payload))
        except (ValueError, binascii.Error, UnicodeDecodeError):
            return None
        if not isinstance(claims, dict):
            return None
        sid, exp = claims.get("sid"), claims.get("exp")
        if not isinstance(sid, str) or not isinstance(exp, int) or isinstance(exp, bool):
            return None
        if exp <= self.clock() or sid in self._revoked:
            return None
        return claims

    def valid(self, token: str | None) -> bool:
        return self._claims(token) is not None

    def revoke(self, token: str | None) -> None:
        claims = self._claims(token)
        now = self.clock()
        self._revoked = {sid: exp for sid, exp in self._revoked.items() if exp > now}
        if claims is not None:
            self._revoked[claims["sid"]] = claims["exp"]
