# Feature Specification: Bolsas y porcentajes

**Feature Branch**: `hito-4-bolsas`

**Created**: 2026-11-10

**Status**: Draft (revisada el 2026-11-10)

**Input**: User description (prompt del Hito 4 en `HITOS.md`): "El propietario quiere definir sus bolsas de dinero (Necesidades, Gustos y Ahorro) y los porcentajes en que se reparte su ingreso cada mes, y cargar una vez el saldo con el que arranca, repartido por montos entre las bolsas. Los porcentajes deben sumar 100, quedar guardados por mes y poder cambiarse sin alterar meses anteriores. Incluye pruebas automáticas que verifiquen los criterios de aceptación."

**Hito**: 4 (Bolsas y porcentajes), según `HITOS.md`.

## Resumen de decisiones

**[DECIDIDO] por el propietario:**

- El Hito 3 está cerrado (etiqueta `hito-3`): desde aquí se permiten datos reales (gobernanza, regla
  no negociable 1). Todas las tools de este hito exigen la autenticación vigente.
- Nombres de tablas, columnas y código en inglés ("bolsa" = `pocket`); documentación y mensajes al
  usuario en español. Las tools conservan los nombres del catálogo del plan técnico.
- Reglas que aplica este hito: RN-01, RN-02, RN-03, RN-08, RN-10, RN-11, RN-12 y RN-54.
- Bolsas iniciales como datos editables (no fijos en el código): Necesidades (`consumo`), Ahorro
  (`acumulable`) y Gustos (`consumo`). Solo se crean las bolsas; los porcentajes iniciales sugeridos
  (50/30/20) los guarda el propietario desde Claude.
- Porcentajes enteros, por mes; el mes se guarda como `YYYY-MM`. La validación vive en la capa de
  dominio, sin depender de MCP ni de la base.
- Saldo inicial: una sola carga, por montos explícitos por bolsa; no cuenta como ingreso del mes; una
  segunda carga se rechaza. Tiene vista previa (`preview_initial_balance`, principio 3.2).
- La prueba del invariante de integridad (sección 11.4) empieza en este hito, que es el primero que
  registra dinero (gobernanza, regla no negociable 3, que prevalece sobre `HITOS.md`). Usa datos
  sintéticos.
- Solo colones, en enteros. La moneda y el tipo de cambio llegan en el Hito 5 con su propia migración.
- Las tools devuelven solo lo necesario (principio 3.10). Las pruebas usan datos sintéticos y los
  registros nunca muestran saldos reales.
- Confirmado el 2026-11-10 en la revisión previa:
  - si un mes no tiene porcentajes, se resuelven al consultar desde el mes anterior más cercano, sin
    guardar nada, y la respuesta indica el mes de origen (RN-03);
  - solo se editan el mes actual y los futuros;
  - redondeo hacia abajo, con el residuo en la última bolsa por orden de creación (RN-08);
  - una configuración debe incluir cada bolsa activa una sola vez;
  - mes actual en America/Costa_Rica;
  - `list_bolsas` muestra el saldo (11.2) de las acumulables y el disponible del mes actual (11.1) de
    las de consumo.

**[PROPUESTO] por Claude (pendiente de tu confirmación):**

- **Mes del saldo inicial:** el mes actual (America/Costa_Rica) en el momento de la carga. En las
  bolsas de consumo cuenta como asignado de ese mes; en el mes siguiente empiezan en cero (RN-11) y su
  sobrante se resuelve en el cierre de mes (Hito 9). En las acumulables forma parte del saldo histórico
  (RN-12).
- **Montos del saldo inicial:** enteros ≥ 0 por bolsa activa, con total > 0; se pueden omitir bolsas
  (cuentan como 0).
- **Valores guardados** (comportamiento, tipo de ingreso, estado del reparto): los de la tabla
  concepto → tabla del plan técnico (`consumo`, `acumulable`, `saldo_inicial`, `repartido`…).
- **Corrección de un saldo inicial mal cargado:** requiere la anulación del Hito 5; hasta entonces no
  hay forma de reemplazarlo desde Claude.
- **Bolsas por nombre:** el propietario se refiere a las bolsas por su nombre (sin distinguir
  mayúsculas); las respuestas no muestran identificadores internos.
- Las decisiones técnicas [PROPUESTO] están en el plan ([plan.md](plan.md), Constitution Check).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Definir los porcentajes de un mes (Priority: P1)

Desde Claude, el propietario indica en qué porcentajes se reparte su ingreso de un mes entre sus
bolsas (por ejemplo, Necesidades 50 %, Ahorro 30 %, Gustos 20 %) y puede consultarlos después. La app
rechaza cualquier configuración que no sume exactamente 100.

**Why this priority**: es el esqueleto del presupuesto; sin porcentajes no se puede repartir ningún
ingreso en el Hito 5.

**Independent Test**: definir 50/30/20 para un mes y consultarlo; intentar 50/30/30 y comprobar el
rechazo sin cambios guardados.

**Acceptance Scenarios**:

1. **Given** las tres bolsas iniciales, **When** el propietario define Necesidades 50, Ahorro 30 y
   Gustos 20 para el mes actual, **Then** se guardan y la consulta del mes los devuelve.
2. **Given** cualquier mes editable, **When** los porcentajes suman distinto de 100 (por ejemplo 110 o
   90), **Then** la app rechaza la operación con un mensaje claro que indica la suma recibida, y no
   guarda nada (RN-01).
3. **Given** una configuración que omite una bolsa activa, la repite, incluye una bolsa inexistente o
   archivada, o usa un porcentaje fuera de 0 a 100 o no entero, **Then** se rechaza sin guardar nada.
4. **Given** un mes pasado, **When** el propietario intenta definir sus porcentajes, **Then** se
   rechaza.
5. **Given** un mes que ya tenía porcentajes, **When** se definen otros válidos, **Then** reemplazan a
   los anteriores de ese mes.

---

### User Story 2 - Porcentajes guardados por mes (Priority: P1)

Los porcentajes de cada mes quedan guardados por separado: cambiar los de un mes no altera los de
meses anteriores. Un mes sin porcentajes propios usa los del mes anterior.

**Why this priority**: es lo que permite que las estadísticas pasadas no cambien (RN-02, principio
3.9).

**Independent Test**: definir 50/30/20 para un mes, 40/40/20 para el siguiente, y comprobar que el
primero sigue en 50/30/20.

**Acceptance Scenarios**:

1. **Given** 50/30/20 en el mes M, **When** se define 40/40/20 para M+1, **Then** M sigue en 50/30/20
   (RN-02).
2. **Given** porcentajes en M y ninguno en M+1, **When** se consulta M+1, **Then** se devuelven los de M
   indicando que vienen de M, y no se guarda nada para M+1 (RN-03).
3. **Given** ningún mes con porcentajes, **When** se consulta un mes, **Then** la respuesta indica que
   no hay porcentajes definidos.

---

### User Story 3 - Cargar el saldo inicial y ver las bolsas (Priority: P1)

El propietario carga una sola vez el dinero con el que arranca, indicando un monto por bolsa, y luego
ve el listado de bolsas con el saldo de cada una. Antes de guardar puede ver una vista previa.

**Why this priority**: sin saldo inicial, las bolsas no reflejan el dinero real del propietario
(RN-54).

**Independent Test**: con datos sintéticos, previsualizar y cargar Necesidades ₡100.000, Gustos
₡50.000 y Ahorro ₡500.000; el listado muestra esos montos; un segundo intento se rechaza.

**Acceptance Scenarios**:

1. **Given** que no hay saldo inicial, **When** el propietario pide la vista previa con montos por
   bolsa, **Then** ve el total y el monto de cada bolsa, y no se guarda nada.
2. **Given** que no hay saldo inicial, **When** confirma la carga, **Then** se guarda en una sola
   operación atómica y el listado de bolsas muestra el saldo de cada una.
3. **Given** un saldo inicial ya cargado, **When** se intenta cargar otro, **Then** se rechaza (RN-54),
   también si los dos intentos llegan al mismo tiempo.
4. **Given** montos negativos, no enteros, todos en cero, o una bolsa inexistente o archivada, **Then**
   se rechaza sin guardar nada.
5. **Given** un saldo inicial cargado, **Then** no cuenta como ingreso del mes, pero sí forma parte de
   los saldos de las bolsas (RN-54).

---

### User Story 4 - Reparto exacto y dinero que cuadra (Priority: P1)

La lógica de reparto convierte un monto y unos porcentajes en montos enteros por bolsa cuya suma es
exactamente el monto original (se usará para repartir ingresos desde el Hito 5). Y el dinero
registrado cuadra siempre con los saldos de las bolsas (invariante 11.4).

**Why this priority**: la regla no negociable 3 exige la prueba del invariante desde el primer hito
que registra dinero, que es este.

**Independent Test**: repartir ₡10.001 entre tres bolsas con 50/30/20 y comprobar que suma ₡10.001;
cargar saldos iniciales sintéticos y comprobar el invariante.

**Acceptance Scenarios**:

1. **Given** ₡10.001 y 50/30/20, **Then** el reparto es 5.000 / 3.000 / 2.001 y suma ₡10.001 (RN-08).
2. **Given** cualquier monto entero positivo y porcentajes que suman 100, **Then** la suma del reparto
   es exactamente el monto y ningún monto es negativo (prueba con datos generados).
3. **Given** una bolsa con 0 % que no es la última, **Then** recibe ₡0.
4. **Given** un saldo inicial sintético cargado, **Then** la suma de lo repartido es igual a la suma de
   los saldos de las bolsas acumulables más los disponibles de las bolsas de consumo en los meses
   abiertos (invariante 11.4), comprobado con muchos conjuntos de datos generados.

### Edge Cases

- Una bolsa con 0 % en la última posición puede recibir el residuo (como máximo, una unidad menos que
  la cantidad de bolsas, en colones). Es una consecuencia de RN-08 y se documenta.
- Meses con formato inválido (por ejemplo `2026-13` o `26-01`) se rechazan con un mensaje claro.
- Consultar un mes muy lejano sin porcentajes propios usa los del mes anterior más cercano.
- Bolsa de consumo en un mes distinto al de la carga del saldo inicial: su disponible empieza en cero
  (RN-11); la acumulable conserva su saldo (RN-12).
- Sin autenticación válida, ninguna tool responde (401, Hito 3).
- Los mensajes de error se devuelven en español y son claros para que Claude los explique (plan
  técnico 12.2).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: La app MUST guardar bolsas con nombre único y comportamiento `consumo` o `acumulable`
  (RN-10), con grupo opcional y estado activa/archivada. No existe una lista fija de tipos ni de
  bolsas en el código.
- **FR-002**: Los datos iniciales MUST crear las bolsas Necesidades (`consumo`), Ahorro (`acumulable`)
  y Gustos (`consumo`), editables como cualquier otro dato.
- **FR-003**: La app MUST guardar categorías asociadas a una bolsa (sin tools de gestión en este hito).
- **FR-004**: La app MUST guardar los porcentajes por mes y bolsa, y MUST rechazar una configuración
  cuya suma no sea exactamente 100 (RN-01), que no cubra exactamente las bolsas activas, o con
  porcentajes no enteros o fuera de 0 a 100.
- **FR-005**: Cambiar los porcentajes de un mes MUST NOT alterar los de otros meses (RN-02); MUST
  rechazarse la edición de meses pasados.
- **FR-006**: Un mes sin porcentajes propios MUST resolverse con los del mes anterior más cercano que
  los tenga, sin guardar nada al consultar, indicando el mes de origen (RN-03).
- **FR-007**: La capa de dominio MUST repartir un monto entero según porcentajes con enteros: las
  primeras bolsas reciben el monto redondeado hacia abajo y la última absorbe el residuo por resta
  (RN-08).
- **FR-008**: La app MUST permitir cargar el saldo inicial una sola vez, por montos explícitos en
  colones entre bolsas activas (RN-54), en una sola operación atómica (principio 3.6), con una vista
  previa que no guarda nada (principio 3.2). La unicidad MUST garantizarse también ante dos cargas
  simultáneas.
- **FR-009**: El saldo inicial MUST quedar registrado como ingreso de tipo saldo inicial: MUST NOT
  contarse como ingreso del mes y MUST formar parte de los saldos de las bolsas (RN-54).
- **FR-010**: Los saldos MUST calcularse a partir de los movimientos, nunca de un campo editable
  (principio 3.3): acumulable según la sección 11.2 y consumo según la sección 11.1, en colones
  enteros (principio 3.5).
- **FR-011**: MUST existir las tools `set_allocation`, `get_allocation`, `preview_initial_balance`,
  `load_initial_balance` y `list_bolsas`, protegidas por la autenticación vigente, que devuelven datos
  exactos, solo lo necesario (principio 3.10) y errores claros en español, sin dar consejos (plan
  técnico 12.2).
- **FR-012**: La lógica de negocio MUST vivir en la capa de dominio, sin depender de MCP ni de la base
  (gobernanza, regla no negociable 2).
- **FR-013**: MUST existir una prueba automática del invariante de integridad (sección 11.4) contra
  datos sintéticos, que se extenderá en los hitos siguientes (gobernanza, regla no negociable 3).
- **FR-014**: Los registros MUST NOT mostrar montos ni saldos; las pruebas MUST usar solo datos
  sintéticos.
- **FR-015**: El diseño del registro de ingresos MUST permitir que el Hito 5 agregue moneda, monto
  original, tipo de cambio y anulación con una migración propia, sin rehacer las tablas de este hito.
- **FR-016**: `docs/plan-tecnico.md` MUST registrar los nombres en inglés de las tablas de este hito en
  el esquema de referencia y en la tabla concepto → tabla, y `HITOS.md` MUST adelantar la prueba del
  invariante al Hito 4.

### Reglas citadas

- RN-01, RN-02, RN-03, RN-08, RN-10, RN-11, RN-12, RN-54.
- Principios 3.2, 3.3, 3.5, 3.6, 3.9 y 3.10.
- Gobernanza, reglas no negociables 1 (datos reales tras el Hito 3), 2 (capa de dominio), 3
  (invariante con prueba automática) y 4 (pruebas del hito).

### Key Entities

- **Bolsa**: nombre, comportamiento (`consumo` o `acumulable`), grupo opcional, destino de sobrante
  opcional, activa/archivada.
- **Categoría**: nombre, bolsa a la que pertenece, activa/archivada.
- **Porcentajes del mes**: mes (`YYYY-MM`), bolsa, porcentaje entero.
- **Ingreso**: fecha, tipo (`base`, `extra`, `saldo_inicial`), mes presupuestario, monto en colones,
  estado del reparto. En este hito solo se crea el de tipo saldo inicial.
- **Reparto de un ingreso**: ingreso, bolsa, porcentaje (vacío en el saldo inicial) y monto en colones.

## Success Criteria *(mandatory)*

- **SC-001**: Desde Claude se definen Necesidades 50 %, Ahorro 30 % y Gustos 20 % para un mes, y una
  suma distinta de 100 se rechaza.
- **SC-002**: Tras cargar un saldo inicial, el listado de bolsas muestra el saldo de cada una, y un
  segundo intento de carga se rechaza.
- **SC-003**: Cambiar los porcentajes del mes siguiente no modifica el mes anterior (prueba
  automática).
- **SC-004**: ₡10.001 repartidos entre tres bolsas suman exactamente ₡10.001, y la suma es exacta para
  cualquier monto en una prueba con datos generados.
- **SC-005**: La prueba del invariante de integridad pasa con al menos 200 conjuntos de datos
  sintéticos generados.
- **SC-006**: Todos los escenarios de aceptación tienen pruebas automáticas (unitarias de dominio e
  integración con la base), y la suite completa pasa.

## Assumptions

- Crear, archivar o reajustar bolsas (RN-13 a RN-18) queda para el Hito 7; en este hito las bolsas
  activas son las tres iniciales.
- Ingresos base y extra, gastos, monedas e idempotencia llegan en los Hitos 5 y 6.
- El cierre de mes no existe todavía: para el invariante, todos los meses se consideran abiertos y no
  hay ajustes de cierre.
