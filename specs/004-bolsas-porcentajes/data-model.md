# Modelo de datos: Bolsas y porcentajes (Hito 4)

**Migración:** `0003_budget` (revisa `0002_oauth`). El SQL de referencia completo está en
`docs/plan-tecnico.md`, sección 17; aquí solo se resumen las tablas, sus reglas y las del código.

## Tablas

| Tabla | Columnas | Restricciones |
|---|---|---|
| `pockets` | `id`, `name`, `behavior`, `group_name`, `surplus_target_pocket_id`, `active`, `created_at` | `name` único sin distinguir mayúsculas (índice sobre `lower(name)`); `behavior IN ('consumo','acumulable')` (RN-10); `active` por defecto `TRUE` |
| `categories` | `id`, `name`, `pocket_id`, `active` | `name` único sin distinguir mayúsculas; FK a `pockets` |
| `budget_month_allocations` | `month`, `pocket_id`, `percentage` | PK (`month`, `pocket_id`); `month` `CHAR(7)` con `CHECK '^[0-9]{4}-(0[1-9]\|1[0-2])$'`; `percentage` entero 0 a 100 |
| `incomes` | `id`, `income_date`, `kind`, `source`, `budget_month`, `amount`, `allocation_status`, `note`, `created_at` | `kind IN ('base','extra','saldo_inicial')`; `amount > 0` (colones); `allocation_status IN ('pendiente','repartido')`; índice único parcial: un solo `saldo_inicial` (RN-54) |
| `income_allocations` | `id`, `income_id`, `pocket_id`, `percentage`, `amount` | `amount >= 0`; `percentage` NULL en el saldo inicial; único (`income_id`, `pocket_id`) |

**Datos iniciales** (en la migración, editables): Necesidades (`consumo`), Ahorro (`acumulable`),
Gustos (`consumo`), en ese orden. Sin porcentajes ni categorías.

**Downgrade protegido:** `0003_budget` aborta el downgrade si hay datos (spec, resumen), salvo con
`ALLOW_DESTRUCTIVE_DOWNGRADE=true`.

**Hito 5** agrega a `incomes`, con su propia migración: `currency`, `original_amount`,
`exchange_rate`, `voided`, `voided_at`, `void_reason` (ver [research.md](research.md) §4).

## Reglas que viven en el código (capa `domain/`)

| Regla | Dónde | Comportamiento |
|---|---|---|
| RN-01 | `domain/allocation.py` | La suma es exactamente 100; cada bolsa activa aparece una vez; enteros entre 0 y 100. |
| RN-02 | servicio + tabla | `set_allocation` reemplaza solo las filas del mes indicado; meses pasados rechazados. |
| RN-03 | `domain/allocation.py` | Un mes sin filas se resuelve con el mes anterior más cercano con filas; no se guarda nada. |
| RN-08 | `domain/allocation.py` | `split_amount`: hacia abajo para todas menos la última (por `id`), que recibe el residuo. |
| RN-10 a 12 | `domain/balances.py` | Saldo de acumulable (11.2) y disponible de consumo por mes (11.1). |
| RN-54 | `domain/initial_balance.py` + índice | Montos enteros ≥ 0, total > 0, bolsas activas; una sola carga. |
| Mes | `domain/months.py` | `Month` (`YYYY-MM`), validación, comparación, anterior y siguiente. |

## Cálculos en el Hito 4

Sin gastos, transferencias ni cierres todavía:

```
asignado(bolsa, mes)   = Σ income_allocations.amount de ingresos 'repartido' con budget_month = mes
disponible consumo     = asignado(bolsa, mes actual)                          (11.1)
saldo acumulable       = Σ income_allocations.amount de todos los meses        (11.2)
invariante (11.4)      : Σ incomes.amount 'repartido' = Σ saldos acumulables
                         + Σ disponibles de consumo de todos los meses (todos abiertos)
```

El saldo inicial no se cuenta en las estadísticas de ingresos del mes (`kind = 'saldo_inicial'` se
excluye de ellas desde el Hito 5), pero sí en los saldos (RN-54).

## Transiciones

- `incomes.allocation_status`: el saldo inicial se crea ya `repartido`, en la misma transacción que
  sus repartos (principio 3.6). `pendiente` se usará con los ingresos extra (Hito 6).
