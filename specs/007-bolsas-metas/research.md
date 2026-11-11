# Research: Bolsas flexibles y metas

## R1. Reajuste como función pura

- **Decisión:** `rebalance_add` y `rebalance_remove` sobre pares (clave, %) en orden de creación.
  Proporcional: `pct × objetivo // total` y la última absorbe el residuo (≥ 0).
- **Prueba de propiedades:** 3 000 casos aleatorios con semilla fija (`20261111`), impresa al fallar;
  sin agregar `hypothesis` como dependencia.

## R2. Archivar sin dejar meses repartiendo a una bolsa inactiva

- **Decisión:** el archivado es inmediato y reescribe el mes actual (propio o heredado, RN-03) y cada
  mes futuro con porcentajes propios; los demás meses futuros heredan de ellos. `month` futuro se
  rechaza: el mes actual seguiría repartiendo a la bolsa archivada.
- **Alternativa descartada:** archivar programado para un mes futuro (requiere estado y tarea).

## R3. Evaluación de `lograda`

- **Decisión:** una sola regla pura (`domain.goals.reached`) y un punto de llamada por almacén
  (`_settle_goals`), dentro de la transacción de salario, saldo inicial, reparto de extra, anulación
  de gasto, creación y cambio de meta. El saldo se calcula con `accumulated_balance` (11.2) sobre las
  filas leídas en la misma conexión.
- **Alternativa descartada:** disparador SQL que recalcule saldos (duplicaría la fórmula de 11.2).

## R4. Meta archivada

- **Decisión:** columna `archived_at`; el estado de RN-24 no cambia (agregar un estado sería una
  enmienda). El índice único parcial excluye las archivadas.

## R5. Nombres de bolsa únicos

- **Decisión:** se reutiliza `ux_pockets_name_ci` (Hito 4), que incluye las archivadas: un nombre
  archivado no se reutiliza (evita confusión en el historial).

## R6. Ficha de vista previa

- **Decisión:** SHA-256 del contenido de la vista previa (nombre, comportamiento, grupo y meses con
  sus porcentajes nuevos), como en el Hito 6.
