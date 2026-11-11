"""Tools de extras y gastos fijos (Hito 6). Contrato: specs/006-extras-fijos/contracts/tools.md.

Delgadas: pasan la entrada al servicio y devuelven sus modelos. La app calcula y valida; Claude
recomienda; el propietario decide (principio 3.1, RN-05). Los errores llegan como is_error en
español, sin montos ni descripciones. Sin identificadores internos: I-n, G-n y F-n.
"""

from __future__ import annotations

from typing import Annotated, Literal

from mcp.server.mcpserver import MCPServer
from pydantic import BaseModel, Field

from puro_pockets.mcp.inputs import (
    DATE_DESCRIPTION,
    MONTH_DESCRIPTION,
    OPERATION_DESCRIPTION,
    CurrencyInput,
    MoneyInput,
    OptionalMoneyInput,
    OptionalWholeNumberInput,
    RateInput,
    WholeNumberInput,
    domain_errors,
)
from puro_pockets.services.extras import (
    AllocationContextResult,
    ExtraAllocationResult,
    ExtraIncomeResult,
)
from puro_pockets.services.ledger import LedgerService
from puro_pockets.services.recurring import PendingRecurringResult, RecurringResult

EXTRA_REF = "Referencia del extra (I-n), la que devolvió register_extra_income."
ExtraRef = Annotated[str, Field(description=EXTRA_REF)]


class ExtraShare(BaseModel):
    pocket: str = Field(description="Nombre de una bolsa activa (sin distinguir mayúsculas).")
    percentage: WholeNumberInput = Field(description="Porcentaje entero entre 0 y 100.")


Shares = Annotated[
    list[ExtraShare],
    Field(
        description="Bolsas y porcentajes enteros que suman exactamente 100 (RN-01). Las omitidas "
        "reciben 0; puede ir el 100 % a una sola bolsa (RN-07)."
    ),
]


def register_extras_tools(server: MCPServer, service: LedgerService) -> None:
    @server.tool()
    @domain_errors
    async def register_extra_income(
        amount: MoneyInput,
        operation_id: str = Field(description=OPERATION_DESCRIPTION),
        currency: CurrencyInput = "CRC",
        exchange_rate: RateInput = None,
        income_date: str | None = Field(default=None, description=DATE_DESCRIPTION),
        source: str | None = Field(
            default=None, description="Origen del extra, texto corto opcional (hasta 120)."
        ),
    ) -> ExtraIncomeResult:
        """Registra un ingreso extra (todo ingreso que no es el salario). Queda PENDIENTE y "sin
        asignar": no suma a ninguna bolsa hasta repartirlo (RN-06). Pertenece al mes de su fecha
        (RN-09). En USD exige el tipo de cambio indicado por el propietario (RN-57).

        Siguiente paso: get_allocation_context con su referencia; luego propón un reparto.
        """
        return await service.register_extra_income(
            amount, operation_id, currency, exchange_rate, income_date, source
        )

    @server.tool()
    @domain_errors
    async def get_allocation_context(
        extra: str = Field(description=EXTRA_REF),
    ) -> AllocationContextResult:
        """Datos del mes del extra para que TÚ (Claude) propongas cómo repartirlo (RN-05): bolsas
        activas con su comportamiento, porcentajes vigentes, presupuesto, gastado y disponible o
        saldo; gastos fijos pendientes (los de USD aparte, sin convertir) y los porcentajes de los
        últimos extras. Solo agregados; no guarda nada. La app no recomienda.

        Con estos datos propón bolsas y porcentajes enteros que sumen 100, con una explicación
        breve (qué bolsa va corta, fijos pendientes, repartos anteriores). Es una heurística de
        presupuesto, no asesoría. Luego pide la vista previa con confirm_allocation (confirm=false)
        y espera la aprobación explícita del propietario.
        """
        return await service.get_allocation_context(extra)

    @server.tool()
    @domain_errors
    async def confirm_allocation(
        extra: ExtraRef,
        percentages: Shares,
        confirm: bool = Field(
            default=False,
            description="false: vista previa en colones con preview_token, sin guardar. true: "
            "solo después de que el propietario apruebe EXPLÍCITAMENTE esa vista previa.",
        ),
        operation_id: str | None = Field(
            default=None, description=f"Obligatoria con confirm=true. {OPERATION_DESCRIPTION}"
        ),
        preview_token: str | None = Field(
            default=None,
            description="Obligatorio con confirm=true: el de la vista previa de estos mismos "
            "porcentajes.",
        ),
    ) -> ExtraAllocationResult:
        """Reparte un extra pendiente entre bolsas (RN-04 a RN-08).

        Paso 1 (confirm=false): devuelve el reparto en colones (la última bolsa que recibe absorbe
        el residuo, RN-08) y un preview_token; no guarda nada. Muéstralo al propietario.
        Paso 2 (confirm=true): solo con su aprobación explícita, mismos porcentajes, el
        preview_token y un operation_id. Guarda el porcentaje usado y pasa el extra a repartido.
        Un extra repartido no se reparte otra vez: para corregir, anúlalo con void_transaction y
        regístralo de nuevo (RN-53, RN-59).
        """
        pairs = [(item.pocket, item.percentage) for item in percentages]
        return await service.confirm_allocation(extra, pairs, confirm, operation_id, preview_token)

    @server.tool()
    @domain_errors
    async def manage_recurring(
        action: Literal["crear", "listar", "actualizar", "desactivar"] = Field(
            description="crear, listar, actualizar o desactivar (nunca se borran)."
        ),
        operation_id: str | None = Field(
            default=None,
            description=f"Obligatoria para crear, actualizar y desactivar. {OPERATION_DESCRIPTION}",
        ),
        recurring: str | None = Field(
            default=None,
            description="Para actualizar o desactivar: referencia (F-n) o nombre del gasto fijo.",
        ),
        name: str | None = Field(
            default=None,
            description="Nombre (único entre los activos sin distinguir mayúsculas, hasta 60).",
        ),
        amount: OptionalMoneyInput = None,
        currency: str | None = Field(
            default=None,
            description="Solo al crear: CRC (por defecto) o USD. No se cambia después.",
        ),
        day_of_month: OptionalWholeNumberInput = None,
        pocket: str | None = Field(
            default=None, description="Bolsa por defecto del pago (o la de la categoría)."
        ),
        category: str | None = Field(default=None, description="Categoría por defecto (opcional)."),
        start_month: str | None = Field(
            default=None,
            description="Solo al crear: primer mes AAAA-MM (por defecto el actual).",
        ),
        include_inactive: bool = Field(
            default=False, description="Al listar: incluir los desactivados."
        ),
    ) -> RecurringResult:
        """Gastos fijos mensuales (RN-35): plantillas con monto, moneda, día del mes (1 a 31; si
        el mes es más corto cuenta el último día), bolsa, categoría opcional y mes de inicio.

        Cambiar el monto afecta solo meses futuros (desde el mes siguiente). Un fijo en USD guarda
        su monto en dólares sin tipo de cambio: cada pago exige el suyo (decisión #12d). Para
        pagarlo usa add_expense con recurring.
        """
        return await service.manage_recurring(
            action,
            operation_id,
            recurring,
            name,
            amount,
            currency,
            day_of_month,
            pocket,
            category,
            start_month,
            include_inactive,
        )

    @server.tool()
    @domain_errors
    async def list_pending_recurring(
        month: str | None = Field(default=None, description=MONTH_DESCRIPTION),
    ) -> PendingRecurringResult:
        """Gastos fijos del mes: los pendientes (activos, sin pago vigente, desde su mes de
        inicio) con vencimiento y marca de atrasado, y los ya pagados (RN-35). Los de USD no se
        convierten. No guarda nada."""
        return await service.list_pending_recurring(month)
