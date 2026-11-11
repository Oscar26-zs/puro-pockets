# Implementation Plan: Bolsas y porcentajes

**Branch**: `hito-4-bolsas` | **Date**: 2026-11-10 | **Spec**: [spec.md](spec.md)

> **Plan delgado (Puro Pockets).** Este plan no repite lo que ya está en
> `.specify/memory/constitution.md` ni en `docs/plan-tecnico.md`: lo referencia. Solo registra lo
> que este hito agrega o cambia. Las reglas se citan por su identificador (`RN-xx`), nunca se
> reescriben.

## Summary

El esqueleto del presupuesto: bolsas (datos iniciales Necesidades, Ahorro y Gustos), porcentajes por
mes con validación de suma 100 y herencia del mes anterior, reparto en enteros con residuo, y la carga
única del saldo inicial con vista previa. Cinco tools nuevas detrás de OAuth y la primera prueba del
invariante de integridad (11.4) con datos sintéticos. Revisión técnica: [research.md](research.md).

## Technical Context

**Base**: stack, arquitectura y esquema en `docs/plan-tecnico.md` (v0.6, ya actualizado con los
nombres de este hito). Aquí solo va lo nuevo o distinto.

**Dependencias nuevas o cambiadas**: ninguna instalación nueva. [PROPUESTO] declarar `tzdata` como
dependencia directa (ya está en `uv.lock`, v2026.6, como dependencia de psycopg; research §2).

**Cambios al esquema**: migración `0003_budget`: `pockets`, `categories`, `budget_month_allocations`,
`incomes`, `income_allocations`, índice único parcial del saldo inicial y datos iniciales (tres
bolsas). Detalle en [data-model.md](data-model.md).

**Tools MCP nuevas**: `set_allocation`, `get_allocation`, `preview_initial_balance`,
`load_initial_balance`, `list_bolsas`. Contrato en [contracts/tools.md](contracts/tools.md).

**Configuración nueva**: `APP_TIMEZONE` (por defecto `America/Costa_Rica`).

**Decisiones pendientes de las que depende**: ninguna [ABIERTO]. La decisión 12 de la constitución
(detalles de monedas) no afecta: este hito es solo en colones.

## Constitution Check

*Revisado antes y después del diseño.*

- **Reglas que implementa este hito**: RN-01, RN-02, RN-03, RN-08, RN-10, RN-11, RN-12, RN-54.
  Principios 3.2 (vista previa), 3.3 (saldos derivados), 3.5 (enteros), 3.6 (atómico), 3.9 (historial
  por mes) y 3.10 (minimización).
- **Reglas no negociables** (Gobernanza):
  - ✓ 1. Datos reales: el Hito 3 está cerrado; todas las tools exigen token.
  - ✓ 2. Capa de negocio: validaciones, reparto, saldos e invariante en `domain/`, sin MCP ni base
    (la prueba de arquitectura existente lo vigila).
  - ✓ 3. Invariante: prueba automática desde este hito, el primero que registra dinero; `HITOS.md`
    corregido (v0.7).
  - ✓ 4. Pruebas del hito: unitarias e integración para cada escenario (sección "Pruebas").
- **Aprobado por el propietario (2026-11-10)**, antes [PROPUESTO]: mes del saldo inicial = mes actual
  en America/Costa_Rica; montos ≥ 0 con total > 0; valores de la tabla concepto → tabla; corrección
  solo con la anulación del Hito 5, con `confirm=true` obligatorio, índice preparado para recargar tras
  anular y sin tool ni script que borre; bolsas por nombre con unicidad sin distinguir mayúsculas en la
  base; `tzdata` directa; pruebas de integración en base temporal que se niegan a correr contra otra;
  generador propio del invariante con semilla fija; downgrade protegido
  (`ALLOW_DESTRUCTIVE_DOWNGRADE`), advertencias del README y respaldo manual con `pg_dump`.
- **[PROPUESTO] que se asumen**:
  1. Herencia RN-03 resuelta al consultar; los meses pasados están congelados, así que lo que heredaron
     no cambia; `set_allocation` sobre un mes pasado se rechaza (ver spec, resumen).
  2. "Datos" para el downgrade protegido: filas en `categories`, `budget_month_allocations`,
     `incomes` o `income_allocations`, o bolsas distintas de las tres iniciales sin modificar.
  3. La base temporal de pruebas se llama `pp_test_<aleatorio>`; las pruebas que tocan la base
     verifican ese prefijo y que sea la base que ellas crearon. Las pruebas existentes que solo
     consultan el contenedor (`ping`, encabezados) siguen apuntando al servicio local.
- **[ABIERTO] de los que depende**: ninguno.

## Project Structure

### Documentation (this feature)

```text
specs/004-bolsas-porcentajes/
├── spec.md, plan.md, research.md, data-model.md, quickstart.md
├── contracts/tools.md
├── checklists/requirements.md
└── tasks.md             # Lo crea /speckit-tasks
```

### Source Code (repository root)

```text
src/puro_pockets/domain/errors.py          # DomainError (mensaje en español, sin montos)
src/puro_pockets/domain/months.py          # Month 'YYYY-MM': validar, comparar, anterior/siguiente
src/puro_pockets/domain/pockets.py         # Behavior (consumo/acumulable), Pocket
src/puro_pockets/domain/allocation.py      # RN-01 validar, RN-03 resolver, RN-08 split_amount
src/puro_pockets/domain/initial_balance.py # RN-54 validar montos
src/puro_pockets/domain/balances.py        # 11.1 / 11.2 y comprobación del invariante 11.4
src/puro_pockets/services/budget.py        # BudgetService + protocolo BudgetStore; mes actual por zona
src/puro_pockets/db/budget_store.py        # SqlBudgetStore (SQLAlchemy Core, transacciones)
src/puro_pockets/mcp/budget_tools.py       # 5 tools: modelos de entrada/salida, DomainError → ToolError
src/puro_pockets/mcp/server.py             # registra las tools (build_server recibe BudgetService)
src/puro_pockets/__main__.py, config.py    # wiring y APP_TIMEZONE
migrations/versions/0003_budget.py         # tablas, índice y datos iniciales
docker-compose.yml, .env.example           # APP_TIMEZONE
README.md                                  # Hito 4, advertencias (downgrade, down -v) y respaldo con pg_dump
tests/fakes.py                             # InMemoryBudgetStore
tests/synthetic.py                         # generador de datos sintéticos (semilla reproducible)
tests/unit/test_months.py, test_allocation.py, test_initial_balance.py, test_balances.py
tests/unit/test_budget_service.py, test_budget_tools.py, test_invariant.py
tests/integration/conftest.py              # base temporal por prueba
tests/integration/test_budget_sql_store.py, test_invariant_sql.py
tests/integration/test_migrations.py       # head = 0003_budget; usa la base temporal
```

## Pruebas

| Criterio (spec) | Prueba |
|---|---|
| US1-1, SC-001: definir 50/30/20 y consultarlo | `test_budget_service.py`, `test_budget_tools.py` (en proceso, con token), `test_budget_sql_store.py` |
| US1-2, SC-001: suma ≠ 100 rechazada sin guardar | `test_allocation.py`, `test_budget_service.py` |
| US1-3: bolsa faltante, repetida, inexistente, archivada; porcentaje inválido | `test_allocation.py` |
| US1-4: mes pasado rechazado; formato de mes | `test_months.py`, `test_budget_service.py` |
| US1-5: reemplazo de un mes | `test_budget_sql_store.py` |
| US2-1, SC-003: cambiar M+1 no altera M | `test_budget_service.py`, `test_budget_sql_store.py` |
| US2-2, US2-3: herencia del mes anterior sin guardar; sin porcentajes | `test_allocation.py`, `test_budget_sql_store.py` |
| US3-1: vista previa sin guardar | `test_budget_service.py`, `test_budget_sql_store.py` |
| US3-2, SC-002: carga atómica y `list_bolsas` | `test_budget_service.py`, `test_budget_sql_store.py`, `test_budget_tools.py` |
| US3-6: sin `confirm=true` solo vista previa | `test_budget_service.py`, `test_budget_tools.py` |
| US3-3, SC-002: segunda carga y cargas simultáneas rechazadas | `test_budget_service.py`, `test_budget_sql_store.py` (dos conexiones) |
| US3-4: montos inválidos | `test_initial_balance.py` |
| US3-5: no cuenta como ingreso del mes, sí en saldos | `test_balances.py` |
| US4-1..3, SC-004: ₡10.001 → 5.000/3.000/2.001; suma exacta con datos generados; 0 % | `test_allocation.py` |
| US4-4, SC-005: invariante con 200 conjuntos sintéticos | `test_invariant.py` (memoria), `test_invariant_sql.py` (Postgres) |
| Edge: consumo en otro mes empieza en cero (RN-11); acumulable conserva (RN-12) | `test_balances.py` |
| Edge: sin token → 401 | `test_budget_tools.py` |
| FR-014: registros y mensajes de error sin montos | `test_budget_service.py`, `test_budget_tools.py` (captura de registros) |
| FR-012: dominio sin MCP ni base | `test_architecture.py` (existente) |
| Migración reversible, datos iniciales, downgrade protegido, nombre único sin mayúsculas | `test_migrations.py`, `test_budget_sql_store.py` |
| FR-018: las pruebas se niegan a correr fuera de la base temporal | `test_temp_database_guard.py` (unitaria) |
| Desde Claude (quickstart) | manual del propietario, en `verificacion.md` |

## Actualización del plan técnico al cerrar

Ya hecho en esta revisión (v0.6): nombres en inglés de las tablas del hito en la sección 17 y en la
tabla concepto → tabla, `pocket` como nombre de "bolsa" y las tools nuevas en el catálogo. Al cerrar:
`APP_TIMEZONE`, la estructura del código del hito y lo que cambie al implementar.

## Complexity Tracking

Sin violaciones.
