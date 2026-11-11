"""Errores de las reglas de negocio. Los mensajes van en español y nunca incluyen montos."""

from __future__ import annotations


class DomainError(Exception):
    """Una regla de negocio rechazó la operación; no se guardó nada."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class InitialBalanceAlreadyLoaded(DomainError):
    """RN-54: el saldo inicial se carga una sola vez (salvo que se anule el vigente)."""

    def __init__(self) -> None:
        super().__init__(
            "El saldo inicial ya fue cargado; solo se carga una vez. Si estaba mal, anúlalo con "
            "void_transaction y vuelve a cargarlo."
        )


class IdempotencyConflict(DomainError):
    """La misma clave de operación llegó con otro contenido."""

    def __init__(self) -> None:
        super().__init__(
            "Esa clave de operación (operation_id) ya se usó con otros datos. Para una operación "
            "distinta usa una clave nueva; para reintentar, repite exactamente los mismos datos."
        )


class AlreadyVoided(DomainError):
    """RN-53: un movimiento se anula una sola vez."""

    def __init__(self, reference: str) -> None:
        super().__init__(f"El movimiento {reference} ya está anulado.")


class MovementNotFound(DomainError):
    def __init__(self, reference: str) -> None:
        super().__init__(f"No existe el movimiento {reference}. Revisa la referencia.")


class CategoryAlreadyExists(DomainError):
    def __init__(self, name: str) -> None:
        super().__init__(f"Ya existe una categoría llamada '{name}' (sin distinguir mayúsculas).")
