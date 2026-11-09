"""Verificación de la contraseña del propietario con argon2 (argon2-cffi)."""

from __future__ import annotations

import anyio
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError


class PasswordVerifier:
    """Verifica contra el hash de OWNER_PASSWORD_HASH. Sin hash válido, nadie puede iniciar sesión.

    Los parámetros de argon2 viajan dentro del hash: no hay que configurarlos aquí.
    """

    def __init__(self, password_hash: str | None) -> None:
        self._hasher = PasswordHasher()
        self._hash = (
            password_hash if password_hash and password_hash.startswith("$argon2") else None
        )

    @property
    def enabled(self) -> bool:
        return self._hash is not None

    def _verify(self, password: str) -> bool:
        if self._hash is None:
            return False
        try:
            return self._hasher.verify(self._hash, password)
        except (VerificationError, InvalidHashError):
            return False

    async def verify(self, password: str) -> bool:
        # argon2 es costoso a propósito: corre en un hilo para no bloquear el servidor
        return await anyio.to_thread.run_sync(self._verify, password)
