# Data Model: Extras y gastos fijos (migración `0005_extras_recurring`)

El esquema completo está en `docs/plan-tecnico.md`, sección 17. Aquí solo lo que cambia.

## `incomes` (se reutiliza)

| Columna | Uso en el Hito 6 |
|---|---|
| `kind` | `extra` para los ingresos extra (ya permitido desde 0003). |
| `allocation_status` | `pendiente` (extra "sin asignar") → `repartido` (una sola vez). |
| `budget_month` | Mes de la fecha del extra (RN-09). |
| `source` | Origen opcional del extra, hasta 120 caracteres (CHECK nuevo). |

Restricciones nuevas: `CHECK (kind = 'extra' OR allocation_status = 'repartido')`,
`CHECK (source IS NULL OR char_length(source) <= 120)`. Disparador: `repartido` no vuelve a
`pendiente`; un ingreso anulado no cambia de estado.

## `recurring_expenses` (nueva)

| Columna | Tipo | Reglas |
|---|---|---|
| `id` | BIGINT identidad | Referencia pública `F-<id>`. |
| `name` | TEXT | 1 a 60; único entre las activas sin distinguir mayúsculas. |
| `currency` | TEXT | `CRC` o `USD`; no se cambia. |
| `day_of_month` | INTEGER | 1 a 31; mes corto → último día. |
| `pocket_id` | FK `pockets` | Bolsa por defecto del pago. |
| `category_id` | FK `categories`, nulo | Categoría por defecto. |
| `start_month` | CHAR(7) | Primer mes; no se cambia. |
| `active` / `deactivated_at` | BOOLEAN / TIMESTAMPTZ | `active = (deactivated_at IS NULL)`; no se reactiva. |

Sin DELETE (disparador).

## `recurring_expense_amounts` (nueva)

`(recurring_id, from_month)` PK; `original_amount > 0` (CRC colones, USD centavos). Sin tipo de
cambio. Sin DELETE.

## `expenses`

`recurring_id` FK nula; índice único parcial `ux_expenses_recurring_month (recurring_id, month)
WHERE recurring_id IS NOT NULL AND NOT voided`. No se edita (disparador de 0004).

## Estados

```
extra:   pendiente ──confirm_allocation──► repartido
            │                                  │
            └──void_transaction──► anulado ◄───┘  (revierte el reparto)
plantilla: activa ──desactivar──► desactivada (final)
fijo en un mes: pendiente ──pago──► pagado ──anular el pago──► pendiente
```
