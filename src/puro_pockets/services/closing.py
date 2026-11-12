"""Cierre de mes (Hito 9; sección 10, RN-44, RN-46 a RN-53, RN-58; 6.5).

- `preview_month_close` no guarda nada (principio 3.2). Sin propuesta devuelve los datos del mes;
  con propuesta (coberturas y destinos) la valida, devuelve el resultado completo y una ficha.
- `close_month` sin `confirm=true` devuelve la misma vista previa; con `confirm=true` exige la ficha
  y guarda todo en una transacción (RN-46): el almacén toma el bloqueo exclusivo de cierres, bloquea
  las bolsas, vuelve a leer el estado y este módulo lo recalcula con las mismas funciones; si algo
  cambió desde la vista previa, se rechaza y no se guarda nada.
- `set_surplus_destination` guarda el destino de sobrante sugerido (6.5): solo un dato para la
  vista previa; la app no recomienda (principio 3.1), la propuesta la arma Claude.

La ficha tiene dos mitades: la huella de la propuesta y la del estado (cifras de las bolsas, metas
activas y extras pendientes). Así se distingue "confirmar sin vista previa" de "el estado cambió".
Los registros no incluyen montos, notas, nombres de bolsas ni de metas.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from functools import partial
from typing import Literal

from pydantic import BaseModel, Field

from puro_pockets.domain.balances import PocketFigures
from puro_pockets.domain.closures import (
    AdjustmentKind,
    ClosePlan,
    MonthPicture,
    analyze,
    check_closable,
    default_close_month,
    last_day,
    parse_moves,
    plan_close,
    require_month,
)
from puro_pockets.domain.errors import (
    ClosureProposalInvalid,
    ClosureStateChanged,
    DomainError,
    ExtrasPendingBlock,
    PreviewRequired,
)
from puro_pockets.domain.goals import progress
from puro_pockets.domain.idempotency import fingerprint, validate_operation_id
from puro_pockets.domain.ledger import MovementKind, MovementRef
from puro_pockets.domain.money import Currency, format_original
from puro_pockets.domain.months import Month
from puro_pockets.domain.pockets import Behavior, Pocket, find_pocket, normalize_name
from puro_pockets.domain.transfers import TransferRef
from puro_pockets.services.ledger_core import BalanceKindName, BehaviorName, LedgerCore, LedgerData
from puro_pockets.services.ledger_core import logger as ledger_logger
from puro_pockets.services.records import (
    ClosureSnapshot,
    ClosureWrite,
    Operation,
    OperationTaken,
)
from puro_pockets.services.transfers import TransferGoalEffect

logger = ledger_logger

NEXT_STEPS = (
    "Ritual de fin de mes (RN-51): con el mes cerrado, registra el salario del mes siguiente "
    "(preview_income y, con la aprobación del propietario, add_income) y, si cambian, ajusta los "
    "porcentajes del mes nuevo con set_allocation."
)


class ClosureAdjustmentItem(BaseModel):
    """Ajuste de cierre (RN-50, 10.2): lo que no se destinó o no se cubrió al cerrar."""

    pocket: str
    kind: Literal["sobrante_no_destinado", "sobregasto_no_cubierto"]
    amount: int = Field(description="Colones con signo: sobrante +, sobregasto −.")


class CloseGoal(BaseModel):
    reference: str = Field(description="Referencia de la meta (M-n).")
    target_amount: int
    percent: int = Field(description="Avance en %, con tope de 100.")
    missing: int


class CloseConsumption(BaseModel):
    pocket: str
    active: bool = Field(description="False si está archivada: no envía ni recibe en el cierre.")
    adjusted_budget: int = Field(description="Presupuesto ajustado del mes (9.1).")
    spent: int
    available: int = Field(description="Disponible del mes (11.1): sobrante (+) o déficit (−).")
    situation: Literal["sobrante", "deficit", "cero"]
    suggested_destination: str | None = Field(
        description="Destino de sobrante sugerido por el propietario (6.5), si existe."
    )


class CloseAccumulable(BaseModel):
    pocket: str
    balance: int = Field(description="Saldo (11.2).")
    goal: CloseGoal | None = Field(description="Su meta activa y su avance, si la tiene.")


class PendingRecurringNotice(BaseModel):
    """Aviso (no bloquea): gastos fijos del mes sin pagar."""

    count: int
    references: list[str] = Field(description="Referencias (F-n).")
    total_crc: int = Field(description="Σ de los pendientes en colones (solo los CRC).")
    usd_count: int
    usd_total: str = Field(description="Σ de los pendientes en USD, sin convertir.")


class CloseMoveItem(BaseModel):
    from_pocket: str
    to_pocket: str | None = Field(description="Null = sobrante no destinado.")
    amount: int
    from_balance: bool = Field(
        description="True si es una cobertura desde el saldo de una acumulable (RN-52)."
    )


class CloseOutcome(BaseModel):
    pocket: str
    behavior: BehaviorName
    balance_kind: BalanceKindName
    before: int = Field(description="Disponible del mes (consumo) o saldo (acumulable) antes.")
    after: int = Field(description="Después del cierre.")


class CloseTransferItem(BaseModel):
    reference: str | None = Field(description="T-n; null en la vista previa.")
    from_pocket: str
    to_pocket: str
    amount: int


class MonthCloseResult(BaseModel):
    saved: bool = Field(description="True solo si el mes quedó cerrado; false es la vista previa.")
    month: str | None = Field(description="Mes AAAA-MM; null si no hay ningún mes para cerrar.")
    closable: bool = Field(
        description="True si el mes se puede cerrar ahora (es su último día o después, va en "
        "orden y no tiene extras pendientes)."
    )
    next_closable_on: str | None = Field(
        default=None, description="Desde qué fecha se podrá cerrar, si todavía no se puede."
    )
    closed_at: str | None = Field(default=None, description="Instante del cierre (UTC).")
    blocked_by: list[str] = Field(
        default_factory=list,
        description="Extras pendientes del mes (I-n): bloquean el cierre; repártelos con "
        "confirm_allocation o anúlalos con void_transaction.",
    )
    warnings: list[str] = Field(description="Avisos para explicar al propietario.")
    consumption: list[CloseConsumption] = Field(default_factory=list)
    accumulable: list[CloseAccumulable] = Field(default_factory=list)
    pending_recurring: PendingRecurringNotice | None = None
    covers: list[CloseMoveItem] = Field(
        default_factory=list, description="Coberturas de déficits (primero, 10.1)."
    )
    destinations: list[CloseMoveItem] = Field(
        default_factory=list, description="Destinos de sobrantes (después, 10.1)."
    )
    outcomes: list[CloseOutcome] = Field(
        default_factory=list, description="Cómo queda cada bolsa con la propuesta."
    )
    goal_effects: list[TransferGoalEffect] = Field(
        default_factory=list, description="Efecto en el avance de las metas activas (RN-58)."
    )
    unassigned_surplus: list[ClosureAdjustmentItem] = Field(
        default_factory=list, description="Sobrante no destinado por bolsa (RN-50, 10.2)."
    )
    unassigned_surplus_total: int = 0
    uncovered_overspend: list[ClosureAdjustmentItem] = Field(
        default_factory=list, description="Sobregasto no cubierto por bolsa (RN-50)."
    )
    uncovered_overspend_total: int = 0
    transfers: list[CloseTransferItem] = Field(
        default_factory=list,
        description="Transferencias cierre_de_mes que se crean (con referencia, una vez guardado).",
    )
    goals_achieved: list[str] = Field(
        default_factory=list, description="Metas (M-n) que el cierre lleva a su objetivo."
    )
    preview_token: str | None = Field(
        default=None,
        description="Solo en la vista previa con propuesta y mes cerrable: envíalo a close_month "
        "con confirm=true tras la aprobación explícita del propietario.",
    )
    next_steps: str | None = Field(default=None, description="Qué sigue en el ritual (RN-51).")


class SurplusDestinationResult(BaseModel):
    pocket: str
    suggested_destination: str | None = Field(
        description="Acumulable sugerida para el sobrante (6.5); null si se quitó."
    )
    note: str


@dataclass(frozen=True)
class _View:
    result: MonthCloseResult
    plan: ClosePlan | None
    token: str | None


def _digest(kind: str, payload: object) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(f"close_month:{kind}:{canonical}".encode()).hexdigest()[:32]


def _normalized(raw: Sequence[Mapping[str, object]] | None) -> list[list[object]]:
    """Propuesta comparable para la clave de operación (nombres sin distinguir mayúsculas)."""
    items = []
    for item in raw or ():
        if not isinstance(item, Mapping):
            items.append([repr(item)])
            continue
        target = item.get("to_pocket")
        items.append(
            [
                normalize_name(str(item.get("from_pocket"))),
                None if target is None else normalize_name(str(target)),
                repr(item.get("amount")),
            ]
        )
    return sorted(items, key=repr)


def _state(snapshot: ClosureSnapshot, figures: Mapping[int, PocketFigures]) -> list[object]:
    """La instantánea del estado que cubre la ficha (PROPUESTO 9)."""
    pockets = [
        [
            p.id,
            p.active,
            p.behavior.value,
            figures[p.id].assigned,
            figures[p.id].transfers_in,
            figures[p.id].transfers_out,
            figures[p.id].spent,
            figures[p.id].amount,
        ]
        for p in snapshot.pockets
    ]
    goals = [[g.id, g.pocket_id, g.target_amount, g.status.value] for g in snapshot.goals if g.live]
    return [pockets, goals, snapshot.pending_extras]


class ClosingMixin(LedgerCore):
    """Casos de uso del cierre de mes. Las cifras salen siempre de `pocket_figures`."""

    async def preview_month_close(
        self,
        month: object = None,
        covers: Sequence[Mapping[str, object]] | None = None,
        destinations: Sequence[Mapping[str, object]] | None = None,
    ) -> MonthCloseResult:
        proposal = covers is not None or destinations is not None
        return await self._run(
            partial(self._close, month, covers or [], destinations or [], proposal, None, None)
        )

    async def close_month(
        self,
        month: object,
        covers: Sequence[Mapping[str, object]] | None = None,
        destinations: Sequence[Mapping[str, object]] | None = None,
        confirm: bool = False,
        preview_token: object = None,
        operation_id: object = None,
    ) -> MonthCloseResult:
        target = require_month(month)
        operation = None
        if confirm:
            op_id = validate_operation_id(operation_id)
            payload = {
                "month": str(target),
                "covers": _normalized(covers),
                "destinations": _normalized(destinations),
            }
            operation = Operation(op_id, "close_month", fingerprint("close_month", payload))
        return await self._run(
            partial(
                self._close,
                str(target),
                covers or [],
                destinations or [],
                True,
                operation,
                preview_token,
            )
        )

    # --- Cálculo (sin guardar) ---

    def _close(
        self,
        month: object,
        covers: Sequence[Mapping[str, object]],
        destinations: Sequence[Mapping[str, object]],
        proposal: bool,
        operation: Operation | None,
        token: object,
    ) -> MonthCloseResult:
        if operation is not None:
            replay = self._replay(operation)
            if replay is not None:
                return MonthCloseResult.model_validate(replay)
        today = self._today()
        if month is None or (isinstance(month, str) and not month.strip()):
            state = self._store.closure_state()
            target = default_close_month(today, state)
            if target is None:
                first = state.first_closable()
                return MonthCloseResult(
                    saved=False,
                    month=None,
                    closable=False,
                    next_closable_on=last_day(first).isoformat() if first else None,
                    warnings=["Todavía no hay ningún mes para cerrar."],
                )
        else:
            target = Month.parse(month)
        snapshot = self._store.closure_snapshot(target)
        sent = token.strip() if isinstance(token, str) else None
        view = self._view(
            snapshot, covers, destinations, proposal, strict=operation is not None, sent=sent
        )
        if operation is None:
            return view.result.model_copy(update={"preview_token": view.token})
        if not isinstance(token, str) or len(token.strip()) != 64:
            raise PreviewRequired("coberturas y destinos")
        assert view.token is not None  # strict: cerrable, sin bloqueos y con propuesta
        sent = token.strip()
        if sent[:32] != view.token[:32]:
            raise PreviewRequired("coberturas y destinos")
        if sent != view.token:
            raise ClosureStateChanged()
        return self._save(target, covers, destinations, operation, view.token)

    def _view(
        self,
        snapshot: ClosureSnapshot,
        covers: Sequence[Mapping[str, object]],
        destinations: Sequence[Mapping[str, object]],
        proposal: bool,
        strict: bool,
        sent: str | None = None,
    ) -> _View:
        """Calcula la vista previa. Con `strict` (al confirmar) exige que el mes sea cerrable y sin
        extras pendientes; si la propuesta ya no cuadra pero `sent` es la ficha de esa misma
        propuesta, el estado cambió desde la vista previa (`ClosureStateChanged`)."""
        month = snapshot.month
        today = self._today()
        check_closable(month, today, snapshot.state, allow_early=not strict)
        blocked = [str(MovementRef(MovementKind.INCOME, i)) for i in snapshot.pending_extras]
        if strict and blocked:
            raise ExtrasPendingBlock(str(month), blocked)
        early = today < last_day(month)
        data = LedgerData(snapshot.entries, snapshot.expenses, snapshot.transfers)
        figures = {p.id: data.figures(p, month) for p in snapshot.pockets}
        picture = analyze(month, snapshot.pockets, figures, snapshot.goals)
        plan = None
        proposal_digest = None
        if proposal:
            cover_moves = parse_moves(covers, snapshot.pockets, allow_null=False)
            dest_moves = parse_moves(destinations, snapshot.pockets, allow_null=True)
            moves = [
                [m.source.id, None if m.target is None else m.target.id, m.amount]
                for m in (*cover_moves, *dest_moves)
            ]
            proposal_digest = _digest("proposal", [str(month), moves])
            try:
                plan = plan_close(picture, cover_moves, dest_moves)
            except ClosureProposalInvalid:
                if strict and sent is not None and sent[:32] == proposal_digest:
                    raise ClosureStateChanged() from None
                raise
        closable = not early and not blocked
        result = self._result(snapshot, picture, plan, closable, early, blocked)
        token = None
        if plan is not None and closable and proposal_digest is not None:
            token = proposal_digest + _digest("state", _state(snapshot, figures))
        return _View(result, plan, token)

    def _result(
        self,
        snapshot: ClosureSnapshot,
        picture: MonthPicture,
        plan: ClosePlan | None,
        closable: bool,
        early: bool,
        blocked: list[str],
    ) -> MonthCloseResult:
        month = snapshot.month
        names = {p.id: p for p in snapshot.pockets}
        warnings = list(plan.warnings) if plan is not None else picture.warnings()
        if early:
            warnings.insert(
                0,
                f"Todavía no se puede cerrar: {month} se cierra desde su último día "
                f"({last_day(month).isoformat()}).",
            )
        if blocked:
            warnings.insert(
                0,
                "Hay extras pendientes del mes que bloquean el cierre: repártelos con "
                "confirm_allocation o anúlalos con void_transaction.",
            )
        pending = self._pending_recurring(month)
        notice = None
        if pending:
            usd = [p for p in pending if p.template.currency is Currency.USD]
            notice = PendingRecurringNotice(
                count=len(pending),
                references=[p.template.reference for p in pending],
                total_crc=sum(p.amount for p in pending if p.template.currency is Currency.CRC),
                usd_count=len(usd),
                usd_total=format_original(Currency.USD, sum(p.amount for p in usd)),
            )
            warnings.append(
                "Hay gastos fijos del mes sin pagar (no bloquean el cierre; si se pagan después, "
                "irán a un mes abierto)."
            )

        def suggested(pocket: Pocket) -> str | None:
            target = names.get(snapshot.surplus_targets.get(pocket.id, -1))
            if target is None or not target.active or target.behavior is not Behavior.ACUMULABLE:
                return None
            return target.name

        consumption = [
            CloseConsumption(
                pocket=line.pocket.name,
                active=line.pocket.active,
                adjusted_budget=line.figures.adjusted_budget,
                spent=line.figures.spent,
                available=line.available,
                situation=line.situation.value,
                suggested_destination=suggested(line.pocket),
            )
            for line in picture.consumption
        ]
        accumulable = []
        for line in picture.accumulable:
            goal = None
            if line.goal is not None:
                figures = progress(line.goal, line.balance)
                goal = CloseGoal(
                    reference=line.goal.reference,
                    target_amount=line.goal.target_amount,
                    percent=figures.percent,
                    missing=figures.missing,
                )
            accumulable.append(
                CloseAccumulable(pocket=line.pocket.name, balance=line.balance, goal=goal)
            )
        result = MonthCloseResult(
            saved=False,
            month=str(month),
            closable=closable,
            next_closable_on=last_day(month).isoformat() if early else None,
            blocked_by=blocked,
            warnings=warnings,
            consumption=consumption,
            accumulable=accumulable,
            pending_recurring=notice,
        )
        if plan is None:
            return result

        def move(m) -> CloseMoveItem:
            return CloseMoveItem(
                from_pocket=m.source.name,
                to_pocket=None if m.target is None else m.target.name,
                amount=m.amount,
                from_balance=m.from_balance,
            )

        def adjustment(kind: AdjustmentKind) -> list[ClosureAdjustmentItem]:
            return [
                ClosureAdjustmentItem(pocket=a.pocket.name, kind=a.kind.value, amount=a.amount)
                for a in plan.adjustments
                if a.kind is kind
            ]

        pocket_of_goal = {g.id: g.pocket_id for g in snapshot.goals}
        return result.model_copy(
            update={
                "covers": [move(m) for m in plan.covers],
                "destinations": [move(m) for m in plan.destinations],
                "outcomes": [
                    CloseOutcome(
                        pocket=o.pocket.name,
                        behavior=o.pocket.behavior.value,
                        balance_kind="saldo"
                        if o.pocket.behavior is Behavior.ACUMULABLE
                        else "disponible_del_mes",
                        before=o.before,
                        after=o.after,
                    )
                    for o in plan.outcomes
                ],
                "goal_effects": [
                    TransferGoalEffect(
                        reference=e.goal.reference,
                        pocket=names[pocket_of_goal[e.goal.id]].name,
                        percent_before=e.percent_before,
                        percent_after=e.percent_after,
                        missing_before=e.missing_before,
                        missing_after=e.missing_after,
                        completes=e.completes,
                    )
                    for e in plan.goal_effects
                ],
                "unassigned_surplus": adjustment(AdjustmentKind.UNASSIGNED_SURPLUS),
                "unassigned_surplus_total": plan.total(AdjustmentKind.UNASSIGNED_SURPLUS),
                "uncovered_overspend": adjustment(AdjustmentKind.UNCOVERED_OVERSPEND),
                "uncovered_overspend_total": plan.total(AdjustmentKind.UNCOVERED_OVERSPEND),
                "transfers": [
                    CloseTransferItem(
                        reference=None,
                        from_pocket=m.source.name,
                        to_pocket=m.target.name,  # type: ignore[union-attr]
                        amount=m.amount,
                    )
                    for m in plan.transfers
                ],
                "goals_achieved": [e.goal.reference for e in plan.goal_effects if e.completes],
            }
        )

    # --- Guardar ---

    def _save(
        self,
        month: Month,
        covers: Sequence[Mapping[str, object]],
        destinations: Sequence[Mapping[str, object]],
        operation: Operation,
        expected: str,
    ) -> MonthCloseResult:
        closed_at = self._now()

        def verify(snapshot: ClosureSnapshot) -> ClosureWrite:
            # Con el bloqueo exclusivo y las bolsas bloqueadas: se recalcula todo (RN-46)
            view = self._view(snapshot, covers, destinations, True, strict=True, sent=expected)
            if view.token != expected or view.plan is None:
                raise ClosureStateChanged()
            plan = view.plan

            def respond(transfer_ids: list[int]) -> dict:
                transfers = [
                    item.model_copy(update={"reference": str(TransferRef(tid))})
                    for item, tid in zip(view.result.transfers, transfer_ids, strict=True)
                ]
                return view.result.model_copy(
                    update={
                        "saved": True,
                        "closable": False,
                        "closed_at": closed_at.isoformat(),
                        "transfers": transfers,
                        "preview_token": None,
                        "next_steps": NEXT_STEPS,
                    }
                ).model_dump(mode="json")

            return ClosureWrite(
                [(m.source.id, m.target.id, m.amount) for m in plan.transfers],  # type: ignore[union-attr]
                [(a.pocket.id, a.kind.value, a.amount) for a in plan.adjustments],
                respond,
            )

        try:
            response = self._store.record_closure(
                month, closed_at, self._today(), operation, verify
            )
        except OperationTaken:
            return MonthCloseResult.model_validate(self._after_race(operation))
        result = MonthCloseResult.model_validate(response)
        logger.info(
            "Cierre registrado: mes=%s transferencias=%d ajustes=%d metas_afectadas=%d",
            result.month,
            len(result.transfers),
            len(result.unassigned_surplus) + len(result.uncovered_overspend),
            len(result.goal_effects),
        )
        return result

    # --- Destino de sobrante sugerido (6.5) ---

    async def set_surplus_destination(
        self, pocket: object, destination_pocket: object, operation_id: object
    ) -> SurplusDestinationResult:
        op_id = validate_operation_id(operation_id)
        clear = destination_pocket is None or (
            isinstance(destination_pocket, str) and not destination_pocket.strip()
        )
        payload = {
            "pocket": normalize_name(str(pocket)),
            "destination": None if clear else normalize_name(str(destination_pocket)),
        }
        operation = Operation(
            op_id, "set_surplus_destination", fingerprint("set_surplus_destination", payload)
        )

        def write() -> SurplusDestinationResult:
            replay = self._replay(operation)
            if replay is not None:
                return SurplusDestinationResult.model_validate(replay)
            pockets = self._store.list_pockets()
            source = find_pocket(pockets, pocket)
            if source.behavior is not Behavior.CONSUMO:
                raise DomainError(
                    f"La bolsa '{source.name}' no es de consumo: solo las bolsas de consumo tienen "
                    "sobrante al cerrar el mes (6.5)."
                )
            target = None if clear else find_pocket(pockets, destination_pocket)
            if target is not None and target.behavior is not Behavior.ACUMULABLE:
                raise DomainError(
                    f"El destino sugerido debe ser una bolsa acumulable activa, y '{target.name}' "
                    "no lo es (6.5)."
                )
            result = SurplusDestinationResult(
                pocket=source.name,
                suggested_destination=None if target is None else target.name,
                note="Es solo un dato para preview_month_close: no mueve dinero. Claude parte de "
                "ahí al proponer el cierre y el propietario decide.",
            )
            try:
                response = self._store.set_surplus_target(
                    source.id,
                    None if target is None else target.id,
                    operation,
                    lambda: result.model_dump(mode="json"),
                )
            except OperationTaken:
                return SurplusDestinationResult.model_validate(self._after_race(operation))
            logger.info("Destino de sobrante sugerido %s", "quitado" if clear else "guardado")
            return SurplusDestinationResult.model_validate(response)

        return await self._run(write)


__all__ = [
    "ClosingMixin",
    "ClosureAdjustmentItem",
    "MonthCloseResult",
    "SurplusDestinationResult",
]
