# Feature Specification: Bolsas flexibles y metas

**Feature Branch**: `hito-7-bolsas-metas`

**Created**: 2026-11-11

**Status**: Implementado (pendiente de la verificación del propietario en el homelab)

**Input**: User description (prompt del Hito 7 en `HITOS.md`): "El propietario quiere crear bolsas
nuevas (por ejemplo Emergencia o Viaje), y que al crearlas se le muestre cómo cambiarían los
porcentajes para aprobarlos. Quiere definir metas de ahorro, como un viaje de ₡500.000 sin fecha
obligatoria, ligadas a una bolsa de ahorro, y ver su avance según el saldo de esa bolsa. Incluye
pruebas automáticas que verifiquen los criterios de aceptación."

**Hito**: 7 (Bolsas flexibles y metas), según `HITOS.md`.

## Resumen de decisiones

**[DECIDIDO] por el propietario (2026-11-11, prompt "/hito 7", sin clarify):**

- El Hito 6 está cerrado (etiqueta `hito-6`). Todas las tools exigen la autenticación vigente.
  Montos enteros en colones, sin `float`.
- Decisión #11 resuelta: una sola meta activa por bolsa. Enmienda PATCH 1.0.3: #11 resuelta
  (sección 14.1.2) y RN-22 [DECIDIDO]. RN-24, RN-28 y RN-29 siguen [PROPUESTO].
- Reglas que aplica: RN-13 a RN-25, RN-28 y RN-29. RN-26 y RN-27 derogadas; RN-30 resuelta (no se
  implementan). Se citan, no se reescriben.
- `preview_rebalance` (proporcional, desde_una_bolsa, manual; RN-01, RN-14) como función pura con
  prueba de propiedades; devuelve porcentajes anteriores y nuevos del mes objetivo.
- `create_bolsa`: nombre único sin mayúsculas; vista previa sin `confirm`; bolsa y porcentajes en
  una transacción (RN-13) con el conjunto completo del mes objetivo; mes siguiente por defecto o el
  actual (RN-15), nunca uno pasado; nada recalcula repartos guardados.
- `archive_bolsa`: solo con saldo o disponible cero (RN-18); nunca se borra (RN-16); redistribuye
  con las mismas estrategias (RN-17); ningún mes de ahora en adelante reparte a una bolsa inactiva ni
  suma distinto de 100; rechaza gastos y repartos; su meta activa se archiva con ella; sin
  reactivación; con saldo, error sin montos y pruebas pendientes anotadas en el Hito 8.
- Sin destinos de sobrante (Hito 9).
- Metas: `create_goal` solo en acumulables activas (RN-21), una activa por bolsa (RN-22) con índice
  único parcial y validación; sin dinero propio (RN-23, RN-25), avance = saldo con la función de 11.2;
  `get_goal_progress` con saldo, objetivo, %, faltante, estado, fecha de logro y RN-28;
  `update_goal` (monto, fecha, pausar, reactivar; reactivar con otra activa se rechaza; lograda no se
  reactiva); `lograda` (RN-24) evaluada en la transacción de cada operación que cambia un saldo;
  excedente en la bolsa (RN-29); metas activas en `get_allocation_context`.
- Mismo patrón de vista previa y `confirm=true`; descripciones con el flujo; se mantiene la nota de
  que `confirm=true` no garantiza que el modelo haya preguntado.
- Migración nueva que conserva los datos del Hito 6; downgrade protegido; invariante con 200
  conjuntos; idempotencia en todas las escrituras; registros y errores sin montos, descripciones ni
  nombres de metas.

**[PROPUESTO] por Claude (para que el propietario confirme):**

1. **Lectura de "recalcular el mes en curso" (RN-15):** aplicar desde el mes actual solo cambia los
   porcentajes para lo que se reparta desde ese momento; ningún reparto guardado se recalcula.
2. **Meses futuros con porcentajes propios al crear:** no se tocan; la bolsa nueva queda en 0 % en
   ellos y la respuesta los lista.
3. **Archivar es inmediato:** `month` solo admite el mes actual; reescribe el mes actual (propio o
   heredado) y cada mes futuro con porcentajes propios. Con `manual`, el mismo reparto se aplica a
   todos esos meses.
4. **Representación mínima de la meta archivada:** columna `archived_at` (el estado de RN-24 no
   cambia; no se agrega un estado nuevo). Se archivan todas las metas no archivadas de la bolsa.
5. **Bolsa archivada en las tools de los Hitos 4 a 6:** rechaza gastos, pagos de fijos, repartos
   de salario y de extras, porcentajes, categorías y metas; `get_bolsa_status` tampoco la consulta;
   `void_transaction` rechaza anular movimientos que la toquen (su saldo debe quedar en cero).
6. **Meta creada con el saldo ya en el objetivo:** nace `lograda` con fecha de hoy, y la respuesta lo
   explica (el excedente se queda en la bolsa).
7. **Fecha de logro:** la del movimiento que cruzó el objetivo (fecha del ingreso o del saldo
   inicial; hoy para el reparto de un extra, una anulación o un cambio de la meta), nunca anterior a
   la creación de la meta.
8. **Anular el movimiento que cruzó el objetivo:** la meta sigue `lograda` (RN-24 la mantiene
   aunque el saldo baje).
9. **Metas pausadas no se evalúan:** solo una activa pasa a lograda; al reactivarla se evalúa.
10. **Una meta lograda es final:** no se pausa, no cambia su objetivo ni su fecha.
11. **Referencia `M-n`** para las metas; `update_goal` las identifica por ella.
12. **Fecha objetivo** no puede estar en el pasado; se puede quitar (`clear_target_date`).
13. **RN-28:** variación neta de un mes = asignado con ese mes presupuestario − gastado ese mes
    calendario; meses completos desde el primero con movimientos de la bolsa; promedio entero hacia
    abajo; `projectable` = al menos un mes y promedio positivo. La app no estima fechas.
14. **`get_goal_progress(bolsa)`** lista todas las metas no archivadas de esa bolsa (activa primero);
    sin bolsa, solo las activas.
15. **Ficha de vista previa** también en `create_bolsa` y `archive_bolsa` ("confirm sin vista
    previa" es un error).
16. **Límites:** nombre de bolsa hasta 40, grupo hasta 40, nombre de meta hasta 60.
17. **Disparadores nuevos:** una bolsa no se borra, no se reactiva ni cambia de comportamiento; una
    meta no se borra ni cambia de bolsa, nombre o fecha de creación; lograda y archivada son fijas.
18. **"Datos" para el downgrade de `0006`:** metas o bolsas archivadas.
19. **`get_bolsa_status`** incluye la meta activa de la bolsa con su avance (el catálogo del plan
    técnico lo anunciaba para el Hito 7).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Crear una bolsa viendo el reajuste (Priority: P1)

1. **Given** porcentajes 40/40/20, **When** pide crear Emergencia al 10 % proporcional, **Then** ve
   36/36/18/10 para el mes siguiente sin que se guarde nada.
2. **Given** su aprobación, **When** confirma con la ficha, **Then** la bolsa y los porcentajes se
   guardan juntos y suman 100; los repartos anteriores no cambian.
3. **Given** un nombre repetido (sin mayúsculas), un mes pasado, un reparto manual que no suma 100 o
   una confirmación sin vista previa, **Then** se rechaza sin guardar.

### User Story 2 - Archivar una bolsa vacía (Priority: P1)

1. **Given** una bolsa con saldo, **Then** archivar se rechaza sin mostrar montos.
2. **Given** una bolsa con saldo cero, **When** confirma, **Then** queda archivada, su porcentaje se
   redistribuye en el mes actual y en los futuros, y su meta se archiva.
3. **Given** una bolsa archivada, **Then** rechaza gastos y repartos, y ningún mes futuro le reparte.

### User Story 3 - Metas de ahorro (Priority: P1)

1. **Given** una bolsa acumulable, **When** crea "Viaje ₡500.000", **Then** el avance es el saldo.
2. **Given** una bolsa de consumo o una segunda meta activa, **Then** se rechaza.
3. **Given** el saldo alcanza el objetivo, **Then** la meta pasa a lograda con la fecha del movimiento
   y sigue lograda aunque se gaste.
4. **Given** una meta pausada y otra activa en la bolsa, **Then** reactivarla se rechaza.
5. **Given** al menos un mes completo, **Then** `get_goal_progress` entrega el promedio del RN-28.

### User Story 4 - Dinero que cuadra y datos que se conservan (Priority: P1)

1. **Given** 200 conjuntos sintéticos, **Then** crear bolsas, reajustar, archivar y crear o cambiar
   metas no altera ningún saldo; el avance de cada meta es el saldo de su bolsa; los meses pasados no
   cambian.
2. **Given** una base con datos del Hito 6, **When** migra a `0006`, **Then** los datos quedan
   iguales y el downgrade se niega si hay metas o bolsas archivadas.

### Edge Cases

- Archivar la única bolsa activa: se rechaza.
- Proporcional al archivar cuando las demás tienen 0 %: se pide desde_una_bolsa o manual.
- Crear sin porcentajes en ningún mes: solo con estrategia manual.
- Dos metas simultáneas en la misma bolsa: solo una se crea (índice único).

## Requirements *(mandatory)*

- **FR-001** `preview_rebalance` calcula sin guardar (crear o archivar, tres estrategias).
- **FR-002** Reajuste puro: enteros 0 a 100, suma 100, residuo en la última (RN-01, RN-14).
- **FR-003** `create_bolsa` atómico con el conjunto completo del mes (RN-13, RN-15).
- **FR-004** `archive_bolsa` con saldo cero, redistribución y metas archivadas (RN-16 a RN-18).
- **FR-005** Bolsa archivada rechaza gastos, repartos, porcentajes y metas.
- **FR-006** `create_goal` en acumulable activa; una activa por bolsa (RN-21, RN-22).
- **FR-007** Avance = saldo de 11.2; crear o cambiar metas no mueve saldos (RN-23, RN-25).
- **FR-008** `lograda` evaluada en la transacción de cada operación que sube un saldo (RN-24).
- **FR-009** `get_goal_progress` con los números del RN-28 y el excedente (RN-29).
- **FR-010** `update_goal`: monto, fecha, pausar, reactivar con sus reglas.
- **FR-011** Metas activas en `get_allocation_context`.
- **FR-012** Vista previa con ficha y `confirm=true` en crear y archivar.
- **FR-013** Idempotencia en todas las escrituras.
- **FR-014** Migración `0006_pockets_goals` que conserva datos; downgrade protegido.
- **FR-015** Registros y errores sin montos, descripciones ni nombres de metas.
- **FR-016** Invariante con 200 conjuntos y pruebas de avance = saldo y meses pasados intactos.
- **FR-017** 401 sin credencial.

### Key Entities

- **Bolsa** (`pockets`): ahora con `archived_at`.
- **Meta** (`savings_goals`): bolsa, nombre, objetivo, fecha opcional, estado, fecha de logro,
  creación, archivado. Referencia `M-n`.

## Success Criteria *(mandatory)*

- **SC-001** Crear una bolsa muestra el reajuste antes de guardar y, al confirmar, los porcentajes
  suman 100.
- **SC-002** El avance de cada meta coincide siempre con el saldo de su bolsa.
- **SC-003** Ninguna operación de este hito cambia un saldo (200 conjuntos).
- **SC-004** Una meta lograda nunca vuelve atrás.
- **SC-005** 0 montos y 0 nombres de metas en los registros.

## Assumptions

- Las transferencias (Hito 8) completarán el archivado de bolsas con saldo.
- Hasta el Hito 9 todos los meses están abiertos.
