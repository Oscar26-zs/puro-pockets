"""Transferencias entre bolsas (Hito 8; sección 9, RN-39 a RN-44, RN-58). RN-45 está derogada.

- `preview_transfer` calcula sin guardar nada (principio 3.2): cómo quedan las dos bolsas (saldo o
  disponible y presupuesto ajustado del mes) y el efecto en el avance de sus metas activas (RN-58).
- `transfer_between_bolsas` sin `confirm=true` devuelve la misma vista previa; con `confirm=true`
  exige su `preview_token` y guarda de forma atómica. El almacén bloquea las dos bolsas, vuelve a
  validar RN-42 con lo que hay en ese momento y evalúa las metas en la misma transacción.

Siempre en colones y con la fecha de hoy; el mes es el de esa fecha, y un mes cerrado no admite
transferencias (RN-44). Las del cierre (`cierre_de_mes`) solo las crea `close_month`.
No hay tools para anular ni editar: un error se corrige con otra
transferencia en sentido contrario (RN-43). Los registros no incluyen montos, notas, nombres de
bolsas ni de metas.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date
from functools import partial
from typing import Literal

from pydantic import BaseModel, Field

from puro_pockets.domain.balances import PocketFigures, TransferEntry
from puro_pockets.domain.errors import PreviewRequired
from puro_pockets.domain.goals import Goal
from puro_pockets.domain.idempotency import fingerprint, validate_operation_id
from puro_pockets.domain.months import Month
from puro_pockets.domain.pockets import Behavior, Pocket, find_pocket, normalize_name
from puro_pockets.domain.transfers import (
    TransferReason,
    TransferRef,
    check_available,
    check_pockets,
    goal_effect,
    parse_reason,
    parse_transfer_amount,
    transfer_date,
    validate_note,
)
from puro_pockets.services.ledger_core import (
    BalanceKindName,
    BehaviorName,
    LedgerCore,
    LedgerData,
    logger,
)
from puro_pockets.services.records import (
    LedgerSnapshot,
    NewTransfer,
    Operation,
    OperationTaken,
)

ReasonName = Literal["cubrir_sobregasto", "reasignacion", "ajuste"]


class TransferSide(BaseModel):
    pocket: str
    behavior: BehaviorName
    balance_kind: BalanceKindName
    before: int = Field(
        description="Colones antes: saldo (acumulable, 11.2) o disponible del mes (consumo, 11.1)."
    )
    after: int = Field(description="Colones después de la transferencia.")
    adjusted_budget_before: int | None = Field(
        description="Consumo: presupuesto ajustado del mes antes (9.1); null en acumulables."
    )
    adjusted_budget_after: int | None = Field(
        description="Consumo: presupuesto ajustado del mes después; null en acumulables."
    )


class TransferGoalEffect(BaseModel):
    """RN-58: efecto en el avance de la meta activa de una de las bolsas."""

    reference: str = Field(description="Referencia de la meta (M-n).")
    pocket: str
    percent_before: int = Field(description="Avance antes, en % con tope de 100.")
    percent_after: int = Field(description="Avance después, en % con tope de 100.")
    missing_before: int
    missing_after: int
    completes: bool = Field(description="True si la transferencia la lleva a su objetivo.")


class TransferResult(BaseModel):
    saved: bool = Field(description="True solo si se guardó; false es la vista previa.")
    reference: str | None = Field(description="Referencia (T-n); null en la vista previa.")
    date: str = Field(description="Siempre hoy (America/Costa_Rica).")
    month: str = Field(description="Mes de la fecha: el de los presupuestos que cambian.")
    amount: int = Field(description="Colones (siempre en colones, sin tipo de cambio).")
    reason: ReasonName
    note: str | None
    from_pocket: TransferSide
    to_pocket: TransferSide
    goal_effects: list[TransferGoalEffect] = Field(
        description="Metas activas de las dos bolsas y cómo cambia su avance (RN-58)."
    )
    warning: str | None = Field(description="Avisos para explicar al propietario.")
    preview_token: str | None = Field(
        default=None,
        description="Solo en la vista previa: envíalo con confirm=true tras la aprobación "
        "explícita del propietario.",
    )


@dataclass(frozen=True)
class _TransferRequest:
    from_pocket: object
    to_pocket: object
    amount: int
    reason: TransferReason
    note: str | None
    day: date
    explicit_date: bool


def _token(payload: dict) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(f"transfer_between_bolsas:{canonical}".encode()).hexdigest()


def _side(before: PocketFigures, after: PocketFigures) -> TransferSide:
    consumo = before.pocket.behavior is Behavior.CONSUMO
    return TransferSide(
        pocket=before.pocket.name,
        behavior=before.pocket.behavior.value,
        balance_kind=before.kind.value,
        before=before.amount,
        after=after.amount,
        adjusted_budget_before=before.adjusted_budget if consumo else None,
        adjusted_budget_after=after.adjusted_budget if consumo else None,
    )


class TransfersMixin(LedgerCore):
    """Casos de uso de las transferencias. Las cifras salen siempre de `pocket_figures`."""

    def _transfer_request(
        self,
        from_pocket: object,
        to_pocket: object,
        amount: object,
        reason: object,
        note: object,
        when: object,
    ) -> _TransferRequest:
        day = transfer_date(when, self._today())
        explicit = isinstance(when, str) and bool(when.strip())
        return _TransferRequest(
            from_pocket,
            to_pocket,
            parse_transfer_amount(amount),
            parse_reason(reason),
            validate_note(note),
            day,
            explicit,
        )

    async def preview_transfer(
        self,
        from_pocket: object,
        to_pocket: object,
        amount: object,
        reason: object,
        note: object = None,
        transfer_date: object = None,
    ) -> TransferResult:
        request = self._transfer_request(
            from_pocket, to_pocket, amount, reason, note, transfer_date
        )
        return await self._run(partial(self._transfer, request, None, None))

    async def transfer_between_bolsas(
        self,
        from_pocket: object,
        to_pocket: object,
        amount: object,
        reason: object,
        note: object = None,
        confirm: bool = False,
        operation_id: object = None,
        preview_token: object = None,
        transfer_date: object = None,
    ) -> TransferResult:
        request = self._transfer_request(
            from_pocket, to_pocket, amount, reason, note, transfer_date
        )
        operation = None
        if confirm:
            op_id = validate_operation_id(operation_id)
            payload = {
                "from": normalize_name(str(from_pocket)),
                "to": normalize_name(str(to_pocket)),
                "amount": request.amount,
                "reason": request.reason.value,
                "note": request.note,
                "date": request.day.isoformat() if request.explicit_date else None,
            }
            operation = Operation(
                op_id, "transfer_between_bolsas", fingerprint("transfer_between_bolsas", payload)
            )
        return await self._run(partial(self._transfer, request, operation, preview_token))

    def _transfer(
        self, request: _TransferRequest, operation: Operation | None, token: object
    ) -> TransferResult:
        if operation is not None:
            replay = self._replay(operation)
            if replay is not None:
                return TransferResult.model_validate(replay)
        pockets = self._store.list_pockets()
        source = find_pocket(pockets, request.from_pocket)
        target = find_pocket(pockets, request.to_pocket)
        check_pockets(source, target)
        month = Month.of(request.day)
        self._ensure_open(month)  # RN-44: el mes de una transferencia normal es el de hoy
        goals = [
            g for g in self._store.list_goals() if g.live and g.pocket_id in (source.id, target.id)
        ]
        preview = self._transfer_view(request, source, target, month, self._data(), goals)
        expected = _token(
            {
                "from": source.id,
                "to": target.id,
                "amount": request.amount,
                "reason": request.reason.value,
                "note": request.note,
                "date": request.day.isoformat(),
            }
        )
        if operation is None:
            return preview.model_copy(update={"preview_token": expected})
        if not isinstance(token, str) or token.strip() != expected:
            raise PreviewRequired("datos de la transferencia")

        def verify(snapshot: LedgerSnapshot):
            # Con las dos bolsas bloqueadas: siguen activas y el origen sigue alcanzando (RN-42)
            locked_source = snapshot.pockets.get(source.id, source)
            locked_target = snapshot.pockets.get(target.id, target)
            check_pockets(locked_source, locked_target)
            data = LedgerData(snapshot.entries, snapshot.expenses, snapshot.transfers)
            view = self._transfer_view(request, locked_source, locked_target, month, data, goals)

            def respond(transfer_id: int) -> dict:
                return view.model_copy(
                    update={"saved": True, "reference": str(TransferRef(transfer_id))}
                ).model_dump(mode="json")

            return respond

        new = NewTransfer(
            request.day, month, source.id, target.id, request.amount, request.reason, request.note
        )
        try:
            response = self._store.record_transfer(new, operation, verify, request.day)
        except OperationTaken:
            return TransferResult.model_validate(self._after_race(operation))
        result = TransferResult.model_validate(response)
        logger.info(
            "Transferencia registrada: ref=%s mes=%s motivo=%s metas_afectadas=%d",
            result.reference,
            result.month,
            result.reason,
            len(result.goal_effects),
        )
        return result

    def _transfer_view(
        self,
        request: _TransferRequest,
        source: Pocket,
        target: Pocket,
        month: Month,
        data: LedgerData,
        goals: list[Goal],
    ) -> TransferResult:
        """Valida RN-42 con las cifras oficiales y arma la vista previa (nada se guarda aquí)."""
        source_before = data.figures(source, month)
        check_available(source_before, request.amount)
        target_before = data.figures(target, month)
        moved = LedgerData(
            data.entries,
            data.expenses,
            [*data.transfers, TransferEntry(source.id, target.id, month, request.amount)],
        )
        source_after = moved.figures(source, month)
        target_after = moved.figures(target, month)
        balances = {
            source.id: (source_before.amount, source_after.amount),
            target.id: (target_before.amount, target_after.amount),
        }
        names = {source.id: source.name, target.id: target.name}
        effects = []
        notes = []
        for goal in sorted(goals, key=lambda g: g.id):
            before, after = balances[goal.pocket_id]
            effect = goal_effect(goal, before, after)
            effects.append(
                TransferGoalEffect(
                    reference=goal.reference,
                    pocket=names[goal.pocket_id],
                    percent_before=effect.percent_before,
                    percent_after=effect.percent_after,
                    missing_before=effect.missing_before,
                    missing_after=effect.missing_after,
                    completes=effect.completes,
                )
            )
            notes.append(effect.message)
        if target_after.negative:
            notes.append(f"La bolsa {target.name} sigue en negativo después de la transferencia.")
        return TransferResult(
            saved=False,
            reference=None,
            date=request.day.isoformat(),
            month=str(month),
            amount=request.amount,
            reason=request.reason.value,
            note=request.note,
            from_pocket=_side(source_before, source_after),
            to_pocket=_side(target_before, target_after),
            goal_effects=effects,
            warning=" ".join(notes) or None,
        )
