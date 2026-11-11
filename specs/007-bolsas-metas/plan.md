# Implementation Plan: Bolsas flexibles y metas

**Branch**: `hito-7-bolsas-metas` | **Date**: 2026-11-11 | **Spec**: [spec.md](spec.md)

Plan delgado: stack, arquitectura y esquema en `docs/plan-tecnico.md` v0.9 ("Bolsas flexibles y
metas (Hito 7)").

## Summary

Reajuste de porcentajes como función pura (`domain/rebalance.py`), crear y archivar bolsas con vista
previa y ficha, metas sin dinero propio con evaluación centralizada de `lograda` en los almacenes
(`_settle_goals` → `domain.goals.reached`). Migración `0006_pockets_goals`.

## Technical Context

Python 3.14, `mcp==2.3.0`, PostgreSQL 18, SQLAlchemy 2 Core, Alembic, pytest, ruff. Sin `float`; sin
montos ni nombres de metas en registros; nada se borra.

## Constitution Check

| Regla | Cómo se cumple |
|---|---|
| RN-13 / principio 3.6 | Bolsa y porcentajes en una transacción (`create_pocket`). |
| RN-01, RN-14 | `rebalance_add` / `rebalance_remove` con prueba de propiedades. |
| RN-15, RN-02 | Mes siguiente por defecto; nunca uno pasado; los repartos guardan su %. |
| RN-16 a RN-18 | Archivado solo con saldo cero; inmediato; reescribe meses actuales y futuros. |
| RN-21 a RN-25 | Acumulable activa; índice único parcial; avance = `accumulated_balance`. |
| RN-24 | `reached` en la transacción de cada operación que sube un saldo. |
| RN-28, RN-29 | Números para Claude; excedente informado, se queda en la bolsa. |
| Principio 3.1 / 3.2 | La app calcula; vista previa con ficha; Claude propone y el propietario aprueba. |
| Principio 3.8 | Bolsas y metas se archivan, nunca se borran (disparadores). |
| Reglas no negociables 3 y 4 | Invariante extendido; 461 pruebas pasan. |

Sin violaciones. Sin contradicciones entre capas altas.

## Project Structure

```text
src/puro_pockets/domain/rebalance.py, goals.py, pockets.py (validaciones), errors.py
src/puro_pockets/services/flex.py, goals.py, records.py, ledger.py (mixins, bolsa archivada, meta
  en get_bolsa_status), extras.py (metas en el contexto)
src/puro_pockets/db/budget_store.py (_settle_goals, tablas), ledger_store.py (bolsas y metas)
src/puro_pockets/mcp/pockets_tools.py, server.py, ledger_tools.py
migrations/versions/0006_pockets_goals.py
tests/unit/test_rebalance_goals_domain.py, test_pockets_goals_service.py, test_pockets_tools.py,
  test_invariant.py; tests/integration/test_migrations.py, test_pockets_goals_sql_store.py,
  conftest.py; tests/fakes.py, tests/synthetic.py
```

## Complexity Tracking

Dos mixins más en `LedgerService` (bolsas y metas), siguiendo el patrón del Hito 6.
