# Implementation Plan: Transferencias entre bolsas

**Branch**: `hito-8-transferencias` | **Date**: 2026-11-11 | **Spec**: [spec.md](spec.md)

## Summary

Registro inmutable de transferencias entre bolsas (RN-39 a RN-44), vista previa con el efecto sobre
las metas (RN-58), presupuesto ajustado en todas las consultas (9.1) con una sola función, y
archivado de bolsas completado (RN-18). Detalle técnico en [research.md](research.md).

## Technical Context

- **Lenguaje**: Python 3.14 con uv; SQLAlchemy Core; psycopg síncrono vía `anyio.to_thread`.
- **MCP**: `mcp==2.3.0` (`MCPServer`), Streamable HTTP detrás de OAuth.
- **Base**: PostgreSQL 18; Alembic (migración `0007_transfers`).
- **Pruebas**: pytest; unitarias con almacén en memoria; integración en bases temporales `pp_test_*`.

## Constitution Check

| Regla | Cumplimiento |
|---|---|
| Ningún dato real antes de autenticación | Autenticación cerrada en el Hito 3; datos de prueba sintéticos. |
| Lógica de negocio en capa propia | `domain/transfers.py` y `domain/balances.py`; el almacén solo bloquea, lee e inserta. |
| Invariante 11.4 con prueba automática | 200 conjuntos en memoria y 40 en Postgres con transferencias. |
| Pruebas en el hito | Unitarias, integración, migración, concurrencia, autenticación y registros. |
| RN-43 / principio 3.4 | Disparador que rechaza UPDATE/DELETE; sin tools de anulación. |
| Precedencia | Sin contradicciones en capas altas; correcciones en capas 2 y 3 (ver research). |

## Project Structure

```
src/puro_pockets/
  domain/balances.py        # TransferEntry, received/sent, PocketFigures, pocket_figures
  domain/transfers.py       # motivos, nota, monto, fecha, T-n, RN-41/42, efecto en metas (RN-58)
  domain/goals.py           # saldo y RN-28 con transferencias
  services/transfers.py     # TransfersMixin: preview_transfer, transfer_between_bolsas
  services/ledger_core.py   # LedgerData (repartos, gastos, transferencias) y figures()
  services/ledger.py        # consultas con 9.1, sobregasto (RN-37), listado con T-n
  services/flex.py          # archivado con nueva comprobación dentro de la transacción
  db/budget_store.py        # tabla transfers, transfer_entries, _settle_goals con transferencias
  db/ledger_store.py        # _lock_and_read, record_transfer, list_transfers, archive con bloqueo
  mcp/transfers_tools.py    # las dos tools
migrations/versions/0007_transfers.py
```
