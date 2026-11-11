# Contrato: tools MCP del Hito 4

**Spec:** FR-004 a FR-011 · **Transporte:** Streamable HTTP en `/mcp`, con token OAuth (Hito 3).
Sin token, ninguna tool responde (401).

**Convenciones:**
- Las bolsas se identifican **por nombre**, sin distinguir mayúsculas ni espacios al borde
  ([research.md](../research.md) §5). No se exponen ids.
- Los meses son texto `YYYY-MM`. Si se omite, el mes es el actual (America/Costa_Rica).
- Los montos son colones enteros.
- **Error:** la tool termina con `is_error=true` y un mensaje en español, sin montos (research §1).
  No se guarda nada.
- Cada tool publica su esquema de salida (`outputSchema`).

## `set_allocation`

Guarda los porcentajes de un mes (RN-01, RN-02).

**Entrada:** `month` (texto, opcional) y `percentages` (lista de `{pocket, percentage}`).

**Salida:** `month` y `items` (lista de `{pocket, behavior, percentage}` en orden de creación).

**Errores:**

| Caso | Mensaje (ejemplo) |
|---|---|
| Suma distinta de 100 | "Los porcentajes deben sumar exactamente 100; suman 110." |
| Falta una bolsa activa | "Falta el porcentaje de: Gustos. Indica todas las bolsas activas (0 si no recibe)." |
| Bolsa repetida, inexistente o archivada | "La bolsa 'Viaje' no existe o está archivada." |
| Porcentaje fuera de 0 a 100 o no entero | "El porcentaje de Ahorro debe ser un entero entre 0 y 100." |
| Mes pasado | "No se pueden cambiar los porcentajes de 2026-10: es un mes pasado." |
| Mes con formato inválido | "El mes debe tener el formato AAAA-MM (por ejemplo 2026-11)." |

## `get_allocation`

Consulta los porcentajes de un mes (RN-02, RN-03). No guarda nada.

**Entrada:** `month` (opcional).

**Salida:**

| Campo | Tipo | Notas |
|---|---|---|
| `month` | texto | El mes consultado. |
| `defined` | booleano | `false` si ni ese mes ni uno anterior tiene porcentajes. |
| `source_month` | texto o nulo | El mes del que vienen; igual a `month` si son propios. |
| `items` | lista de `{pocket, behavior, percentage}` | Vacía si `defined` es `false`. |

```json
{ "month": "2026-12", "defined": true, "source_month": "2026-11",
  "items": [ {"pocket": "Necesidades", "behavior": "consumo", "percentage": 50},
             {"pocket": "Ahorro", "behavior": "acumulable", "percentage": 30},
             {"pocket": "Gustos", "behavior": "consumo", "percentage": 20} ] }
```

Si alguna bolsa activa no tiene porcentaje en el mes de origen (por ejemplo, una bolsa creada después
en el Hito 7), aparece con `percentage: 0`.

## `preview_initial_balance`

Vista previa del saldo inicial (principio 3.2, RN-54). **No guarda nada.**

**Entrada:** `amounts` (lista de `{pocket, amount}`). Las bolsas activas omitidas cuentan como 0.

**Salida:** `month` (mes al que pertenecerá: el actual en America/Costa_Rica), `total`, `items` (lista de
`{pocket, behavior, amount}` con todas las bolsas activas) y `already_loaded` (booleano; si es `true`,
`load_initial_balance` lo rechazará).

**Errores:** los mismos de validación que `load_initial_balance`.

## `load_initial_balance`

Carga el saldo inicial, una sola vez, en una transacción (RN-54, principio 3.6).

**Entrada:** `amounts` (igual que `preview_initial_balance`) y `confirm` (booleano, por defecto
`false`). Sin `confirm=true` no guarda nada y devuelve la vista previa.

**Salida:** `saved` (booleano), `month`, `total`, `items` y `already_loaded`, con la misma forma que
la vista previa. `saved` es `true` solo si se guardó.

No existe ninguna tool ni script que borre el saldo inicial; se corrige con la anulación del Hito 5.

**Errores:**

| Caso | Mensaje (ejemplo) |
|---|---|
| Ya hay un saldo inicial (también ante dos cargas simultáneas) | "El saldo inicial ya fue cargado; solo se carga una vez." |
| Monto negativo o no entero | "El monto de Gustos debe ser un entero mayor o igual a 0." |
| Todos los montos en 0 | "El saldo inicial debe tener al menos un monto mayor que 0." |
| Bolsa repetida, inexistente o archivada | "La bolsa 'Viaje' no existe o está archivada." |

## `list_bolsas`

Lista las bolsas activas con su saldo (RN-10 a RN-12). No guarda nada.

**Entrada:** ninguna.

**Salida:** `month` (mes actual) y `pockets` (lista en orden de creación):

| Campo | Tipo | Notas |
|---|---|---|
| `name` | texto | |
| `behavior` | texto | `consumo` o `acumulable` |
| `balance` | entero | Colones. Acumulable: saldo (11.2). Consumo: disponible del mes actual (11.1). |
| `balance_kind` | texto | `saldo` o `disponible_del_mes` |
