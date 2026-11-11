# Feature Specification: Ingresos base y gastos (MVP)

**Feature Branch**: `hito-5-movimientos`

**Created**: 2026-11-10

**Status**: Draft

**Input**: User description (prompt del Hito 5 en `HITOS.md`): "El propietario quiere registrar desde
Claude su salario y sus gastos, en colones o dólares. El salario que entra a fin de mes se reparte entre
las bolsas según los porcentajes del mes siguiente. Quiere ver cuánto lleva gastado y cuánto le queda en
cada bolsa, ver en qué gasta más, y anular un movimiento mal registrado dejando constancia. Un gasto que
excede una bolsa se registra igual y avisa. Incluye pruebas automáticas que verifiquen los criterios de
aceptación."

**Hito**: 5 (Ingresos base y gastos, MVP), según `HITOS.md`.

## Resumen de decisiones

**[DECIDIDO] por el propietario (2026-11-10):**

- El Hito 4 está cerrado. Todas las tools exigen la autenticación vigente (Hito 3).
- Solo colones y dólares. Ningún monto pasa por `float` en el código.
- Decisión #12 resuelta (constitución 1.0.1, sección 14.1.1): el tipo de cambio lo indica el
  propietario en cada movimiento en USD y nunca se asume; todo se convierte a colones al registrar
  (RN-56); metas solo en colones; los gastos fijos en USD quedan para el Hito 6.
- Reglas que aplica este hito: RN-31 a RN-34, RN-37, RN-38, RN-53, RN-55 a RN-57 y RN-59, más RN-02,
  RN-03 y RN-08 para el reparto del salario. Se citan, no se reescriben.
- Ingreso base: mes presupuestario = mes siguiente a la fecha del ingreso (constitución 5.1), con
  opción explícita de otro mes; se reparte con los porcentajes de ese mes (o heredados, RN-03) y cada
  reparto guarda el porcentaje usado; sin porcentajes, error claro. Solo tipo `base` (los extras son
  del Hito 6). Sin `confirm=true` no guarda nada.
- Gastos: monto positivo, fecha (por defecto hoy en America/Costa_Rica; las futuras se rechazan),
  bolsa, categoría opcional (sin categoría = "pendiente de clasificar", RN-34), descripción corta
  opcional y moneda. Pertenecen al mes calendario de su fecha (RN-32), contra cualquier bolsa (RN-33).
  Un sobregasto se guarda y la respuesta advierte con las bolsas que tienen saldo disponible (RN-37,
  RN-38).
- Categorías: `create_category` (nombre y bolsa por defecto, nombre único sin distinguir mayúsculas) y
  `list_categories`.
- Monedas: colones enteros; USD en centavos; entrada en USD con hasta 2 decimales convertida con
  `Decimal`; tipo de cambio entero escalado ×100; `monto_crc` = redondeo half-up de
  `centavos × tipo_cambio_x100 / 10 000` (USD 10,00 a 512,34 = ₡5.123). Se rechazan conversiones que
  den 0 colones y tipos de cambio fuera de un rango configurable por variable de entorno. El
  equivalente en colones se calcula una vez y no se recalcula (RN-57).
- Migración nueva (`0004`), sin editar la `0003`: moneda, monto original, tipo de cambio y anulación
  en `incomes`, y la tabla de gastos. Conserva los datos del Hito 4 (quedan en CRC con monto original
  = monto y sin tipo de cambio). Downgrade protegido igual que el de `0003`.
- Anulación (RN-53, RN-59): `void_transaction` anula ingresos y gastos con motivo, sin borrar. Hasta el
  Hito 9 todos los meses cuentan como abiertos. Los cálculos ignoran lo anulado. Anular un ingreso
  repartido revierte sus asignaciones y puede dejar una bolsa en negativo (se advierte, RN-37). Se
  puede anular el saldo inicial (RN-54) y después cargar uno nuevo. Nada borra filas del libro mayor.
- Idempotencia: `operation_id` obligatorio en `add_income` (al confirmar), `add_expense` y
  `void_transaction`. Misma clave y mismo contenido: devuelve el resultado original sin duplicar.
  Misma clave y otro contenido: error.
- Tools: `add_income`, `add_expense`, `void_transaction`, `get_bolsa_status`, `list_transactions`
  (límite 20 por defecto, máximo 100), `get_summary` (mes), `top_categories`, `create_category`,
  `list_categories`. Devuelven solo lo necesario (principio 3.10).
- Cálculos: secciones 11.1 y 11.2. Sin transferencias todavía: presupuesto ajustado = original.
- Invariante 11.4 extendido a ingresos repartidos, gastos, anulaciones y USD: 200 conjuntos sintéticos
  con semilla fija que se imprime si falla.
- Registros y mensajes de error sin montos ni descripciones; `sse_starlette` sigue fijado en INFO con
  su prueba. Datos de prueba sintéticos.

**[PROPUESTO] por Claude (se asumen; el propietario los confirma en el reporte):**

1. **Referencias de movimientos:** `I-<n>` para ingresos (incluido el saldo inicial) y `G-<n>` para
   gastos, donde `<n>` es el número de fila del movimiento. Se aceptan sin distinguir mayúsculas
   (`g-12`). No se expone ningún otro identificador (ni de bolsas ni de categorías).
2. **Vista previa del salario:** además de `add_income` sin `confirm`, se agrega la tool
   `preview_income` (principio 3.2: toda operación que reparte dinero tiene una tool `preview_*`).
3. **Formato de entrada de montos:** colones como entero (o texto con solo dígitos); USD y tipo de
   cambio como entero o texto con hasta 2 decimales y punto decimal (`"10.50"`, `"512.34"`), sin
   separador de miles. Un número JSON con decimales (`10.5`) se rechaza con un mensaje que pide
   enviarlo como texto, porque llegaría como `float`. Lo mismo vale ahora para los enteros de las
   tools del Hito 4 (`50.0` se rechaza).
4. **Tipo de cambio en colones:** si se indica tipo de cambio con moneda CRC, se rechaza (evita
   confundir monedas).
5. **Rango del tipo de cambio:** `USD_RATE_MIN` y `USD_RATE_MAX` (colones por dólar, enteros,
   inclusivos; por defecto 300 y 1000).
6. **Fecha del ingreso:** por defecto hoy; las futuras se rechazan, igual que en los gastos.
7. **Mes presupuestario explícito:** cualquier mes válido (todos están abiertos hasta el Hito 9).
8. **Bolsa del gasto:** si se omite la bolsa y se indica categoría, se usa la bolsa por defecto de la
   categoría; si se omiten las dos, error. Una categoría inexistente es error (no se crea sola).
9. **Longitudes:** descripción hasta 120 caracteres; motivo de anulación de 3 a 200; nombre de
   categoría de 1 a 60. La descripción es opcional (RN-31 la enumera; el esquema de referencia ya la
   permite vacía, y el propietario la pidió opcional).
10. **Clave de operación:** de 8 a 100 caracteres (`A-Z a-z 0-9 . _ : -`), única entre todas las tools.
    La huella del contenido se calcula con los datos tal como se enviaron, ya normalizados (nombres sin
    mayúsculas, montos convertidos a enteros); una fecha omitida sigue omitida, así que repetir al día
    siguiente devuelve el mismo resultado. Se guarda la respuesta original y se devuelve tal cual.
11. **Anulación con vista previa:** `void_transaction` sin `confirm=true` muestra qué se anularía y qué
    bolsas quedarían en negativo, sin guardar nada (regla 12.2.3 del plan técnico: las tools
    destructivas piden confirmación).
12. **Detección del sobregasto:** bolsa de consumo → su disponible del mes del gasto (11.1) queda
    negativo; bolsa acumulable → su saldo (11.2) queda negativo. "Bolsas con saldo disponible" son las
    demás bolsas activas con valor positivo (consumo: disponible del mes del gasto; acumulable: saldo).
13. **Resumen y listados:** `get_summary` muestra, para las acumulables, el saldo actual (11.2, todo
    el historial) junto con lo asignado y gastado en el mes; `list_transactions` filtra los ingresos por
    mes presupuestario y el filtro por bolsa solo aplica a gastos; `top_categories` muestra 5 por
    defecto (máximo 20) e incluye "pendiente de clasificar".
14. **% usado:** entero redondeado hacia abajo; vacío si el presupuesto ajustado es 0 o negativo.
15. **Protección del libro mayor en la base:** disparadores que impiden borrar filas de `incomes`,
    `income_allocations` y `expenses`, modificar `income_allocations`, cambiar montos, moneda, fechas
    o bolsa de un movimiento, y deshacer una anulación.
16. **"Datos" para el downgrade de `0004`:** cualquier gasto o clave de operación, o cualquier ingreso
    en USD o anulado.
17. **Residuo con porcentaje 0 al final:** RN-08 se aplica entre las bolsas que reciben (porcentaje
    mayor que 0); la última de ellas absorbe el residuo y una bolsa con 0 % recibe 0, aunque sea la
    última por orden de creación (por ejemplo 50/50/0 con ₡10.001 → 5.000 / 5.001 / 0).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Registrar el salario y repartirlo (Priority: P1)

El propietario le dice a Claude cuánto le pagaron (en colones o dólares). La app le muestra a qué mes
presupuestario pertenece y cuánto recibe cada bolsa con los porcentajes de ese mes; al confirmar, se
guarda el ingreso con su reparto.

**Why this priority**: es el corazón del presupuesto mensual (constitución 5.1) y la base del MVP.

**Independent Test**: con porcentajes 50/30/20 definidos para 2026-12, registrar ₡1.000.001 con fecha
2026-11-30: la vista previa y la confirmación asignan 500.000 / 300.000 / 200.001 a 2026-12.

**Acceptance Scenarios**:

1. **Given** porcentajes 50/30/20 en 2026-12, **When** registra un salario con fecha 2026-11-30 y
   `confirm=true`, **Then** queda en el mes 2026-12 repartido 50/30/20 con el residuo en la última
   bolsa (RN-08) y cada reparto guarda su porcentaje.
2. **Given** porcentajes solo en 2026-11, **When** registra un salario para 2026-12, **Then** usa los de
   2026-11 e indica el mes de origen (RN-03).
3. **Given** ningún mes con porcentajes, **When** registra un salario, **Then** recibe un error que
   pide definirlos con `set_allocation` y nada se guarda.
4. **Given** un salario en USD 1.000,00 con tipo de cambio 512,34, **When** lo confirma, **Then** se
   guardan ₡512.340, la moneda, los centavos originales y el tipo de cambio (RN-57).
5. **Given** un salario en USD sin tipo de cambio, **When** lo envía, **Then** recibe un error y nada
   se guarda (decisión #12 a).
6. **Given** `confirm` omitido, **When** llama a `add_income` o a `preview_income`, **Then** ve el
   reparto y nada se guarda.
7. **Given** un salario confirmado con una clave de operación, **When** Claude repite la misma llamada,
   **Then** recibe la misma respuesta y hay un solo ingreso; con la misma clave y otro monto, error.
8. **Given** un mes explícito distinto, **When** lo indica, **Then** el ingreso pertenece a ese mes.

---

### User Story 2 - Registrar gastos en colones o dólares (Priority: P1)

El propietario registra un gasto con una frase: monto, bolsa o categoría, y opcionalmente fecha,
descripción y moneda.

**Why this priority**: es el uso diario de la app (requerimiento de una sola frase, sección 15).

**Independent Test**: registrar ₡12.500 en Gustos con categoría "Restaurantes" y ver que el disponible
de Gustos baja en ₡12.500.

**Acceptance Scenarios**:

1. **Given** Gustos con disponible, **When** registra un gasto en CRC, **Then** se guarda en el mes de
   su fecha (RN-32) y la respuesta muestra la referencia y el disponible resultante.
2. **Given** un gasto de USD 10,00 a 512,34, **When** lo registra, **Then** se guardan ₡5.123 (redondeo
   half-up) con moneda, centavos y tipo de cambio.
3. **Given** un gasto en USD sin tipo de cambio, o con un tipo de cambio fuera del rango, o que convierte
   a 0 colones, **When** lo envía, **Then** recibe un error y nada se guarda.
4. **Given** un gasto sin categoría, **When** lo registra, **Then** queda como "pendiente de clasificar"
   (RN-34).
5. **Given** un gasto contra Ahorro (acumulable), **When** lo registra, **Then** se acepta y baja el
   saldo de Ahorro (RN-33).
6. **Given** un gasto con fecha futura, monto 0 o negativo, o bolsa inexistente, **When** lo envía,
   **Then** recibe un error claro y nada se guarda.
7. **Given** la misma llamada repetida con la misma clave de operación, **When** llega dos veces,
   **Then** hay un solo gasto y la segunda respuesta es igual a la primera.
8. **Given** solo una categoría con bolsa por defecto, **When** registra el gasto sin bolsa, **Then** se
   carga a la bolsa por defecto de la categoría.

---

### User Story 3 - Sobregasto que se registra y avisa (Priority: P1)

**Why this priority**: principio 3.7 (registrar la realidad); RN-37 y RN-38.

**Independent Test**: Gustos con disponible de ₡10.000 y un gasto de ₡15.000: se guarda, Gustos queda
en -₡5.000 y la respuesta advierte y lista las bolsas con saldo.

**Acceptance Scenarios**:

1. **Given** un gasto mayor que el disponible, **When** lo registra, **Then** se guarda, la respuesta
   marca el sobregasto y lista las demás bolsas con saldo disponible (RN-37).
2. **Given** una bolsa en negativo, **When** consulta su estado o el resumen, **Then** aparece en
   negativo y marcada (RN-38).

---

### User Story 4 - Ver el estado de cada bolsa, el resumen y en qué gasta más (Priority: P1)

**Why this priority**: objetivos 1, 3 y 5 de la constitución; cierre del MVP.

**Independent Test**: con un salario repartido y varios gastos sintéticos, `get_bolsa_status`,
`get_summary`, `top_categories` y `list_transactions` cuadran entre sí.

**Acceptance Scenarios**:

1. **Given** una bolsa de consumo, **When** pide su estado, **Then** ve asignado, transferencias (0),
   presupuesto ajustado (= original), gastado, disponible y % usado (11.1).
2. **Given** una bolsa acumulable, **When** pide su estado, **Then** ve su saldo histórico (11.2) y lo
   asignado y gastado en el mes.
3. **Given** un mes, **When** pide el resumen, **Then** ve el ingreso del mes (sin el saldo inicial,
   RN-54), el total gastado y cada bolsa.
4. **Given** gastos con y sin categoría, **When** pide `top_categories`, **Then** ve las categorías
   ordenadas por monto, incluida "pendiente de clasificar".
5. **Given** más de 20 movimientos, **When** lista sin límite, **Then** recibe 20 (los más recientes) y
   la indicación de que hay más; con límite 150, error (máximo 100).

---

### User Story 5 - Anular un movimiento dejando constancia (Priority: P1)

**Why this priority**: RN-53 es la única forma de corregir (libro mayor inmutable, principio 3.4).

**Independent Test**: anular un gasto: desaparece de los cálculos, sigue en `list_transactions` como
anulado, con su motivo.

**Acceptance Scenarios**:

1. **Given** un gasto, **When** lo anula con motivo y `confirm=true`, **Then** queda anulado con fecha y
   motivo, los cálculos lo ignoran y sigue visible en el historial.
2. **Given** un salario repartido, **When** lo anula, **Then** sus asignaciones dejan de contar (RN-59)
   y, si una bolsa queda en negativo, la respuesta lo advierte (RN-37).
3. **Given** el saldo inicial cargado, **When** lo anula, **Then** se puede cargar uno nuevo con
   `load_initial_balance`.
4. **Given** un movimiento ya anulado, **When** intenta anularlo de nuevo con otra clave, **Then**
   recibe un error; con la misma clave y el mismo contenido, la respuesta original.
5. **Given** `confirm` omitido, **When** pide la anulación, **Then** ve el efecto y nada se guarda.
6. **Given** una referencia que no existe o con formato inválido, **When** la usa, **Then** recibe un
   error claro.

---

### User Story 6 - Categorías (Priority: P2)

**Acceptance Scenarios**:

1. **Given** la bolsa Gustos, **When** crea la categoría "Restaurantes" con bolsa por defecto Gustos,
   **Then** aparece en `list_categories`.
2. **Given** "Restaurantes" existente, **When** crea "restaurantes", **Then** recibe un error (único
   sin distinguir mayúsculas).

---

### User Story 7 - Dinero que cuadra y datos que se conservan (Priority: P1)

**Acceptance Scenarios**:

1. **Given** 200 conjuntos sintéticos con saldo inicial, salarios en CRC y USD, gastos y anulaciones,
   **When** corre la prueba, **Then** el invariante 11.4 cuadra en todos y, si falla, muestra la
   semilla.
2. **Given** una base del Hito 4 con porcentajes y saldo inicial, **When** se aplica la migración
   nueva, **Then** los datos siguen ahí, en CRC, con monto original = monto y sin tipo de cambio.
3. **Given** datos del Hito 5, **When** se intenta el downgrade sin la variable explícita, **Then** se
   niega y no borra nada.

### Edge Cases

- Gasto en USD que redondea a 0 colones (USD 0,01 a 300): error.
- Tipo de cambio con más de 2 decimales, texto inválido o número JSON con decimales: error en español.
- Salario cuyo reparto da 0 a una bolsa con 0 %: se guarda la línea en 0 con su porcentaje.
- Dos llamadas simultáneas con la misma clave de operación: solo una escribe; la otra devuelve el
  resultado guardado.
- Anular un gasto nunca deja una bolsa en negativo (solo la sube); anular un ingreso sí puede.
- Anular el saldo inicial dos veces seguidas: la segunda con otra clave es error ("ya está anulado").
- Una bolsa de consumo con gastos en un mes sin asignación queda en negativo en ese mes.
- Mes con formato inválido en cualquier tool: error.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: El sistema DEBE registrar un ingreso base con monto, moneda, tipo de cambio (solo USD),
  fecha (por defecto hoy, no futura) y mes presupuestario (por defecto el siguiente a la fecha;
  constitución 5.1), solo con `confirm=true` y una clave de operación.
- **FR-002**: El sistema DEBE repartir el ingreso base con los porcentajes de su mes presupuestario o
  los heredados (RN-02, RN-03), con enteros y residuo en la última bolsa (RN-08), y guardar el
  porcentaje usado en cada reparto. Sin porcentajes, DEBE rechazar con un error que pida definirlos.
- **FR-003**: El sistema DEBE ofrecer la vista previa del ingreso sin guardar nada (`preview_income` y
  `add_income` sin `confirm`).
- **FR-004**: El sistema DEBE registrar un gasto con monto positivo, fecha (por defecto hoy, no
  futura), bolsa, categoría opcional, descripción opcional y moneda (RN-31), en el mes calendario de
  su fecha (RN-32), contra cualquier bolsa activa (RN-33); sin categoría queda "pendiente de
  clasificar" (RN-34).
- **FR-005**: El sistema DEBE guardar un gasto que deja una bolsa en negativo y devolver una
  advertencia con las bolsas que tienen saldo disponible (RN-37, RN-38).
- **FR-006**: El sistema DEBE convertir los montos en USD a colones al registrar, con el tipo de cambio
  indicado, en enteros y con redondeo half-up, y guardar moneda, monto original en centavos y tipo de
  cambio ×100 (RN-55 a RN-57); nunca recalcular el equivalente.
- **FR-007**: El sistema DEBE rechazar: USD sin tipo de cambio, tipo de cambio fuera de
  `USD_RATE_MIN`..`USD_RATE_MAX`, conversiones que den 0 colones, más de 2 decimales y números con
  decimales enviados como número JSON. Ningún monto pasa por `float`.
- **FR-008**: El sistema DEBE anular ingresos y gastos con motivo y fecha, sin borrarlos (RN-53); los
  cálculos DEBEN ignorar lo anulado y el historial DEBE mostrarlo como anulado.
- **FR-009**: Al anular un ingreso repartido, sus asignaciones DEBEN dejar de contar (RN-59) y la
  respuesta DEBE advertir las bolsas que quedan en negativo (RN-37).
- **FR-010**: El sistema DEBE permitir anular el saldo inicial y, después, cargar uno nuevo (RN-54).
- **FR-011**: `add_income` (confirmado), `add_expense` y `void_transaction` DEBEN exigir una clave de
  operación: misma clave y mismo contenido devuelven la respuesta original sin duplicar; misma clave
  con otro contenido, error. DEBE resistir dos llamadas simultáneas con la misma clave.
- **FR-012**: `get_bolsa_status` DEBE devolver, para un mes, asignado, transferencias (0), presupuesto
  ajustado (= original), gastado y disponible con % usado (consumo, 11.1) o saldo (acumulable, 11.2).
- **FR-013**: `get_summary` DEBE devolver el ingreso del mes (solo base, sin saldo inicial), el total
  gastado y el estado de cada bolsa activa; las bolsas en negativo DEBEN marcarse.
- **FR-014**: `top_categories` DEBE devolver las categorías del mes ordenadas por monto gastado, con
  "pendiente de clasificar" como una más.
- **FR-015**: `list_transactions` DEBE listar movimientos (más recientes primero) con filtros de mes,
  tipo y bolsa, límite 20 por defecto y máximo 100, con referencia corta y sin identificadores internos.
- **FR-016**: `create_category` y `list_categories` DEBEN gestionar categorías con bolsa por defecto y
  nombre único sin distinguir mayúsculas.
- **FR-017**: Una migración nueva DEBE agregar moneda, monto original, tipo de cambio y anulación a
  `incomes`, crear la tabla de gastos y la de claves de operación, conservar los datos del Hito 4 y
  permitir un nuevo saldo inicial tras anular el anterior. Su downgrade DEBE abortar si hay datos, salvo
  con `ALLOW_DESTRUCTIVE_DOWNGRADE=true`.
- **FR-018**: Ninguna tool ni script DEBE borrar filas de ingresos, repartos o gastos.
- **FR-019**: Registros y mensajes de error NO DEBEN incluir montos ni descripciones.
- **FR-020**: Todas las tools DEBEN exigir la autenticación vigente (sin credencial: 401).
- **FR-021**: La prueba del invariante 11.4 DEBE cubrir ingresos repartidos, gastos, anulaciones y USD
  con 200 conjuntos sintéticos de semilla fija, imprimiendo la semilla si falla.
- **FR-022**: Las pruebas automáticas DEBEN incluir casos negativos: sin credencial 401, porcentajes que
  no suman 100, USD sin tipo de cambio, conversión con redondeo, sobregasto, anulación y nueva carga del
  saldo inicial, idempotencia, migración que conserva datos, downgrade protegido y ausencia de montos en
  registros (gobernanza, regla no negociable 4).

### Reglas citadas

RN-02, RN-03, RN-08 (reparto del salario); RN-31, RN-32, RN-33, RN-34 (gastos); RN-37, RN-38
(sobregasto); RN-53, RN-59 (anulación); RN-54 (saldo inicial); RN-55, RN-56, RN-57 (monedas);
secciones 5.1, 11.1, 11.2 y 11.4; principios 3.2, 3.3, 3.4, 3.5, 3.6, 3.7 y 3.10.

### Key Entities

- **Ingreso**: tipo (`base` o `saldo_inicial` en este hito), fecha, mes presupuestario, moneda, monto
  original, tipo de cambio, monto en colones, anulación (fecha y motivo). Referencia `I-<n>`.
- **Reparto de un ingreso**: bolsa, porcentaje usado (vacío en el saldo inicial) y monto en colones.
- **Gasto**: fecha, mes calendario, bolsa, categoría opcional, descripción opcional, moneda, monto
  original, tipo de cambio, monto en colones, anulación. Referencia `G-<n>`.
- **Categoría**: nombre único y bolsa por defecto.
- **Clave de operación**: clave, tool, huella del contenido y respuesta original.

## Success Criteria *(mandatory)*

- **SC-001**: Desde Claude, un salario se registra y queda repartido 50/30/20 en el mes siguiente, con
  la suma exacta.
- **SC-002**: Un gasto en dólares queda convertido a colones con el tipo de cambio indicado (USD 10,00 a
  512,34 = ₡5.123).
- **SC-003**: Un gasto que deja una bolsa en negativo se guarda y la respuesta advierte.
- **SC-004**: Un gasto anulado desaparece de los cálculos y sigue en el historial.
- **SC-005**: Repetir la misma llamada no duplica el movimiento.
- **SC-006**: El invariante cuadra en 200 conjuntos sintéticos y la suite completa pasa.
- **SC-007**: Registrar un gasto toma una sola frase a Claude.

## Assumptions

- Hasta el Hito 9 no hay cierre de mes: todos los meses están abiertos para anular (RN-53).
- Hasta el Hito 8 no hay transferencias: presupuesto ajustado = original y transferencias en 0.
- Los extras (Hito 6), los gastos fijos (Hito 6) y las metas (Hito 7) quedan fuera.
- Las bolsas activas son las únicas que reciben gastos (no hay archivado todavía).
- La prueba de uso real de una semana la hace el propietario después de este hito.
