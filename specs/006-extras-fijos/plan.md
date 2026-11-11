# Implementation Plan: Extras y gastos fijos

**Branch**: `hito-6-extras-fijos` | **Date**: 2026-11-11 | **Spec**: [spec.md](spec.md)

Plan delgado: el stack, la arquitectura y el esquema viven en `docs/plan-tecnico.md` (v0.8, sección
"Extras y gastos fijos (Hito 6)").

## Summary

Extras pendientes con reparto propuesto por Claude y confirmado con la ficha de la vista previa;
plantillas de gastos fijos con historial de monto, pendientes del mes y pago enlazado a `add_expense`.
Migración `0005_extras_recurring`. Se reutilizan `kind = 'extra'` y `allocation_status` de `incomes`
(existen desde 0003; el disparador de 0004 ya permitía cambiar `allocation_status`).

## Technical Context

- **Language/Version**: Python 3.14 con uv; `mcp==2.3.0` (`MCPServer`, parámetro `instructions`).
- **Storage**: PostgreSQL 18; SQLAlchemy 2 Core, psycopg 3 síncrono en un hilo; Alembic.
- **Testing**: pytest (unitarias en memoria, integración en `pp_test_*`), ruff.
- **Constraints**: sin `float`; sin montos ni descripciones en registros; nada se borra.

## Constitution Check

| Regla | Cómo se cumple |
|---|---|
| Principio 3.1 / RN-05 | La app solo entrega agregados y valida; la propuesta es de Claude (instrucciones y descripciones). |
| Principio 3.2 | `confirm_allocation` sin `confirm` es la vista previa; `confirm=true` exige su ficha. |
| Principio 3.3 | Pendientes y "sin asignar" se derivan; nada se guarda como saldo. |
| Principio 3.4 / RN-53 | Disparadores: sin borrar ni editar; un reparto no se deshace; corregir = anular. |
| Principio 3.5 | Montos enteros; USD en centavos; floats rechazados sin mostrar el valor. |
| Principio 3.6 | Reparto, pago y plantilla con su clave de operación en una transacción. |
| Principio 3.8 | Plantillas se desactivan, nunca se borran. |
| Regla no negociable 3 | Invariante 11.4 extendido (200 en memoria, 40 en Postgres). |
| Regla no negociable 4 | 399 pruebas automáticas pasan. |

Sin violaciones. Sin contradicciones entre capas altas.

## Project Structure

```text
specs/006-extras-fijos/   spec, plan, research, data-model, contracts/tools.md, quickstart, tasks,
                          checklists/requirements.md, verificacion.md
src/puro_pockets/
  domain/extras.py, domain/recurring.py, domain/errors.py (errores nuevos)
  services/records.py (registros y LedgerStore), services/ledger_core.py (base común),
  services/extras.py, services/recurring.py (mixins), services/ledger.py (pago de fijos, "sin asignar")
  db/budget_store.py (tablas), db/ledger_store.py (métodos nuevos)
  mcp/extras_tools.py, mcp/inputs.py (entradas opcionales), mcp/ledger_tools.py, mcp/server.py
migrations/versions/0005_extras_recurring.py
tests/unit/test_recurring_domain.py, test_extras_service.py, test_extras_tools.py, test_invariant.py
tests/integration/test_migrations.py, test_extras_sql_store.py, test_invariant_sql.py, conftest.py
tests/fakes.py, tests/synthetic.py
```

## Pruebas

Unitarias (dominio, servicio con almacén en memoria, tools por HTTP con OAuth real), integración
(migraciones sobre base temporal con datos del Hito 5, almacén SQL con concurrencia, invariante en
Postgres) y verificación manual en la base de desarrollo (`verificacion.md`).

## Actualización del plan técnico al cerrar

Hecha: `docs/plan-tecnico.md` v0.8 (sección del Hito 6, catálogo, reglas 12.2.2 y 12.2.5, esquema,
concepto → tabla) y `HITOS.md` v0.9.

## Complexity Tracking

`LedgerService` se dividió en una base (`LedgerCore`) y dos mixins para no superar las ~1000 líneas
en un solo archivo; `services/ledger.py` reexporta los registros para no romper importaciones.
