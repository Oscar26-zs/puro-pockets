"""Tools de movimientos (Hito 5). Contrato: specs/005-ingresos-gastos/contracts/tools.md.

Delgadas: pasan la entrada al servicio y devuelven sus modelos. Los errores de negocio llegan como
is_error con el mensaje en español, sin montos ni descripciones (el SDK registra ese mensaje).
Bolsas y categorías por nombre; movimientos por referencia corta (I-3, G-12). Sin identificadores
internos.
"""

from __future__ import annotations

from typing import Annotated, Literal

from mcp.server.mcpserver import MCPServer
from pydantic import Field

from puro_pockets.mcp.inputs import (
    DATE_DESCRIPTION,
    MONTH_DESCRIPTION,
    OPERATION_DESCRIPTION,
    CurrencyInput,
    LimitInput,
    MoneyInput,
    OptionalMoneyInput,
    RateInput,
    domain_errors,
)
from puro_pockets.services.ledger import (
    BolsaStatus,
    CategoriesResult,
    CategoryItem,
    ExpenseResult,
    IncomeResult,
    LedgerService,
    SummaryResult,
    TopCategoriesResult,
    TransactionsResult,
    VoidResult,
)

BUDGET_MONTH_DESCRIPTION = (
    "Mes presupuestario AAAA-MM. Si se omite, el mes siguiente a la fecha del ingreso (el salario "
    "de fin de mes financia el mes siguiente)."
)
TopLimit = Annotated[LimitInput, Field(description="Cuántas (1 a 20; 5 por defecto).")]
ListLimit = Annotated[LimitInput, Field(description="Cuántos (1 a 100; 20 por defecto).")]


def register_ledger_tools(server: MCPServer, service: LedgerService) -> None:
    @server.tool()
    @domain_errors
    async def preview_income(
        amount: MoneyInput,
        currency: CurrencyInput = "CRC",
        exchange_rate: RateInput = None,
        income_date: str | None = Field(default=None, description=DATE_DESCRIPTION),
        budget_month: str | None = Field(default=None, description=BUDGET_MONTH_DESCRIPTION),
    ) -> IncomeResult:
        """Vista previa del salario (ingreso base): mes presupuestario y reparto por bolsa con los
        porcentajes de ese mes (o heredados, RN-03). No guarda nada (principio 3.2)."""
        return await service.preview_income(
            amount, currency, exchange_rate, income_date, budget_month
        )

    @server.tool()
    @domain_errors
    async def add_income(
        amount: MoneyInput,
        currency: CurrencyInput = "CRC",
        exchange_rate: RateInput = None,
        income_date: str | None = Field(default=None, description=DATE_DESCRIPTION),
        budget_month: str | None = Field(default=None, description=BUDGET_MONTH_DESCRIPTION),
        confirm: bool = Field(
            default=False,
            description="true solo tras confirmarlo el propietario; con false devuelve la vista "
            "previa y no guarda nada.",
        ),
        operation_id: str | None = Field(
            default=None, description=f"Obligatoria con confirm=true. {OPERATION_DESCRIPTION}"
        ),
    ) -> IncomeResult:
        """Registra el salario (ingreso base) y lo reparte entre las bolsas con los porcentajes de
        su mes presupuestario; guarda el porcentaje usado en cada reparto (RN-02, RN-03, RN-08).

        En USD exige el tipo de cambio (nunca se asume) y guarda el equivalente en colones (RN-57).
        Solo salario: un ingreso extra se registra con register_extra_income.
        """
        return await service.add_income(
            amount, currency, exchange_rate, income_date, budget_month, confirm, operation_id
        )

    @server.tool()
    @domain_errors
    async def add_expense(
        operation_id: str = Field(description=OPERATION_DESCRIPTION),
        amount: OptionalMoneyInput = None,
        pocket: str | None = Field(
            default=None,
            description="Bolsa del gasto. Si se omite, la bolsa por defecto de la categoría.",
        ),
        category: str | None = Field(
            default=None,
            description='Categoría (opcional). Sin categoría queda "pendiente de clasificar".',
        ),
        currency: str | None = Field(
            default=None,
            description="CRC o USD. Por defecto CRC, o la moneda del gasto fijo si se paga uno.",
        ),
        exchange_rate: RateInput = None,
        expense_date: str | None = Field(default=None, description=DATE_DESCRIPTION),
        description: str | None = Field(
            default=None, description="Descripción corta opcional (hasta 120 caracteres)."
        ),
        recurring: str | None = Field(
            default=None,
            description="Para pagar un gasto fijo: su referencia (F-n) o nombre. Sin monto se usa "
            "el de la plantilla para ese mes; bolsa y categoría por defecto, las de la plantilla.",
        ),
    ) -> ExpenseResult:
        """Registra un gasto contra cualquier bolsa (RN-31 a RN-34), en el mes de su fecha.

        Si deja la bolsa en negativo, se guarda igual y la respuesta advierte con las bolsas que
        tienen saldo disponible (RN-37, RN-38). En USD exige el tipo de cambio (RN-57).

        El monto es obligatorio salvo al pagar un gasto fijo (recurring). Un fijo admite un solo
        pago vigente por mes (el mes de la fecha del pago); un fijo en USD exige el tipo de cambio
        de este pago, nunca se reutiliza otro (decisión #12d).
        """
        return await service.add_expense(
            amount,
            operation_id,
            pocket,
            category,
            currency,
            exchange_rate,
            expense_date,
            description,
            recurring,
        )

    @server.tool()
    @domain_errors
    async def void_transaction(
        reference: str = Field(
            description="Referencia del movimiento: G-12 (gasto) o I-3 (ingreso)."
        ),
        reason: str = Field(description="Motivo de la anulación (3 a 200 caracteres)."),
        operation_id: str = Field(description=OPERATION_DESCRIPTION),
        confirm: bool = Field(
            default=False,
            description="true solo tras confirmarlo el propietario; con false muestra el efecto "
            "y no anula nada.",
        ),
    ) -> VoidResult:
        """Anula un ingreso o gasto con motivo, sin borrarlo (RN-53): deja de contar en los cálculos
        y sigue en el historial. Anular un salario revierte su reparto y puede dejar bolsas en
        negativo (RN-59). Anular el saldo inicial permite cargar uno nuevo."""
        return await service.void_transaction(reference, reason, operation_id, confirm)

    @server.tool()
    @domain_errors
    async def get_bolsa_status(
        pocket: str = Field(description="Nombre de la bolsa (sin distinguir mayúsculas)."),
        month: str | None = Field(default=None, description=MONTH_DESCRIPTION),
    ) -> BolsaStatus:
        """Estado de una bolsa en un mes: asignado, transferencias, presupuesto ajustado, gastado y
        disponible con % usado (consumo, 11.1) o saldo (acumulable, 11.2)."""
        return await service.get_bolsa_status(pocket, month)

    @server.tool()
    @domain_errors
    async def get_summary(
        month: str | None = Field(default=None, description=MONTH_DESCRIPTION),
    ) -> SummaryResult:
        """Resumen del mes: ingresos (sin el saldo inicial), total gastado y estado de cada bolsa,
        con las bolsas en negativo marcadas."""
        return await service.get_summary(month)

    @server.tool()
    @domain_errors
    async def top_categories(
        month: str | None = Field(default=None, description=MONTH_DESCRIPTION),
        limit: TopLimit = None,
    ) -> TopCategoriesResult:
        """En qué se gasta más en el mes: categorías ordenadas por monto, incluida "pendiente de
        clasificar"."""
        return await service.top_categories(month, limit)

    @server.tool()
    @domain_errors
    async def list_transactions(
        month: str | None = Field(
            default=None,
            description="AAAA-MM (opcional). Gastos por mes calendario; ingresos por mes "
            "presupuestario.",
        ),
        type: Literal["gasto", "ingreso"] | None = Field(  # noqa: A002 - nombre del contrato
            default=None, description="gasto o ingreso (opcional)."
        ),
        pocket: str | None = Field(default=None, description="Bolsa (opcional; solo gastos)."),
        include_voided: bool = Field(default=True, description="Incluir los anulados."),
        limit: ListLimit = None,
    ) -> TransactionsResult:
        """Lista movimientos, los más recientes primero, con su referencia (I-n, G-n). Los anulados
        aparecen marcados con su motivo."""
        return await service.list_transactions(month, type, pocket, include_voided, limit)

    @server.tool()
    @domain_errors
    async def create_category(
        name: str = Field(description="Nombre (único sin distinguir mayúsculas, hasta 60)."),
        pocket: str = Field(description="Bolsa por defecto de la categoría."),
    ) -> CategoryItem:
        """Crea una categoría de gasto con su bolsa por defecto."""
        return await service.create_category(name, pocket)

    @server.tool()
    @domain_errors
    async def list_categories() -> CategoriesResult:
        """Lista las categorías de gasto con su bolsa por defecto."""
        return await service.list_categories()
