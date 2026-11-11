# Tasks: Bolsas y porcentajes

**Input**: `specs/004-bolsas-porcentajes/` (spec, plan, research, data-model, contracts, quickstart)

**Tests**: OBLIGATORIAS (gobernanza, regla no negociable 4). Pruebas antes que la implementación.
Datos de prueba siempre sintéticos. Nada se ejecuta contra la base del homelab.

## Phase 1: Setup

- [X] T001 Declarar `tzdata` como dependencia directa en `pyproject.toml` y actualizar `uv.lock` (ya instalado, v2026.6)
- [X] T002 [P] `APP_TIMEZONE` (por defecto `America/Costa_Rica`) en `src/puro_pockets/config.py`, `docker-compose.yml` y `.env.example`, con prueba en `tests/unit/test_config.py` (zona inválida → error claro)

## Phase 2: Foundational (bloquea todas las historias)

- [X] T003 [P] Prueba del guardián de la base temporal en `tests/unit/test_temp_database_guard.py`: rechaza URLs cuya base no empiece por `pp_test_` o no sea la creada por la fixture (FR-018)
- [X] T004 Base temporal en `tests/integration/conftest.py`: crea `pp_test_<aleatorio>` en el Postgres local (a partir de `DATABASE_URL`, solo para `CREATE/DROP DATABASE`), aplica migraciones, entrega su URL como `database_url`, la borra al final; `assert_temp_database(url)` en `tests/db_guard.py`; `reset_budget(engine)` restaura las tres bolsas iniciales y vacía las tablas del hito
- [X] T005 [P] Pruebas de `Month` en `tests/unit/test_months.py` (formato `YYYY-MM`, `2026-13` y `26-01` inválidos, anterior/siguiente, comparación, mes actual en America/Costa_Rica cerca de medianoche UTC)
- [X] T006 [P] `src/puro_pockets/domain/errors.py` (`DomainError`, mensaje en español) y `src/puro_pockets/domain/months.py`
- [X] T007 [P] `src/puro_pockets/domain/pockets.py`: `Behavior` (`consumo`, `acumulable`; RN-10) y `Pocket` (id interno, nombre, comportamiento, activa); normalización de nombres (sin distinguir mayúsculas, recorta espacios)
- [X] T008 Migración `migrations/versions/0003_budget.py`: `pockets` (nombre único con índice `lower(name)`, `behavior IN ('consumo','acumulable')`), `categories` (índice `lower(name)`), `budget_month_allocations` (PK `month, pocket_id`; `CHECK month ~ '^[0-9]{4}-(0[1-9]|1[0-2])$'`; `percentage BETWEEN 0 AND 100`), `incomes` (`kind IN ('base','extra','saldo_inicial')`, `amount > 0`, `allocation_status IN ('pendiente','repartido')`), `income_allocations` (`amount >= 0`, `percentage` NULL o 0..100, único `income_id, pocket_id`), índice `ux_incomes_single_initial_balance ON incomes (kind) WHERE kind = 'saldo_inicial'`; datos iniciales Necesidades, Ahorro, Gustos; downgrade que aborta si hay datos salvo `ALLOW_DESTRUCTIVE_DOWNGRADE=true`
- [X] T009 Pruebas de migración en `tests/integration/test_migrations.py` sobre base temporal propia: head = `0003_budget`, subir dos veces, datos iniciales, downgrade con datos aborta, con la variable pasa, bajar y subir de nuevo
- [X] T010 `BudgetStore` (protocolo) en `src/puro_pockets/services/budget.py` e `InMemoryBudgetStore` en `tests/fakes.py`

## Phase 3: US1 - Definir los porcentajes de un mes (P1) 🎯 MVP

**Prueba independiente:** definir 50/30/20 y consultarlo; 50/30/30 se rechaza sin guardar.

- [X] T011 [P] [US1] Pruebas de validación RN-01 en `tests/unit/test_allocation.py`: suma ≠ 100 (mensaje con la suma), bolsa faltante, repetida (también con otra capitalización), inexistente, archivada, porcentaje no entero o fuera de 0..100
- [X] T012 [US1] `validate_allocation` en `src/puro_pockets/domain/allocation.py`
- [X] T013 [P] [US1] Pruebas de servicio en `tests/unit/test_budget_service.py`: guardar y consultar, rechazo sin guardar, mes pasado rechazado (también si no tenía porcentajes), reemplazo del mes
- [X] T014 [US1] `BudgetService.set_allocation` / `get_allocation` en `src/puro_pockets/services/budget.py` (mes actual por zona; llamadas bloqueantes en un hilo; registros sin montos)
- [X] T015 [US1] `SqlBudgetStore` (bolsas y porcentajes, reemplazo atómico del mes) en `src/puro_pockets/db/budget_store.py`
- [X] T016 [US1] Tools `set_allocation` y `get_allocation` en `src/puro_pockets/mcp/budget_tools.py` (modelos de salida, `DomainError` → `ToolError`) y registro en `src/puro_pockets/mcp/server.py` y `src/puro_pockets/__main__.py`

## Phase 4: US2 - Porcentajes guardados por mes (P1)

**Prueba independiente:** 50/30/20 en M, 40/40/20 en M+1; M no cambia.

- [X] T017 [P] [US2] Pruebas de `resolve_allocation` (RN-03) en `tests/unit/test_allocation.py`: hereda del mes anterior más cercano, indica `source_month`, sin porcentajes → `defined=false`, bolsa activa sin fila en el mes de origen → 0
- [X] T018 [US2] `resolve_allocation` en `src/puro_pockets/domain/allocation.py`
- [X] T019 [US2] Pruebas de servicio de RN-02/RN-03 en `tests/unit/test_budget_service.py` (M+1 no altera M; consultar no guarda nada)

## Phase 5: US3 - Saldo inicial y listado de bolsas (P1)

**Prueba independiente:** vista previa y carga sintéticas; `list_bolsas` muestra los saldos; la segunda carga se rechaza.

- [X] T020 [P] [US3] Pruebas de `validate_initial_balance` en `tests/unit/test_initial_balance.py` (negativo, no entero, todo en 0, bolsa inexistente/archivada/repetida, omitidas = 0)
- [X] T021 [P] [US3] Pruebas de saldos en `tests/unit/test_balances.py` (acumulable 11.2; consumo 11.1 por mes; consumo en otro mes = 0 por RN-11; acumulable conserva por RN-12; el saldo inicial no es ingreso del mes pero sí saldo, RN-54)
- [X] T022 [US3] `src/puro_pockets/domain/initial_balance.py` y `src/puro_pockets/domain/balances.py`
- [X] T023 [US3] Pruebas de servicio en `tests/unit/test_budget_service.py`: vista previa sin guardar, `confirm=false` solo vista previa, carga y `list_bolsas`, segunda carga rechazada, registros capturados sin montos sintéticos
- [X] T024 [US3] `preview_initial_balance`, `load_initial_balance(confirm)` y `list_pockets` en `src/puro_pockets/services/budget.py`; unicidad traducida a "ya fue cargado"
- [X] T025 [US3] Saldo inicial y saldos en `src/puro_pockets/db/budget_store.py` (ingreso + repartos en una transacción; violación del índice único → `InitialBalanceAlreadyLoaded`)
- [X] T026 [US3] Tools `preview_initial_balance`, `load_initial_balance` y `list_bolsas` en `src/puro_pockets/mcp/budget_tools.py`

## Phase 6: US4 - Reparto exacto e invariante (P1)

- [X] T027 [P] [US4] Pruebas de `split_amount` (RN-08) en `tests/unit/test_allocation.py`: ₡10.001 con 50/30/20 → 5.000/3.000/2.001; datos generados (semilla fija) con suma exacta y sin negativos; 0 % intermedio → 0
- [X] T028 [US4] `split_amount` en `src/puro_pockets/domain/allocation.py`
- [X] T029 [US4] Generador sintético en `tests/synthetic.py` (semilla fija, 1 a 8 bolsas, porcentajes que suman 100, saldo inicial e ingresos repartidos con `split_amount` en varios meses)
- [X] T030 [US4] `integrity_gap` (invariante 11.4) en `src/puro_pockets/domain/balances.py` y prueba `tests/unit/test_invariant.py` con 200 conjuntos (imprime la semilla si falla)

## Phase 7: Integración con Postgres y autenticación de las tools

- [X] T031 [P] `tests/integration/test_budget_sql_store.py`: US1 a US3 contra la base temporal (reemplazo del mes, herencia sin escribir, carga atómica, dos cargas simultáneas con dos conexiones → una sola, nombre único sin distinguir mayúsculas en la base)
- [X] T032 [P] `tests/integration/test_invariant_sql.py`: invariante con conjuntos sintéticos en Postgres (lado izquierdo por SQL directo contra lado derecho de los saldos del servicio)
- [X] T033 [P] `tests/unit/test_budget_tools.py`: app ASGI real con OAuth y almacén en memoria: sin token → 401; con token, las 5 tools; errores con `is_error` y mensaje en español sin montos; `confirm=false` no guarda; registros capturados sin los montos sintéticos
- [X] T034 Mover las pruebas de integración existentes que escriben en la base (`test_oauth_sql_store.py`, `test_oauth_sql_e2e.py`) a la base temporal (`test_oauth_sql_store.py` ya no escribe en la base del contenedor: valida los tokens con la app real en proceso sobre la base temporal)

## Phase 8: Polish

- [X] T035 [P] README: sección del Hito 4, advertencias (`alembic downgrade`, `ALLOW_DESTRUCTIVE_DOWNGRADE`, `docker compose down -v` solo en desarrollo) y respaldo manual con `pg_dump` a un archivo fuera del repositorio
- [X] T036 [P] `docs/plan-tecnico.md`: `APP_TIMEZONE` y estructura del código del Hito 4
- [X] T037 `uv run ruff check .`, `ruff format --check .`, suite completa (unitarias + integración)
- [X] T038 Comprobación manual en la base de desarrollo con datos sintéticos (tools vía cliente MCP local) y `specs/004-bolsas-porcentajes/verificacion.md`

## Dependencies

- Setup → Foundational → US1 → US2 (usa la misma validación y el almacén) → US3 → US4 → Fase 7 → Polish.
- US4 (`split_amount`) no depende de US1-US3 y puede hacerse en paralelo con ellas.

## Parallel Examples

- Foundational: T003, T005, T006, T007 en paralelo.
- US3: T020 y T021 en paralelo.
- Fase 7: T031, T032, T033 en paralelo.

## Implementation Strategy

MVP = US1 (porcentajes desde Claude). Luego US2, US3 (saldo inicial) y US4 (invariante). La fase 7 cierra la
integración real y la autenticación de las tools.
