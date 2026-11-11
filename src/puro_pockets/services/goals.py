"""Metas de ahorro (Hito 7; sección 7, RN-19 a RN-25, RN-28, RN-29).

Una meta es un objetivo sobre el dinero de una bolsa acumulable, sin dinero propio (RN-23, RN-25):
crearla o cambiarla no mueve ningún saldo, y su avance es `accumulated_balance` (11.2), la misma
función de `get_bolsa_status`. El paso a `lograda` lo decide `domain.goals.reached` dentro de la
transacción de cada operación que sube un saldo (RN-24). La app entrega los números del RN-28; la
proyección y la sugerencia sobre el excedente (RN-29) las hace Claude, con confirmación.

Los registros no incluyen montos ni nombres de metas (solo M-n).
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date
from functools import partial
from typing import Literal

from pydantic import BaseModel, Field

from puro_pockets.domain.errors import (
    DomainError,
    GoalAlreadyActive,
    GoalClosed,
    GoalNeedsSavingsPocket,
    GoalNotFound,
)
from puro_pockets.domain.goals import (
    Goal,
    GoalRef,
    GoalStatus,
    balance_function,
    net_monthly_change,
    progress,
    reached,
    validate_goal_name,
    validate_target_amount,
    validate_target_date,
)
from puro_pockets.domain.idempotency import fingerprint, validate_operation_id
from puro_pockets.domain.ledger import parse_date
from puro_pockets.domain.months import Month
from puro_pockets.domain.pockets import Behavior, find_pocket, normalize_name
from puro_pockets.services.ledger_core import LedgerCore, logger
from puro_pockets.services.records import GoalChange, NewGoal, Operation, OperationTaken

GoalStatusName = Literal["activa", "lograda", "pausada"]


class GoalResult(BaseModel):
    saved: bool
    reference: str = Field(description="Referencia de la meta (M-n).")
    pocket: str
    name: str
    target_amount: int = Field(description="Colones.")
    target_date: str | None
    status: GoalStatusName
    achieved_on: str | None
    balance: int = Field(description="Saldo de la bolsa = avance de la meta (RN-23).")
    percent: int = Field(description="Avance en %, con tope de 100.")
    missing: int = Field(description="Faltante: max(0, objetivo − saldo).")
    note: str | None = None


class GoalProgressItem(BaseModel):
    reference: str
    pocket: str
    name: str
    status: GoalStatusName
    target_amount: int
    target_date: str | None
    achieved_on: str | None
    balance: int = Field(description="Saldo de la bolsa (11.2) = avance.")
    percent: int = Field(description="Avance en %, con tope de 100.")
    missing: int
    excess: int = Field(description="Saldo por encima del objetivo; se queda en la bolsa (RN-29).")
    months_considered: int = Field(
        description="RN-28: meses calendario completos usados (hasta 3)."
    )
    avg_monthly_net_change: int | None = Field(
        description="RN-28: promedio mensual de la variación neta del saldo; null sin meses."
    )
    projectable: bool = Field(
        description="RN-28: true si hay al menos un mes completo y el promedio es positivo. La "
        "proyección la calcula Claude; la app no estima fechas."
    )


class GoalsProgressResult(BaseModel):
    month: str = Field(description="Mes actual.")
    items: list[GoalProgressItem]


def _blank(value: object) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


class GoalsMixin(LedgerCore):
    def _balances(self):
        return balance_function(self._store.allocation_entries(), self._store.expense_entries())

    def _goal_result(self, goal: Goal, pocket_name: str, balance: int, saved: bool, note=None):
        figures = progress(goal, balance)
        return GoalResult(
            saved=saved,
            reference=goal.reference,
            pocket=pocket_name,
            name=goal.name,
            target_amount=goal.target_amount,
            target_date=goal.target_date.isoformat() if goal.target_date else None,
            status=goal.status.value,
            achieved_on=goal.achieved_on.isoformat() if goal.achieved_on else None,
            balance=balance,
            percent=figures.percent,
            missing=figures.missing,
            note=note,
        )

    @staticmethod
    def _settled(goal: Goal, balance: int, on: date) -> Goal:
        """Lo que hará el almacén al evaluar (misma regla `reached`): para la respuesta."""
        hit = reached([goal], lambda _pocket: balance, on)
        return replace(goal, status=GoalStatus.ACHIEVED, achieved_on=hit[0][1]) if hit else goal

    # --- create_goal (RN-19 a RN-22) ---

    async def create_goal(
        self,
        pocket: object,
        name: object,
        target_amount: object,
        operation_id: object,
        target_date: object = None,
    ) -> GoalResult:
        op_id = validate_operation_id(operation_id)
        clean = validate_goal_name(name)
        target = validate_target_amount(target_amount)
        when = validate_target_date(parse_date(target_date, "objetivo"), self._today())
        payload = {
            "pocket": normalize_name(str(pocket)),
            "name": clean,
            "target_amount": target,
            "target_date": when.isoformat() if when else None,
        }
        operation = Operation(op_id, "create_goal", fingerprint("create_goal", payload))
        return await self._run(partial(self._create_goal, pocket, clean, target, when, operation))

    def _create_goal(
        self, pocket: object, name: str, target: int, when: date | None, operation: Operation
    ) -> GoalResult:
        replay = self._replay(operation)
        if replay is not None:
            return GoalResult.model_validate(replay)
        bag = find_pocket(self._store.list_pockets(), pocket)  # activa (RN-21)
        if bag.behavior is not Behavior.ACUMULABLE:
            raise GoalNeedsSavingsPocket()
        current = next(
            (g for g in self._store.list_goals() if g.live and g.pocket_id == bag.id), None
        )
        if current is not None:
            raise GoalAlreadyActive(current.reference)
        today = self._today()
        balance = self._balances()(bag.id)

        def respond(goal_id: int) -> dict:
            draft = Goal(goal_id, bag.id, name, target, when, GoalStatus.ACTIVE, None, today)
            goal = self._settled(draft, balance, today)
            note = None
            if goal.status is GoalStatus.ACHIEVED:
                note = (
                    "El saldo de la bolsa ya alcanza el objetivo: la meta queda lograda desde hoy "
                    "(RN-24). El excedente se queda en la bolsa (RN-29)."
                )
            return self._goal_result(goal, bag.name, balance, True, note).model_dump(mode="json")

        new = NewGoal(bag.id, name, target, when, today)
        try:
            response = self._store.create_goal(new, operation, respond, today)
        except OperationTaken:
            return GoalResult.model_validate(self._after_race(operation))
        result = GoalResult.model_validate(response)
        logger.info("Meta creada: ref=%s estado=%s", result.reference, result.status)
        return result

    # --- update_goal ---

    async def update_goal(
        self,
        goal: object,
        operation_id: object,
        target_amount: object = None,
        target_date: object = None,
        clear_target_date: bool = False,
        action: object = None,
    ) -> GoalResult:
        ref = GoalRef.parse(goal)
        op_id = validate_operation_id(operation_id)
        target = None if target_amount is None else validate_target_amount(target_amount)
        when = validate_target_date(parse_date(target_date, "objetivo"), self._today())
        verb = None if _blank(action) else str(action).strip().casefold()
        if verb not in (None, "pausar", "reactivar"):
            raise DomainError("La acción debe ser pausar o reactivar.")
        if when is not None and clear_target_date:
            raise DomainError("Indica una fecha objetivo nueva o quítala, no ambas cosas.")
        if target is None and when is None and not clear_target_date and verb is None:
            raise DomainError("Indica qué cambiar: monto objetivo, fecha, pausar o reactivar.")
        payload = {
            "goal": str(ref),
            "target_amount": target,
            "target_date": when.isoformat() if when else None,
            "clear_target_date": bool(clear_target_date),
            "action": verb,
        }
        operation = Operation(op_id, "update_goal", fingerprint("update_goal", payload))
        return await self._run(
            partial(self._update_goal, ref, target, when, bool(clear_target_date), verb, operation)
        )

    def _update_goal(
        self,
        ref: GoalRef,
        target: int | None,
        when: date | None,
        clear: bool,
        verb: str | None,
        operation: Operation,
    ) -> GoalResult:
        replay = self._replay(operation)
        if replay is not None:
            return GoalResult.model_validate(replay)
        goals = self._store.list_goals()
        goal = next((g for g in goals if g.id == ref.number), None)
        if goal is None:
            raise GoalNotFound(str(ref))
        if goal.archived:
            raise GoalClosed(str(ref), "está archivada con su bolsa")
        if goal.status is GoalStatus.ACHIEVED:
            raise GoalClosed(str(ref), "ya está lograda y se queda así (RN-24)")
        status = None
        if verb == "pausar":
            if goal.status is not GoalStatus.ACTIVE:
                raise DomainError(f"La meta {ref} no está activa: no se puede pausar.")
            status = GoalStatus.PAUSED
        elif verb == "reactivar":
            if goal.status is not GoalStatus.PAUSED:
                raise DomainError(f"La meta {ref} no está pausada: no se puede reactivar.")
            other = next((g for g in goals if g.live and g.pocket_id == goal.pocket_id), None)
            if other is not None:
                raise GoalAlreadyActive(other.reference)
            status = GoalStatus.ACTIVE
        today = self._today()
        names = {p.id: p.name for p in self._store.list_pockets()}
        balance = self._balances()(goal.pocket_id)
        updated = replace(
            goal,
            target_amount=target if target is not None else goal.target_amount,
            target_date=None if clear else (when or goal.target_date),
            status=status or goal.status,
        )
        final = self._settled(updated, balance, today)
        note = None
        if final.status is GoalStatus.ACHIEVED:
            note = "Con este cambio el saldo alcanza el objetivo: la meta queda lograda (RN-24)."
        change = GoalChange(goal.id, target, when, clear, status)
        result = self._goal_result(final, names.get(goal.pocket_id, "?"), balance, True, note)
        try:
            response = self._store.update_goal(
                change, operation, lambda: result.model_dump(mode="json"), today
            )
        except OperationTaken:
            return GoalResult.model_validate(self._after_race(operation))
        logger.info("Meta actualizada: ref=%s estado=%s", ref, final.status.value)
        return GoalResult.model_validate(response)

    # --- get_goal_progress (11.3, RN-28, RN-29) ---

    async def get_goal_progress(self, pocket: object = None) -> GoalsProgressResult:
        return await self._run(partial(self._goal_progress, pocket))

    def _goal_progress(self, pocket: object) -> GoalsProgressResult:
        pockets = self._store.list_pockets()
        names = {p.id: p.name for p in pockets}
        goals = [g for g in self._store.list_goals() if not g.archived]
        if _blank(pocket):
            chosen = [g for g in goals if g.status is GoalStatus.ACTIVE]
        else:
            bag = find_pocket(pockets, pocket)
            order = {GoalStatus.ACTIVE: 0, GoalStatus.ACHIEVED: 1, GoalStatus.PAUSED: 2}
            chosen = sorted(
                (g for g in goals if g.pocket_id == bag.id), key=lambda g: (order[g.status], -g.id)
            )
        entries = self._store.allocation_entries()
        expenses = self._store.expense_entries()
        balance_of = balance_function(entries, expenses)
        current = Month.of(self._today())
        items = []
        for goal in chosen:
            balance = balance_of(goal.pocket_id)
            figures = progress(goal, balance)
            change = net_monthly_change(entries, expenses, goal.pocket_id, current)
            items.append(
                GoalProgressItem(
                    reference=goal.reference,
                    pocket=names.get(goal.pocket_id, "?"),
                    name=goal.name,
                    status=goal.status.value,
                    target_amount=goal.target_amount,
                    target_date=goal.target_date.isoformat() if goal.target_date else None,
                    achieved_on=goal.achieved_on.isoformat() if goal.achieved_on else None,
                    balance=balance,
                    percent=figures.percent,
                    missing=figures.missing,
                    excess=max(0, balance - goal.target_amount),
                    months_considered=change.months,
                    avg_monthly_net_change=change.average,
                    projectable=change.projectable,
                )
            )
        return GoalsProgressResult(month=str(current), items=items)
