# Research: Ingresos base y gastos (MVP)

## R1. Montos sin `float`

- **Decisión**: las tools aceptan colones como entero y USD y tipo de cambio como entero o texto con
  hasta 2 decimales (`"10.50"`). Un número JSON con decimales se rechaza con un mensaje en español que
  pide enviarlo como texto. El texto se lee con `Decimal` y se pasa a centavos (o a ×100) con una
  comprobación exacta; de ahí en adelante todo es `int`.
- **Por qué**: el JSON-RPC llega ya decodificado; un `10.5` es `float` antes de llegar a la tool. El
  SDK (`func_metadata.pre_parse_json`, `mcp==2.3.0`) deja intactos los textos que decodifican a un
  escalar, así que `"10.50"` llega como texto. Verificado en el código instalado.
- **Alternativas**: aceptar `float` y redondear (viola el principio 3.5); pedir centavos enteros (poco
  natural para el propietario y propenso a errores ×100).

## R2. Conversión half-up en enteros

- **Decisión**: `crc = (centavos × tasa_x100 + 5 000) // 10 000` (todos positivos). USD 10,00 a 512,34:
  `(1 000 × 51 234 + 5 000) // 10 000 = 5 123`. Se rechaza el resultado 0.
- **Alternativas**: `Decimal.quantize(ROUND_HALF_UP)`: mismo resultado, más pasos; el entero es exacto.

## R3. Idempotencia

- **Decisión**: tabla `idempotency_keys(operation_id PK, tool, fingerprint, response JSONB)`. El servicio
  normaliza la entrada, calcula la huella (SHA-256 de JSON canónico) y consulta la clave: si existe con la
  misma huella devuelve la respuesta guardada; con otra huella, error. Si no existe, el almacén escribe el
  movimiento y la clave en la misma transacción; si otra llamada simultánea insertó la clave primero
  (violación de la PK), se revierte y se repite la consulta.
- **Por qué**: devuelve exactamente el resultado original (las advertencias de sobregasto podrían cambiar
  si se recalcularan) y la PK resuelve la carrera sin bloqueos explícitos.
- **Alternativas**: columna `operation_id` única en cada tabla (no cubre la anulación ni guarda la
  respuesta).

## R4. Referencias cortas

- **Decisión**: `I-<n>` y `G-<n>` con el número de fila (identidad) de `incomes` y `expenses`. [PROPUESTO]
- **Por qué**: cortas, legibles y estables; no requieren otra secuencia. No revelan nada más que el orden
  de registro.
- **Alternativa**: una secuencia pública aparte (más columnas, mismo efecto práctico).

## R5. Nueva carga del saldo inicial

- **Decisión**: la migración recrea `ux_incomes_single_initial_balance` con
  `WHERE kind = 'saldo_inicial' AND NOT voided`. `has_initial_balance` ignora los anulados.

## R6. Libro mayor inmutable en la base

- **Decisión**: disparadores `BEFORE DELETE` en `incomes`, `income_allocations` y `expenses`, `BEFORE
  UPDATE` en `income_allocations`, y `BEFORE UPDATE` en `incomes` y `expenses` que solo permiten pasar de
  no anulado a anulado (más `allocation_status`, que usará el Hito 6). `TRUNCATE` no dispara reglas por
  fila, así que las pruebas pueden vaciar su base temporal. [PROPUESTO]
- **Por qué**: "nada borra filas del libro mayor" queda garantizado aunque un script futuro se equivoque.

## R7. Migración que conserva datos

- **Decisión**: `original_amount` se agrega nulo, se rellena con `amount` y luego se marca `NOT NULL`;
  `currency` con valor por defecto `'CRC'`; `voided` con `FALSE`. Se prueba en una base temporal llevada
  a `0003_budget` con datos sintéticos del Hito 4 (porcentajes, saldo inicial y repartos) antes de subir a
  `0004_movements`.

## R8. Rango del tipo de cambio

- **Decisión**: `USD_RATE_MIN` y `USD_RATE_MAX` en colones enteros (por defecto 300 y 1000), validadas al
  arrancar (enteros, mínimo > 0 y mínimo < máximo). [PROPUESTO]
