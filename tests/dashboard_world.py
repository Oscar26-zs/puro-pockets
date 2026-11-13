"""Mundo sintético del dashboard (Hito 10): sirve con el almacén en memoria y con Postgres.

Hoy es 2026-11-12. Bolsas Necesidades (1, consumo), Ahorro (2, acumulable), Gustos (3, consumo).
Todo se escribe por los servicios de los Hitos 4 a 9, como lo haría Claude. Cifras a mano:

Octubre (cerrado): salario 1 000 000 (500 000 / 300 000 / 200 000); gastos 480 000 y 205 000.
  Cierre: Necesidades cubre 5 000 de Gustos, envía 10 000 a Ahorro y 5 000 quedan no destinados.
  Ahorrado = 300 000 + 10 000 (sobrante de cierre) = 310 000.
Noviembre (abierto): salario 500 000 (250 000 / 150 000 / 100 000); gastos de Necesidades 168 000
  + 30 000 (alquiler, fijo F-1); Gustos 112 000; un gasto de Gustos de 35 000 anulado;
  transferencia Necesidades → Gustos 7 500 (cubrir_sobregasto); extra de US$ 25 pendiente.
  Necesidades: ajustado 242 500, disponible 44 500, 81 % → uso alto.
  Gustos: ajustado 107 500, disponible −4 500, 104 % → sobregasto.
  Ahorro: saldo 300 000 + 10 000 + 150 000 = 460 000; meta de 500 000 (92 %, faltan 40 000).
  Ahorrado = 150 000. Gastado = 310 000 (el anulado no suma). Disponible = 44 500 − 4 500 = 40 000.
"""

from __future__ import annotations

from datetime import date

from puro_pockets.domain.months import Month
from puro_pockets.services.ledger import LedgerService

TODAY = date(2026, 11, 12)
OCT, NOV = Month(2026, 10), Month(2026, 11)
GOAL_NAME = "meta privada sintética"
SECRET_DESCRIPTION = "descripcion privada sintetica"
SECRET_NOTE = "nota privada sintetica"
ALLOCATION = {1: 50, 2: 30, 3: 20}

EXPECTED = {
    "nov": {"income": 500_000, "spent": 310_000, "available": 40_000, "saved": 150_000},
    "oct": {"income": 1_000_000, "spent": 685_000, "saved": 310_000},
}


async def build_world(store, ledger: LedgerService) -> None:
    store.replace_allocation(OCT, ALLOCATION)
    store.replace_allocation(NOV, ALLOCATION)
    await ledger.create_category("Alimentación", "Necesidades")
    await ledger.create_category("Salidas", "Gustos")
    # Octubre
    await ledger.add_income(
        1_000_000,
        income_date="2026-09-30",
        budget_month="2026-10",
        confirm=True,
        operation_id="world-op-sal-oct",
    )
    await ledger.add_expense(
        480_000, "world-op-g-oct-1", pocket="Necesidades", expense_date="2026-10-10"
    )
    await ledger.add_expense(
        205_000, "world-op-g-oct-2", pocket="Gustos", expense_date="2026-10-12"
    )
    covers = [{"from_pocket": "Necesidades", "to_pocket": "Gustos", "amount": 5_000}]
    dests = [{"from_pocket": "Necesidades", "to_pocket": "Ahorro", "amount": 10_000}]
    preview = await ledger.preview_month_close("2026-10", covers, dests)
    await ledger.close_month(
        "2026-10",
        covers,
        dests,
        confirm=True,
        preview_token=preview.preview_token,
        operation_id="world-op-close-oct",
    )
    # Noviembre
    await ledger.add_income(
        500_000,
        income_date="2026-11-01",
        budget_month="2026-11",
        confirm=True,
        operation_id="world-op-sal-nov",
    )
    await ledger.manage_recurring(
        "crear",
        operation_id="world-op-f-alq",
        name="Alquiler",
        amount=30_000,
        day_of_month=1,
        pocket="Necesidades",
        start_month="2026-11",
    )
    await ledger.manage_recurring(
        "crear",
        operation_id="world-op-f-int",
        name="Internet",
        amount=18_000,
        day_of_month=15,
        pocket="Necesidades",
        start_month="2026-11",
    )
    await ledger.manage_recurring(
        "crear",
        operation_id="world-op-f-vid",
        name="Video",
        amount="12.99",
        currency="USD",
        day_of_month=5,
        pocket="Gustos",
        start_month="2026-11",
    )
    await ledger.add_expense(
        168_000,
        "world-op-g-nov-1",
        category="Alimentación",
        expense_date="2026-11-11",
        description=SECRET_DESCRIPTION,
    )
    await ledger.add_expense(
        None, "world-op-g-nov-alq", recurring="Alquiler", expense_date="2026-11-01"
    )
    await ledger.add_expense(
        112_000, "world-op-g-nov-2", category="Salidas", expense_date="2026-11-10"
    )
    voided = await ledger.add_expense(
        35_000, "world-op-g-nov-3", pocket="Gustos", expense_date="2026-11-08"
    )
    await ledger.void_transaction(
        voided.reference, "registro duplicado", "world-op-void", confirm=True
    )
    transfer = await ledger.preview_transfer(
        "Necesidades", "Gustos", 7_500, "cubrir_sobregasto", SECRET_NOTE
    )
    await ledger.transfer_between_bolsas(
        "Necesidades",
        "Gustos",
        7_500,
        "cubrir_sobregasto",
        SECRET_NOTE,
        confirm=True,
        operation_id="world-op-t-1",
        preview_token=transfer.preview_token,
    )
    await ledger.register_extra_income(
        25, "world-op-extra", currency="USD", exchange_rate=520, income_date="2026-11-09"
    )
    await ledger.create_goal("Ahorro", GOAL_NAME, 500_000, "world-op-goal")
