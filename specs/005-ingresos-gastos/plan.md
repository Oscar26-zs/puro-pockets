# Implementation Plan: Ingresos base y gastos (MVP)

**Branch**: `hito-5-movimientos` | **Date**: 2026-11-10 | **Spec**: [spec.md](spec.md)

**Input**: `specs/005-ingresos-gastos/spec.md`. Plan delgado: la técnica general está en
`docs/plan-tecnico.md`; aquí solo lo que cambia en este hito.

## Summary

Salario repartido por porcentajes del mes presupuestario, gastos en CRC o USD convertidos a colones,
sobregasto que se guarda y avisa, anulación con registro (incluido el saldo inicial), idempotencia por
clave de operación, consultas de estado, resumen, categorías y listado. Migración `0004_movements`
que conserva los datos del Hito 4. Invariante 11.4 extendido.

## Technical Context

**Language/Version**: Python 3.14 (uv 0.12.5)

**Primary Dependencies**: `mcp==2.3.0` (`MCPServer`), SQLAlchemy 2 Core, psycopg 3 síncrono, Alembic.
`decimal` (biblioteca estándar) para leer montos con decimales. Sin dependencias nuevas.

**Storage**: PostgreSQL 18. Migración `0004_movements` (ver [data-model.md](data-model.md)).

**Testing**: pytest + anyio. Unitarias (dominio, servicio con almacén en memoria, tools por HTTP en
proceso con OAuth real) y de integración en la base temporal `pp_test_*` (almacén SQL, migración con
datos del Hito 4, downgrade protegido, invariante, concurrencia de claves).

**Target Platform**: contenedor Linux en el homelab; desarrollo en Windows 11 con Docker Desktop.

**Constraints**: enteros en todo cálculo de dinero (principio 3.5), ningún `float`; registros sin
montos ni descripciones; escrituras atómicas (principio 3.6); libro mayor inmutable (3.4).

**Scale/Scope**: un usuario; cientos de movimientos por mes.

## Constitution Check

| Regla | Cómo se cumple |
|---|---|
| Regla no negociable 1 (datos reales tras OAuth) | Todas las tools detrás del token (Hito 3). |
| Regla no negociable 2 (capa de negocio) | Conversión, referencias, validaciones, saldos e invariante en `domain/`; la prueba de arquitectura lo vigila. |
| Regla no negociable 3 (invariante) | `integrity_gap` con gastos y anulaciones; 200 conjuntos en memoria y 40 en Postgres. |
| Regla no negociable 4 (pruebas) | Tareas de prueba explícitas antes de cada implementación (tasks.md). |
| 3.2 Previsualizar | `preview_income`; `add_income`, `void_transaction` y `load_initial_balance` sin `confirm` solo muestran. [PROPUESTO] la tool `preview_income` y la vista previa de la anulación. |
| 3.3 Calcular, no guardar | Saldos y disponibles se derivan de repartos y gastos no anulados. |
| 3.4 Libro mayor inmutable | Anulación con registro; disparadores que impiden borrar y cambiar montos [PROPUESTO]. |
| 3.5 Dinero entero | Colones enteros, centavos enteros, tipo de cambio ×100; `Decimal` solo para leer texto. |
| 3.6 Atómico | Ingreso + repartos + clave de operación en una transacción; gasto + clave; anulación + clave. |
| 3.7 Registrar la realidad | El sobregasto no se bloquea (RN-37). |
| 3.10 Minimización | Referencias cortas; sin ids internos; respuestas acotadas. |
| RN-53 mes abierto | Sin cierre hasta el Hito 9: todos los meses abiertos (supuesto de la spec). |
| RN-54 una sola carga | Índice único parcial recreado con `AND NOT voided`: tras anular, se permite una nueva carga. |
| RN-56, RN-57 | `domain/money.py`; columnas `currency`, `original_amount`, `exchange_rate`, `amount`. |
| RN-59 [PROPUESTO en la constitución] | Se aplica como pidió el propietario; sigue [PROPUESTO] porque la enmienda autorizada solo cubría #12, RN-55 a RN-57. |

Resultado: sin violaciones. Lo asumido está como [PROPUESTO] en la spec.

## Project Structure

### Documentation (this feature)

```text
specs/005-ingresos-gastos/
├── spec.md, plan.md, research.md, data-model.md, quickstart.md, tasks.md, verificacion.md
├── contracts/tools.md
└── checklists/requirements.md
```

### Source Code (repository root)

```text
src/puro_pockets/
├── config.py                 # + USD_RATE_MIN / USD_RATE_MAX
├── domain/
│   ├── money.py              # NUEVO: monedas, lectura con Decimal, conversión half-up (RN-55 a 57)
│   ├── ledger.py             # NUEVO: referencias I-/G-, fechas, mes del salario, motivo, descripción
│   ├── categories.py         # NUEVO: categorías, "pendiente de clasificar"
│   ├── idempotency.py        # NUEVO: clave de operación y huella del contenido
│   ├── balances.py           # + gastos en 11.1, 11.2 e invariante 11.4; sobregasto
│   └── errors.py             # + errores del hito
├── services/
│   ├── budget.py             # saldos con gastos; ignora lo anulado
│   └── ledger.py             # NUEVO: LedgerService (ingresos, gastos, anulación, consultas)
├── db/
│   ├── budget_store.py       # tablas actualizadas; ignora lo anulado
│   └── ledger_store.py       # NUEVO: SqlLedgerStore (escrituras atómicas con clave de operación)
└── mcp/
    ├── inputs.py             # NUEVO: validación de entradas sin float, compartida
    ├── budget_tools.py       # usa inputs.py
    ├── ledger_tools.py       # NUEVO: tools del hito
    └── server.py             # registra las tools del hito
migrations/versions/0004_movements.py
tests/unit/        test_money, test_ledger_domain, test_idempotency, test_balances (+),
                   test_ledger_service, test_ledger_tools, test_invariant (+)
tests/integration/ test_migrations (+0004), test_ledger_sql_store, test_invariant_sql (+)
tests/fakes.py     InMemoryLedgerStore
tests/synthetic.py gastos, USD y anulaciones
```

## Pruebas

| Requisito | Pruebas |
|---|---|
| FR-001 a FR-003 (salario) | `test_ledger_service`, `test_ledger_tools`, `test_ledger_sql_store` |
| FR-004, FR-005 (gastos, sobregasto) | `test_ledger_service`, `test_ledger_tools`, `test_balances` |
| FR-006, FR-007 (monedas) | `test_money` (incluye USD 10,00 a 512,34 = ₡5.123 y half-up), `test_ledger_tools` |
| FR-008 a FR-010 (anulación) | `test_ledger_service`, `test_ledger_sql_store` (nueva carga del saldo inicial) |
| FR-011 (idempotencia) | `test_idempotency`, `test_ledger_service`, `test_ledger_sql_store` (concurrencia) |
| FR-012 a FR-016 (consultas, categorías) | `test_ledger_service`, `test_ledger_tools` |
| FR-017, FR-018 (migración, inmutabilidad) | `test_migrations` (datos del Hito 4, downgrade protegido, disparadores) |
| FR-019 (sin montos) | `test_ledger_tools` (registros y errores), `test_budget_tools` (BODY_LOGGERS en INFO) |
| FR-020 (401) | `test_ledger_tools` |
| FR-021 (invariante) | `test_invariant`, `test_invariant_sql` |

## Actualización del plan técnico al cerrar

`docs/plan-tecnico.md` v0.7: sección "Movimientos (Hito 5)", esquema de la sección 17 (`incomes`
completo, `expenses`, `idempotency_keys`), catálogo (`preview_income`, `create_category`,
`list_categories`), regla 12.2.2 pasa a [DECIDIDO], tabla concepto → tabla. `HITOS.md` v0.8.

## Complexity Tracking

Sin violaciones que justificar.
