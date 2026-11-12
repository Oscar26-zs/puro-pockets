# Research: Transferencias entre bolsas

## Una sola función de cálculo

- **Decisión:** `domain.balances.pocket_figures(pocket, month, entries, expenses, transfers)` devuelve
  `PocketFigures` (original, recibidas, enviadas, ajustado, gastado, disponible o saldo, % sobre
  ajustado y sobre original). `pocket_balance`, `integrity_gap`, `balance_function` (metas) y
  `net_monthly_change` (RN-28) aceptan las transferencias. Los servicios leen todo con
  `LedgerCore._data()` → `LedgerData.figures()`.
- **Razón:** el propietario pidió no duplicar cálculos; antes había tres copias del 11.1/11.2
  (`_pocket_line`, el contexto del extra y `pocket_balance`).
- **Alternativas:** agregar los campos en cada consulta (descartado: tres sitios que podían
  divergir).

## Concurrencia

- **Decisión:** en `record_transfer`, `SELECT … FOR UPDATE` de las dos filas de `pockets` en orden de
  id; después se leen sus repartos, gastos y transferencias y el servicio vuelve a validar con
  `check_available` antes del INSERT. `archive_pocket` bloquea su bolsa y vuelve a comprobar el saldo
  cero (RN-18).
- **Razón:** con READ COMMITTED, la segunda transacción espera el bloqueo y, al obtenerlo, sus
  consultas ven lo confirmado por la primera. El orden por id evita interbloqueos entre
  transferencias cruzadas.
- **Prueba:** un almacén de prueba se detiene 0,6 s dentro de la transacción; tres transferencias de
  200 000 desde 500 000 → pasan dos. Quitando el bloqueo, la prueba falla (comprobado).
- **Alternativas:** SERIALIZABLE con reintentos (más complejo); bloqueo consultivo global (bloquea
  operaciones que no compiten).

## Ficha de vista previa

- **Decisión:** SHA-256 de origen, destino (ids), monto, motivo, nota y fecha. No incluye saldos.
- **Razón:** misma mitigación que los Hitos 6 y 7 (no se confirma algo que nunca se mostró); lo
  disponible se valida de nuevo al guardar.

## Migración `0007_transfers`

- Tabla `transfers` (`transfer_date`, `month`, `from_pocket_id`, `to_pocket_id`, `amount`, `reason`,
  `note`, `created_at`); CHECK de monto, origen ≠ destino, motivo (cuatro valores), mes y nota ≤ 140;
  FK ON DELETE RESTRICT; índices por mes, origen+mes y destino+mes; disparador
  `trg_transfers_immutable` (BEFORE UPDATE OR DELETE). Downgrade: se niega si hay filas salvo con
  `ALLOW_DESTRUCTIVE_DOWNGRADE=true`.

## Correcciones en capas inferiores (regla de precedencia)

- `HITOS.md`: la vista general y el entregable del Hito 8 citaban "RN-39 a 45"; RN-45 está derogada
  → "RN-39 a 44 y RN-58; completa RN-18".
- `docs/plan-tecnico.md`: el borrador de `transfers` estaba en español (`fecha`, `mes`,
  `from_bolsa_id`, `monto`, `motivo`, `nota`) → nombres en inglés (convención del Hito 1).
- Código del Hito 7: el error de `archive_bolsa` decía "la transferencia llega en el Hito 8"; ahora
  indica las tools. `PreviewRequired` hablaba solo de "porcentajes". `get_bolsa_status` decía
  "transferencias: 0 hasta el Hito 8".
- No se encontraron contradicciones en la constitución.
