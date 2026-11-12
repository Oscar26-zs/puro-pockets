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
    """confirm=true exige la ficha de una vista previa con exactamente esos datos."""

    def __init__(self, subject: str = "porcentajes") -> None:
        super().__init__(
            f"Antes de confirmar, pide la vista previa (confirm=false) con estos mismos {subject}, "
            "muéstrala al propietario y, con su aprobación explícita, confirma con el "
            "preview_token que devuelve."
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


class PocketAlreadyExists(DomainError):
    def __init__(self) -> None:
        super().__init__(
            "Ya existe una bolsa con ese nombre (sin distinguir mayúsculas), activa o archivada."
        )


class PocketNotEmpty(DomainError):
    """RN-18: se archiva solo con saldo (acumulable) o disponible del mes (consumo) cero."""

    def __init__(self, kind: str) -> None:
        super().__init__(
            f"No se puede archivar: su {kind} no es cero (RN-18). Primero mueve ese dinero a otra "
            "bolsa con una transferencia (preview_transfer y luego transfer_between_bolsas, motivo "
            "reasignacion); si está en negativo, cúbrela antes con una transferencia hacia ella. "
            "Después vuelve a pedir el archivado."
        )


class GoalNeedsSavingsPocket(DomainError):
    """RN-21: una meta solo se asocia a una bolsa acumulable."""

    def __init__(self) -> None:
        super().__init__(
            "Una meta solo se asocia a una bolsa acumulable (RN-21); esa bolsa es de consumo."
        )


class GoalAlreadyActive(DomainError):
    """RN-22: una sola meta activa por bolsa."""

    def __init__(self, reference: str) -> None:
        super().__init__(
            f"Esa bolsa ya tiene una meta activa ({reference}); una bolsa admite una sola (RN-22). "
            "Pausa esa meta o usa otra bolsa acumulable."
        )


class GoalNotFound(DomainError):
    def __init__(self, reference: str) -> None:
        super().__init__(f"No existe la meta {reference}. Consúltalas con get_goal_progress.")


class GoalClosed(DomainError):
    def __init__(self, reference: str, reason: str) -> None:
        super().__init__(f"La meta {reference} {reason}: no admite cambios.")


class MovementTouchesArchivedPocket(DomainError):
    def __init__(self, reference: str) -> None:
        super().__init__(
            f"El movimiento {reference} afecta a una bolsa archivada: anularlo cambiaría el saldo "
            "de una bolsa que debe quedar en cero (RN-18)."
        )


class TransferSamePocket(DomainError):
    """RN-41: el origen y el destino de una transferencia son distintos."""

    def __init__(self) -> None:
        super().__init__("El origen y el destino de una transferencia deben ser bolsas distintas.")


class TransferExceedsAvailable(DomainError):
    """RN-42: no se mueve más de lo disponible en el origen."""

    def __init__(self, pocket: str, kind: str) -> None:
        super().__init__(
            f"El monto supera el {kind} de la bolsa '{pocket}': no se puede mover más de lo "
            "disponible en el origen (RN-42). Consulta get_bolsa_status y usa un monto menor."
        )


class TransferFromNegative(DomainError):
    """RN-42: una bolsa en negativo no tiene nada disponible para mover."""

    def __init__(self, pocket: str, kind: str) -> None:
        super().__init__(
            f"La bolsa '{pocket}' tiene su {kind} en negativo: no se puede transferir desde ella "
            "(RN-42). Primero cúbrela con una transferencia hacia ella."
        )


class TransfersAreFinal(DomainError):
    """RN-43: las transferencias no se editan ni se borran."""

    def __init__(self, reference: str) -> None:
        super().__init__(
            f"La transferencia {reference} no se anula ni se edita (RN-43). Para corregirla, "
            "registra otra transferencia en sentido contrario."
        )


class MonthClosed(DomainError):
    """RN-44, RN-48, RN-53: un mes cerrado no admite movimientos, repartos, transferencias,
    anulaciones ni cambios de porcentajes."""

    def __init__(self, month: str, earlier: bool = False) -> None:
        why = "es anterior a un mes ya cerrado y cuenta como cerrado" if earlier else "está cerrado"
        super().__init__(
            f"El mes {month} {why}: no admite movimientos nuevos, repartos, transferencias, "
            "anulaciones ni cambios de porcentajes (RN-44, RN-48, RN-53). Un cierre no se reabre; "
            "para corregir, registra una transferencia de ajuste o un movimiento en un mes abierto."
        )


class MonthNotClosable(DomainError):
    """El mes pedido no se puede cerrar ahora (ya cerrado, futuro, antes de su último día o fuera
    de orden)."""

    def __init__(self, month: str, reason: str) -> None:
        super().__init__(f"No se puede cerrar el mes {month}: {reason}")


class ExtrasPendingBlock(DomainError):
    """Un extra pendiente del mes bloquea su cierre (RN-06, RN-09)."""

    def __init__(self, month: str, references: list[str]) -> None:
        refs = ", ".join(references)
        super().__init__(
            f"El mes {month} tiene ingresos extra pendientes de repartir ({refs}). Antes de "
            "cerrarlo, repártelos con confirm_allocation o anúlalos con void_transaction."
        )


class ClosureStateChanged(DomainError):
    """La ficha del cierre ya no corresponde al estado actual."""

    def __init__(self) -> None:
        super().__init__(
            "El estado del mes cambió desde la vista previa (saldos, gastos, transferencias o "
            "metas): repite preview_month_close, muéstrale el resultado al propietario y confirma "
            "con la ficha nueva."
        )


class ClosureProposalInvalid(DomainError):
    """La propuesta de coberturas o destinos no cumple RN-47, RN-52 o la sección 10."""

    def __init__(self, reason: str) -> None:
        super().__init__(f"La propuesta de cierre no es válida: {reason}")
