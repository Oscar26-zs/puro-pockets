# Data Model: Ingresos base y gastos (MVP)

Migración `0004_movements` (revisa `0003_budget`; no la edita). Nombres en inglés; valores guardados
como en la tabla concepto → tabla del plan técnico.

## `incomes` (se amplía)

| Columna | Tipo | Regla |
|---|---|---|
| `currency` | `TEXT NOT NULL DEFAULT 'CRC'` | `IN ('CRC','USD')` (RN-55) |
| `original_amount` | `BIGINT NOT NULL` | `> 0`; CRC: colones; USD: centavos. Filas existentes: `= amount` |
| `exchange_rate` | `BIGINT` | colones por USD ×100; `NULL` en CRC; `> 0` en USD |
| `voided` | `BOOLEAN NOT NULL DEFAULT FALSE` | RN-53 |
| `voided_at` | `TIMESTAMPTZ` | obligatorio si `voided` |
| `void_reason` | `TEXT` | obligatorio si `voided`; de 3 a 200 caracteres |

CHECK: `(currency = 'CRC' AND exchange_rate IS NULL AND original_amount = amount) OR (currency = 'USD'
AND exchange_rate > 0)`; `(NOT voided AND voided_at IS NULL AND void_reason IS NULL) OR (voided AND
voided_at IS NOT NULL AND void_reason IS NOT NULL)`.

Índice único parcial recreado: `ux_incomes_single_initial_balance ON incomes (kind) WHERE kind =
'saldo_inicial' AND NOT voided` (RN-54: tras anular se permite otra carga).

`amount` sigue siendo el equivalente en colones, base de todos los cálculos (RN-56), calculado una vez.

## `expenses` (nueva)

| Columna | Tipo | Regla |
|---|---|---|
| `id` | `BIGINT IDENTITY PK` | referencia pública `G-<id>` |
| `expense_date` | `DATE NOT NULL` | no futura (se valida en código) |
| `month` | `CHAR(7) NOT NULL` | `'YYYY-MM'` del mes de `expense_date` (RN-32) |
| `pocket_id` | `BIGINT NOT NULL → pockets` | cualquier bolsa activa (RN-33) |
| `category_id` | `BIGINT → categories` | `NULL` = "pendiente de clasificar" (RN-34) |
| `description` | `TEXT` | opcional, hasta 120 caracteres |
| `currency`, `original_amount`, `exchange_rate`, `amount` | como en `incomes` | `amount > 0` (colones) |
| `voided`, `voided_at`, `void_reason` | como en `incomes` | RN-53 |
| `created_at` | `TIMESTAMPTZ NOT NULL DEFAULT now()` | |

Índices: `ix_expenses_month (month)`, `ix_expenses_pocket_month (pocket_id, month)`.

## `idempotency_keys` (nueva)

| Columna | Tipo | Regla |
|---|---|---|
| `operation_id` | `TEXT PK` | 8 a 100 caracteres |
| `tool` | `TEXT NOT NULL` | `add_income`, `add_expense`, `void_transaction` |
| `fingerprint` | `CHAR(64) NOT NULL` | SHA-256 del contenido normalizado |
| `response` | `JSONB NOT NULL` | respuesta original, devuelta tal cual |
| `created_at` | `TIMESTAMPTZ NOT NULL DEFAULT now()` | |

## Protección del libro mayor (disparadores) [PROPUESTO]

- `incomes`, `income_allocations`, `expenses`: `BEFORE DELETE` → error.
- `income_allocations`: `BEFORE UPDATE` → error.
- `incomes`, `expenses`: `BEFORE UPDATE` → error si cambia cualquier columna salvo la anulación
  (`voided` de `FALSE` a `TRUE`, con `voided_at` y `void_reason`) y, en `incomes`,
  `allocation_status` (Hito 6). Deshacer una anulación es error.

## Downgrade protegido

Aborta salvo `ALLOW_DESTRUCTIVE_DOWNGRADE=true` si hay filas en `expenses` o `idempotency_keys`, o
ingresos en USD o anulados. Sin datos: quita disparadores, tablas nuevas y columnas, y recrea el índice
del Hito 4.

## Derivados (no se guardan; principio 3.3)

- Asignado del mes (11.1) = Σ `income_allocations.amount` de ingresos no anulados con ese
  `budget_month`.
- Gastado del mes = Σ `expenses.amount` no anulados con ese `month`.
- Disponible (consumo) = asignado − gastado del mes. Saldo (acumulable) = Σ asignado − Σ gastado, todo
  el historial no anulado.
- Ingreso del mes = Σ `incomes.amount` no anulados de tipo `base` con ese `budget_month` (RN-54: sin
  saldo inicial).
