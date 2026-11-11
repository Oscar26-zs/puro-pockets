# Feature Specification: Extras y gastos fijos

**Feature Branch**: `hito-6-extras-fijos`

**Created**: 2026-11-11

**Status**: Implementado (pendiente de la verificación del propietario en el homelab)

**Input**: User description (prompt del Hito 6 en `HITOS.md`): "El propietario quiere registrar
ingresos extra y que, en cada uno, Claude le proponga cómo repartirlo entre las bolsas según la
situación del mes, para él confirmar o ajustar antes de guardar. También quiere registrar sus gastos
fijos mensuales y saber cuáles ya pagó y cuáles faltan. Incluye pruebas automáticas que verifiquen los
criterios de aceptación."

**Hito**: 6 (Extras y gastos fijos), según `HITOS.md`.

## Resumen de decisiones

**[DECIDIDO] por el propietario (2026-11-10, prompt "/hito 6", sin clarify):**

- El Hito 5 está cerrado (etiqueta `hito-5`). Todas las tools exigen la autenticación vigente.
  Montos enteros, sin `float`. Colones y dólares según RN-55 a RN-57.
- Decisión #12d resuelta (constitución 1.0.2, sección 14.1.1): un pago de gasto fijo en USD exige el
  tipo de cambio que indique el propietario en ese pago; si falta, error; nunca se asume ni se
  reutiliza el último.
- Reglas que aplica este hito: RN-04 a RN-09, RN-35 y RN-36 (además de RN-01 para la suma, RN-53 y
  RN-59 para corregir, y RN-55 a RN-57 para monedas). Se citan, no se reescriben.
- `register_extra_income`: tipo `extra`, estado pendiente, mes = mes de su fecha (RN-09), moneda y
  tipo de cambio como en el Hito 5, `operation_id` obligatorio. Pendiente, no suma a ninguna bolsa y
  se muestra como "sin asignar" (RN-06).
- `get_allocation_context(extra)`: solo agregados: bolsas activas con comportamiento, porcentajes
  vigentes del mes, presupuesto, gastado y disponible por bolsa, total de fijos pendientes del mes y
  porcentajes de los últimos extras. Sin descripciones de gastos ni identificadores internos. Los
  fijos pendientes en USD aparte, sin convertir.
- `confirm_allocation(extra, porcentajes, confirm, operation_id)`: enteros 0 a 100 que suman 100
  (RN-01), solo bolsas activas existentes; sin `confirm=true` devuelve la vista previa en colones y no
  guarda; reparte con RN-08, guarda el porcentaje usado y pasa el extra a repartido. Un extra
  repartido no se reparte de nuevo (corregir = anular y registrar, RN-53, RN-59). 100 % a una sola
  bolsa y bolsas personalizadas permitidos (RN-07).
- Claude recomienda, la app no (RN-05, principio 3.1). Instrucciones del servidor MCP y descripciones
  de tools con el flujo; el plan técnico documenta que `confirm=true` no garantiza por sí solo que el
  modelo haya preguntado y cómo se mitiga.
- Los extras pendientes aparecen como "sin asignar" (cantidad y total en colones, y los de USD aparte)
  en `get_summary` y `list_transactions`.
- `manage_recurring` (crear, listar, actualizar, desactivar): nombre único sin distinguir mayúsculas,
  monto, moneda, día del mes (si el mes es más corto, el último día), bolsa por defecto, categoría
  opcional y mes de inicio (por defecto el actual). Nunca se borran. Cambiar el monto afecta solo
  meses futuros.
- `list_pending_recurring(mes)` (por defecto el actual en America/Costa_Rica): plantillas activas sin
  pago activo ese mes, desde su mes de inicio, con vencimiento y marca de atrasado. No convierte USD.
- Pagar un fijo: `add_expense` con referencia opcional a la plantilla; monto por defecto el de la
  plantilla (se puede cambiar); un solo pago activo por plantilla y mes; si se anula, vuelve a
  pendiente. Generación **bajo demanda** (sin proceso programado).
- Migración nueva que conserva los datos del Hito 5 y reutiliza lo existente en `incomes`; downgrade
  protegido como los anteriores. Invariante 11.4 con 200 conjuntos sintéticos. Idempotencia en todas
  las escrituras de dinero y de plantillas. Registros y errores sin montos ni descripciones.

**[PROPUESTO] por Claude (para que el propietario confirme):**

1. **Referencia `F-n`** para las plantillas de gastos fijos (número de fila), junto a `I-n` y `G-n`.
2. **Ficha de vista previa (`preview_token`)**: `confirm=true` exige la ficha que devuelve la vista
   previa con exactamente esos porcentajes. Es la prueba negativa "confirm sin vista previa" y la
   primera capa de la mitigación de `confirm=true`.
3. **Bolsas omitidas = 0 %** en `confirm_allocation` (a diferencia de `set_allocation`, que exige
   todas); los repartos solo guardan las bolsas con porcentaje mayor que 0.
4. **"Sin asignar" global**: cuenta los extras pendientes de cualquier mes, no solo del mes
   consultado; `total_crc` incluye el equivalente en colones de los USD (calculado al registrarlos) y
   además se informan aparte su cantidad y total en dólares.
5. **`income_total` de `get_summary`** pasa a ser base + extras repartidos del mes (sin saldo
   inicial), con `extra_income_total` aparte.
6. **Origen opcional del extra** (`source`, hasta 120 caracteres), guardado en `incomes.source`;
   nunca en registros ni errores.
7. **Contexto también para un extra ya repartido** (marcado `repartido`); confirmar sí exige
   pendiente. Los "últimos extras" son los 3 más recientes repartidos y vigentes.
8. **Nombre único solo entre plantillas activas**: al desactivar una, su nombre queda libre.
9. **El cambio de monto vale desde el mes siguiente** (o desde el mes de inicio, si es posterior);
   cambios repetidos para el mismo mes futuro se reemplazan.
10. **Moneda y mes de inicio no se cambian**; una plantilla desactivada no se reactiva ni se edita
    (se crea otra). Día, bolsa, categoría y nombre sí se cambian y valen de inmediato.
11. **El pago pertenece al mes calendario de su fecha** (RN-32); no se admite un pago con fecha
    anterior al mes de inicio. La moneda del pago es la de la plantilla salvo que se indique otra
    (entonces el monto es obligatorio).
12. **`list_pending_recurring` también lista los pagados** del mes (con la referencia del gasto),
    para mostrar "cuáles ya se pagaron y cuáles faltan" (RN-35).
13. **Atrasado** = hoy (America/Costa_Rica) posterior al vencimiento; un mes futuro nunca está
    atrasado.
14. **Disparadores nuevos**: un reparto no vuelve a pendiente ni se hace sobre un ingreso anulado;
    plantillas y montos no se borran; moneda e inicio no cambian; no se reactiva.
15. **El upgrade de `0005` se niega** si encuentra un ingreso que no es extra en estado pendiente
    (no debería existir); "datos" para el downgrade = plantillas, extras o gastos enlazados.
16. **Una sola tool `manage_recurring` con `action`** (`crear`, `listar`, `actualizar`,
    `desactivar`), como pide el catálogo; `operation_id` obligatorio salvo al listar.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Registrar un extra que queda "sin asignar" (Priority: P1)

El propietario dice "me entraron ₡40.000 extra". Queda registrado como pendiente, en el mes de su
fecha, sin tocar ninguna bolsa, y el resumen lo muestra como "sin asignar".

**Acceptance Scenarios**:

1. **Given** porcentajes del mes, **When** registra un extra de ₡40.000, **Then** recibe `I-n`,
   estado `pendiente`, mes = el de su fecha, y ninguna bolsa cambia.
2. **Given** un extra pendiente, **When** pide `get_summary` o `list_transactions`, **Then** ve "sin
   asignar": cantidad 1 y total ₡40.000.
3. **Given** un extra en USD sin tipo de cambio, **Then** se rechaza y no se guarda nada.
4. **Given** la misma llamada repetida con la misma clave, **Then** no se duplica.

### User Story 2 - Claude propone y el propietario aprueba el reparto (Priority: P1)

Claude pide el contexto, propone bolsas y porcentajes con una explicación breve, muestra la vista
previa y solo confirma cuando el propietario aprueba.

**Acceptance Scenarios**:

1. **Given** un extra pendiente, **When** Claude pide el contexto, **Then** recibe solo agregados
   (bolsas, porcentajes, presupuesto, gastado, disponible o saldo, fijos pendientes con USD aparte,
   porcentajes de extras previos), sin descripciones ni identificadores internos.
2. **Given** porcentajes que suman 100, **When** pide la vista previa, **Then** recibe el reparto en
   colones con el residuo en la última bolsa que recibe (RN-08) y no se guarda nada.
3. **Given** la aprobación del propietario, **When** confirma con la ficha y una clave, **Then** el
   extra pasa a repartido, cada reparto guarda su porcentaje y la suma es exactamente el monto.
4. **Given** un reparto que no suma 100, una bolsa inexistente o archivada, o una confirmación sin
   la ficha de su vista previa, **Then** se rechaza sin guardar.
5. **Given** un extra ya repartido, **Then** no se reparte otra vez; se corrige anulando (revierte el
   reparto) y registrando de nuevo.
6. **Given** 100 % a una sola bolsa personalizada, **Then** se acepta (RN-07).

### User Story 3 - Gastos fijos: plantillas y pendientes (Priority: P1)

**Acceptance Scenarios**:

1. **Given** una plantilla nueva (nombre, monto, moneda, día, bolsa, categoría opcional, inicio),
   **Then** recibe `F-n`; un nombre repetido (sin mayúsculas) entre las activas se rechaza.
2. **Given** plantillas activas, **When** pide `list_pending_recurring`, **Then** ve las que faltan
   pagar en el mes con vencimiento y atraso, y las ya pagadas; las de USD sin convertir.
3. **Given** día 31 en febrero, **Then** vence el 28 (o 29).
4. **Given** un cambio de monto, **Then** vale desde el mes siguiente; el mes actual conserva el suyo.
5. **Given** una plantilla desactivada, **Then** no figura como pendiente, no admite pagos ni cambios,
   y su historial se conserva.

### User Story 4 - Pagar un gasto fijo (Priority: P1)

**Acceptance Scenarios**:

1. **Given** un fijo pendiente, **When** paga con `add_expense` y `recurring` sin monto, **Then** se
   registra un gasto con el monto de la plantilla, en su bolsa, y deja de estar pendiente.
2. **Given** un pago vigente en el mes, **Then** un segundo pago se rechaza; anulado el primero, vuelve
   a pendiente y se puede pagar.
3. **Given** un fijo en USD, **Then** cada pago exige su tipo de cambio; nunca se reutiliza el anterior.

### User Story 5 - Dinero que cuadra y datos que se conservan (Priority: P1)

**Acceptance Scenarios**:

1. **Given** 200 conjuntos sintéticos con extras pendientes, repartidos y anulados y pagos de fijos,
   **Then** el invariante 11.4 cuadra (pendientes fuera, repartidos dentro, anulaciones revierten).
2. **Given** una base con datos del Hito 5, **When** se migra a `0005`, **Then** los datos quedan
   iguales; el downgrade se niega si hay datos del Hito 6.
3. **Given** cualquier llamada, **Then** registros y errores no contienen montos ni descripciones.

### Edge Cases

- Extra anulado mientras está pendiente: deja de figurar como "sin asignar"; no cambia bolsas.
- Anular un extra repartido puede dejar bolsas en negativo: se advierte (RN-59, RN-37).
- Dos confirmaciones simultáneas del mismo extra con claves distintas: solo una reparte.
- Dos pagos simultáneos del mismo fijo en el mes: solo uno se guarda.
- Pago con fecha anterior al mes de inicio de la plantilla: se rechaza.
- Bolsa por defecto de la plantilla archivada: se pide la bolsa del pago.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: `register_extra_income` registra un extra pendiente, mes = mes de su fecha (RN-09),
  fecha no futura, moneda y tipo de cambio como en el Hito 5, `operation_id` obligatorio.
- **FR-002**: Un extra pendiente no suma a ninguna bolsa ni al invariante (RN-06, 11.4).
- **FR-003**: `get_summary` y `list_transactions` muestran "sin asignar": cantidad, total en colones,
  cantidad y total de los USD, referencias.
- **FR-004**: `get_allocation_context` entrega solo agregados del mes del extra (ver Resumen).
- **FR-005**: `confirm_allocation` valida RN-01 entre bolsas activas, reparte con RN-08, guarda el
  porcentaje y pasa a repartido, atómico.
- **FR-006**: Sin `confirm=true`, `confirm_allocation` no guarda y devuelve la vista previa y su ficha.
- **FR-007**: Con `confirm=true` exige `operation_id` y la ficha de la vista previa de esos mismos
  porcentajes.
- **FR-008**: Un extra repartido o anulado no se reparte; un ingreso que no es extra tampoco.
- **FR-009**: Instrucciones del servidor y descripciones de tools explican el flujo y piden la
  aprobación explícita.
- **FR-010**: `manage_recurring` crea, lista, actualiza y desactiva plantillas; nunca las borra.
- **FR-011**: Nombre único entre las activas sin distinguir mayúsculas; día 1 a 31.
- **FR-012**: Cambiar el monto vale solo para meses futuros.
- **FR-013**: `list_pending_recurring` lista pendientes (activas, desde su inicio, sin pago vigente)
  con vencimiento y atraso, y los pagados; no convierte USD.
- **FR-014**: `add_expense` acepta `recurring`; monto por defecto el de la plantilla; un solo pago
  vigente por plantilla y mes.
- **FR-015**: Un pago en USD exige su tipo de cambio (decisión #12d).
- **FR-016**: Idempotencia en `register_extra_income`, `confirm_allocation`, `add_expense` y las
  escrituras de `manage_recurring`.
- **FR-017**: Migración `0005_extras_recurring` que conserva los datos del Hito 5; downgrade protegido.
- **FR-018**: Registros y errores sin montos, descripciones ni nombres de plantillas.
- **FR-019**: Invariante 11.4 con 200 conjuntos sintéticos en memoria y una muestra en Postgres.
- **FR-020**: Todas las tools exigen el token (401 sin credencial).

### Reglas citadas

RN-01, RN-04 a RN-09, RN-35, RN-36, RN-53, RN-55 a RN-57, RN-59; principios 3.1, 3.2, 3.4, 3.5, 3.6
y 3.8; decisión #12d.

### Key Entities

- **Ingreso extra** (`incomes`, `kind = 'extra'`): estado pendiente o repartido; origen opcional.
- **Plantilla de gasto fijo** (`recurring_expenses`): nombre, moneda, día, bolsa, categoría, inicio,
  activa; referencia `F-n`.
- **Monto de la plantilla por mes** (`recurring_expense_amounts`).
- **Pago de un fijo**: un gasto con `recurring_id`.

## Success Criteria *(mandatory)*

- **SC-001**: Un extra queda pendiente y visible como "sin asignar" en una sola frase a Claude.
- **SC-002**: Al confirmar un reparto, la suma de los montos es exactamente el monto del extra.
- **SC-003**: Ningún reparto se guarda sin una vista previa previa con esos porcentajes.
- **SC-004**: `list_pending_recurring` refleja cada pago y cada anulación en el acto.
- **SC-005**: Ningún pago en USD se registra sin su tipo de cambio.
- **SC-006**: El invariante cuadra en 200 conjuntos sintéticos.
- **SC-007**: 0 montos y 0 descripciones en los registros del servidor.

## Assumptions

- Hasta el Hito 9 todos los meses están abiertos; las anulaciones siempre se permiten.
- Las metas (Hito 7) se agregarán al contexto del extra cuando existan.
- La aprobación humana la garantiza el cliente (permiso por tool) y el propietario; la app solo puede
  exigir que exista la vista previa.
