"""Tools del presupuesto (Hito 4). Contrato: specs/004-bolsas-porcentajes/contracts/tools.md.

Desde el Hito 5 los enteros no aceptan decimales (50.0 se rechaza: ningún `float`).

Las tools son delgadas: convierten la entrada, llaman al servicio y traducen `DomainError` a
`ToolError` (el cliente recibe is_error con el mensaje en español). Los mensajes nunca incluyen
montos, porque el SDK los registra. Las bolsas se identifican por nombre; no se exponen ids.
"""

from __future__ import annotations

from typing import Literal

from mcp.server.mcpserver import MCPServer
from pydantic import BaseModel, Field

from puro_pockets.domain.allocation import ResolvedAllocation
from puro_pockets.mcp.inputs import MONTH_DESCRIPTION, WholeNumberInput
from puro_pockets.mcp.inputs import domain_errors as _domain_errors
from puro_pockets.services.budget import BudgetService, InitialBalanceView

# Porcentajes y montos pasan sin validar a la capa de dominio, que exige enteros (rechaza 50.0) con
# mensajes sin el valor recibido: el error de pydantic lo incluiría y el SDK lo registra.


class PocketPercentage(BaseModel):
    pocket: str = Field(description="Nombre de la bolsa (sin distinguir mayúsculas).")
    percentage: WholeNumberInput = Field(description="Porcentaje entero entre 0 y 100.")


class PocketAmount(BaseModel):
    pocket: str = Field(description="Nombre de la bolsa (sin distinguir mayúsculas).")
    amount: WholeNumberInput = Field(description="Monto en colones, entero mayor o igual a 0.")


class AllocationItem(BaseModel):
    pocket: str
    behavior: Literal["consumo", "acumulable"]
    percentage: int


class AllocationResult(BaseModel):
    month: str = Field(description="Mes consultado o guardado.")
    defined: bool = Field(description="False si ni este mes ni uno anterior tiene porcentajes.")
    source_month: str | None = Field(
        description="Mes del que vienen los porcentajes; igual a month si son propios (RN-03)."
    )
    items: list[AllocationItem]


class AmountItem(BaseModel):
    pocket: str
    behavior: Literal["consumo", "acumulable"]
    amount: int = Field(description="Colones.")


class InitialBalanceResult(BaseModel):
    saved: bool = Field(description="True solo si se guardó el saldo inicial.")
    month: str = Field(description="Mes al que pertenece el saldo inicial (el actual).")
    total: int = Field(description="Total en colones.")
    items: list[AmountItem]
    already_loaded: bool = Field(description="True si ya hay un saldo inicial guardado.")


class PocketStatus(BaseModel):
    name: str
    behavior: Literal["consumo", "acumulable"]
    balance: int = Field(description="Colones: saldo (acumulable) o disponible del mes (consumo).")
    balance_kind: Literal["saldo", "disponible_del_mes"]


class PocketsResult(BaseModel):
    month: str = Field(description="Mes actual.")
    pockets: list[PocketStatus]


def _allocation(resolved: ResolvedAllocation) -> AllocationResult:
    return AllocationResult(
        month=str(resolved.month),
        defined=resolved.defined,
        source_month=str(resolved.source_month) if resolved.source_month else None,
        items=[
            AllocationItem(pocket=p.name, behavior=p.behavior.value, percentage=pct)
            for p, pct in resolved.items
        ],
    )


def _initial(view: InitialBalanceView) -> InitialBalanceResult:
    return InitialBalanceResult(
        saved=view.saved,
        month=str(view.month),
        total=view.total,
        items=[
            AmountItem(pocket=p.name, behavior=p.behavior.value, amount=a) for p, a in view.items
        ],
        already_loaded=view.already_loaded,
    )


def register_budget_tools(server: MCPServer, service: BudgetService) -> None:
    @server.tool()
    @_domain_errors
    async def set_allocation(
        percentages: list[PocketPercentage],
        month: str | None = Field(default=None, description=MONTH_DESCRIPTION),
    ) -> AllocationResult:
        """Guarda los porcentajes de reparto de un mes (RN-01, RN-02).

        Incluye todas las bolsas activas (0 si no recibe); deben sumar exactamente 100. Solo se
        editan el mes actual y los siguientes. Reemplaza los porcentajes previos de ese mes.
        """
        pairs = [(item.pocket, item.percentage) for item in percentages]
        return _allocation(await service.set_allocation(pairs, month))

    @server.tool()
    @_domain_errors
    async def get_allocation(
        month: str | None = Field(default=None, description=MONTH_DESCRIPTION),
    ) -> AllocationResult:
        """Consulta los porcentajes de un mes. Si no tiene, devuelve los del mes anterior más
        cercano e indica su origen (RN-03). No guarda nada."""
        return _allocation(await service.get_allocation(month))

    @server.tool()
    @_domain_errors
    async def preview_initial_balance(amounts: list[PocketAmount]) -> InitialBalanceResult:
        """Vista previa del saldo inicial (RN-54): total y monto por bolsa. No guarda nada.

        Las bolsas omitidas cuentan como 0. Muéstrala al propietario antes de cargarlo.
        """
        pairs = [(item.pocket, item.amount) for item in amounts]
        return _initial(await service.preview_initial_balance(pairs))

    @server.tool()
    @_domain_errors
    async def load_initial_balance(
        amounts: list[PocketAmount],
        confirm: bool = Field(
            default=False,
            description="Debe ser true, tras confirmarlo el propietario. Si es false, solo "
            "devuelve la vista previa y no guarda nada.",
        ),
    ) -> InitialBalanceResult:
        """Carga el saldo inicial, una sola vez (RN-54). No cuenta como ingreso del mes.

        Exige confirm=true; sin él devuelve la vista previa. Una segunda carga se rechaza, salvo
        que el saldo inicial vigente se haya anulado con void_transaction.
        """
        pairs = [(item.pocket, item.amount) for item in amounts]
        return _initial(await service.load_initial_balance(pairs, confirm=confirm))

    @server.tool()
    @_domain_errors
    async def list_bolsas() -> PocketsResult:
        """Lista las bolsas activas con su saldo: acumulable = saldo; consumo = disponible del
        mes actual (RN-10 a RN-12)."""
        view = await service.list_pockets()
        return PocketsResult(
            month=str(view.month),
            pockets=[
                PocketStatus(
                    name=b.pocket.name,
                    behavior=b.pocket.behavior.value,
                    balance=b.balance,
                    balance_kind=b.kind.value,
                )
                for b in view.pockets
            ],
        )
