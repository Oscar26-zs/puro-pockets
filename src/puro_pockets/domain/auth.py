"""Reglas puras de autenticación. Capa de dominio: no depende de MCP ni de la base de datos."""

from __future__ import annotations

import hashlib
from collections import defaultdict, deque
from collections.abc import Iterable
from dataclasses import dataclass, field
from urllib.parse import urlsplit


def hash_token(token: str) -> str:
    """SHA-256 de un código o token. Solo se guarda este valor, nunca el token."""
    return hashlib.sha256(token.encode()).hexdigest()


def redirect_uri_allowed(uri: str, allowlist: Iterable[str]) -> bool:
    """Coincidencia exacta con la lista blanca (sin comodines ni prefijos)."""
    return uri in set(allowlist)


def redirect_domain(uri: str) -> str:
    """Dominio de una URL de retorno, para mostrarlo y registrarlo."""
    return urlsplit(uri).hostname or ""


@dataclass
class LoginRateLimiter:
    """Límite de intentos fallidos de inicio de sesión: por clave (IP) y global.

    - Por IP: `per_key_max` fallos dentro de `window_seconds` bloquean esa IP hasta que salgan de la
      ventana.
    - Global: `global_max` fallos dentro de `window_seconds` (de cualquier IP) bloquean todo el
      inicio de sesión durante `global_lock_seconds`.
    """

    per_key_max: int = 5
    window_seconds: float = 900
    global_max: int = 20
    global_lock_seconds: float = 300
    _per_key: dict[str, deque[float]] = field(default_factory=lambda: defaultdict(deque))
    _global: deque[float] = field(default_factory=deque)
    _global_locked_until: float = 0

    def _trim(self, events: deque[float], now: float) -> None:
        while events and events[0] <= now - self.window_seconds:
            events.popleft()

    def retry_after(self, key: str, now: float) -> float:
        """Segundos que faltan para poder intentar de nuevo (0 si se puede)."""
        if now < self._global_locked_until:
            return self._global_locked_until - now
        events = self._per_key.get(key)
        if events is None:
            return 0
        self._trim(events, now)
        if len(events) >= self.per_key_max:
            return events[0] + self.window_seconds - now
        return 0

    def record_failure(self, key: str, now: float) -> None:
        events = self._per_key[key]
        self._trim(events, now)
        events.append(now)
        self._trim(self._global, now)
        self._global.append(now)
        if len(self._global) >= self.global_max:
            self._global_locked_until = now + self.global_lock_seconds
            self._global.clear()

    def record_success(self, key: str) -> None:
        self._per_key.pop(key, None)


@dataclass
class EventLimiter:
    """Como máximo `max_events` eventos dentro de `window_seconds` (p. ej. registros)."""

    max_events: int
    window_seconds: float
    _events: deque[float] = field(default_factory=deque)

    def allow(self, now: float) -> bool:
        while self._events and self._events[0] <= now - self.window_seconds:
            self._events.popleft()
        if len(self._events) >= self.max_events:
            return False
        self._events.append(now)
        return True
