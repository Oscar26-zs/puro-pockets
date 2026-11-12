# Data Model: Transferencias entre bolsas

## `transfers` (migración `0007_transfers`)

| Columna | Tipo | Regla |
|---|---|---|
| `id` | BIGINT identity | Referencia pública `T-<id>`; no se expone otro identificador. |
| `transfer_date` | DATE | Siempre hoy (America/Costa_Rica). |
| `month` | CHAR(7) | Mes de la fecha; CHECK `^[0-9]{4}-(0[1-9]\|1[0-2])$`. |
| `from_pocket_id` | BIGINT FK `pockets` | ON DELETE RESTRICT; bolsa activa (se valida en código). |
| `to_pocket_id` | BIGINT FK `pockets` | ON DELETE RESTRICT; CHECK distinto del origen (RN-41). |
| `amount` | BIGINT | Colones; CHECK > 0 (RN-41). |
| `reason` | TEXT | CHECK `cubrir_sobregasto`, `reasignacion`, `cierre_de_mes`, `ajuste` (la tool no acepta `cierre_de_mes`). |
| `note` | TEXT NULL | CHECK hasta 140 caracteres. Nunca en registros ni errores. |
| `created_at` | TIMESTAMPTZ | `now()`. |

Índices: `ix_transfers_month`, `ix_transfers_from_month`, `ix_transfers_to_month`.
Disparador `trg_transfers_immutable`: BEFORE UPDATE OR DELETE → error (RN-43).

## Cálculos (sin columnas nuevas: todo se deriva, principio 3.3)

```
presupuesto ajustado (mes) = asignado + recibidas del mes − enviadas del mes      (9.1)
disponible (consumo)       = ajustado − gastado del mes                           (11.1)
saldo (acumulable)         = Σ asignado + Σ recibidas − Σ enviadas − Σ gastos     (11.2)
% usado                    = gastado / ajustado; referencia: gastado / asignado   (11.1)
```

## Registros del servicio

- `TransferEntry(from_pocket_id, to_pocket_id, month, amount)` para los cálculos.
- `NewTransfer`, `TransferRow` y `LedgerSnapshot` (lo leído con las bolsas bloqueadas).
