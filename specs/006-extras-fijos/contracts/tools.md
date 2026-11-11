# Contrato de tools: Extras y gastos fijos (Hito 6)

Todas exigen el token OAuth (sin él, `/mcp` responde 401). Los errores llegan como `isError` con el
mensaje en español, sin montos ni descripciones. Montos: colones enteros; USD como texto con hasta 2
decimales; un número JSON con decimales se rechaza.

## `register_extra_income`

| Parámetro | Tipo | Notas |
|---|---|---|
| `amount` | entero o texto | Obligatorio. |
| `operation_id` | texto 8..100 | Obligatorio. |
| `currency` | `CRC` / `USD` | Por defecto `CRC`. |
| `exchange_rate` | texto | Obligatorio en USD; nunca se asume. |
| `income_date` | `AAAA-MM-DD` | Por defecto hoy; no futura. |
| `source` | texto ≤ 120 | Opcional. |

Respuesta: `reference` (I-n), `kind = extra`, `income_date`, `budget_month` (mes de la fecha),
`currency`, `original_amount`, `exchange_rate`, `amount_crc`, `allocation_status = pendiente`,
`source`, `note`.

## `get_allocation_context`

Parámetro `extra` (I-n). Respuesta: `extra` (datos y estado), `month`, `percentages_source_month`,
`pockets[]` (`pocket`, `behavior`, `percentage`, `budget`, `spent`, `available` o `balance`,
`negative`), `recurring_pending` (`count`, `overdue_count`, `total_crc`, `usd_count`, `usd_total`),
`recent_extras[]` (`budget_month`, `shares[]` con `pocket` y `percentage`). Errores: no es extra, no
existe, anulado.

## `confirm_allocation`

| Parámetro | Tipo | Notas |
|---|---|---|
| `extra` | I-n | Extra pendiente. |
| `percentages` | lista de `{pocket, percentage}` | Enteros 0..100 que suman 100; omitidas = 0. |
| `confirm` | bool | `false` (por defecto) = vista previa. |
| `operation_id` | texto | Obligatorio con `confirm=true`. |
| `preview_token` | texto | Obligatorio con `confirm=true`: el de la vista previa de esos porcentajes. |

Respuesta: `saved`, `reference`, `budget_month`, `amount_crc`, `items[]` (`pocket`, `behavior`,
`percentage`, `amount`; solo las que reciben), `preview_token` (solo en la vista previa),
`allocation_status`. Errores: suma ≠ 100, bolsa inexistente o archivada, porcentaje no entero, falta
la ficha o no coincide, ya repartido, anulado, no es extra, clave reutilizada con otro contenido.

## `manage_recurring`

`action`: `crear` | `listar` | `actualizar` | `desactivar`.

| Parámetro | crear | actualizar | desactivar | listar |
|---|---|---|---|---|
| `operation_id` | obligatorio | obligatorio | obligatorio | — |
| `recurring` (F-n o nombre) | — | obligatorio | obligatorio | — |
| `name` | obligatorio | opcional | — | — |
| `amount` | obligatorio | opcional (desde el mes siguiente) | — | — |
| `currency` | opcional (`CRC`) | rechazado | — | — |
| `day_of_month` | obligatorio (1..31) | opcional | — | — |
| `pocket` | obligatorio o la de la categoría | opcional | — | — |
| `category` | opcional | opcional | — | — |
| `start_month` | opcional (mes actual) | rechazado | — | — |
| `include_inactive` | — | — | — | opcional |

Respuesta: `action`, `saved`, `items[]` (`reference`, `name`, `currency`, `amount` del mes actual,
`scheduled_change`, `day_of_month`, `pocket`, `category`, `start_month`, `active`), `note`.

## `list_pending_recurring`

Parámetro `month` (por defecto el actual). Respuesta: `month`, `pending[]` (`reference`, `name`,
`currency`, `amount`, `amount_crc` o null en USD, `due_date`, `overdue`, `pocket`, `category`),
`paid[]` (`reference`, `name`, `expense_reference`, `amount_crc`), `pending_count`, `overdue_count`,
`pending_total_crc`, `pending_usd_count`, `pending_usd_total`.

## Cambios en tools del Hito 5

- `add_expense`: nuevo `recurring` (F-n o nombre); `amount` opcional solo con `recurring`;
  `currency` por defecto `CRC` o la de la plantilla. Respuesta: `recurring`. Errores nuevos: fijo
  desactivado, ya pagado en el mes, pago antes del inicio, USD sin tipo de cambio.
- `get_summary`: `income_total` = base + extras repartidos; `extra_income_total`; `unassigned`.
- `list_transactions`: `allocation_status` (ingresos), `recurring` (gastos), `description` = origen
  del extra; `unassigned`.
- `void_transaction`: `movement` admite `extra`; advierte si un fijo vuelve a pendiente.
