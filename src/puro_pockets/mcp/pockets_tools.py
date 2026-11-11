"""Tools de bolsas flexibles y metas (Hito 7). Contrato: specs/007-bolsas-metas/contracts/tools.md.

Delgadas: pasan la entrada al servicio y devuelven sus modelos. La app calcula y valida; Claude
propone con una explicación breve; el propietario aprueba de forma explícita (principio 3.1). Los
errores llegan como is_error en español, sin montos ni nombres de metas. Bolsas por nombre; metas
por referencia M-n.
"""

from __future__ import annotations

from typing import Annotated, Literal

from mcp.server.mcpserver import MCPServer
from pydantic import BaseModel, Field

from puro_pockets.mcp.inputs import (
    OPERATION_DESCRIPTION,
    OptionalWholeNumberInput,
    WholeNumberInput,
    domain_errors,
)
from puro_pockets.services.flex import ArchivePocketResult, CreatePocketResult, RebalanceResult
from puro_pockets.services.goals import GoalResult, GoalsProgressResult
from puro_pockets.services.ledger import LedgerService

StrategyName = Literal["proporcional", "desde_una_bolsa", "manual"]
STRATEGY = Field(
    default="proporcional",
    description="proporcional (todas cambian en proporción; la última absorbe el residuo, RN-14), "
    "desde_una_bolsa (solo una cede o recibe) o manual (reparto completo en percentages).",
)


class PocketShare(BaseModel):
    pocket: str = Field(description="Nombre de la bolsa (sin distinguir mayúsculas).")
    percentage: WholeNumberInput = Field(description="Porcentaje entero entre 0 y 100.")


Shares = Annotated[
    list[PocketShare] | None,
    Field(
        description="Solo con manual: el reparto completo resultante (todas las bolsas activas, "
        "incluida la nueva al crear); enteros que suman exactamente 100 (RN-01)."
    ),
]
PocketName = Annotated[str, Field(description="Nombre de la bolsa (sin distinguir mayúsculas).")]
GoalReference = Annotated[str, Field(description="Referencia de la meta (M-n).")]
GoalName = Annotated[str, Field(description="Nombre de la meta, hasta 60 caracteres.")]
OperationId = Annotated[str, Field(description=OPERATION_DESCRIPTION)]
TargetAmount = Annotated[WholeNumberInput, Field(description="Monto objetivo en colones (RN-19).")]


def _pairs(shares: list[PocketShare] | None) -> list[tuple[object, object]] | None:
    return None if shares is None else [(s.pocket, s.percentage) for s in shares]


def register_pockets_tools(server: MCPServer, service: LedgerService) -> None:
    @server.tool()
    @domain_errors
    async def preview_rebalance(
        strategy: StrategyName = STRATEGY,
        new_pocket: str | None = Field(
            default=None, description="Para crear: nombre de la bolsa nueva."
        ),
        new_percentage: OptionalWholeNumberInput = None,
        archive_pocket: str | None = Field(
            default=None, description="Para archivar: nombre de la bolsa a archivar."
        ),
        from_pocket: str | None = Field(
            default=None,
            description="Con desde_una_bolsa: la bolsa que cede (crear) o recibe (archivar).",
        ),
        percentages: Shares = None,
        month: str | None = Field(
            default=None,
            description="AAAA-MM. Crear: por defecto el mes siguiente (RN-15); nunca un mes "
            "pasado. Archivar: siempre el mes actual.",
        ),
    ) -> RebalanceResult:
        """Calcula cómo quedarían los porcentajes al crear o archivar una bolsa (RN-13, RN-14,
        RN-17), con los anteriores y los nuevos de cada mes afectado. No guarda nada."""
        return await service.preview_rebalance(
            strategy,
            new_pocket,
            new_percentage,
            archive_pocket,
            from_pocket,
            _pairs(percentages),
            month,
        )

    @server.tool()
    @domain_errors
    async def create_bolsa(
        name: str = Field(description="Nombre único (sin distinguir mayúsculas), hasta 40."),
        behavior: Literal["consumo", "acumulable"] = Field(
            description="consumo (gastos; empieza cada mes en cero) o acumulable (guarda saldo)."
        ),
        percentage: OptionalWholeNumberInput = None,
        strategy: StrategyName = STRATEGY,
        from_pocket: str | None = Field(
            default=None, description="Con desde_una_bolsa: la bolsa que cede el porcentaje."
        ),
        percentages: Shares = None,
        group: str | None = Field(
            default=None, description="Grupo opcional, solo para estadísticas."
        ),
        month: str | None = Field(
            default=None,
            description="Mes desde el que aplican los porcentajes: por defecto el siguiente "
            "(RN-15); el actual si se pide; nunca uno pasado.",
        ),
        confirm: bool = Field(
            default=False, description="false: vista previa con preview_token; true: crear."
        ),
        operation_id: str | None = Field(
            default=None, description=f"Obligatoria con confirm=true. {OPERATION_DESCRIPTION}"
        ),
        preview_token: str | None = Field(
            default=None, description="Obligatorio con confirm=true: el de la vista previa."
        ),
    ) -> CreatePocketResult:
        """Crea una bolsa y reajusta los porcentajes del mes en una sola operación atómica
        (RN-13): o todo o nada. `percentage` es el de la bolsa nueva (no hace falta con manual).
        Los repartos ya guardados no cambian

        Flujo: pide la vista previa (confirm=false), explica el cambio en pocas palabras, espera la
        aprobación EXPLÍCITA del propietario y solo entonces repite con confirm=true, el
        preview_token y un operation_id nuevo.
        """
        return await service.create_bolsa(
            name,
            behavior,
            percentage,
            strategy,
            from_pocket,
            _pairs(percentages),
            group,
            month,
            confirm,
            operation_id,
            preview_token,
        )

    @server.tool()
    @domain_errors
    async def archive_bolsa(
        name: PocketName,
        strategy: StrategyName = STRATEGY,
        to_pocket: str | None = Field(
            default=None, description="Con desde_una_bolsa: la bolsa que recibe el porcentaje."
        ),
        percentages: Shares = None,
        month: str | None = Field(
            default=None, description="Solo el mes actual (archivar es inmediato)."
        ),
        confirm: bool = Field(
            default=False, description="false: vista previa con preview_token; true: archivar."
        ),
        operation_id: str | None = Field(
            default=None, description=f"Obligatoria con confirm=true. {OPERATION_DESCRIPTION}"
        ),
        preview_token: str | None = Field(
            default=None, description="Obligatorio con confirm=true: el de la vista previa."
        ),
    ) -> ArchivePocketResult:
        """Archiva una bolsa (nunca se borra, RN-16) solo si su saldo (acumulable) o disponible
        del mes (consumo) es cero (RN-18). Redistribuye su porcentaje en el mes actual y en los
        meses futuros con porcentajes propios (RN-17); sus metas se archivan con ella. Una bolsa
        archivada no recibe gastos ni repartos y no se reactiva. Para vaciarla hará falta una
        transferencia (Hito 8)

        Flujo: pide la vista previa (confirm=false), explica el cambio en pocas palabras, espera la
        aprobación EXPLÍCITA del propietario y solo entonces repite con confirm=true, el
        preview_token y un operation_id nuevo.
        """
        return await service.archive_bolsa(
            name,
            strategy,
            to_pocket,
            _pairs(percentages),
            month,
            confirm,
            operation_id,
            preview_token,
        )

    @server.tool()
    @domain_errors
    async def create_goal(
        pocket: PocketName,
        name: GoalName,
        target_amount: TargetAmount,
        operation_id: OperationId,
        target_date: str | None = Field(
            default=None, description="Fecha objetivo AAAA-MM-DD opcional (RN-20); no pasada."
        ),
    ) -> GoalResult:
        """Crea una meta de ahorro en una bolsa acumulable activa (RN-21); una sola meta activa por
        bolsa (RN-22). La meta no tiene dinero propio: su avance es el saldo de la bolsa (RN-23) y
        crearla no mueve ningún saldo. Si el saldo ya alcanza el objetivo, queda lograda.

        Antes de crearla, confirma con el propietario la bolsa, el nombre y el monto."""
        return await service.create_goal(pocket, name, target_amount, operation_id, target_date)

    @server.tool()
    @domain_errors
    async def get_goal_progress(
        pocket: str | None = Field(
            default=None,
            description="Bolsa (opcional): sus metas. Sin ella, todas las metas activas.",
        ),
    ) -> GoalsProgressResult:
        """Avance de las metas: saldo de la bolsa, objetivo, % (tope 100), faltante, excedente,
        estado y fecha de logro. Incluye el promedio mensual de variación neta del saldo de los
        últimos 3 meses completos (RN-28): con esos números TÚ (Claude) puedes estimar una fecha si
        projectable es true; la app no estima. El excedente se queda en la bolsa; puedes sugerir qué
        hacer con él, siempre con confirmación (RN-29). No guarda nada."""
        return await service.get_goal_progress(pocket)

    @server.tool()
    @domain_errors
    async def update_goal(
        goal: GoalReference,
        operation_id: str = Field(description=OPERATION_DESCRIPTION),
        target_amount: OptionalWholeNumberInput = None,
        target_date: str | None = Field(
            default=None, description="Nueva fecha objetivo AAAA-MM-DD (no pasada)."
        ),
        clear_target_date: bool = Field(default=False, description="Quitar la fecha objetivo."),
        action: Literal["pausar", "reactivar"] | None = Field(
            default=None, description="pausar una activa o reactivar una pausada."
        ),
    ) -> GoalResult:
        """Cambia el monto o la fecha de una meta, o la pausa o reactiva. Reactivar se rechaza si
        la bolsa ya tiene otra meta activa (RN-22). Una meta lograda no cambia ni se reactiva
        (RN-24). No mueve ningún saldo. Confirma el cambio con el propietario antes de pedirlo."""
        return await service.update_goal(
            goal, operation_id, target_amount, target_date, clear_target_date, action
        )
