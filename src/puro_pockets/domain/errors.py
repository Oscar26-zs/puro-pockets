"""Errores de las reglas de negocio. Los mensajes van en español y nunca incluyen montos."""

from __future__ import annotations


class DomainError(Exception):
    """Una regla de negocio rechazó la operación; no se guardó nada."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class InitialBalanceAlreadyLoaded(DomainError):
    """RN-54: el saldo inicial se carga una sola vez."""

    def __init__(self) -> None:
        super().__init__("El saldo inicial ya fue cargado; solo se carga una vez.")
