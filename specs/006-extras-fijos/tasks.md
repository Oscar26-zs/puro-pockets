# Tasks: Extras y gastos fijos

**Input**: `specs/006-extras-fijos/` (spec, plan, research, data-model, contracts, quickstart)

**Tests**: OBLIGATORIAS (gobernanza, regla no negociable 4). Datos siempre sintéticos. Nada se ejecuta
contra la base del homelab.

## Phase 1: Setup

- [X] T001 Enmienda PATCH 1.0.2 de la constitución: decisión #12d resuelta en la sección 14.1.1 y
  registro de cambios (sin tocar nada más)
- [X] T002 Rama `hito-6-extras-fijos` desde `main` (con la etiqueta `hito-5` en la fusión del PR #6)

## Phase 2: Foundational

- [X] T003 [P] `src/puro_pockets/domain/recurring.py` (`RecurringRef` F-n, `RecurringTemplate` con
  historial de monto, `due_date` con mes corto, `pending_in_month`, `find_recurring`, validaciones)
- [X] T004 [P] `src/puro_pockets/domain/extras.py` (`validate_extra_shares` RN-01/RN-07,
  `preview_token`) y errores nuevos en `domain/errors.py`
- [X] T005 [P] Pruebas `tests/unit/test_recurring_domain.py` (día 31 en febrero y bisiesto, F-n,
  historial, pendientes y atrasados, reparto inválido, ficha)
- [X] T006 `services/records.py` (registros y protocolo `LedgerStore` ampliado) y
  `services/ledger_core.py` (base común); `services/ledger.py` reexporta
- [X] T007 Migración `migrations/versions/0005_extras_recurring.py` (plantillas, montos,
  `expenses.recurring_id` con índice único parcial, CHECK de `incomes`, disparadores, downgrade
  protegido, upgrade que se niega ante pendientes que no son extras)
- [X] T008 Tablas en `db/budget_store.py`; métodos en `db/ledger_store.py` (`distribute_extra`
  atómico, pendientes, repartidos, totales, plantillas, upsert de montos, pagos)
- [X] T009 `tests/fakes.py`: `InMemoryLedgerStore` con la misma semántica (pendientes fuera de
  `LIVE_INCOME`, un pago por mes, nombres únicos)

## Phase 3: US1 + US2 — Extras (P1)

- [X] T010 `services/extras.py`: `register_extra_income`, `get_allocation_context`,
  `confirm_allocation` con ficha e idempotencia
- [X] T011 "Sin asignar" en `get_summary` y `list_transactions`; `income_total` con extras repartidos;
  anulación de extras (pendiente o repartido)

## Phase 4: US3 + US4 — Gastos fijos (P1)

- [X] T012 `services/recurring.py`: `manage_recurring` (crear, listar, actualizar, desactivar) y
  `list_pending_recurring`
- [X] T013 `add_expense` con `recurring` (monto de la plantilla, un pago por mes, USD con su tipo de
  cambio, huella del Hito 5 intacta sin plantilla)

## Phase 5: Tools y servidor

- [X] T014 `mcp/extras_tools.py`, entradas opcionales en `mcp/inputs.py`, `add_expense` en
  `mcp/ledger_tools.py`, instrucciones del servidor y registro en `mcp/server.py`
- [X] T015 [P] `tests/unit/test_extras_service.py` (positivas y negativas, idempotencia, registros)
- [X] T016 [P] `tests/unit/test_extras_tools.py` (401, instrucciones en `initialize`, tools con
  esquema, flujo completo, USD sin tipo de cambio, registros sin montos)

## Phase 6: US5 — Invariante y Postgres

- [X] T017 `tests/synthetic.py` con extras y fijos; `tests/unit/test_invariant.py` (200 conjuntos,
  coberturas mínimas, detección de un pendiente contado)
- [X] T018 [P] `tests/integration/test_migrations.py` (HEAD 0005, conserva datos del Hito 5,
  downgrade protegido, restricciones y disparadores) y `conftest.reset_budget`
- [X] T019 [P] `tests/integration/test_extras_sql_store.py` (reparto atómico, dos confirmaciones y dos
  pagos simultáneos, historial de montos, desactivación)

## Phase 7: Polish

- [X] T020 `docs/plan-tecnico.md` v0.8 y `HITOS.md` v0.9; README "Extras y gastos fijos (Hito 6)"
- [X] T021 ruff y suite completa (399 pasan); 0 bases `pp_test_*` sobrantes
- [X] T022 Verificación manual en la base de desarrollo (respaldo previo) y `verificacion.md`

## Dependencies

Setup → Foundational (T003–T009) → Extras / Fijos → Tools → Invariante e integración → Polish.
