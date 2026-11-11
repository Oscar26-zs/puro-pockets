"""Mes presupuestario con formato 'YYYY-MM'."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

from puro_pockets.domain.errors import DomainError

_MONTH_RE = re.compile(r"^([0-9]{4})-(0[1-9]|1[0-2])$")
INVALID_MONTH_MESSAGE = "El mes debe tener el formato AAAA-MM (por ejemplo 2026-11)."


@dataclass(frozen=True, order=True)
class Month:
    year: int
    month: int

    @classmethod
    def parse(cls, text: object) -> Month:
        if not isinstance(text, str):
            raise DomainError(INVALID_MONTH_MESSAGE)
        match = _MONTH_RE.match(text.strip())
        if match is None or int(match.group(1)) < 1:
            raise DomainError(INVALID_MONTH_MESSAGE)
        return cls(int(match.group(1)), int(match.group(2)))

    @classmethod
    def of(cls, day: date) -> Month:
        return cls(day.year, day.month)

    def previous(self) -> Month:
        return Month(self.year - 1, 12) if self.month == 1 else Month(self.year, self.month - 1)

    def next(self) -> Month:
        return Month(self.year + 1, 1) if self.month == 12 else Month(self.year, self.month + 1)

    def __str__(self) -> str:
        return f"{self.year:04d}-{self.month:02d}"
