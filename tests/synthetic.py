"""Generador de datos sintéticos para la prueba del invariante de integridad (11.4).

Nunca usa datos reales. Cada conjunto sale de una semilla fija, que las pruebas imprimen al fallar
para reproducir el caso. Los Hitos 5, 8 y 9 lo extienden con gastos, transferencias y cierres.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import date

from puro_pockets.domain.allocation import split_amount
from puro_pockets.domain.balances import IncomeKind
from puro_pockets.domain.months import Month
from puro_pockets.domain.pockets import Behavior
from puro_pockets.services.budget import AllocationLine

BASE_SEED = 20261110
DATASETS = 200
TODAY = date(2026, 11, 10)


@dataclass(frozen=True)
class SyntheticIncome:
    month: Month
    amount: int
    percentages: tuple[int, ...]  # uno por bolsa, en orden de creación; suman 100


@dataclass(frozen=True)
class SyntheticDataset:
    seed: int
    pockets: tuple[tuple[str, Behavior], ...]
    initial: tuple[tuple[str, int], ...]
    incomes: tuple[SyntheticIncome, ...]


def _percentages(rng: random.Random, count: int) -> tuple[int, ...]:
    cuts = sorted(rng.randint(0, 100) for _ in range(count - 1))
    return tuple(b - a for a, b in zip([0, *cuts], [*cuts, 100], strict=True))


def generate(seed: int) -> SyntheticDataset:
    rng = random.Random(seed)
    count = rng.randint(1, 8)
    pockets = tuple((f"Bolsa sintética {i + 1}", rng.choice(list(Behavior))) for i in range(count))
    initial = [(name, rng.choice([0, rng.randint(1, 5_000_000)])) for name, _ in pockets]
    if all(amount == 0 for _, amount in initial):
        index = rng.randrange(count)
        initial[index] = (pockets[index][0], rng.randint(1, 5_000_000))
    rng.shuffle(initial)  # el orden de entrada no debe importar
    months = [Month(2026, 6)]
    while len(months) < 13:
        months.append(months[-1].next())
    incomes = tuple(
        SyntheticIncome(rng.choice(months), rng.randint(1, 3_000_000), _percentages(rng, count))
        for _ in range(rng.randint(0, 6))
    )
    return SyntheticDataset(seed, pockets, tuple(initial), incomes)


def datasets(n: int = DATASETS) -> list[SyntheticDataset]:
    return [generate(BASE_SEED + i) for i in range(n)]


def record_incomes(store, dataset: SyntheticDataset) -> None:
    """Ingresos sintéticos ya repartidos con RN-08 (simulan los del Hito 5)."""
    ids = [p.id for p in sorted(store.list_pockets(), key=lambda p: p.id) if p.active]
    for income in dataset.incomes:
        parts = split_amount(income.amount, list(zip(ids, income.percentages, strict=True)))
        lines = [
            AllocationLine(pid, pct, amount)
            for (pid, amount), pct in zip(parts, income.percentages, strict=True)
        ]
        store.record_distributed_income(
            IncomeKind.BASE, date(income.month.year, income.month.month, 28), income.month, lines
        )
