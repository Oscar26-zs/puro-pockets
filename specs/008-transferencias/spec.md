# Feature Specification: Transferencias entre bolsas

**Feature Branch**: `hito-8-transferencias`

**Created**: 2026-11-11

**Status**: Implementado (pendiente de la verificación del propietario en el homelab)

**Input**: User description (prompt del Hito 8 en `HITOS.md`): "El propietario quiere mover dinero
de una bolsa a otra, por ejemplo para cubrir un gasto que excedió Gustos, viendo antes cómo
quedarían ambas bolsas y qué efecto tendría sobre su meta de ahorro. Cada movimiento debe quedar
registrado y no poder editarse ni borrarse. Incluye pruebas automáticas que verifiquen los criterios
de aceptación."

**Hito**: 8 (Transferencias entre bolsas), según `HITOS.md`.

## Resumen de decisiones

**[DECIDIDO] por el propietario (2026-11-11, prompt "/hito 8", sin clarify):**

- El Hito 7 está cerrado (etiqueta `hito-7`). Todas las tools exigen la autenticación vigente.
  Montos enteros en colones, sin `float`. Las transferencias son internas: siempre en colones, sin
  moneda ni tipo de cambio.
- Enmienda PATCH 1.0.4: RN-58 pasa a [DECIDIDO]. Nada más cambia en la constitución.
- Reglas que aplica: RN-39 a RN-44 y RN-58; completa RN-18; usa RN-37, la sección 9.1 y los
  cálculos de 11.1 y 11.2. RN-45 está derogada (no se implementa). Se citan, no se reescriben.
- `preview_transfer(origen, destino, monto, motivo, nota)` calcula sin guardar: cómo quedan ambas
  bolsas (saldo si es acumulable; disponible y presupuesto ajustado del mes si es de consumo) y el
  efecto en el avance de su meta activa (RN-58), incluido si la completaría. Rechaza sin montos lo
  que viole RN-41 o RN-42.
- `transfer_between_bolsas(…, confirm, operation_id)`: sin `confirm=true` devuelve la vista previa;
  con `confirm=true` guarda.
- Validaciones: monto entero positivo; origen distinto del destino; ambas bolsas activas y
  existentes (nombre sin distinguir mayúsculas, sin identificadores internos); no más de lo
  disponible en el origen y nunca desde una bolsa en negativo (RN-42); motivo `cubrir_sobregasto`,
  `reasignacion` o `ajuste` (`cierre_de_mes` reservado para el Hito 9, la tool lo rechaza); nota de
  hasta 140 caracteres.
- Fecha: siempre hoy en America/Costa_Rica; el mes es el de esa fecha; sin fechas pasadas ni
  futuras. Hasta el Hito 9 todos los meses cuentan como abiertos.
- Una sola transacción; las dos bolsas se bloquean en orden fijo (por id) y lo disponible se vuelve
  a comprobar dentro de la transacción; el estado de las metas se evalúa en esa misma transacción
  con la función central del Hito 7. Concurrencia probada.
- Tabla nueva en inglés, inmutable (RN-43, principio 3.4): CHECK de monto > 0, origen ≠ destino,
  motivo permitido (incluido el reservado) y mes `YYYY-MM`; claves foráneas ON DELETE RESTRICT;
  disparador que rechaza UPDATE y DELETE. Sin tools para anular ni editar: se corrige con otra en
  sentido contrario.
- Referencia `T-n`; `list_transactions` incluye transferencias (filtro por tipo; límites iguales).
  La nota nunca va a registros ni a errores.
- `get_bolsa_status`, `get_summary` y `get_allocation_context`: presupuesto original, recibidas,
  enviadas, ajustado, gastado y disponible (consumo); el saldo de las acumulables ya incluye las
  transferencias (11.2). Una sola función compartida hace esos cálculos.
- % usado sobre el presupuesto ajustado, con el % sobre el original como referencia; las
  anulaciones se ignoran.
- RN-37: la advertencia de `add_expense` lista las bolsas con disponible o saldo según los cálculos
  nuevos; las descripciones guían: tras un sobregasto, proponer una transferencia con
  `preview_transfer`, esperar la aprobación explícita y solo entonces confirmar. Se mantiene la nota
  de que `confirm=true` no garantiza que el modelo haya preguntado.
- `archive_bolsa` con saldo distinto de cero indica, sin montos, que primero hay que mover el saldo
  con una transferencia; una bolsa de consumo con disponible del mes mayor que cero también debe
  vaciarse. Se completan las pruebas pendientes del Hito 7.
- Migración nueva que conserva los datos del Hito 7, probada con datos; downgrade protegido;
  invariante con 200 conjuntos y semilla fija; idempotencia en toda escritura; registros y errores
  sin montos, notas ni nombres de metas; `sse_starlette` en INFO.

**[PROPUESTO] por Claude (para que el propietario confirme):**

1. **Fecha (pedido del propietario):** la fecha es siempre hoy; `transfer_date` es opcional y solo
   se acepta si es la de hoy (así una fecha pasada o futura se rechaza con un mensaje claro). Hasta
   el Hito 9 todos los meses están abiertos; RN-44 se completa allí.
2. **Inmutabilidad en la base (pedido del propietario):** `transfers` con las restricciones CHECK,
   claves foráneas ON DELETE RESTRICT y el disparador `trg_transfers_immutable` que rechaza UPDATE y
   DELETE.
3. **% usado (11.1, pedido del propietario):** sobre el presupuesto ajustado, con el % sobre el
   original aparte (`percent_used_original`).
4. **Ficha de vista previa:** `transfer_between_bolsas` con `confirm=true` exige el `preview_token`
   de una vista previa con exactamente los mismos datos (origen, destino, monto, motivo, nota y
   fecha), como en los Hitos 6 y 7. La ficha no incluye saldos: lo disponible se vuelve a validar al
   guardar.
5. **Mecanismo de concurrencia:** no existía uno previo; se usa `SELECT … FOR UPDATE` sobre las dos
   filas de `pockets` en orden de id. `archive_bolsa` también bloquea su bolsa y vuelve a comprobar
   el saldo cero dentro de la transacción, para que una transferencia simultánea hacia ella no la
   deje archivada con dinero.
6. **Mes de una transferencia:** el de hoy para las dos bolsas. En consumo cambia el presupuesto
   ajustado y el disponible de ese mes; en acumulable, el saldo histórico.
7. **RN-58 en ambas bolsas:** la vista previa muestra el efecto en la meta activa del origen (baja) y
   del destino (sube, y si la completa). Solo cuentan las metas activas (no pausadas, logradas ni
   archivadas). El aviso usa porcentajes y la referencia `M-n`, nunca el nombre de la meta.
8. **Destino en negativo:** se puede transferir hacia una bolsa en negativo (cubrir sobregasto); si
   sigue en negativo después, la vista previa lo avisa.
9. **Meta completada por una transferencia:** pasa a `lograda` en la transacción, con fecha de hoy;
   sacar dinero después no la revierte (RN-24).
10. **RN-28:** la variación neta mensual del saldo incluye las transferencias de ese mes.
11. **`void_transaction` con una `T-n`:** devuelve un error explícito que explica la corrección con
    una transferencia inversa (RN-43).
12. **`list_transactions`:** el filtro por bolsa aplica a gastos y a transferencias (como origen o
    destino); las transferencias siempre se listan (nunca están anuladas).
13. **Nota visible:** aparece en la respuesta y en `list_transactions` (es un dato del registro,
    RN-40), y se guarda con la respuesta de la clave de operación; nunca en registros ni errores.
14. **Monto:** solo un entero JSON (sin texto ni decimales), porque las transferencias son siempre
    en colones.
15. **Archivar (RN-18):** una bolsa de consumo con disponible del mes negativo tampoco se archiva:
    primero se cubre con una transferencia hacia ella. Solo cuenta el disponible del mes actual; los
    sobrantes de meses anteriores se resolverán con el cierre (Hito 9).
16. **Motivo validado en el dominio:** el esquema anuncia los tres valores, pero la validación la hace
    la capa de dominio para responder en español (incluido el aviso de `cierre_de_mes`) sin repetir
    el valor recibido.
17. **"Datos" para el downgrade de `0007`:** cualquier fila en `transfers`.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Cubrir un sobregasto (Priority: P1)

El propietario gasta de más en Gustos. `add_expense` lo guarda (RN-37), avisa y lista las bolsas
con disponible o saldo. Claude propone cubrirlo desde Necesidades, muestra la vista previa y espera
la aprobación; al confirmar, Gustos vuelve a cero y el movimiento queda en el historial.

**Independent Test**: salario, gasto que deja Gustos en negativo, `preview_transfer` y
`transfer_between_bolsas` con la ficha; Gustos queda en 0 y `list_transactions` muestra `T-1`.

**Acceptance Scenarios**:

1. **Given** Gustos en −30 000, **When** se pide la vista previa desde Necesidades por 30 000,
   **Then** no se guarda nada y Gustos pasaría a 0, con su presupuesto ajustado.
2. **Given** esa vista previa aprobada, **When** se confirma con la ficha, **Then** se guarda `T-1`,
   la suma de saldos y disponibles no cambia y Gustos queda en 0.
3. **Given** un monto mayor que el disponible de Necesidades, **When** se pide la vista previa,
   **Then** se rechaza sin mostrar montos (RN-42).

### User Story 2 - Efecto sobre la meta (Priority: P1)

Al mover dinero fuera de una bolsa con meta activa, la vista previa muestra cuánto baja su avance
(RN-58); al moverlo hacia ella, cuánto sube y si la completaría.

**Acceptance Scenarios**:

1. **Given** Ahorro con 300 000 y una meta de 1 000 000, **When** se previsualiza mover 60 000 a
   Gustos, **Then** el avance baja de 30 % a 24 %.
2. **Given** una meta a 100 000 de su objetivo, **When** se transfieren 100 000 a su bolsa,
   **Then** la meta pasa a `lograda` en la misma transacción.

### User Story 3 - Archivar tras vaciar (Priority: P1)

Una bolsa con saldo no se archiva; el error explica que primero hay que transferir. Tras vaciarla
con una transferencia (`reasignacion`), se archiva y su meta se archiva con ella.

**Acceptance Scenarios**:

1. **Given** Ahorro con saldo y una meta activa, **When** se pide archivarla, **Then** se rechaza
   indicando usar `transfer_between_bolsas` (sin montos).
2. **Given** Ahorro vaciada con una transferencia, **When** se archiva, **Then** queda archivada y
   su meta también.
3. **Given** Gustos con disponible del mes, **When** se vacía y se archiva, **Then** queda archivada
   y ya no admite transferencias.

### User Story 4 - Registro inmutable y cálculos (Priority: P1)

Las transferencias no se editan ni se borran (RN-43); un error se corrige con otra en sentido
contrario. Las consultas muestran el presupuesto original y el ajustado (9.1).

**Acceptance Scenarios**:

1. **Given** `T-1`, **When** se intenta `void_transaction("T-1")`, **Then** se rechaza explicando la
   transferencia inversa; un UPDATE o DELETE directo en la base también se rechaza.
2. **Given** transferencias del mes, **When** se consulta `get_bolsa_status`, **Then** muestra
   original, recibidas, enviadas, ajustado, gastado, disponible y % usado sobre ambos.
3. **Given** 200 conjuntos sintéticos con transferencias, **Then** el invariante 11.4 cuadra y el
   ajustado es asignado + recibidas − enviadas.

### Edge Cases

- Origen igual al destino; monto 0, negativo, decimal o texto; bolsa archivada o inexistente.
- Motivo inválido o `cierre_de_mes`; nota de más de 140; fecha pasada o futura.
- `confirm=true` sin ficha o con otra ficha; la misma clave con otro contenido.
- Dos transferencias simultáneas que juntas sobregirarían el origen: solo pasan las que caben.
- Archivar y transferir hacia la misma bolsa a la vez: nunca queda archivada con dinero.
- Cambia el disponible entre la vista previa y la confirmación: se valida de nuevo al guardar.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: `preview_transfer` no guarda nada y devuelve ambas bolsas antes y después (saldo o
  disponible, y presupuesto ajustado en consumo) y el efecto en las metas activas (RN-58).
- **FR-002**: `transfer_between_bolsas` sin `confirm=true` devuelve la vista previa; con
  `confirm=true` exige `operation_id` y la ficha, y guarda de forma atómica (RN-39, RN-40).
- **FR-003**: monto entero positivo y origen distinto del destino (RN-41); no más de lo disponible
  ni desde una bolsa en negativo (RN-42), validado otra vez con las bolsas bloqueadas.
- **FR-004**: motivo `cubrir_sobregasto`, `reasignacion` o `ajuste`; `cierre_de_mes` rechazado; nota
  hasta 140; fecha hoy.
- **FR-005**: tabla `transfers` inmutable (CHECK, FK RESTRICT, disparador); sin tools de anulación
  ni edición (RN-43).
- **FR-006**: referencia `T-n`; `list_transactions` con tipo `transferencia` y filtro por bolsa.
- **FR-007**: `get_bolsa_status`, `get_summary` y `get_allocation_context` muestran 9.1 con una sola
  función (`pocket_figures`).
- **FR-008**: la advertencia de sobregasto (RN-37) usa los cálculos nuevos y guía hacia
  `preview_transfer`.
- **FR-009**: `archive_bolsa` exige saldo o disponible cero y, si no, indica transferir (RN-18).
- **FR-010**: las metas se evalúan en la transacción de la transferencia (RN-24).
- **FR-011**: migración `0007_transfers` que conserva los datos y downgrade protegido.
- **FR-012**: invariante 11.4 con 200 conjuntos; idempotencia; registros y errores sin montos, notas
  ni nombres de metas.

### Key Entities

- **Transferencia**: fecha, mes, origen, destino, monto en colones, motivo y nota (RN-40); `T-n`.

## Success Criteria *(mandatory)*

- **SC-001**: Gustos en negativo vuelve a cero con una transferencia desde Necesidades, visible en el
  historial.
- **SC-002**: no se puede mover más de lo disponible, ni siquiera con dos transferencias a la vez.
- **SC-003**: mover dinero fuera de una bolsa con meta activa muestra el efecto en su avance.
- **SC-004**: el invariante sigue cuadrando con transferencias.
- **SC-005**: una bolsa se archiva tras vaciarla con una transferencia.

## Assumptions

- Datos siempre sintéticos en pruebas; nada se ejecuta contra la base del homelab desde el
  desarrollo.
- El cierre de mes (RN-44, `cierre_de_mes`) es del Hito 9.
