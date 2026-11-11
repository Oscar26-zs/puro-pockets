# Research: Extras y gastos fijos

## R1. Instrucciones del servidor en el SDK fijado

- **Decisión:** `MCPServer("puro-pockets", instructions=SERVER_INSTRUCTIONS)`.
- **Verificación:** en `mcp==2.3.0`, `MCPServer.__init__` acepta `instructions: str | None` y lo pasa
  al servidor de bajo nivel, que lo devuelve en `InitializeResult.instructions` (comprobado con
  `inspect.signature` y en `test_extras_tools.py::test_instrucciones_del_servidor_en_initialize`, y en
  la verificación manual contra el contenedor).
- **Alternativas:** solo descripciones de tools (insuficiente para el flujo de varios pasos); un
  `prompt` MCP (el cliente no lo carga solo).

## R2. Mitigar que `confirm=true` no prueba la aprobación

- **Decisión:** ficha de vista previa (`preview_token`) determinista: SHA-256 del extra, su monto y
  el reparto (bolsa:porcentaje). `confirm=true` la exige; además instrucciones, descripciones,
  permiso por tool en el cliente y corrección por anulación.
- **Alternativas:** guardar vistas previas en la base con vencimiento (más estado y limpieza);
  una clave secreta por proceso (se invalida al reiniciar y con varias réplicas). La ficha determinista
  basta: no es un secreto, solo obliga a pasar por la vista previa.

## R3. Historial del monto de una plantilla

- **Decisión:** tabla `recurring_expense_amounts (recurring_id, from_month, original_amount)`; el
  monto de un mes es la fila con el mayor `from_month` ≤ mes. Un cambio vale desde
  `max(mes siguiente, inicio)`; el mismo mes futuro se reemplaza (`ON CONFLICT DO UPDATE`).
- **Alternativas:** columna de monto en la plantilla (cambiaría los meses pasados); versión completa
  de la plantilla por mes (más de lo necesario).

## R4. Un solo pago vigente por plantilla y mes

- **Decisión:** índice único parcial `(recurring_id, month) WHERE recurring_id IS NOT NULL AND NOT
  voided`, más comprobación en el servicio para un mensaje claro. Anular el pago libera el índice.
- **Alternativas:** solo comprobación en el servicio (carrera entre dos llamadas simultáneas).

## R5. Repartir un extra una sola vez

- **Decisión:** `UPDATE incomes SET allocation_status = 'repartido' WHERE id = … AND
  allocation_status = 'pendiente' AND NOT voided` dentro de la transacción del reparto; 0 filas =
  ya repartido (o anulado). Disparador que impide volver a pendiente o repartir un anulado.

## R6. Generación de fijos

- **Decisión:** bajo demanda (`list_pending_recurring`), sin proceso programado (decisión del
  propietario; recomendación de `HITOS.md`).

## R7. Huella de idempotencia del pago de un fijo

- **Decisión:** sin plantilla, la huella de `add_expense` es idéntica a la del Hito 5 (no cambia para
  claves ya guardadas). Con plantilla se agrega `recurring` y el monto tal como llegó (puede faltar).

## R8. División del servicio

- **Decisión:** `LedgerCore` (almacén, reloj, idempotencia, pendientes) + `ExtrasMixin` +
  `RecurringMixin`; registros en `services/records.py` reexportados por `services/ledger.py`.
