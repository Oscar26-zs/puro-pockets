"""Generador de datos sintéticos para la prueba del invariante de integridad (11.4).

Nunca usa datos reales. Cada conjunto sale de una semilla fija, que las pruebas imprimen al fallar
para reproducir el caso. Desde el Hito 5: salarios en CRC y USD, gastos (con sobregastos, en CRC y
USD), anulaciones (incluido el saldo inicial y su nueva carga). Desde el Hito 6: extras pendientes
(fuera del invariante), repartidos (dentro) y anulados (revierten), y gastos fijos con pagos
(algunos anulados y vueltos a pagar). Desde el Hito 7, operaciones estructurales
(`apply_structure`): bolsas nuevas con las tres estrategias, metas creadas y cambiadas, y archivado
de bolsas con saldo cero; ninguna mueve un saldo. Los Hitos 8 y 9 agregan transferencias y cierres.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import date, timedelta

from puro_pockets.domain.money import RateRange
from puro_pockets.domain.months import Month
from puro_pockets.domain.pockets import Behavior
from puro_pockets.services.budget import BudgetService
from puro_pockets.services.ledger import LedgerService

BASE_SEED = 20261110
DATASETS = 200
TODAY = date(2026, 11, 10)
FIRST_DAY = date(2026, 6, 1)
RATES = RateRange(300, 1000)
VOID_REASON = "anulación sintética"


@dataclass(frozen=True)
class SyntheticMoney:
    amount: int | str  # colones (int) o dólares en texto con 2 decimales
    currency: str
    rate: str | None


@dataclass(frozen=True)
class SyntheticIncome:
    day: date
    money: SyntheticMoney


@dataclass(frozen=True)
class SyntheticExpense:
    day: date
    pocket_index: int
    money: SyntheticMoney


@dataclass(frozen=True)
class SyntheticExtra:
    day: date
    money: SyntheticMoney
    shares: tuple[int, ...] | None  # porcentajes por bolsa (suman 100); None = queda pendiente


@dataclass(frozen=True)
class SyntheticRecurring:
    money: SyntheticMoney  # el tipo de cambio es el de cada pago, no de la plantilla
    day_of_month: int
    pocket_index: int
    start: Month


@dataclass(frozen=True)
class SyntheticPayment:
    recurring_index: int
    day: date
    rate: str | None  # tipo de cambio de este pago (solo USD)
    void_and_repay: bool


@dataclass(frozen=True)
class SyntheticDataset:
    seed: int
    pockets: tuple[tuple[str, Behavior], ...]
    initial: tuple[tuple[str, int], ...]
    allocations: tuple[tuple[Month, tuple[int, ...]], ...]  # porcentajes por bolsa; suman 100
    incomes: tuple[SyntheticIncome, ...]
    expenses: tuple[SyntheticExpense, ...]
    voided_incomes: tuple[int, ...]  # índices en `incomes`
    voided_expenses: tuple[int, ...]  # índices en `expenses`
    reload_initial: (
        tuple[tuple[str, int], ...] | None
    )  # anula el saldo inicial y lo vuelve a cargar
    extras: tuple[SyntheticExtra, ...] = ()
    voided_extras: tuple[int, ...] = ()  # índices en `extras`
    recurring: tuple[SyntheticRecurring, ...] = ()
    payments: tuple[SyntheticPayment, ...] = ()
    structure_seed: int = 0  # semilla de las operaciones estructurales (Hito 7)


def _percentages(rng: random.Random, count: int) -> tuple[int, ...]:
    cuts = sorted(rng.randint(0, 100) for _ in range(count - 1))
    return tuple(b - a for a, b in zip([0, *cuts], [*cuts, 100], strict=True))


def _initial(rng: random.Random, pockets) -> tuple[tuple[str, int], ...]:
    initial = [(name, rng.choice([0, rng.randint(1, 5_000_000)])) for name, _ in pockets]
    if all(amount == 0 for _, amount in initial):
        index = rng.randrange(len(pockets))
        initial[index] = (pockets[index][0], rng.randint(1, 5_000_000))
    rng.shuffle(initial)  # el orden de entrada no debe importar
    return tuple(initial)


def _day(rng: random.Random) -> date:
    return FIRST_DAY + timedelta(days=rng.randint(0, (TODAY - FIRST_DAY).days))


def _money(rng: random.Random, max_crc: int) -> SyntheticMoney:
    if rng.random() < 0.3:
        cents = rng.randint(1, max_crc // 5)
        rate = rng.randint(45_000, 65_099)
        return SyntheticMoney(
            f"{cents // 100}.{cents % 100:02d}" if cents >= 100 else f"0.{cents:02d}",
            "USD",
            f"{rate // 100}.{rate % 100:02d}",
        )
    return SyntheticMoney(rng.randint(1, max_crc), "CRC", None)


def generate(seed: int) -> SyntheticDataset:
    rng = random.Random(seed)
    count = rng.randint(1, 8)
    pockets = tuple((f"Bolsa sintética {i + 1}", rng.choice(list(Behavior))) for i in range(count))
    months = [Month(2026, 6)]
    while len(months) < 7:
        months.append(months[-1].next())
    allocations = [(Month(2026, 6), _percentages(rng, count))]
    allocations += [(m, _percentages(rng, count)) for m in months[1:] if rng.random() < 0.3]
    incomes = tuple(
        SyntheticIncome(_day(rng), _money(rng, 3_000_000)) for _ in range(rng.randint(0, 6))
    )
    expenses = tuple(
        SyntheticExpense(_day(rng), rng.randrange(count), _money(rng, 900_000))
        for _ in range(rng.randint(0, 15))
    )
    voided_incomes = tuple(i for i in range(len(incomes)) if rng.random() < 0.2)
    voided_expenses = tuple(i for i in range(len(expenses)) if rng.random() < 0.2)
    reload = _initial(rng, pockets) if rng.random() < 0.25 else None
    initial = _initial(rng, pockets)
    extras = tuple(
        SyntheticExtra(
            _day(rng),
            _money(rng, 1_000_000),
            _percentages(rng, count) if rng.random() < 0.6 else None,
        )
        for _ in range(rng.randint(0, 4))
    )
    voided_extras = tuple(i for i in range(len(extras)) if rng.random() < 0.25)
    recurring = tuple(
        SyntheticRecurring(
            _money(rng, 400_000),
            rng.randint(1, 31),
            rng.randrange(count),
            rng.choice(months[:6]),
        )
        for _ in range(rng.randint(0, 3))
    )
    payments = []
    for index, template in enumerate(recurring):
        month = template.start
        while month <= Month.of(TODAY):
            if rng.random() < 0.6:
                last = TODAY.day if month == Month.of(TODAY) else 28
                rate = template.money.rate and f"{rng.randint(450, 650)}.{rng.randint(0, 99):02d}"
                payments.append(
                    SyntheticPayment(
                        index,
                        date(month.year, month.month, rng.randint(1, last)),
                        rate,
                        rng.random() < 0.2,
                    )
                )
            month = month.next()
    return SyntheticDataset(
        seed,
        pockets,
        initial,
        tuple(allocations),
        incomes,
        expenses,
        voided_incomes,
        voided_expenses,
        reload,
        extras,
        voided_extras,
        recurring,
        tuple(payments),
        rng.randrange(2**31),
    )


def datasets(n: int = DATASETS) -> list[SyntheticDataset]:
    return [generate(BASE_SEED + i) for i in range(n)]


async def apply(store, dataset: SyntheticDataset) -> None:
    """Registra el conjunto con los servicios reales (las mismas reglas que usan las tools)."""
    await apply_money(store, dataset)
    await apply_structure(store, dataset)


async def apply_money(store, dataset: SyntheticDataset) -> None:
    """Movimientos de dinero de los Hitos 4 a 6."""
    ids = [p.id for p in sorted(store.list_pockets(), key=lambda p: p.id) if p.active]
    for month, percentages in dataset.allocations:
        store.replace_allocation(month, dict(zip(ids, percentages, strict=True)))
    budget = BudgetService(store, today=lambda: TODAY)
    ledger = LedgerService(store, today=lambda: TODAY, rate_range=RATES)
    await budget.load_initial_balance(list(dataset.initial), confirm=True)
    prefix = f"syn-{dataset.seed}"

    income_refs = []
    for n, income in enumerate(dataset.incomes):
        result = await ledger.add_income(
            income.money.amount,
            income.money.currency,
            income.money.rate,
            income.day.isoformat(),
            confirm=True,
            operation_id=f"{prefix}-inc-{n}",
        )
        income_refs.append(result.reference)
    expense_refs = []
    for n, expense in enumerate(dataset.expenses):
        result = await ledger.add_expense(
            expense.money.amount,
            f"{prefix}-exp-{n}",
            pocket=dataset.pockets[expense.pocket_index][0],
            currency=expense.money.currency,
            exchange_rate=expense.money.rate,
            expense_date=expense.day.isoformat(),
        )
        expense_refs.append(result.reference)

    refs = [income_refs[i] for i in dataset.voided_incomes]
    refs += [expense_refs[i] for i in dataset.voided_expenses]
    if dataset.reload_initial is not None:
        refs.append("I-1")  # el saldo inicial es el primer ingreso de cada conjunto
    for n, ref in enumerate(refs):
        await ledger.void_transaction(ref, VOID_REASON, f"{prefix}-void-{n}", confirm=True)
    if dataset.reload_initial is not None:
        await budget.load_initial_balance(list(dataset.reload_initial), confirm=True)
    await _apply_extras(ledger, dataset, prefix)
    await _apply_recurring(ledger, dataset, prefix)


async def _apply_extras(ledger: LedgerService, dataset: SyntheticDataset, prefix: str) -> None:
    for n, extra in enumerate(dataset.extras):
        result = await ledger.register_extra_income(
            extra.money.amount,
            f"{prefix}-ext-{n}",
            currency=extra.money.currency,
            exchange_rate=extra.money.rate,
            income_date=extra.day.isoformat(),
        )
        if extra.shares is not None:
            shares = [
                (name, pct)
                for (name, _), pct in zip(dataset.pockets, extra.shares, strict=True)
                if pct
            ]
            preview = await ledger.confirm_allocation(result.reference, shares)
            await ledger.confirm_allocation(
                result.reference,
                shares,
                confirm=True,
                operation_id=f"{prefix}-alloc-{n}",
                preview_token=preview.preview_token,
            )
        if n in dataset.voided_extras:
            await ledger.void_transaction(
                result.reference, VOID_REASON, f"{prefix}-vext-{n}", confirm=True
            )


async def _apply_recurring(ledger: LedgerService, dataset: SyntheticDataset, prefix: str) -> None:
    for n, template in enumerate(dataset.recurring):
        await ledger.manage_recurring(
            "crear",
            f"{prefix}-rec-{n}",
            name=f"Fijo sintético {n + 1}",
            amount=template.money.amount,
            currency=template.money.currency,
            day_of_month=template.day_of_month,
            pocket=dataset.pockets[template.pocket_index][0],
            start_month=str(template.start),
        )
    for n, payment in enumerate(dataset.payments):
        args = {"recurring": f"F-{payment.recurring_index + 1}", "exchange_rate": payment.rate}
        paid = await ledger.add_expense(
            operation_id=f"{prefix}-pay-{n}", expense_date=payment.day.isoformat(), **args
        )
        if payment.void_and_repay:
            await ledger.void_transaction(
                paid.reference, VOID_REASON, f"{prefix}-vpay-{n}", confirm=True
            )
            await ledger.add_expense(
                operation_id=f"{prefix}-repay-{n}", expense_date=payment.day.isoformat(), **args
            )


STRATEGIES = ("proporcional", "desde_una_bolsa", "manual")


def _shares(rng: random.Random, names: list[str]) -> list[tuple[str, int]]:
    return list(zip(names, _percentages(rng, len(names)), strict=True))


async def apply_structure(store, dataset: SyntheticDataset) -> None:
    """Hito 7: bolsas nuevas, metas y archivado de bolsas vacías. No mueve dinero."""
    rng = random.Random(dataset.structure_seed)
    ledger = LedgerService(store, today=lambda: TODAY, rate_range=RATES)
    prefix = f"syn-{dataset.seed}-h7"
    created = []
    for n in range(rng.randint(0, 3)):
        name = f"Bolsa nueva sintética {n + 1}"
        behavior = rng.choice(["consumo", "acumulable"])
        month = rng.choice([None, str(Month.of(TODAY))])
        strategy = rng.choice(STRATEGIES)
        active = [p for p in store.list_pockets() if p.active]
        args = {"strategy": strategy, "month": month, "percentage": rng.randint(0, 40)}
        if strategy == "desde_una_bolsa":
            args["from_pocket"] = rng.choice(active).name
            args["percentage"] = 0  # siempre alcanza
        if strategy == "manual":
            args["percentages"] = _shares(rng, [p.name for p in active] + [name])
            args["percentage"] = None
        preview = await ledger.create_bolsa(name, behavior, **args)
        await ledger.create_bolsa(
            name,
            behavior,
            confirm=True,
            operation_id=f"{prefix}-bolsa-{n}",
            preview_token=preview.preview_token,
            **args,
        )
        created.append(name)
    goals = 0
    for pocket in [p for p in store.list_pockets() if p.active]:
        if pocket.behavior is not Behavior.ACUMULABLE or rng.random() < 0.4:
            continue
        goal = await ledger.create_goal(
            pocket.name,
            f"Meta sintética {goals}",
            rng.randint(1, 8_000_000),
            f"{prefix}-meta-{goals}",
        )
        goals += 1
        if goal.status == "activa" and rng.random() < 0.5:
            change = rng.choice(
                [{"target_amount": rng.randint(1, 8_000_000)}, {"action": "pausar"}]
            )
            await ledger.update_goal(goal.reference, f"{prefix}-upd-{goals}", **change)
    for n, name in enumerate(created):
        if rng.random() < 0.5:
            continue  # las bolsas nuevas no recibieron dinero: su saldo es cero
        preview = await ledger.archive_bolsa(name)
        await ledger.archive_bolsa(
            name,
            confirm=True,
            operation_id=f"{prefix}-arch-{n}",
            preview_token=preview.preview_token,
        )
