# Tasks: Bolsas flexibles y metas

**Input**: `specs/007-bolsas-metas/` (spec, plan, research, data-model, contracts, quickstart)

**Tests**: OBLIGATORIAS (gobernanza, regla no negociable 4). Datos siempre sintéticos. Nada se ejecuta
contra la base del homelab.

## Phase 1: Setup

- [X] T001 Enmienda PATCH 1.0.3: decisión #11 resuelta (14.1.2) y RN-22 [DECIDIDO]; #11 fuera de la
  sección 3 de `HITOS.md`
- [X] T002 Rama `hito-7-bolsas-metas` desde `main` (etiqueta `hito-6` sobre la fusión del PR #7)

## Phase 2: Foundational

- [X] T003 [P] `domain/rebalance.py` (proporcional, desde_una_bolsa, manual; RN-01, RN-14, RN-17)
- [X] T004 [P] `domain/goals.py` (estados, `reached`, avance, RN-28) y validaciones de bolsa
- [X] T005 [P] `tests/unit/test_rebalance_goals_domain.py` con prueba de propiedades (semilla fija)
- [X] T006 Migración `0006_pockets_goals` (`archived_at`, `savings_goals`, índice único parcial,
  disparadores, downgrade protegido)
- [X] T007 Registros (`NewPocket`, `NewGoal`, `GoalChange`) y protocolo `LedgerStore`
- [X] T008 Almacén SQL: `_settle_goals` en la transacción de salario, saldo inicial, reparto de
  extra y anulación de gasto; `create_pocket`, `archive_pocket`, metas
- [X] T009 `tests/fakes.py` con la misma semántica

## Phase 3: US1 + US2 — Bolsas (P1)

- [X] T010 `services/flex.py`: `preview_rebalance`, `create_bolsa`, `archive_bolsa` con ficha
- [X] T011 Bolsa archivada en las tools anteriores (gastos, repartos, porcentajes, metas, anulación)

## Phase 4: US3 — Metas (P1)

- [X] T012 `services/goals.py`: `create_goal`, `update_goal`, `get_goal_progress`
- [X] T013 Metas activas en `get_allocation_context`; meta activa en `get_bolsa_status`

## Phase 5: Tools

- [X] T014 `mcp/pockets_tools.py`, instrucciones del servidor y registro en `mcp/server.py`
- [X] T015 [P] `tests/unit/test_pockets_goals_service.py` (positivas y negativas, idempotencia,
  registros)
- [X] T016 [P] `tests/unit/test_pockets_tools.py` (401, esquemas, flujo, registros)

## Phase 6: US4 — Invariante y Postgres

- [X] T017 `tests/synthetic.py` (`apply_structure`) y `tests/unit/test_invariant.py` (estructura no
  mueve saldos, avance = saldo, meses pasados intactos; 200 conjuntos)
- [X] T018 [P] `tests/integration/test_migrations.py` (HEAD 0006, conserva datos del Hito 6,
  downgrade protegido, restricciones y disparadores) y `conftest.reset_budget`
- [X] T019 [P] `tests/integration/test_pockets_goals_sql_store.py` (bolsa atómica, archivado, meta
  lograda en la transacción, dos metas simultáneas)

## Phase 7: Polish

- [X] T020 `docs/plan-tecnico.md` v0.9, `HITOS.md` v0.10 (Hito 7 y pruebas pendientes en el Hito 8),
  README
- [X] T021 ruff y suite completa (461 pasan); 0 bases `pp_test_*` sobrantes
- [X] T022 Verificación manual en la base de desarrollo (respaldo previo) y `verificacion.md`

## Pendiente para el Hito 8

- [ ] Vaciar una bolsa con saldo mediante transferencia y archivarla (acumulable con meta y consumo);
  aviso del efecto sobre la meta (RN-58). Anotado en `HITOS.md`, Hito 8.
