"""Tools del cierre de mes (Hito 9). Contrato: specs/009-cierre-mes/plan.md ("Contrato de tools").

Delgadas: pasan la entrada al servicio y devuelven sus modelos. La app calcula y valida; Claude
propone coberturas y destinos con una explicación breve; el propietario aprueba de forma explícita
(principio 3.1). Los errores llegan como is_error en español, sin montos, notas ni nombres de metas.
Las coberturas y los destinos llegan sin validar por pydantic (un monto con decimales llegaría como
`float`): el dominio los valida y responde en español.
"""

from __future__ import annotations

from typing import Annotated, Any

from mcp.server.mcpserver import MCPServer
from pydantic import Field, WithJsonSchema

from puro_pockets.mcp.inputs import OPERATION_DESCRIPTION, domain_errors
from puro_pockets.services.closing import MonthCloseResult, SurplusDestinationResult
from puro_pockets.services.ledger import LedgerService


def _moves_schema(target_nullable: bool, description: str) -> dict:
    target: dict = {"type": ["string", "null"] if target_nullable else "string"}
    target["description"] = (
        "Acumulable activa que recibe el sobrante, o null para dejarlo como no destinado."
        if target_nullable
        else "Bolsa de consumo con déficit que se cubre."
    )
    return {
        "type": ["array", "null"],
        "description": description,
        "items": {
            "type": "object",
            "properties": {
                "from_pocket": {"type": "string", "description": "Bolsa de origen."},
                "to_pocket": target,
                "amount": {"type": "integer", "description": "Colones: entero positivo."},
            },
            "required": ["from_pocket", "amount"] + ([] if target_nullable else ["to_pocket"]),
        },
    }


Covers = Annotated[
    Any,
    WithJsonSchema(
        _moves_schema(
            False,
            "Coberturas de déficits (primero, 10.1): desde el sobrante de una bolsa de consumo o, "
            "solo si los sobrantes de consumo ya están usados, desde el saldo de una acumulable "
            "(RN-52, opcional y con aprobación explícita).",
        )
    ),
]
Destinations = Annotated[
    Any,
    WithJsonSchema(
        _moves_schema(
            True,
            "Destinos de sobrantes de consumo (después, 10.2): una acumulable activa o null "
            "(sobrante no destinado). Lo que no se asigne también queda como no destinado.",
        )
    ),
]
MONTH = Field(
    default=None,
    description="Mes AAAA-MM. Si se omite, el más antiguo que falta cerrar.",
)


def register_closing_tools(server: MCPServer, service: LedgerService) -> None:
    @server.tool()
    @domain_errors
    async def preview_month_close(
        month: str | None = MONTH,
        covers: Covers = None,
        destinations: Destinations = None,
    ) -> MonthCloseResult:
        """Vista previa del cierre de un mes, sin guardar nada (principio 3.2).

        Sin covers ni destinations devuelve los datos: por cada bolsa de consumo su sobrante o
        déficit del mes (11.1) y su destino de sobrante sugerido (6.5); por cada acumulable su saldo
        y su meta activa con avance; los extras pendientes del mes (bloquean el cierre) y los gastos
        fijos pendientes (solo aviso). La app no recomienda: tú armas la propuesta.

        Con covers y/o destinations (envía [] para "nada que mover") valida la propuesta (orden
        10.1, RN-47, RN-52) y devuelve cómo queda cada bolsa, el efecto en las metas (RN-58), lo no
        destinado y el sobregasto no cubierto (RN-50), y el preview_token que exige close_month.
        Siempre avisa que, al cerrar, el mes no admitirá más movimientos, ni siquiera los de hoy."""
        return await service.preview_month_close(month, covers, destinations)

    @server.tool()
    @domain_errors
    async def close_month(
        month: str = Field(description="Mes AAAA-MM a cerrar, el mismo de la vista previa."),
        covers: Covers = None,
        destinations: Destinations = None,
        confirm: bool = Field(
            default=False, description="false: vista previa con preview_token; true: cerrar."
        ),
        preview_token: str | None = Field(
            default=None, description="Obligatorio con confirm=true: el de la vista previa."
        ),
        operation_id: str | None = Field(
            default=None, description=f"Obligatoria con confirm=true. {OPERATION_DESCRIPTION}"
        ),
    ) -> MonthCloseResult:
        """Cierra un mes de forma atómica (RN-46): transferencias cierre_de_mes para coberturas y
        destinos, ajustes de cierre (sobrante no destinado, sobregasto no cubierto), evaluación de
        metas y marca de cerrado, o nada. Sin confirm=true solo devuelve la vista previa.

        Un mes se cierra desde su último día, en orden (no se cierra uno sin haber cerrado el
        anterior) y sin extras pendientes. Después no admite gastos, ingresos, extras, repartos,
        transferencias ni anulaciones, y no se reabre (RN-44, RN-48, RN-53).

        Flujo: preview_month_close con la propuesta, explicación breve, aprobación EXPLÍCITA del
        propietario y solo entonces close_month con confirm=true, el preview_token y un
        operation_id nuevo. Si el estado cambió desde la vista previa, repítela. Luego sigue el
        ritual (RN-51): salario del mes siguiente y porcentajes si cambian."""
        return await service.close_month(
            month, covers, destinations, confirm, preview_token, operation_id
        )

    @server.tool()
    @domain_errors
    async def set_surplus_destination(
        pocket: str = Field(description="Bolsa de consumo activa."),
        destination_pocket: str | None = Field(
            default=None,
            description="Acumulable activa que se sugiere para su sobrante; null lo quita.",
        ),
        operation_id: str = Field(description=OPERATION_DESCRIPTION),
    ) -> SurplusDestinationResult:
        """Fija o quita el destino de sobrante sugerido de una bolsa de consumo (6.5). Es solo un
        dato para preview_month_close: no mueve dinero y el propietario decide en cada cierre."""
        return await service.set_surplus_destination(pocket, destination_pocket, operation_id)
