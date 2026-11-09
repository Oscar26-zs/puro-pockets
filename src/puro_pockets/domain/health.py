"""Estado de salud del sistema. Capa de dominio: no depende de MCP ni de la base de datos."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class HealthStatus:
    server: Literal["ok"]
    database: Literal["ok", "error"]
    detail: str | None = None

    @classmethod
    def database_ok(cls) -> HealthStatus:
        return cls(server="ok", database="ok", detail=None)

    @classmethod
    def database_error(cls, detail: str) -> HealthStatus:
        return cls(server="ok", database="error", detail=detail)
