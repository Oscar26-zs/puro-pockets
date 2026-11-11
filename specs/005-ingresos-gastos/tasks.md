# Tasks: Ingresos base y gastos (MVP)

**Input**: `specs/005-ingresos-gastos/` (spec, plan, research, data-model, contracts, quickstart)

**Tests**: OBLIGATORIAS (gobernanza, regla no negociable 4). Pruebas antes que la implementación. Datos
siempre sintéticos. Nada se ejecuta contra la base del homelab.

## Phase 1: Setup

- [X] T001 `USD_RATE_MIN` / `USD_RATE_MAX` (enteros, por defecto 300 y 1000, mínimo > 0 y < máximo) en `src/puro_pockets/config.py`, `docker-compose.yml` y `.env.example`, con pruebas en `tests/unit/test_config.py`

## Phase 2: Foundational (bloquea todas las historias)

- [X] T002 [P] Pruebas de `tests/unit/test_money.py`: lectura de CRC (entero, texto de dígitos; rechaza decimales, `float`, booleano, 0, negativo), USD (entero, `"10"`, `"10.5"`, `"10.50"`; rechaza 3 decimales, coma, `float`), tipo de cambio ×100 y rango, half-up (USD 10,00 a 512,34 = 5123; caso .5 sube), conversión a 0 rechazada, USD sin tipo de cambio, CRC con tipo de cambio, formato de salida
- [X] T003 [P] `src/puro_pockets/domain/money.py` (`Currency`, `parse_amount`, `parse_exchange_rate`, `RateRange`, `to_crc`, `convert`, `format_original`, `format_rate`)
- [X] T004 [P] Pruebas de `tests/unit/test_ledger_domain.py`: referencias `I-`/`G-` (formato, mayúsculas, inválidas), fecha no futura, mes del salario (siguiente; explícito), motivo 3..200, descripción ≤ 120, nombre de categoría 1..60
- [X] T005 [P] `src/puro_pockets/domain/ledger.py`, `src/puro_pockets/domain/categories.py` y errores nuevos en `src/puro_pockets/domain/errors.py`
- [X] T006 [P] Pruebas y `src/puro_pockets/domain/idempotency.py` (`validate_operation_id`, `fingerprint` determinista con orden de claves indistinto) en `tests/unit/test_idempotency.py`
- [X] T007 Pruebas de saldos con gastos en `tests/unit/test_balances.py` (11.1 disponible = asignado − gastado del mes; 11.2 saldo histórico; sobregasto por comportamiento; % usado entero o vacío; invariante con gastos)
- [X] T008 `src/puro_pockets/domain/balances.py`: `ExpenseEntry`, gastos en 11.1/11.2, `integrity_gap` con gastos, `pocket_figure`, `percent_used`
- [X] T009 Migración `migrations/versions/0004_movements.py` (columnas de `incomes` rellenadas desde `amount`, índice parcial con `AND NOT voided`, `expenses`, `idempotency_keys`, disparadores del libro mayor, downgrade protegido)
- [X] T010 Pruebas de migración en `tests/integration/test_migrations.py`: head = `0004_movements`; base en `0003_budget` con datos sintéticos del Hito 4 → `0004` los conserva (CRC, original = monto, sin tipo de cambio); downgrade con gastos se niega y con la variable pasa; restricciones (moneda, CRC con tipo de cambio, USD sin él, anulación incompleta); disparadores (no borrar, no cambiar montos, no deshacer anulación); segundo saldo inicial permitido tras anular
- [X] T011 Tablas y lecturas que ignoran lo anulado en `src/puro_pockets/db/budget_store.py` (`has_initial_balance`, `allocation_entries`, `distributed_income_total`, `expense_entries`, `expense_total`); `BudgetStore` + `expense_entries` y saldos con gastos en `src/puro_pockets/services/budget.py`; `InMemoryBudgetStore` en `tests/fakes.py`
- [X] T012 `LedgerStore` (protocolo) y vistas en `src/puro_pockets/services/ledger.py`; `InMemoryLedgerStore` en `tests/fakes.py`

## Phase 3: US1 - Salario repartido (P1) 🎯 MVP

- [X] T013 [P] [US1] Pruebas de servicio en `tests/unit/test_ledger_service.py`: mes siguiente por defecto, mes explícito, herencia RN-03 con origen, sin porcentajes → error sin guardar, USD convertido, vista previa sin guardar, porcentaje guardado por reparto, residuo en la última bolsa
- [X] T014 [US1] `LedgerService.preview_income` / `add_income` en `src/puro_pockets/services/ledger.py`
- [X] T015 [US1] `SqlLedgerStore.record_income` (ingreso + repartos + clave en una transacción) en `src/puro_pockets/db/ledger_store.py`

## Phase 4: US2 + US3 - Gastos y sobregasto (P1)

- [X] T016 [P] [US2] Pruebas de servicio: gasto CRC/USD, mes de la fecha, sin categoría = pendiente, bolsa por defecto de la categoría, contra acumulable, fecha futura/0/bolsa inexistente rechazados, sobregasto guardado con advertencia y bolsas disponibles
- [X] T017 [US2] `LedgerService.add_expense` y `SqlLedgerStore.record_expense`
- [X] T018 [P] [US6] Pruebas y `create_category` / `list_categories` (servicio y almacén; único sin distinguir mayúsculas)

## Phase 5: US5 - Anulación (P1)

- [X] T019 [P] [US5] Pruebas de servicio: anular gasto (ignorado en cálculos, visible), anular salario (revierte y advierte negativos), anular y recargar el saldo inicial, ya anulado, referencia inexistente/inválida, vista previa sin guardar
- [X] T020 [US5] `LedgerService.void_transaction` y `SqlLedgerStore.void_movement` (`UPDATE ... WHERE NOT voided`)

## Phase 6: Idempotencia (FR-011)

- [X] T021 [P] Pruebas de servicio: misma clave y contenido → misma respuesta y un solo movimiento (las tres tools); otra huella → error; misma clave en otra tool → error; `confirm=true` sin clave → error
- [X] T022 Idempotencia en el servicio y manejo de la carrera por la PK en `src/puro_pockets/db/ledger_store.py`

## Phase 7: US4 - Consultas (P1)

- [X] T023 [P] [US4] Pruebas de servicio: `get_bolsa_status` (consumo y acumulable), `get_summary` (sin saldo inicial; negativos marcados), `top_categories` (orden, pendiente, límite), `list_transactions` (orden, filtros, límite 20/100, `has_more`, anulados con motivo)
- [X] T024 [US4] Consultas en `src/puro_pockets/services/ledger.py` y lecturas en `src/puro_pockets/db/ledger_store.py`

## Phase 8: Tools, autenticación y registros

- [X] T025 [P] `src/puro_pockets/mcp/inputs.py` (enteros y montos sin `float`, mensajes en español) y uso en `src/puro_pockets/mcp/budget_tools.py`
- [X] T026 [P] Pruebas `tests/unit/test_ledger_tools.py` (app ASGI real con OAuth): 401 sin token; tools publicadas con esquema de salida; salario 50/30/20; USD convertido; USD sin tipo de cambio; número JSON decimal rechazado; sobregasto; idempotencia; anulación; registros y errores sin montos ni descripciones
- [X] T027 Tools en `src/puro_pockets/mcp/ledger_tools.py`; registro en `src/puro_pockets/mcp/server.py` y `src/puro_pockets/__main__.py`

## Phase 9: US7 - Invariante e integración con Postgres

- [X] T028 Generador sintético en `tests/synthetic.py`: salarios CRC y USD, gastos con y sin categoría, sobregastos, anulaciones (incluido el saldo inicial y su recarga); `tests/unit/test_invariant.py` con 200 conjuntos (semilla impresa al fallar) y detección de un gasto alterado
- [X] T029 [P] `tests/integration/test_invariant_sql.py`: 40 conjuntos contra Postgres
- [X] T030 [P] `tests/integration/test_ledger_sql_store.py`: salario atómico, gasto USD, anulación y recarga del saldo inicial, dos llamadas simultáneas con la misma clave (un solo movimiento), categoría única sin distinguir mayúsculas; `reset_budget` vacía también `expenses` e `idempotency_keys`

## Phase 10: Polish

- [X] T031 [P] `docs/plan-tecnico.md` v0.7 (sección "Movimientos (Hito 5)", esquema, catálogo, 12.2.2, concepto → tabla) y `HITOS.md` v0.8 (Hito 5, "Terminado cuando", RN-59 en el Hito 5)
- [X] T032 [P] README: sección del Hito 5 (tools, USD como texto, rango del tipo de cambio, migración `0004` con respaldo previo)
- [X] T033 `uv run ruff check .`, `ruff format --check .`, suite completa (unitarias + integración)
- [X] T034 Comprobación manual en la base de desarrollo con datos sintéticos y `specs/005-ingresos-gastos/verificacion.md`

## Dependencies

- Setup → Foundational (T002–T012) → US1 → US2/US3 → US5 → Idempotencia → US4 → Tools → Invariante e
  integración → Polish.
- T003, T005, T006 son independientes entre sí; T008 depende de T005; T011–T012 dependen de T008 y T009.

## Parallel Examples

- Foundational: T002+T003, T004+T005, T006 en paralelo.
- Fase 9: T029 y T030 en paralelo.

## Implementation Strategy

MVP = US1 + US2 (salario y gastos). Luego sobregasto, anulación, idempotencia, consultas y tools. La fase
9 cierra el invariante y la integración real.
