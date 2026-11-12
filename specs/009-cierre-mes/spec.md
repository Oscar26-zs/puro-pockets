# Feature Specification: Cierre de mes

**Feature Branch**: `hito-9-cierre-mes`

**Created**: 2026-11-11

**Status**: Implementado (pendiente de la verificación del propietario en el homelab)

**Input**: User description (prompt del Hito 9 en `HITOS.md`): "A fin de mes, el propietario quiere
ver los déficits y sobrantes de sus bolsas de consumo, recibir una propuesta de cómo cubrir déficits
y a dónde enviar los sobrantes, confirmarla o cambiarla, y cerrar el mes de forma que lo cerrado no
pueda modificarse. Las bolsas de consumo empiezan el mes siguiente en cero. Incluye pruebas
automáticas que verifiquen los criterios de aceptación."

**Hito**: 9 (Cierre de mes), según `HITOS.md`.

## Resumen de decisiones

**[DECIDIDO] por el propietario (2026-11-11, prompt "/hito 9 revisar", sin clarify):**

- El Hito 8 está cerrado (etiqueta `hito-8`). Todas las tools exigen la autenticación vigente.
  Montos enteros en colones, sin `float`.
- Enmienda PATCH 1.0.5: RN-51 pasa a [DECIDIDO]. Nada más cambia en la constitución.
- Reglas que aplica: RN-44, RN-46 a RN-53 y RN-58; sección 10 completa (10.1 orden, 10.2 destinos,
  10.4 flujo), 6.5 (destino de sobrante sugerido), 11.1, 11.2 y el invariante 11.4. Se citan, no se
  reescriben.
- `preview_month_close(month?, covers?, destinations?)` no guarda nada (principio 3.2). Sin
  propuesta devuelve datos: por bolsa de consumo, sobrante o déficit del mes (11.1); por acumulable,
  saldo y meta activa con avance; extras pendientes (bloqueo), fijos pendientes (aviso) y el destino
  de sobrante sugerido (6.5). La app no recomienda (principio 3.1): Claude arma la propuesta. Con
  propuesta valida y devuelve cómo queda cada bolsa, el efecto en las metas (RN-58), lo "no
  destinado" y el "sobregasto no cubierto" de forma explícita, más un `preview_token`. Siempre
  advierte que, al cerrar, el mes no admitirá más movimientos, ni siquiera de hoy.
- `close_month(month, covers, destinations, confirm, preview_token, operation_id)`: sin
  `confirm=true` no guarda nada. `covers = [{from_pocket, to_pocket, amount}]` cubre déficits
  (RN-52); `destinations = [{from_pocket, to_pocket | null, amount}]` envía sobrantes a una
  acumulable activa o a "no destinado". Orden fijo (10.1): primero déficits, después sobrantes;
  primero los sobrantes de consumo; tomar de una acumulable solo si esos sobrantes ya quedaron
  usados, y la vista previa lo marca como cobertura desde saldo con aviso de meta.
- Validaciones: enteros positivos; bolsas activas; lo que sale de una bolsa no supera su sobrante
  ni (acumulable) su saldo (RN-47); lo no asignado de un sobrante queda como sobrante no destinado
  y lo no cubierto de un déficit como sobregasto no cubierto (RN-50); el mes se cierra igual. Nada
  de la tabla de ajustes se oculta.
- Atomicidad (RN-46): una transacción con las transferencias `cierre_de_mes` (mes = el cerrado,
  fecha = hoy), los ajustes, la evaluación de metas con la función central del Hito 7 y la marca de
  cerrado, o nada. Bloqueo de las bolsas involucradas en orden de id y nueva comprobación dentro de
  la transacción. La ficha se invalida si el estado cambió (error claro: repetir la vista previa).
  Concurrencia probada (un gasto del mes llegando mientras se cierra).
- Tablas en inglés `month_closures` (mes `YYYY-MM` clave primaria con CHECK, estado, `closed_at`
  TIMESTAMPTZ) y `closure_adjustments` (tipo `sobrante_no_destinado` | `sobregasto_no_cubierto`,
  bolsa, monto con signo: sobrante +, sobregasto −); claves foráneas ON DELETE RESTRICT;
  disparadores que impiden reabrir y borrar. Un mes sin fila cuenta como abierto; la migración no
  cierra nada (los datos de noviembre de 2026 quedan abiertos).
- Mes cerrado (RN-44, RN-48, RN-53): no admite gastos (mes calendario), ingresos ni extras (mes
  presupuestario), repartos de extras, transferencias (su mes) ni anulaciones de lo que pertenece a
  ese mes. Todas las tools de los Hitos 4 a 8 usan **una sola** función central. Errores claros, sin
  montos ni notas. El mes de una transferencia normal es el de hoy; las del cierre llevan el mes
  cerrado.
- Porcentajes (`set_allocation`, `create_bolsa`, `archive_bolsa`): solo meses abiertos.
- `get_summary` y `list_bolsas` incluyen `pending_closure` (RN-49). Las instrucciones del servidor
  explican el ritual de fin de mes (RN-51): `preview_month_close` → propuesta de Claude con una
  explicación breve basada en los datos → aprobación explícita → `close_month` → salario del mes
  siguiente (`preview_income`, `add_income`) → porcentajes si cambian. Se mantiene la nota de que
  `confirm=true` no garantiza que el modelo haya preguntado.
- `set_surplus_destination(pocket, destination_pocket | null)`: fija o quita el destino sugerido
  (6.5) reutilizando `pockets.surplus_target_pocket_id`; es solo un dato para la vista previa.
- Migración nueva (sin editar las anteriores) que conserva los datos, probada con una base temporal
  con datos del Hito 8; downgrade protegido. Invariante 11.4 extendido con cierres (200 conjuntos,
  semilla fija que se imprime al fallar). Idempotencia con `operation_id` en toda escritura.
  Registros y errores sin montos, notas ni nombres de metas; `sse_starlette` en INFO.
- Documentación: `docs/plan-tecnico.md` (esquema, tools, concepto → tabla), `HITOS.md` (Hito 9 y su
  "Terminado cuando"), README (corrección posterior); se quita "todos los meses cuentan como
  abiertos" de las tools anteriores y de `HITOS.md`.

**Precisiones del propietario en la pausa 1 (2026-11-11):** aprobados los PROPUESTO 1, 2, 4, 5,
10 y la ficha con instantánea (9); los demás, aprobados por defecto. Además:
(a) el estado "cerrado" lo decide **una sola** función central (mes ≤ último cerrado, o fila
cerrada) que usan todas las tools; (b) tomar de una acumulable para un déficit es opcional
(RN-52): si el propietario lo rechaza, lo restante queda como sobregasto no cubierto (RN-50) y el
mes se cierra; (c) una acumulable en negativo aparece en la vista previa como advertencia, con el
camino para corregirla (transferencia hacia ella); (d) las restricciones de `transfers` permiten un
mes distinto del de la fecha solo con el motivo `cierre_de_mes`, cambiando lo mínimo y con las
pruebas del Hito 8 pasando. Prueba de concurrencia que demuestre que no hay interbloqueos entre una
escritura del mes y `close_month`.

**[PROPUESTO] por el propietario en su pedido (se asumen; van al reporte):**

- P1. Qué mes se cierra: desde su último día (hoy en America/Costa_Rica ≥ último día del mes),
  siempre en orden; el primer mes cerrable es el más antiguo con movimientos; cerrar uno ya
  cerrado, futuro o fuera de orden se rechaza con un error claro y sin montos.
- P2. Extras pendientes del mes (por mes de su fecha, RN-09) bloquean el cierre; los fijos
  pendientes solo avisan.
- P3. Tablas, CHECK, claves foráneas y disparadores descritos arriba.
- P4. Si el mes actual ya está cerrado (cierre hecho el último día), `create_bolsa` y
  `archive_bolsa` aplican solo a los meses siguientes y lo dicen en la vista previa.
- P5. No hay tool para reabrir ni borrar cierres; una corrección posterior es una transferencia de
  ajuste o un movimiento nuevo en un mes abierto (README).

**[PROPUESTO] por Claude (huecos que el pedido no cubre; para que el propietario confirme):**

1. **Orden estricto por meses calendario consecutivos.** Entre el primer mes cerrable y el que se
   quiere cerrar, también los meses sin movimientos deben cerrarse (un cierre trivial, sin
   transferencias ni ajustes). Si no, un gasto con fecha pasada podría caer después en un mes vacío
   ya "saltado" y quedaría pendiente detrás de uno cerrado. Por eso `pending_closure` lista todos los
   meses terminados y no cerrados desde el primer mes cerrable, cada uno con `has_movements`.
2. **Meses anteriores a un mes cerrado.** Un mes sin fila cuenta como abierto, **salvo** que sea
   anterior al último mes cerrado: escribir ahí se rechaza ("anterior a un mes cerrado"), porque
   rompería el orden (por ejemplo, un gasto con fecha de octubre después de cerrar noviembre). La
   función central decide "cerrado" como: tiene fila `cerrado` o es anterior al último cerrado.
3. **"Mes con movimientos":** tiene al menos un ingreso (de cualquier tipo, incluido el saldo inicial
   y los anulados o pendientes) con ese mes presupuestario, un gasto (incluidos anulados) con ese mes
   calendario o una transferencia con ese mes.
4. **Déficit y sobrante solo en bolsas de consumo** (RN-11, 11.1): sobrante = disponible del mes > 0;
   déficit = disponible < 0. Una acumulable en negativo no es un déficit del mes (conserva su saldo,
   RN-12): se muestra como dato y no se resuelve en el cierre.
5. **Orden fijo en la validación (10.1, RN-52):** mientras quede un déficit sin cubrir, o si alguna
   cobertura sale de una acumulable, **todo** el sobrante de las bolsas de consumo activas debe ir a
   coberturas (no a destinos ni a "no destinado"). Así nunca se envía un sobrante a ahorro dejando
   un déficit que ese sobrante podía cubrir. Una cobertura desde acumulable exige saldo positivo y,
   en la vista previa, se marca `from_balance: true` con el efecto en su meta (RN-58).
6. **Coberturas:** `to_pocket` es una bolsa de consumo activa con déficit; lo que recibe no supera
   su déficit (cubrir de más sería un destino hacia consumo, que 10.2 no permite). `from_pocket` es
   una de consumo con sobrante o una acumulable activa. **Destinos:** `from_pocket` de consumo con
   sobrante; `to_pocket` acumulable activa o `null`. Un par (origen, destino) repetido se rechaza.
7. **Bolsas archivadas con cifras en el mes** (posible si se archivó con disponible cero en el mes
   actual pero tenía sobrante en un mes anterior aún abierto): aparecen en la vista previa marcadas
   como archivadas, no envían ni reciben, y su sobrante o déficit pasa a la tabla de ajustes.
8. **Ajustes:** una fila por bolsa y tipo (`UNIQUE(month, pocket_id, kind)`); el `null` explícito y
   lo sobrante sin asignar se suman en `sobrante_no_destinado`. Tras el cierre, el disponible del mes
   cerrado de cada bolsa de consumo es exactamente la suma de sus ajustes (es lo que hace cuadrar
   11.4 con "meses abiertos").
9. **Ficha (`preview_token`):** SHA-256 del mes, la propuesta normalizada y una instantánea del
   estado: cifras de 11.1 del mes de cada bolsa, saldos de las acumulables, metas activas y extras
   pendientes del mes. Dentro de la transacción se recalcula; si difiere, error "el estado cambió,
   repite la vista previa" (sin montos).
10. **Guardia del mes contra la concurrencia:** cada escritura que toca un mes toma un bloqueo
    consultivo compartido de ese mes (`pg_advisory_xact_lock_shared`) antes de comprobar que está
    abierto; `close_month` toma el exclusivo y después bloquea las bolsas involucradas con
    `FOR UPDATE` en orden de id (el orden "mes y luego bolsas" en todas las rutas evita
    interbloqueos). Un gasto que llega mientras se cierra espera y luego se rechaza por mes cerrado;
    si entró antes, el cierre ve el cambio y pide repetir la vista previa.
11. **Transferencias del cierre:** motivo `cierre_de_mes`, sin nota, fecha hoy, mes el cerrado; la
    respuesta lista sus `T-n`. `transfer_between_bolsas` sigue rechazando `cierre_de_mes`.
12. **Metas:** se evalúan en la transacción del cierre con `_settle_goals` y fecha de hoy (RN-24).
13. **Mes por defecto:** `preview_month_close` sin `month` usa el más antiguo cerrable; si no hay
    ninguno, responde sin error con `closable: false` y desde qué fecha podrá cerrarse el siguiente.
    `close_month` exige `month` explícito.
14. **Fijos pendientes como aviso:** cantidad, referencias `F-n` y total en colones (los de USD
    aparte y sin convertir), como `list_pending_recurring`. Los extras pendientes bloquean con un
    error que da sus referencias `I-n` (sin montos) y pide `confirm_allocation` o
    `void_transaction`.
15. **Mes cerrado en las consultas:** `get_bolsa_status` y `get_summary` de un mes cerrado muestran
    las mismas cifras más `month_closed: true` y los ajustes de cierre (RN-50: "aparece en las
    estadísticas"). `list_bolsas` del mes actual cerrado lo indica igual.
16. **Archivar con el mes actual cerrado (P4):** la comprobación de saldo cero (RN-18) de una bolsa
    de consumo usa el primer mes abierto, y los porcentajes se reescriben desde ese mes. Al archivar
    una acumulable, se quita como destino sugerido de las bolsas que la tenían (misma transacción).
    `create_bolsa` con "aplicar en el mes actual" y el actual cerrado aplica desde el siguiente.
17. **`set_surplus_destination`:** exige `operation_id` (escritura); sin vista previa porque no mueve
    dinero; la bolsa debe ser de consumo activa y el destino acumulable activa o `null`.
18. **"Datos" para el downgrade de la migración nueva:** cualquier fila en `month_closures` o
    `closure_adjustments`.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Ver el cierre (Priority: P1)

El último día del mes, el propietario pide cerrar. Claude llama `preview_month_close`: ve el
sobrante o déficit de cada bolsa de consumo, el saldo y la meta de cada acumulable, los fijos
pendientes y el destino sugerido. Claude propone coberturas y destinos con una explicación breve.

**Independent Test**: salario y gastos sintéticos en un mes ya terminado; la vista previa sin
propuesta no guarda nada y devuelve las cifras de 11.1 y 11.2.

**Acceptance Scenarios**:

1. **Given** Necesidades con sobrante 20 000 y Gustos con déficit 5 000, **When** se pide la vista
   previa, **Then** no se guarda nada y muestra ambos, el aviso de que el mes no admitirá más
   movimientos y ningún `preview_token`.
2. **Given** un extra pendiente con fecha del mes, **When** se pide la vista previa, **Then** lo
   marca como bloqueo; **When** se intenta cerrar, **Then** se rechaza pidiendo repartirlo o anularlo.
3. **Given** hoy anterior al último día del mes, **When** se pide cerrarlo, **Then** se rechaza sin
   montos.

### User Story 2 - Cerrar con propuesta (Priority: P1)

El propietario aprueba: el sobrante de Necesidades cubre Gustos y el resto va a Ahorro. Al
confirmar con la ficha, todo se guarda en una transacción.

**Acceptance Scenarios**:

1. **Given** la propuesta aprobada, **When** se confirma, **Then** hay dos transferencias
   `cierre_de_mes` con el mes cerrado, Gustos queda en 0, Ahorro sube y el mes queda `cerrado`.
2. **Given** un sobrante que no se asigna entero, **When** se cierra, **Then** el resto queda como
   `sobrante_no_destinado` visible en la respuesta y el invariante cuadra.
3. **Given** un déficit sin sobrantes de consumo, **When** se cubre desde Ahorro, **Then** la vista
   previa lo marca como cobertura desde saldo con el efecto en la meta (RN-52, RN-58); sin cubrirlo,
   queda `sobregasto_no_cubierto` y el mes se cierra igual (RN-50).
4. **Given** la vista previa hecha y un gasto nuevo del mes antes de confirmar, **When** se confirma,
   **Then** se rechaza pidiendo repetir la vista previa.
5. **Given** un fallo a mitad del cierre, **Then** no queda ninguna transferencia, ajuste ni marca.

### User Story 3 - Mes cerrado (Priority: P1)

Lo cerrado no se modifica (RN-44, RN-48, RN-53); las bolsas de consumo del mes siguiente empiezan en
cero más lo que reciban (RN-11).

**Acceptance Scenarios**:

1. **Given** noviembre cerrado, **When** se registra un gasto, ingreso, extra, reparto,
   transferencia o anulación de noviembre, **Then** se rechaza con un error claro y sin montos.
2. **Given** noviembre cerrado, **Then** las bolsas de consumo de diciembre muestran 0 hasta que
   reciban su reparto.
3. **Given** un intento de UPDATE que saque un mes de `cerrado`, o un DELETE en `month_closures` o
   `closure_adjustments`, **Then** el disparador lo rechaza.

### User Story 4 - Alerta y ritual (Priority: P2)

`get_summary` y `list_bolsas` avisan de los meses con cierre pendiente (RN-49); las instrucciones del
servidor guían el ritual de fin de mes (RN-51). `set_surplus_destination` guarda el destino sugerido
(6.5).

**Acceptance Scenarios**:

1. **Given** octubre terminado con movimientos y sin cerrar, **Then** `pending_closure` lo incluye.
2. **Given** Gustos con destino sugerido Viaje, **Then** la vista previa del cierre lo muestra; un
   destino que no es acumulable activa se rechaza.

### Edge Cases

- Mes futuro, ya cerrado, fuera de orden, anterior al último cerrado; mes vacío en medio.
- Montos 0, negativos, decimales o texto; bolsa inexistente o archivada; par repetido.
- Destino que no es acumulable activa; lo que sale de una bolsa supera su sobrante o saldo.
- Cobertura desde acumulable con sobrante de consumo sin usar; destino con déficit sin cubrir.
- `confirm=true` sin ficha, con otra ficha o con ficha vencida; misma clave con otro contenido.
- Cierre el último día: un gasto de hoy después del cierre se rechaza; el salario de hoy (mes
  siguiente) se acepta.
- Mes actual cerrado: `set_allocation` del mes rechazado; `create_bolsa`/`archive_bolsa` desde el
  siguiente.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: `preview_month_close` no guarda nada; sin propuesta devuelve las cifras del mes (11.1,
  11.2), metas activas, bloqueos, avisos y destinos sugeridos; con propuesta valida, devuelve el
  resultado completo (incluidos ajustes) y la ficha; siempre advierte que el mes quedará cerrado.
- **FR-002**: reglas de qué mes se cierra (P1, PROPUESTO 1 a 3) y bloqueo por extras pendientes
  (P2).
- **FR-003**: validaciones de coberturas y destinos (RN-47, RN-52, 10.1, 10.2; PROPUESTO 4 a 7).
- **FR-004**: `close_month` atómico (RN-46) con transferencias `cierre_de_mes`, ajustes (RN-50),
  metas evaluadas y marca de cerrado; exige `confirm=true`, ficha vigente y `operation_id`.
- **FR-005**: una sola función central de "mes abierto" usada por todas las escrituras de los Hitos
  4 a 8 (RN-44, RN-48, RN-53) y por los cambios de porcentajes; errores sin montos ni notas.
- **FR-006**: tablas `month_closures` y `closure_adjustments` con CHECK, FK RESTRICT y disparadores
  contra reabrir y borrar; migración que conserva datos y downgrade protegido.
- **FR-007**: `pending_closure` en `get_summary` y `list_bolsas` (RN-49); instrucciones del ritual
  (RN-51).
- **FR-008**: `set_surplus_destination` (6.5) con `operation_id`.
- **FR-009**: invariante 11.4 con cierres (200 conjuntos, semilla impresa al fallar); pruebas de que
  cerrar no cambia la suma total y de que el mes siguiente empieza en cero.
- **FR-010**: concurrencia probada contra Postgres (gasto del mes durante el cierre).
- **FR-011**: registros sin montos, notas ni nombres de metas.

### Key Entities

- **Cierre de mes**: mes `YYYY-MM`, estado `cerrado`, instante del cierre.
- **Ajuste de cierre**: mes, bolsa, tipo (`sobrante_no_destinado` +, `sobregasto_no_cubierto` −) y
  monto con signo.

## Success Criteria *(mandatory)*

- **SC-001**: un mes con un déficit y un sobrante se cierra y el sobrante cubre el déficit.
- **SC-002**: un sobrante enviado a una acumulable aparece en su saldo.
- **SC-003**: un sobrante sin destino queda "no destinado" y el invariante cuadra.
- **SC-004**: un fallo a mitad del cierre no deja nada a medias.
- **SC-005**: un mes cerrado rechaza gastos, ingresos, extras, repartos, transferencias y
  anulaciones.
- **SC-006**: las bolsas de consumo del mes siguiente empiezan en cero.
- **SC-007**: Claude no cierra sin mostrar la vista previa y esperar la aprobación explícita.

## Assumptions

- Datos siempre sintéticos en pruebas; nada se ejecuta contra la base del homelab ni se cierra un
  mes real desde el desarrollo.
- El dashboard (alerta visual de cierre pendiente) es del Hito 10; aquí la alerta viaja en las tools.
