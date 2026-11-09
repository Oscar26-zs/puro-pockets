# Plan técnico de Puro Pockets

**Versión:** 0.1
**Fecha:** 2026-11-09
**Capa:** 2 en la gobernanza de `.specify/memory/constitution.md`. Decide la técnica; si contradice a
la constitución, gana la constitución y se corrige este documento.

Este documento contiene el stack, la arquitectura, el catálogo de tools y el esquema de datos. Las
reglas de negocio no se repiten aquí: se citan por su identificador (`RN-xx`). La numeración de las
secciones 12, 13, 15, 16 y 17 conserva la del documento de origen v0.3
(`docs/origen/CONSTITUCION-origen.md`, archivado). Se actualiza al cerrar cada hito si cambió el
esquema o la arquitectura.

**Hoja de ruta:** el alcance, el orden y los criterios de cierre de cada hito están en
[`HITOS.md`](../HITOS.md). Este documento no copia el mapa de hitos.

---

## Stack

| Área | Elección | Estado |
|---|---|---|
| Lenguaje | Python (3.12 o superior) | [DECIDIDO] (decisión 10) |
| Gestor de entornos y dependencias | uv | [PROPUESTO] |
| Base de datos | PostgreSQL en Docker (Docker Compose), con volumen persistente y puerto atado a `127.0.0.1` | [DECIDIDO] |
| Acceso a datos | SQLAlchemy | [DECIDIDO] |
| Migraciones | Alembic | [DECIDIDO] |
| Servidor MCP | Remoto por HTTPS (transporte Streamable HTTP) | [DECIDIDO] (decisión 9) |
| SDK de MCP | Biblioteca y versión por fijar | [ABIERTO]: se resuelve en el Hito 1 |
| Publicación | Túnel con nombre de Cloudflare hacia un subdominio fijo | [DECIDIDO] (decisión 9) |
| Autenticación del MCP | OAuth (el MCP actúa como servidor de recursos) | [DECIDIDO] |
| Servidor de autorización de OAuth | Propio o externo | [ABIERTO]: se resuelve en el Hito 3 |
| Pruebas y estilo | pytest y ruff; CI en GitHub Actions | Definido en `HITOS.md` (Hito 1) |
| Dashboard | React + Vite + TypeScript + Tailwind, con una librería de gráficos | [PROPUESTO] (sección 16) |
| API del dashboard | Framework por decidir | [ABIERTO]: se resuelve en el Hito 10 |
| Ejecución | Homelab del propietario | [DECIDIDO] |

---

## 12. Integración con Claude (MCP)

### 12.1 Catálogo de tools

| Tool | Función | Estado |
|---|---|---|
| `load_initial_balance` | Cargar el saldo inicial repartido por montos entre bolsas (una sola vez). | [DECIDIDO] |
| `add_expense` | Registrar gasto (con moneda y, si es USD, tipo de cambio). Si deja una bolsa en negativo, devuelve advertencia con las bolsas disponibles. | [DECIDIDO] |
| `add_income` | Registrar ingreso base (con moneda y tipo de cambio si aplica). | [DECIDIDO] |
| `register_extra_income` | Registrar ingreso extra en estado pendiente. | [DECIDIDO] |
| `get_allocation_context` | Entregar a Claude el panorama del mes: presupuesto vs gastado por bolsa, fijos pendientes, metas y repartos previos. | [DECIDIDO] |
| `confirm_allocation` | Confirmar el reparto de un extra (valida suma = 100). | [DECIDIDO] |
| `void_transaction` | Anular un ingreso o gasto con motivo, solo en mes abierto. Reemplaza a `update_transaction` y `delete_transaction`. | [DECIDIDO] |
| `get_bolsa_status` | Estado de una bolsa: asignado, transferencias, gastado, disponible y avance de su meta si la tiene. | [DECIDIDO] |
| `get_summary(mes)` | Resumen mensual. | [DECIDIDO] |
| `top_categories` | En qué se gasta más. | [DECIDIDO] |
| `list_transactions` | Listar movimientos con filtros. | [DECIDIDO] |
| `manage_recurring` | Crear, listar y modificar gastos fijos. | [DECIDIDO] |
| `set_allocation` / `update_allocation` | Cambiar porcentajes de un mes. | [DECIDIDO] |
| `preview_rebalance` | Calcular reajuste de porcentajes sin guardar. | [DECIDIDO] |
| `create_bolsa` | Crear bolsa y reajustar porcentajes (atómico). | [DECIDIDO] |
| `archive_bolsa` | Archivar bolsa (exige saldo cero, mediante transferencia previa) y redistribuir porcentaje. | [DECIDIDO] |
| `create_goal` | Crear meta asociada a una bolsa acumulable. | [DECIDIDO] |
| `get_goal_progress` | Avance, faltante, % y fecha estimada de una meta. | [DECIDIDO] |
| `update_goal` | Cambiar monto o fecha, pausar o reactivar. | [DECIDIDO] |
| `preview_transfer` | Simular movimiento entre bolsas (con aviso de efecto en metas). | [DECIDIDO] |
| `transfer_between_bolsas` | Registrar movimiento entre bolsas. | [DECIDIDO] |
| `preview_month_close` | Calcular déficits y sobrantes del mes, con propuesta. | [DECIDIDO] |
| `close_month` | Ejecutar el cierre (atómico). | [DECIDIDO] |

**Tools eliminadas en v0.2:** `contribute_to_goal`, `withdraw_from_goal`, `spend_from_goal`, `update_transaction`, `delete_transaction`. Las metas ya no reciben ni entregan dinero por separado (sección 7), y las correcciones se hacen por anulación (RN-53).

### 12.2 Reglas para las tools
1. Las tools devuelven datos exactos y validan reglas. No dan consejos.
2. Las tools que modifican dinero deben ser **idempotentes** o aceptar una clave de operación, para que una llamada repetida por Claude no duplique un movimiento. **[PROPUESTO]**
3. Las tools destructivas o de reparto piden confirmación del usuario antes de ejecutarse.
4. Las respuestas de error deben ser claras para que Claude pueda explicarlas.
5. Toda tool que reciba un monto en dólares exige el tipo de cambio (RN-57). Si falta, devuelve error en lugar de asumirlo.

---

## 13. Estadísticas y dashboard **[DECIDIDO en intención; detalle PROPUESTO]**

### 13.1 Preguntas que debe responder
- ¿En qué gasto más?
- ¿Cuánto de cada bolsa llevo gastado este mes (% del presupuesto)?
- ¿Cuánto he ingresado al ahorro, y de dónde vino (asignación mensual, extras, sobrantes de cierre)?
- ¿Cuánto ingreso tengo en el mes? (sin contar el saldo inicial)
- ¿Cuáles son mis gastos necesarios y cuáles son fijos?
- ¿Cómo voy en cada meta?

### 13.2 Componentes
- Tarjetas: ingreso del mes, gastado, disponible, ahorrado, ingresos **sin asignar**.
- Barras de progreso por bolsa (usado vs. presupuesto ajustado, con el original como referencia).
- Dona de gasto por categoría.
- Evolución mensual (línea o barras).
- Tabla de últimos movimientos con filtros (los anulados se distinguen visualmente).
- Lista de gastos fijos: pagados y pendientes.
- Tarjeta por meta: barra de progreso basada en el saldo de su bolsa, "faltan ₡X" y fecha estimada.
- Alertas: bolsa por encima de 80 % y 100 %, bolsa en negativo (rojo), cierre de mes pendiente, ingreso pendiente de repartir.
- Totales en colones, con equivalente en dólares opcional.


## 15. Requerimientos no funcionales

- **Privacidad:** Los datos se almacenan en el servidor del propietario. Al usar Claude mediante MCP, la información consultada y registrada transita por Cloudflare y Anthropic, y el propietario acepta ese tránsito. Las tools devuelven solo la información necesaria para cada consulta (minimización).
- **Autenticación:** el endpoint del MCP y el dashboard requieren token o login, aunque sea uso personal.
- **Respaldo:** copia automática y periódica de la base de datos.
- **Simplicidad de uso:** registrar un gasto debe tomar una sola frase a Claude.
- **Liviandad:** debe correr cómodamente en el hardware del homelab (laptop vieja, pocos recursos). Postgres corre en Docker; su consumo de memoria se mide con `docker stats` desde el Hito 1.
- **Calidad:** el invariante de la sección 11.4, las validaciones de sumas (porcentajes = 100) y la conversión de monedas deben estar cubiertos por tests automáticos.

---

## 16. Arquitectura propuesta **[PROPUESTO]**

```
Claude (chat) ──► Servidor MCP ──► PostgreSQL ◄── API ◄── Dashboard (React)
                  (tools)          (datos)
```

- **Base de datos:** PostgreSQL en un contenedor Docker, con volumen persistente.
- **MCP:** en Python, remoto por HTTPS mediante un túnel de Cloudflare (decisiones 9 y 10). El servidor de autorización de OAuth se decide en el Hito 3.
- **Dashboard:** React + Vite + TypeScript + Tailwind, con una librería de gráficos (por ejemplo Recharts).
- **Ejecución:** en el homelab del propietario.

---

## 17. Esquema de datos de referencia (v0.3, borrador, PostgreSQL)

Consolida y reemplaza los borradores anteriores. Es una propuesta técnica: puede ajustarse al implementar, siempre que respete las reglas de este documento.

Convenciones de tipos: identificadores y montos en `BIGINT`; banderas en `BOOLEAN`; fechas de calendario en `DATE`; instantes en `TIMESTAMPTZ`; el mes se guarda como texto de 7 caracteres `'YYYY-MM'` con un `CHECK` de formato.

```sql
-- Bolsas flexibles
CREATE TABLE bolsas (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  nombre TEXT NOT NULL UNIQUE,
  comportamiento TEXT NOT NULL CHECK (comportamiento IN ('consumo','acumulable')),
  grupo TEXT,                                          -- opcional, solo estadísticas
  destino_sobrante_id BIGINT REFERENCES bolsas(id),    -- opcional; debe ser acumulable (se valida en código)
  activa BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE categorias (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  nombre TEXT NOT NULL UNIQUE,
  bolsa_id BIGINT NOT NULL REFERENCES bolsas(id),
  activa BOOLEAN NOT NULL DEFAULT TRUE
);

-- Porcentajes por mes (historial). La app valida que cada mes sume 100.
CREATE TABLE budget_month_allocations (
  mes CHAR(7) NOT NULL CHECK (mes ~ '^[0-9]{4}-(0[1-9]|1[0-2])$'),  -- 'YYYY-MM'
  bolsa_id BIGINT NOT NULL REFERENCES bolsas(id),
  porcentaje INTEGER NOT NULL CHECK (porcentaje BETWEEN 0 AND 100),
  PRIMARY KEY (mes, bolsa_id)
);

-- Ingresos (incluye el saldo inicial como registro especial)
CREATE TABLE ingresos (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  fecha DATE NOT NULL,
  tipo TEXT NOT NULL CHECK (tipo IN ('base','extra','saldo_inicial')),
  fuente TEXT,
  mes_presupuesto CHAR(7) NOT NULL                     -- salario de fin de mes -> mes siguiente
    CHECK (mes_presupuesto ~ '^[0-9]{4}-(0[1-9]|1[0-2])$'),
  moneda TEXT NOT NULL DEFAULT 'CRC' CHECK (moneda IN ('CRC','USD')),
  monto_original BIGINT NOT NULL CHECK (monto_original > 0),  -- CRC: colones; USD: centavos
  tipo_cambio BIGINT,                                  -- colones por USD x100; NULL si moneda = CRC
  monto BIGINT NOT NULL CHECK (monto > 0),             -- equivalente en colones (base de todos los cálculos)
  estado_reparto TEXT NOT NULL DEFAULT 'pendiente'
    CHECK (estado_reparto IN ('pendiente','repartido')),
  nota TEXT,
  anulado BOOLEAN NOT NULL DEFAULT FALSE,
  anulado_en TIMESTAMPTZ,
  motivo_anulacion TEXT,
  CHECK ((moneda = 'CRC' AND tipo_cambio IS NULL) OR (moneda = 'USD' AND tipo_cambio IS NOT NULL))
);

-- Reparto de cada ingreso por bolsa
CREATE TABLE income_allocations (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  ingreso_id BIGINT NOT NULL REFERENCES ingresos(id),
  bolsa_id BIGINT NOT NULL REFERENCES bolsas(id),
  porcentaje INTEGER CHECK (porcentaje BETWEEN 0 AND 100),  -- NULL en el saldo inicial (monto explícito)
  monto BIGINT NOT NULL CHECK (monto >= 0)             -- colones; la última bolsa absorbe el residuo
);

-- Metas: objetivo asociado a una bolsa acumulable. No guardan dinero ni avance.
CREATE TABLE savings_goals (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  bolsa_id BIGINT NOT NULL REFERENCES bolsas(id),      -- debe ser acumulable (se valida en create_goal)
  nombre TEXT NOT NULL,
  monto_objetivo BIGINT NOT NULL CHECK (monto_objetivo > 0),  -- en colones
  fecha_objetivo DATE,                                 -- opcional
  estado TEXT NOT NULL DEFAULT 'activa'
    CHECK (estado IN ('activa','lograda','pausada')),
  fecha_logro DATE                                     -- se llena al pasar a 'lograda'
);
-- Una sola meta activa por bolsa (RN-22, pendiente de confirmar en decisión #11)
CREATE UNIQUE INDEX ux_meta_activa_por_bolsa
  ON savings_goals(bolsa_id) WHERE estado = 'activa';

-- Gastos
CREATE TABLE gastos (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  fecha DATE NOT NULL,
  mes CHAR(7) NOT NULL                                 -- mes calendario de la fecha
    CHECK (mes ~ '^[0-9]{4}-(0[1-9]|1[0-2])$'),
  bolsa_id BIGINT NOT NULL REFERENCES bolsas(id),
  categoria_id BIGINT REFERENCES categorias(id),
  descripcion TEXT,
  moneda TEXT NOT NULL DEFAULT 'CRC' CHECK (moneda IN ('CRC','USD')),
  monto_original BIGINT NOT NULL CHECK (monto_original > 0),
  tipo_cambio BIGINT,
  monto BIGINT NOT NULL CHECK (monto > 0),             -- equivalente en colones
  anulado BOOLEAN NOT NULL DEFAULT FALSE,
  anulado_en TIMESTAMPTZ,
  motivo_anulacion TEXT,
  CHECK ((moneda = 'CRC' AND tipo_cambio IS NULL) OR (moneda = 'USD' AND tipo_cambio IS NOT NULL))
);

-- Gastos fijos mensuales (plantillas)
CREATE TABLE gastos_recurrentes (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  nombre TEXT NOT NULL,
  moneda TEXT NOT NULL DEFAULT 'CRC' CHECK (moneda IN ('CRC','USD')),
  monto_original BIGINT NOT NULL CHECK (monto_original > 0),
  dia_del_mes INTEGER NOT NULL CHECK (dia_del_mes BETWEEN 1 AND 31),
  bolsa_id BIGINT NOT NULL REFERENCES bolsas(id),
  categoria_id BIGINT REFERENCES categorias(id),
  activo BOOLEAN NOT NULL DEFAULT TRUE
);

-- Libro mayor de transferencias entre bolsas (inmutable; siempre en colones)
CREATE TABLE transfers (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  fecha DATE NOT NULL,
  mes CHAR(7) NOT NULL                                 -- mes presupuestario
    CHECK (mes ~ '^[0-9]{4}-(0[1-9]|1[0-2])$'),
  from_bolsa_id BIGINT NOT NULL REFERENCES bolsas(id),
  to_bolsa_id BIGINT NOT NULL REFERENCES bolsas(id),
  monto BIGINT NOT NULL CHECK (monto > 0),
  motivo TEXT NOT NULL CHECK (motivo IN
    ('cubrir_sobregasto','reasignacion','cierre_de_mes','ajuste')),
  nota TEXT,
  CHECK (from_bolsa_id <> to_bolsa_id)
);

-- Estado de cada mes
CREATE TABLE month_closures (
  mes CHAR(7) PRIMARY KEY CHECK (mes ~ '^[0-9]{4}-(0[1-9]|1[0-2])$'),
  estado TEXT NOT NULL DEFAULT 'abierto' CHECK (estado IN ('abierto','cerrado')),
  cerrado_en TIMESTAMPTZ
);

-- Sobrantes no destinados y sobregastos no cubiertos al cerrar
CREATE TABLE closure_adjustments (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  mes CHAR(7) NOT NULL REFERENCES month_closures(mes),
  bolsa_id BIGINT NOT NULL REFERENCES bolsas(id),
  tipo TEXT NOT NULL CHECK (tipo IN ('sobrante_no_destinado','sobregasto_no_cubierto')),
  monto BIGINT NOT NULL                                -- con signo: sobrante +, sobregasto -
);
```

**Cambios en v0.3:** traducción técnica a PostgreSQL (sin `PRAGMA`; `BOOLEAN`, `DATE`/`TIMESTAMPTZ`, `BIGINT`; mes como `CHAR(7)` con `CHECK` de formato). No cambia ninguna regla.

**Cambios respecto a v0.1:** se eliminan `goal_movements` y los campos `goal_id` de `gastos` y `transfers` (la meta ya no tiene dinero propio); se agregan campos de moneda, anulación y saldo inicial; se agrega `fecha_logro` a las metas.

**Validaciones que viven en el código (no en el esquema):**
- Cada mes suma 100 % en `budget_month_allocations` (RN-01).
- Las metas solo se asocian a bolsas `acumulable` (RN-21).
- No se transfiere más del saldo o disponible de la bolsa de origen (RN-42).
- Un mes cerrado no admite movimientos nuevos ni anulaciones (RN-44, RN-48, RN-53).
- Una bolsa solo se archiva con saldo cero (RN-18).
- El saldo inicial se carga una sola vez (RN-54).
- La conversión USD → CRC usa el tipo de cambio guardado y redondeo half-up (RN-57).
- Las operaciones compuestas (crear bolsa, cerrar mes, anular un ingreso ya repartido) se ejecutan en una sola transacción.

---

## Concepto → tabla

La constitución habla en conceptos de negocio; esta tabla los lleva a las tablas y columnas del
esquema de la sección 17, con los valores que se guardan para estados, tipos y motivos.

| Concepto (constitución) | Tabla / columna | Valores que se guardan |
|---|---|---|
| Bolsa | `bolsas` | — |
| Comportamiento de la bolsa (RN-10) | `bolsas.comportamiento` | `consumo`, `acumulable` |
| Bolsa inactiva (archivada, RN-16) | `bolsas.activa` | `TRUE` activa, `FALSE` archivada |
| Grupo de la bolsa | `bolsas.grupo` | texto libre u omitido |
| Destino de sobrante sugerido (6.5) | `bolsas.destino_sobrante_id` | id de una bolsa acumulable u omitido |
| Categoría | `categorias` (`activa`) | `TRUE`, `FALSE` |
| Los porcentajes de cada mes (RN-01 a 03) | `budget_month_allocations` | `porcentaje` entre 0 y 100 |
| Ingreso | `ingresos` | — |
| Tipo de ingreso: base, extra, saldo inicial (5.1, 5.3, RN-54) | `ingresos.tipo` | `base`, `extra`, `saldo_inicial` |
| Mes presupuestario (5.1, RN-09) | `ingresos.mes_presupuesto` | `'YYYY-MM'` |
| Estado del reparto de un ingreso (RN-06) | `ingresos.estado_reparto` | `pendiente`, `repartido` |
| Moneda (RN-55) | `ingresos.moneda`, `gastos.moneda`, `gastos_recurrentes.moneda` | `CRC`, `USD` |
| Monto original y tipo de cambio (RN-57) | `monto_original`, `tipo_cambio`, `monto` | CRC en colones; USD en centavos; tipo de cambio en colones por USD × 100 |
| Lo asignado a la bolsa por los ingresos del mes (11.1) | `income_allocations.monto` | colones enteros |
| Gasto | `gastos` | — |
| Mes calendario del gasto (RN-32) | `gastos.mes` | `'YYYY-MM'` |
| Anulación con registro (RN-53) | `anulado`, `anulado_en`, `motivo_anulacion` en `ingresos` y `gastos` | `anulado`: `TRUE`, `FALSE` |
| Gasto fijo mensual (8.1) | `gastos_recurrentes` (`activo`) | `TRUE`, `FALSE` |
| Meta de ahorro (sección 7) | `savings_goals` | — |
| Estado de una meta (RN-24) | `savings_goals.estado` | `activa`, `lograda`, `pausada` |
| El registro de transferencias (RN-40) | `transfers` | — |
| Motivo de una transferencia (sección 9) | `transfers.motivo` | `cubrir_sobregasto`, `reasignacion`, `cierre_de_mes`, `ajuste` |
| Estado del mes (RN-49) | `month_closures.estado` | `abierto`, `cerrado` |
| Ajustes de cierre (RN-50, 10.2) | `closure_adjustments.tipo` | `sobrante_no_destinado`, `sobregasto_no_cubierto` |

**Idioma de los nombres:** el idioma de los nombres de tablas, columnas y código se decide en el
Hito 1 y se anota aquí. Los nombres de esta tabla y de la sección 17 son los del borrador de
referencia.

---

## Registro de cambios

| Versión | Fecha | Cambio |
|---|---|---|
| 0.1 | 2026-11-09 | Primera versión: secciones 12, 13, 15, 16 y 17 del documento de origen v0.3, stack decidido, tabla concepto → tabla y enlace a `HITOS.md`. |
