"""Bolsas flexibles (Hito 7): reajuste de porcentajes, crear y archivar bolsas (RN-13 a RN-18).

- `preview_rebalance` calcula sin guardar nada (principio 3.2).
- `create_bolsa` crea la bolsa y escribe el conjunto completo de porcentajes del mes objetivo en una
  transacción (RN-13). Aplica desde el mes siguiente por defecto o desde el actual (RN-15); nunca un
  mes pasado. Ningún reparto ya guardado se recalcula: guardan el porcentaje que usaron.
- `archive_bolsa` exige saldo o disponible cero (RN-18; se vacía antes con una transferencia,
  Hito 8, y se vuelve a comprobar dentro de la transacción), nunca borra (RN-16) y reescribe sin
  ella los porcentajes del mes actual y de cada mes futuro con porcentajes propios (RN-17): ningún
  mes de ahora en adelante reparte a una bolsa inactiva. Sus metas se archivan con ella (6.4).

Con `confirm=true` se exige la ficha de la vista previa (`preview_token`). Los registros no incluyen
montos, porcentajes ni nombres.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from functools import partial
from typing import Literal

from pydantic import BaseModel, Field

from puro_pockets.domain.allocation import pick_source_month, resolve_allocation
from puro_pockets.domain.balances import PocketFigures
from puro_pockets.domain.errors import (
    DomainError,
    PocketAlreadyExists,
    PocketNotEmpty,
    PreviewRequired,
)
from puro_pockets.domain.idempotency import fingerprint, validate_operation_id
from puro_pockets.domain.months import Month
from puro_pockets.domain.pockets import (
    Behavior,
    Pocket,
    find_pocket,
    is_plain_int,
    normalize_name,
    ordered_active,
    parse_behavior,
    validate_group,
    validate_pocket_name,
)
from puro_pockets.domain.rebalance import (
    Strategy,
    parse_strategy,
    rebalance_add,
    rebalance_remove,
    validate_share,
)
from puro_pockets.services.ledger_core import BehaviorName, LedgerCore, LedgerData, logger
from puro_pockets.services.records import LedgerSnapshot, NewPocket, Operation, OperationTaken

NEW = "__bolsa_nueva__"  # clave de la bolsa que aún no existe


def _require_empty(figures: PocketFigures) -> None:
    """RN-18: saldo (acumulable) o disponible del mes (consumo) exactamente cero."""
    if figures.amount != 0:
        kind = "saldo" if figures.pocket.behavior is Behavior.ACUMULABLE else "disponible del mes"
        raise PocketNotEmpty(kind)


class Share(BaseModel):
    pocket: str
    percentage: int


class MonthShares(BaseModel):
    month: str
    source_month: str | None = Field(
        description="Mes del que venían los porcentajes anteriores (RN-03); null si no había."
    )
    previous: list[Share]
    new: list[Share] = Field(description="Conjunto completo nuevo; suma exactamente 100.")


class RebalanceResult(BaseModel):
    action: Literal["crear", "archivar"]
    strategy: Literal["proporcional", "desde_una_bolsa", "manual"]
    months: list[MonthShares] = Field(
        description="Crear: solo el mes objetivo. Archivar: el mes actual y cada mes futuro con "
        "porcentajes propios."
    )
    note: str | None = None


class PocketInfo(BaseModel):
    name: str
    behavior: BehaviorName
    group: str | None


class CreatePocketResult(BaseModel):
    saved: bool = Field(description="True solo si se creó; false es la vista previa.")
    pocket: PocketInfo
    rebalance: RebalanceResult
    preview_token: str | None = Field(
        description="Solo en la vista previa: create_bolsa con confirm=true lo exige."
    )


class ArchivePocketResult(BaseModel):
    saved: bool = Field(description="True solo si se archivó; false es la vista previa.")
    pocket: str
    rebalance: RebalanceResult
    archived_goals: list[str] = Field(description="Metas (M-n) que se archivan con la bolsa.")
    preview_token: str | None = Field(
        description="Solo en la vista previa: archive_bolsa con confirm=true lo exige."
    )


def _blank(value: object) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _token(kind: str, payload: dict) -> str:
    canonical = json.dumps({"kind": kind, **payload}, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode()).hexdigest()[:24]


def _manual_pairs(percentages: Sequence[tuple[object, object]] | None) -> list[tuple[str, int]]:
    pairs = []
    for name, value in percentages or []:
        if not isinstance(name, str) or not name.strip():
            raise DomainError("Cada bolsa se indica por su nombre.")
        pairs.append((name, validate_share(value, name.strip())))
    return pairs


class PocketsMixin(LedgerCore):
    # --- Cálculo compartido ---

    def _shares(self, month: Month) -> tuple[Month | None, list[tuple[Pocket, int]]]:
        """Porcentajes vigentes de `month` (propios o heredados, RN-03) de las bolsas activas."""
        pockets = self._store.list_pockets()
        source = pick_source_month(month, self._store.allocation_months(month))
        rows = self._store.allocation_rows(source) if source else {}
        resolved = resolve_allocation(month, source, rows, pockets)
        return source, list(resolved.items)

    def _target_month(self, month: object, default_next: bool) -> Month:
        current = Month.of(self._today())
        if _blank(month):
            return current.next() if default_next else current
        target = Month.parse(month)
        if target < current:
            raise DomainError(
                f"{target} es un mes pasado: los porcentajes solo cambian desde el mes actual "
                f"({current}) en adelante (RN-02)."
            )
        return target

    @staticmethod
    def _manual_map(
        pairs: list[tuple[str, int]], active: list[Pocket], new_name: str | None
    ) -> dict[object, int]:
        by_name: dict[str, object] = {normalize_name(p.name): p for p in active}
        if new_name is not None:
            by_name[normalize_name(new_name)] = NEW
        result: dict[object, int] = {}
        for name, value in pairs:
            key = by_name.get(normalize_name(name))
            if key is None:
                raise DomainError(f"La bolsa '{name.strip()}' no existe o está archivada.")
            if key in result:
                raise DomainError(f"La bolsa '{name.strip()}' aparece más de una vez.")
            result[key] = value
        return result

    @staticmethod
    def _label(key: object, new_name: str | None) -> str:
        return new_name if key == NEW else key.name  # type: ignore[union-attr]

    def _month_shares(
        self,
        month: Month,
        source: Month | None,
        before: Sequence[tuple[Pocket, int]],
        after: Sequence[tuple[object, int]],
        new_name: str | None = None,
    ) -> MonthShares:
        return MonthShares(
            month=str(month),
            source_month=str(source) if source else None,
            previous=[Share(pocket=p.name, percentage=pct) for p, pct in before],
            new=[Share(pocket=self._label(k, new_name), percentage=pct) for k, pct in after],
        )

    def _plan_create(
        self,
        name: str,
        share: object,
        strategy: Strategy,
        source_pocket: object,
        percentages: list[tuple[str, int]],
        month: Month,
    ) -> tuple[RebalanceResult, dict[int, int], int]:
        pockets = self._store.list_pockets()
        if any(normalize_name(p.name) == normalize_name(name) for p in pockets):
            raise PocketAlreadyExists()
        active = ordered_active(pockets)
        source, before = self._shares(month)
        if source is None and strategy is not Strategy.MANUAL:
            raise DomainError(
                f"No hay porcentajes definidos para {month} ni para un mes anterior: usa la "
                "estrategia manual con el reparto completo."
            )
        current = before if source else [(p, 0) for p in active]
        donor = None if _blank(source_pocket) else find_pocket(active, source_pocket)
        manual = (
            self._manual_map(percentages, active, name) if strategy is Strategy.MANUAL else None
        )
        new_share = 0 if strategy is Strategy.MANUAL and _blank(share) else share
        # En manual, `current` solo aporta las claves (todas las activas); los porcentajes salen
        # del reparto indicado, así funciona también sin porcentajes previos
        after = rebalance_add(current, NEW, new_share, strategy, donor, manual)  # type: ignore[arg-type]
        later = self._store.future_allocation_months(month)
        note = (
            f"Aplica desde {month}. Los repartos ya guardados no cambian (cada uno guarda el "
            "porcentaje que usó)."
        )
        if later:
            note += (
                " Estos meses ya tienen porcentajes propios y la bolsa nueva quedará en 0 % en "
                f"ellos hasta que los cambies: {', '.join(str(m) for m in later)}."
            )
        result = RebalanceResult(
            action="crear",
            strategy=strategy.value,
            months=[self._month_shares(month, source, before, after, name)],
            note=note,
        )
        existing = {k.id: pct for k, pct in after if k != NEW}  # type: ignore[union-attr]
        return result, existing, dict(after)[NEW]

    def _plan_archive(
        self,
        pocket: Pocket,
        strategy: Strategy,
        receiver: object,
        percentages: list[tuple[str, int]],
    ) -> tuple[RebalanceResult, dict[Month, dict[int, int]]]:
        active = ordered_active(self._store.list_pockets())
        rest = [p for p in active if p.id != pocket.id]
        to = None if _blank(receiver) else find_pocket(rest, receiver)
        manual = self._manual_map(percentages, rest, None) if strategy is Strategy.MANUAL else None
        current = Month.of(self._today())
        months = [current, *self._store.future_allocation_months(current)]
        plan: dict[Month, dict[int, int]] = {}
        shown = []
        for month in months:
            source, before = self._shares(month)
            if source is None:
                continue  # sin porcentajes en ningún mes: nada que redistribuir
            after = rebalance_remove(before, pocket, strategy, to, manual)
            plan[month] = {p.id: pct for p, pct in after}
            shown.append(self._month_shares(month, source, before, after))
        result = RebalanceResult(
            action="archivar",
            strategy=strategy.value,
            months=shown,
            note="Archivar es inmediato: los porcentajes del mes actual y de cada mes futuro con "
            "porcentajes propios quedan sin la bolsa. Los meses pasados no cambian.",
        )
        return result, plan

    # --- preview_rebalance ---

    async def preview_rebalance(
        self,
        strategy: object,
        new_pocket: object = None,
        new_percentage: object = None,
        archive_pocket: object = None,
        from_pocket: object = None,
        percentages: Sequence[tuple[object, object]] | None = None,
        month: object = None,
    ) -> RebalanceResult:
        """Calcula el reajuste al crear (`new_pocket`) o archivar (`archive_pocket`); no guarda."""
        plan = parse_strategy(strategy)
        pairs = _manual_pairs(percentages)
        if _blank(new_pocket) == _blank(archive_pocket):
            raise DomainError("Indica new_pocket (para crear) o archive_pocket (para archivar).")
        if not _blank(new_pocket):
            name = validate_pocket_name(new_pocket)
            target = self._target_month(month, default_next=True)
            share = 0 if new_percentage is None and plan is Strategy.MANUAL else new_percentage
            result, _, _ = await self._run(
                partial(self._plan_create, name, share, plan, from_pocket, pairs, target)
            )
            return result
        self._archive_month(month)

        def run() -> RebalanceResult:
            pocket = find_pocket(self._store.list_pockets(), archive_pocket)
            return self._plan_archive(pocket, plan, from_pocket, pairs)[0]

        return await self._run(run)

    def _archive_month(self, month: object) -> None:
        current = Month.of(self._today())
        if _blank(month):
            return
        target = Month.parse(month)
        if target < current:
            raise DomainError(f"{target} es un mes pasado; los meses pasados no cambian (RN-02).")
        if target > current:
            raise DomainError(
                "Archivar es inmediato: la redistribución empieza en el mes actual "
                f"({current}). Si empezara después, el mes actual seguiría repartiendo a una "
                "bolsa archivada."
            )

    # --- create_bolsa (RN-13 a RN-15) ---

    async def create_bolsa(
        self,
        name: object,
        behavior: object,
        percentage: object = None,
        strategy: object = "proporcional",
        from_pocket: object = None,
        percentages: Sequence[tuple[object, object]] | None = None,
        group: object = None,
        month: object = None,
        confirm: bool = False,
        operation_id: object = None,
        preview_token: object = None,
    ) -> CreatePocketResult:
        clean = validate_pocket_name(name)
        kind = parse_behavior(behavior)
        group_name = validate_group(group)
        plan = parse_strategy(strategy)
        pairs = _manual_pairs(percentages)
        if plan is not Strategy.MANUAL and percentage is None:
            raise DomainError("Indica el porcentaje de la bolsa nueva (entero de 0 a 100).")
        if percentage is not None and not is_plain_int(percentage):
            validate_share(percentage)
        target = self._target_month(month, default_next=True)
        operation = None
        if confirm:
            op_id = validate_operation_id(operation_id)
            payload = {
                "name": normalize_name(clean),
                "behavior": kind.value,
                "group": group_name,
                "percentage": percentage,
                "strategy": plan.value,
                "from_pocket": None if _blank(from_pocket) else normalize_name(str(from_pocket)),
                "percentages": sorted([normalize_name(n), v] for n, v in pairs),
                "month": str(target),
            }
            operation = Operation(op_id, "create_bolsa", fingerprint("create_bolsa", payload))
        return await self._run(
            partial(
                self._create_bolsa,
                clean,
                kind,
                group_name,
                percentage,
                plan,
                from_pocket,
                pairs,
                target,
                operation,
                preview_token,
            )
        )

    def _create_bolsa(
        self,
        name: str,
        kind: Behavior,
        group: str | None,
        percentage: object,
        plan: Strategy,
        from_pocket: object,
        pairs: list[tuple[str, int]],
        month: Month,
        operation: Operation | None,
        token: object,
    ) -> CreatePocketResult:
        if operation is not None:
            replay = self._replay(operation)
            if replay is not None:
                return CreatePocketResult.model_validate(replay)
        share = 0 if percentage is None else percentage
        rebalance, existing, new_share = self._plan_create(
            name, share, plan, from_pocket, pairs, month
        )
        expected = _token(
            "create_bolsa",
            {
                "name": normalize_name(name),
                "behavior": kind.value,
                "group": group,
                "months": rebalance.model_dump(mode="json")["months"],
            },
        )
        preview = CreatePocketResult(
            saved=False,
            pocket=PocketInfo(name=name, behavior=kind.value, group=group),
            rebalance=rebalance,
            preview_token=expected,
        )
        if operation is None:
            return preview
        if not isinstance(token, str) or token.strip() != expected:
            raise PreviewRequired()
        result = preview.model_copy(update={"saved": True, "preview_token": None})
        new = NewPocket(name, kind, group, month, existing, new_share)
        try:
            response = self._store.create_pocket(
                new, operation, lambda _id: result.model_dump(mode="json")
            )
        except OperationTaken:
            return CreatePocketResult.model_validate(self._after_race(operation))
        logger.info("Bolsa creada: comportamiento=%s desde=%s", kind.value, month)
        return CreatePocketResult.model_validate(response)

    # --- archive_bolsa (RN-16 a RN-18) ---

    async def archive_bolsa(
        self,
        name: object,
        strategy: object = "proporcional",
        to_pocket: object = None,
        percentages: Sequence[tuple[object, object]] | None = None,
        month: object = None,
        confirm: bool = False,
        operation_id: object = None,
        preview_token: object = None,
    ) -> ArchivePocketResult:
        plan = parse_strategy(strategy)
        pairs = _manual_pairs(percentages)
        self._archive_month(month)
        operation = None
        if confirm:
            op_id = validate_operation_id(operation_id)
            payload = {
                "pocket": normalize_name(str(name)),
                "strategy": plan.value,
                "to_pocket": None if _blank(to_pocket) else normalize_name(str(to_pocket)),
                "percentages": sorted([normalize_name(n), v] for n, v in pairs),
            }
            operation = Operation(op_id, "archive_bolsa", fingerprint("archive_bolsa", payload))
        return await self._run(
            partial(self._archive_bolsa, name, plan, to_pocket, pairs, operation, preview_token)
        )

    def _archive_bolsa(
        self,
        name: object,
        plan: Strategy,
        to_pocket: object,
        pairs: list[tuple[str, int]],
        operation: Operation | None,
        token: object,
    ) -> ArchivePocketResult:
        if operation is not None:
            replay = self._replay(operation)
            if replay is not None:
                return ArchivePocketResult.model_validate(replay)
        pockets = self._store.list_pockets()
        pocket = find_pocket(pockets, name)
        current = Month.of(self._today())
        _require_empty(self._data().figures(pocket, current))
        rebalance, months = self._plan_archive(pocket, plan, to_pocket, pairs)
        goals = [
            g.reference
            for g in self._store.list_goals()
            if g.pocket_id == pocket.id and not g.archived
        ]
        expected = _token(
            "archive_bolsa",
            {"pocket": pocket.id, "months": rebalance.model_dump(mode="json")["months"]},
        )
        preview = ArchivePocketResult(
            saved=False,
            pocket=pocket.name,
            rebalance=rebalance,
            archived_goals=goals,
            preview_token=expected,
        )
        if operation is None:
            return preview
        if not isinstance(token, str) or token.strip() != expected:
            raise PreviewRequired()
        result = preview.model_copy(update={"saved": True, "preview_token": None})

        def verify(snapshot: LedgerSnapshot) -> None:
            # Con la bolsa bloqueada: una transferencia simultánea hacia ella no la deja con dinero
            data = LedgerData(snapshot.entries, snapshot.expenses, snapshot.transfers)
            _require_empty(data.figures(pocket, current))

        try:
            response = self._store.archive_pocket(
                pocket.id,
                self._now(),
                months,
                operation,
                lambda: result.model_dump(mode="json"),
                verify,
            )
        except OperationTaken:
            return ArchivePocketResult.model_validate(self._after_race(operation))
        logger.info("Bolsa archivada: meses_reajustados=%d metas=%d", len(months), len(goals))
        return ArchivePocketResult.model_validate(response)
