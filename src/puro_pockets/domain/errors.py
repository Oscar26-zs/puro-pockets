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


class NotAnExtra(DomainError):
    def __init__(self, reference: str) -> None:
        super().__init__(
            f"{reference} no es un ingreso extra. Solo los extras se reparten con "
            "confirm_allocation."
        )


class ExtraAlreadyDistributed(DomainError):
    """Un extra se reparte una sola vez; corregir es anular y registrar de nuevo (RN-53, RN-59)."""

    def __init__(self, reference: str) -> None:
        super().__init__(
            f"El extra {reference} ya se repartió y no se reparte de nuevo. Para corregirlo, "
            "anúlalo con void_transaction (revierte su reparto) y regístralo otra vez."
        )


class MovementVoided(DomainError):
    def __init__(self, reference: str) -> None:
        super().__init__(f"El movimiento {reference} está anulado.")


class PreviewRequired(DomainError):
    """confirm=true exige la ficha de una vista previa con exactamente esos porcentajes."""

    def __init__(self) -> None:
        super().__init__(
            "Antes de confirmar, pide la vista previa (confirm=false) con estos mismos "
            "porcentajes, muéstrala al propietario y, con su aprobación explícita, confirma con "
            "el preview_token que devuelve."
        )


class RecurringAlreadyPaid(DomainError):
    """Un solo pago vigente por gasto fijo y mes; si se anula, vuelve a quedar pendiente."""

    def __init__(self, reference: str, month: str) -> None:
        super().__init__(
            f"El gasto fijo {reference} ya tiene un pago vigente en {month}. Si ese pago estaba "
            "mal, anúlalo con void_transaction y registra el nuevo."
        )


class RecurringInactive(DomainError):
    def __init__(self, reference: str) -> None:
        super().__init__(f"El gasto fijo {reference} está desactivado: no admite pagos ni cambios.")


class RecurringNameTaken(DomainError):
    def __init__(self) -> None:
        super().__init__(
            "Ya existe un gasto fijo activo con ese nombre (sin distinguir mayúsculas)."
        )
