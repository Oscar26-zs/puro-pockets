# Tasks: Transferencias entre bolsas

**Input**: `specs/008-transferencias/` (spec, plan, research, data-model, contracts, quickstart)

**Tests**: OBLIGATORIAS (gobernanza, regla no negociable 4). Datos siempre sintéticos. Nada se
ejecuta contra la base del homelab.

## Phase 1: Setup

- [X] T001 Enmienda PATCH 1.0.4: RN-58 [DECIDIDO] en `.specify/memory/constitution.md`
- [X] T002 Rama `hito-8-transferencias` desde `main` (etiqueta `hito-7` sobre la fusión del PR #8)

## Phase 2: Foundational

- [X] T003 [P] `domain/balances.py`: `TransferEntry`, `received`/`sent`, `PocketFigures` y
  `pocket_figures` (9.1, 11.1, 11.2); `integrity_gap` con transferencias
- [X] T004 [P] `domain/transfers.py`: motivos, nota ≤ 140, monto, fecha de hoy, `T-n`, RN-41,
  RN-42, efecto en metas (RN-58); `domain/goals.py` con transferencias (saldo y RN-28)
- [X] T005 [P] `tests/unit/test_transfers_domain.py` con propiedades (semilla fija)
- [X] T006 Migración `0007_transfers` (tabla, CHECK, FK RESTRICT, índices, disparador, downgrade
  protegido)
- [X] T007 Registros (`NewTransfer`, `TransferRow`, `LedgerSnapshot`) y protocolo `LedgerStore`
- [X] T008 Almacén SQL: `transfer_entries`, `_settle_goals` con transferencias, `_lock_and_read`,
  `record_transfer`, `list_transfers`; `archive_pocket` con bloqueo y nueva comprobación
- [X] T009 `tests/fakes.py` con la misma semántica

## Phase 3: US1 + US2 — Transferir con vista previa (P1)

- [X] T010 `services/transfers.py`: `preview_transfer`, `transfer_between_bolsas` (ficha, nueva
  validación con las bolsas bloqueadas, metas en la transacción)
- [X] T011 `services/ledger.py`: 9.1 en `get_bolsa_status` y `get_summary`; RN-37 con los cálculos
  nuevos; `list_transactions` con `T-n`; `services/extras.py` y `services/goals.py` con
  `LedgerData`

## Phase 4: US3 — Archivar tras vaciar (P1)

- [X] T012 `services/flex.py`: error con la indicación de transferir; comprobación dentro de la
  transacción

## Phase 5: Tools

- [X] T013 `mcp/transfers_tools.py`, instrucciones del servidor y descripciones de `add_expense`,
  `void_transaction`, `get_bolsa_status`, `get_summary`, `list_transactions` y `archive_bolsa`
- [X] T014 [P] `tests/unit/test_transfers_service.py` (positivas, negativas, idempotencia, RN-58,
  archivado de punta a punta, registros)
- [X] T015 [P] `tests/unit/test_transfers_tools.py` (401, esquemas, flujo, registros)

## Phase 6: US4 — Invariante y Postgres

- [X] T016 `tests/synthetic.py` (`apply_transfers`) y `tests/unit/test_invariant.py` (200 conjuntos)
- [X] T017 [P] `tests/integration/test_migrations.py` (HEAD 0007, conserva datos del Hito 7,
  downgrade protegido, CHECK, FK RESTRICT, disparador) y `conftest.reset_budget`
- [X] T018 [P] `tests/integration/test_transfers_sql_store.py` (atomicidad, disparador, meta en la
  transacción, archivado, concurrencia, transferencias cruzadas, archivar y transferir a la vez)

## Phase 7: Polish

- [X] T019 `docs/plan-tecnico.md` v0.10, `HITOS.md` v0.11, README
- [X] T020 ruff y suite completa (537 pasan); 0 bases `pp_test_*` sobrantes
- [X] T021 Verificación manual en la base de desarrollo (respaldo previo) y `verificacion.md`
