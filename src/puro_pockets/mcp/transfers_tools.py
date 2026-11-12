"""Tools de transferencias entre bolsas (Hito 8).

Contrato: specs/008-transferencias/contracts/tools.md.

Delgadas: pasan la entrada al servicio y devuelven sus modelos. La app calcula y valida; Claude
propone con una explicación breve; el propietario aprueba de forma explícita (principio 3.1). Los
errores llegan como is_error en español, sin montos, notas ni nombres de metas. Bolsas por nombre;
transferencias por referencia T-n. Siempre en colones, con la fecha de hoy.
"""

from __future__ import annotations

from typing import Annotated, Any

from mcp.server.mcpserver import MCPServer
from pydantic import Field, WithJsonSchema

from puro_pockets.mcp.inputs import OPERATION_DESCRIPTION, WholeNumberInput, domain_errors
from puro_pockets.services.ledger import LedgerService
from puro_pockets.services.transfers import TransferResult

FromPocket = Annotated[str, Field(description="Bolsa de origen (sin distinguir mayúsculas).")]
ToPocket = Annotated[str, Field(description="Bolsa de destino (sin distinguir mayúsculas).")]
Amount = Annotated[
    WholeNumberInput, Field(description="Colones: entero positivo (sin decimales ni dólares).")
]
# El motivo no se valida con pydantic (su error saldría en inglés y con el valor recibido): pasa al
# dominio, que rechaza 'cierre_de_mes' (solo de close_month) y cualquier otro con un mensaje en
# español. El esquema JSON sigue declarando los tres valores permitidos.
Reason = Annotated[
    Any,
    WithJsonSchema(
        {
            "type": "string",
            "enum": ["cubrir_sobregasto", "reasignacion", "ajuste"],
            "description": "cubrir_sobregasto (cubrir una bolsa en negativo), reasignacion (por "
            "ejemplo vaciar una bolsa antes de archivarla) o ajuste. 'cierre_de_mes' es solo del "
            "cierre de mes (close_month).",
        }
    ),
]
NOTE = Field(default=None, description="Nota opcional, hasta 140 caracteres.")
DATE = Field(
    default=None,
    description="Opcional: solo se admite la fecha de hoy (America/Costa_Rica); se puede omitir.",
)


def register_transfers_tools(server: MCPServer, service: LedgerService) -> None:
    @server.tool()
    @domain_errors
    async def preview_transfer(
        from_pocket: FromPocket,
        to_pocket: ToPocket,
        amount: Amount,
        reason: Reason,
        note: str | None = NOTE,
        transfer_date: str | None = DATE,
    ) -> TransferResult:
        """Simula mover colones entre dos bolsas activas sin guardar nada (principio 3.2): cómo
        quedarían ambas (saldo si es acumulable; disponible y presupuesto ajustado del mes si es de
        consumo, 9.1) y, si alguna tiene meta activa, el efecto en su avance y si la completaría
        (RN-58). Rechaza un origen igual al destino o un monto no positivo (RN-41) y mover más de
        lo disponible en el origen o desde una bolsa en negativo (RN-42).

        Devuelve el preview_token que exige transfer_between_bolsas con confirm=true."""
        return await service.preview_transfer(
            from_pocket, to_pocket, amount, reason, note, transfer_date
        )

    @server.tool()
    @domain_errors
    async def transfer_between_bolsas(
        from_pocket: FromPocket,
        to_pocket: ToPocket,
        amount: Amount,
        reason: Reason,
        note: str | None = NOTE,
        confirm: bool = Field(
            default=False, description="false: vista previa con preview_token; true: guardar."
        ),
        operation_id: str | None = Field(
            default=None, description=f"Obligatoria con confirm=true. {OPERATION_DESCRIPTION}"
        ),
        preview_token: str | None = Field(
            default=None, description="Obligatorio con confirm=true: el de la vista previa."
        ),
        transfer_date: str | None = DATE,
    ) -> TransferResult:
        """Mueve colones de una bolsa a otra y lo deja en el registro de transferencias (RN-39,
        RN-40), con la fecha de hoy y el mes de esa fecha. Sin confirm=true solo devuelve la vista
        previa. Las transferencias nunca se editan ni se borran: un error se corrige con otra en
        sentido contrario (RN-43). La respuesta trae su referencia T-n.

        Flujo: pide la vista previa (preview_transfer o confirm=false), explica en pocas palabras
        cómo quedan las bolsas y el efecto en la meta, espera la aprobación EXPLÍCITA del
        propietario y solo entonces repite con confirm=true, el preview_token y un operation_id
        nuevo. Tras un sobregasto (add_expense con overspent=true), propón aquí cubrirlo desde una
        de las bolsas que la advertencia lista, con motivo cubrir_sobregasto.
        """
        return await service.transfer_between_bolsas(
            from_pocket,
            to_pocket,
            amount,
            reason,
            note,
            confirm,
            operation_id,
            preview_token,
            transfer_date,
        )
