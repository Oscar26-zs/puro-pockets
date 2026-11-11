# Investigación: Bolsas y porcentajes (Hito 4)

**Fecha:** 2026-11-10 · **Spec:** [spec.md](spec.md)

Cada punto sigue el formato decisión, razón y alternativas. Los puntos marcados antes como
[PROPUESTO] fueron aprobados por el propietario el 2026-11-10 (**[APROBADO]**).

## 1. Errores de las tools

- **Decisión:** las validaciones de dominio lanzan `DomainError` con un mensaje en español; la capa MCP
  lo convierte en `ToolError` del SDK (`mcp.server.mcpserver.exceptions`). El cliente recibe
  `is_error=True` con el texto; el SDK lo registra en INFO sin traza.
- **Razón:** verificado en `mcp==2.3.0` (`tools/base.py`): `ToolError` es la falla prevista; cualquier
  otra excepción llega al modelo solo como "Error executing tool <nombre>", sin detalle.
- **Consecuencia:** como el SDK registra el mensaje, **los mensajes de error no incluyen montos**
  (FR-014). Pueden incluir porcentajes, meses y nombres de bolsa.
- **Alternativas:** devolver `{ok: false, error}` como resultado normal (descartada: Claude no lo
  distingue de un éxito).

## 2. Zona horaria del mes actual

- **Decisión:** `APP_TIMEZONE` (por defecto `America/Costa_Rica`) con `zoneinfo`. El dominio recibe
  la fecha local ya calculada; la conversión vive en el servicio.
- **Razón:** verificado: `zoneinfo.ZoneInfo("America/Costa_Rica")` funciona en Windows y en el
  contenedor `python:3.14-slim`. En Windows necesita el paquete `tzdata`, que ya está instalado
  (v2026.6) como dependencia de psycopg.
- **[APROBADO]:** declarar `tzdata` como dependencia directa en `pyproject.toml`, porque el código lo
  usa directamente. No instala nada nuevo: ya está en `uv.lock`.
- **Alternativas:** desfase fijo UTC−6 (Costa Rica no tiene horario de verano); descartada porque la
  zona debe ser configurable.

## 3. Unicidad del saldo inicial

- **Decisión:** índice único parcial `ux_incomes_single_initial_balance ON incomes (kind) WHERE kind =
  'saldo_inicial'`, además de la comprobación del servicio.
- **Razón:** garantiza RN-54 también ante dos cargas simultáneas (la segunda recibe un error de
  unicidad, que se traduce al mismo mensaje en español). En el Hito 5 se recrea con `AND NOT voided`
  para permitir recargar tras una anulación.
- **Alternativas:** bloqueo de tabla o `SERIALIZABLE` (más complejo, sin ventaja).

## 4. Diseño pensando en el Hito 5

- **Decisión:** `incomes.amount` es siempre el equivalente en colones y la base de todos los cálculos.
  El Hito 5 agrega con su propia migración `currency` (por defecto `'CRC'`), `original_amount`
  (rellenado con `amount` en las filas existentes), `exchange_rate`, `voided`, `voided_at`,
  `void_reason` y el `CHECK` de moneda. Ninguna consulta del Hito 4 cambia.
- **Razón:** el propietario pidió dejar la moneda para el Hito 5 (FR-015).

## 5. Identificación de bolsas en las tools

- **[APROBADO]:** las tools reciben y devuelven las bolsas **por nombre** (único), comparando sin
  distinguir mayúsculas ni espacios al borde. No exponen ids.
- **Razón:** el propietario habla de "Ahorro", no de "bolsa 2"; minimización (principio 3.10).
- **Alternativas:** por id (obliga a Claude a listar primero).

## 6. Orden de las bolsas para RN-08

- **Decisión:** orden de creación (`pockets.id`). Los datos iniciales se crean en el orden
  Necesidades, Ahorro, Gustos, así que Gustos absorbe el residuo (₡10.001 → 5.000 / 3.000 / 2.001).

## 7. Aislamiento de las pruebas de integración

- **[APROBADO]:** las pruebas de integración crean una base temporal propia (`pp_test_<aleatorio>`)
  y se niegan a correr contra cualquier otra base en el Postgres local, aplican las migraciones, y la borran al terminar.
- **Razón:** no tocan los datos de desarrollo y cada prueba arranca sin saldo inicial (la regla de una
  sola carga haría fallar una segunda ejecución). El usuario de la imagen oficial de Postgres puede
  crear bases. Nunca se ejecutan contra el homelab.
- **Alternativas:** transacción con rollback (no sirve para la prueba de cargas simultáneas, que
  necesita dos conexiones que confirman).

## 8. Prueba del invariante sin dependencias nuevas

- **[APROBADO]:** generador propio con `random.Random(semilla)`: 200 conjuntos de datos sintéticos
  (entre 1 y 8 bolsas con comportamiento al azar, porcentajes que suman 100, un saldo inicial y
  varios ingresos sintéticos repartidos con RN-08 en varios meses). La semilla se imprime al fallar
  para reproducir el caso.
- **Razón:** evita agregar `hypothesis`; los Hitos 5, 8 y 9 extienden el mismo generador con gastos,
  transferencias y cierres.
- **Qué se compara:** el lado izquierdo (suma de `incomes.amount` repartidos, consultada directamente)
  contra el lado derecho (saldos de acumulables + disponibles de consumo de todos los meses,
  calculados por el mismo código que usa `list_bolsas`). Así la prueba detecta repartos que no suman
  el ingreso y cálculos de saldo erróneos.
- **Alternativas:** `hypothesis` (dependencia nueva; se puede adoptar después si el propietario
  quiere).

## 9. Registros sin montos

- **Decisión:** los servicios registran solo eventos ("Porcentajes guardados: mes=2026-11", "Saldo
  inicial cargado: mes=2026-11, bolsas=3"), nunca montos ni saldos. Una prueba captura los registros
  de la carga del saldo inicial y comprueba que no contienen los montos sintéticos.
