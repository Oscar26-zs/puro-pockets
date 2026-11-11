# Contrato de tools: Hito 5

Todas exigen el token OAuth (sin él: HTTP 401). Los errores llegan como resultado con `isError: true` y
un mensaje en español sin montos ni descripciones. Bolsas y categorías se identifican por nombre (sin
distinguir mayúsculas); los movimientos por referencia (`I-3`, `G-12`). Ninguna respuesta incluye
identificadores internos.

**Montos de entrada**: `amount` es entero (colones o dólares enteros) o texto (`"10.50"`, hasta 2
decimales con punto, sin separador de miles; en CRC solo dígitos). `exchange_rate` es entero o texto con
hasta 2 decimales. Un número JSON con decimales (`10.5`) se rechaza.

**Montos de salida**: `original_amount` y `exchange_rate` como texto (`"10.00"`, `"512.34"`; CRC sin
decimales); `amount_crc` y todos los saldos como enteros de colones.

**Clave de operación** (`operation_id`): texto de 8 a 100 caracteres (`A-Z a-z 0-9 . _ : -`), nueva por
operación y la misma en cada reintento. Misma clave + mismo contenido → respuesta original; misma clave +
otro contenido → error.

## `preview_income` / `add_income`

Entrada: `amount`, `currency` (`CRC` por defecto | `USD`), `exchange_rate` (obligatorio en USD,
prohibido en CRC), `income_date` (`AAAA-MM-DD`, por defecto hoy, no futura), `budget_month` (`AAAA-MM`,
por defecto el mes siguiente a la fecha). `add_income` agrega `confirm` (por defecto `false`) y
`operation_id` (obligatorio con `confirm=true`).

Salida `IncomeResult`: `saved`, `reference` (`null` si no se guardó), `kind` (`base`), `income_date`,
`budget_month`, `currency`, `original_amount`, `exchange_rate`, `amount_crc`, `allocation_source_month`
(mes del que vienen los porcentajes, RN-03), `items[]` (`pocket`, `behavior`, `percentage`, `amount`).

Errores: sin porcentajes en el mes ni antes; USD sin tipo de cambio; tipo de cambio fuera de rango;
conversión a 0; fecha futura; mes inválido; clave en conflicto o faltante al confirmar.

## `add_expense`

Entrada: `amount`, `operation_id`, `pocket` (opcional si hay `category`), `category` (opcional),
`currency`, `exchange_rate`, `expense_date` (por defecto hoy, no futura), `description` (opcional, hasta
120 caracteres).

Salida `ExpenseResult`: `reference`, `expense_date`, `month`, `pocket`, `category` (nombre o
`"pendiente de clasificar"`), `currency`, `original_amount`, `exchange_rate`, `amount_crc`,
`pocket_balance` (`balance`, `balance_kind`: `disponible_del_mes` | `saldo`), `overspent`, `warning`
(texto o `null`), `available_pockets[]` (solo si `overspent`: `pocket`, `balance`, `balance_kind`).

## `void_transaction`

Entrada: `reference`, `reason` (3 a 200 caracteres), `operation_id`, `confirm` (por defecto `false`: vista
previa).

Salida `VoidResult`: `saved`, `reference`, `movement` (`gasto` | `ingreso` | `saldo_inicial`), `date`,
`month`, `amount_crc`, `voided_on` (`null` en la vista previa), `negative_pockets[]` (`pocket`, `balance`,
`balance_kind`), `warning`, `initial_balance_reloadable` (`true` si se anuló el saldo inicial).

Errores: referencia inválida o inexistente; ya anulado; clave en conflicto.

## `get_bolsa_status`

Entrada: `pocket`, `month` (por defecto el actual).

Salida: `pocket`, `behavior`, `month`, `assigned`, `transfers_in` (0), `transfers_out` (0),
`adjusted_budget` (= `assigned`), `spent`, `available` (consumo) o `null`, `percent_used` (consumo, entero
o `null`), `balance` (acumulable, 11.2) o `null`, `negative`.

## `get_summary`

Entrada: `month` (por defecto el actual).

Salida: `month`, `income_total` (solo base, sin saldo inicial), `expense_total`, `pockets[]` (`pocket`,
`behavior`, `assigned`, `spent`, `available` | `null`, `balance` | `null`, `negative`),
`negative_pockets[]` (nombres).

## `top_categories`

Entrada: `month` (por defecto el actual), `limit` (5 por defecto, de 1 a 20).

Salida: `month`, `total_spent`, `items[]` (`category`, `amount_crc`, `count`, `percent` entero hacia
abajo).

## `list_transactions`

Entrada: `month` (opcional; ingresos por mes presupuestario), `type` (`gasto` | `ingreso`, opcional),
`pocket` (opcional; solo gastos), `include_voided` (`true` por defecto), `limit` (20 por defecto, de 1 a
100).

Salida: `items[]` (`reference`, `type`, `kind` (ingresos: `base` | `saldo_inicial`), `date`, `month`,
`pocket`, `category`, `description`, `currency`, `original_amount`, `exchange_rate`, `amount_crc`,
`voided`, `void_reason`), `has_more`.

## `create_category` / `list_categories`

`create_category`: `name` (1 a 60), `pocket` (bolsa por defecto). Salida: `name`, `pocket`.
`list_categories`: sin entrada. Salida: `items[]` (`name`, `pocket`).
