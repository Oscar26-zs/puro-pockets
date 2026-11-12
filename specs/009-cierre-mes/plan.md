# Implementation Plan: Cierre de mes

**Branch**: `hito-9-cierre-mes` | **Date**: 2026-11-11 | **Spec**: [spec.md](spec.md)

## Summary

Cierre de mes atómico (RN-46 a RN-52, sección 10): vista previa con datos y propuesta validada,
transferencias `cierre_de_mes`, ajustes de cierre, metas evaluadas y marca de cerrado en una
transacción. Una sola función decide si un mes está cerrado y todas las escrituras la usan (RN-44,
RN-48, RN-53). Alerta de cierre pendiente (RN-49), ritual de fin de mes (RN-51) y destino de
sobrante sugerido (6.5).

## Technical Context

- Python 3.14 con uv; SQLAlchemy Core; psycopg síncrono vía `anyio.to_thread`; `mcp==2.3.0`.
- PostgreSQL 18; Alembic: migración nueva `0008_month_closures` (no se editan las anteriores).
- pytest: unitarias con el almacén en memoria (`tests/fakes.py`); integración en `pp_test_*`.

## Constitution Check

| Regla | Cumplimiento |
|---|---|
| Ningún dato real antes de autenticación | Hito 3 cerrado; pruebas con datos sintéticos; nada contra el homelab. |
| Lógica de negocio en capa propia | `domain/closures.py` (puro): qué mes es cerrable, si un mes está cerrado, validación y resultado del cierre. El almacén solo bloquea, lee e inserta. |
| Invariante 11.4 con prueba automática | `integrity_gap` con meses cerrados y ajustes; 200 conjuntos en memoria (semilla impresa) y 40 en Postgres con cierres. |
| Pruebas en el hito | Unitarias, integración, migración, concurrencia, disparadores, autenticación y registros, positivas y negativas. |
| Reglas citadas | RN-44, RN-46 a RN-53, RN-58; 6.5, 10.1, 10.2, 10.4, 11.1, 11.2, 11.4. RN-51 [DECIDIDO] en 1.0.5. |
| Sin reabrir | No hay tool ni camino de código que reabra o borre; disparadores en la base. |

## Decisiones técnicas

1. **Función central del mes cerrado (2a).** `domain/closures.py::is_closed(month, closed)`:
   cerrado si tiene fila `cerrado` o es anterior o igual al último mes cerrado. `check_open(month,
   closed)` lanza `MonthClosed` (mensaje sin montos: "El mes 2026-11 está cerrado: …"). Es la única
   que decide; la usan:
   - los servicios, para fallar temprano en vistas previas (`LedgerCore._ensure_open`,
     `BudgetService._ensure_open`), y
   - el almacén, dentro de cada transacción de escritura (`SqlBudgetStore._guard_months`), con lo
     leído en ese momento.
2. **Guardia contra la concurrencia.** `_guard_months(conn, months)` toma primero
   `pg_advisory_xact_lock_shared(NS, 0)` (bloqueo consultivo global de cierres) y luego lee
   `month_closures` y llama a `check_open`. `close_month` toma `pg_advisory_xact_lock(NS, 0)`
   exclusivo y después bloquea las bolsas involucradas con `FOR UPDATE` en orden de id. Un solo
   bloqueo global (y no uno por mes) porque "anterior al último cerrado = cerrado" hace que cerrar
   M afecte a todos los meses ≤ M; las escrituras entre sí siguen en paralelo (bloqueo compartido).
   Orden en todas las rutas: guardia → bolsas → filas, así no hay interbloqueos (probado).
3. **Meses que toca cada escritura** (sin cambiar firmas del almacén): ingreso → `budget_month`;
   saldo inicial → su mes; gasto → `month`; reparto de extra y anulación → el mes de la fila, leído
   dentro de la transacción; transferencia → `month`; porcentajes → el mes escrito; crear o archivar
   bolsa → los meses cuyos porcentajes se reescriben.
4. **Cerrable (P1, PROPUESTO 1 a 3).** `oldest` = mes más antiguo con movimientos (ingresos de
   cualquier tipo o estado por `budget_month`, gastos incluidos anulados por `month`,
   transferencias). Primer cerrable = el siguiente al último cerrado, o `oldest` si no hay cierres.
   `check_closable(month, today, oldest, closed)`: ya cerrado; futuro o `today < último día`; no es
   el primero cerrable (fuera de orden, con el mes que toca); sin movimientos y sin cierres previos.
   `pending_closure(today, oldest, closed)`: del primero cerrable al último terminado (o en su último
   día), con `has_movements`.
5. **Cálculo del cierre (puro).** `plan_close(month, pockets, figures, covers, destinations,
   goals)`: consumo activa con disponible > 0 = sobrante, < 0 = déficit; archivadas con cifras
   distintas de 0 se listan y van enteras a ajustes; acumulables con saldo (negativo → advertencia
   con el camino: transferencia hacia ella, 2c). Validaciones de la spec (PROPUESTO 5 a 7):
   - montos enteros JSON positivos; pares repetidos; bolsas activas y existentes;
   - cobertura: destino consumo con déficit, recibido ≤ déficit; origen consumo con sobrante o
     acumulable (saldo > 0);
   - destino: origen consumo con sobrante; `to_pocket` acumulable activa o `null`;
   - lo que sale de cada bolsa ≤ su sobrante (consumo) o saldo (acumulable) (RN-47);
   - orden 10.1: si queda déficit sin cubrir o hay cobertura desde acumulable, todo el sobrante de
     consumo debe ir a coberturas. Rechazar la cobertura desde acumulable es válido (RN-52 es
     opcional, 2b): lo no cubierto queda `sobregasto_no_cubierto` (RN-50).
   Resultado: transferencias a crear, ajustes por bolsa (`sobrante_no_destinado` = sobrante − salidas,
   incluido el `null` explícito; `sobregasto_no_cubierto` = −(déficit − recibido)), cifras antes y
   después por bolsa, efecto en metas (RN-58, con `goal_effect` del Hito 8) y avisos.
6. **Ficha.** SHA-256 de `close_month`, mes, propuesta normalizada (ids y montos ordenados) e
   instantánea: por bolsa (id, activa, comportamiento, asignado, recibidas, enviadas, gastado,
   disponible o saldo), metas activas (id, bolsa, objetivo, estado) y referencias de extras
   pendientes del mes. Dentro de la transacción, con el bloqueo exclusivo, se relee todo y se
   recalcula; si difiere: `ClosureStateChanged` ("El estado cambió desde la vista previa: repite
   `preview_month_close`"). También se revalida que el mes siga siendo cerrable y sin extras.
7. **Transacción del cierre** (`record_closure`): guardia exclusiva → `FOR UPDATE` de las bolsas
   involucradas (todas las de la propuesta y las que tienen cifras en el mes) → `verify(snapshot)` →
   INSERT `month_closures` (`cerrado`, `closed_at = now`) → INSERT transferencias (`cierre_de_mes`,
   fecha hoy, mes el cerrado, sin nota) → INSERT ajustes → `_settle_goals(conn, hoy)` → clave de
   operación. Para la prueba de "cierre interrumpido" el almacén admite un gancho de fallo en las
   pruebas (subclase), no en producción.
8. **Transferencias (2d).** CHECK nuevo `ck_transfers_month_date`:
   `reason = 'cierre_de_mes' OR month = to_char(transfer_date, 'YYYY-MM')`, y para
   `cierre_de_mes`, `month <= to_char(transfer_date, 'YYYY-MM')`. La migración comprueba antes que
   los datos existentes lo cumplen (todas las del Hito 8 tienen mes = mes de la fecha) y, si no,
   aborta con un mensaje claro. `transfer_between_bolsas` sigue rechazando `cierre_de_mes`.
9. **Mes actual cerrado (P4, PROPUESTO 16).** `set_allocation` del mes cerrado: `MonthClosed`.
   `create_bolsa` con mes actual cerrado aplica desde el siguiente y la vista previa lo dice;
   `archive_bolsa` reescribe desde el primer mes abierto y su RN-18 de consumo usa ese mes. Archivar
   una acumulable quita `surplus_target_pocket_id` de las bolsas que la tenían.
10. **Consultas.** `get_summary(mes)` y `get_bolsa_status(…, mes)`: `month_closed` y ajustes del
    mes (por bolsa). `get_summary` y `list_bolsas`: `pending_closure` (lista de `{month,
    has_movements}`). Instrucciones del servidor con el ritual (RN-51).
11. **Invariante.** `integrity_gap(…, closed=…, adjustments=…)`: suma disponibles de consumo solo
    de meses abiertos (con `is_closed`) más Σ ajustes. Generador sintético con cierres (déficits
    cubiertos o no, sobrantes destinados o no, coberturas desde acumulable).
12. **Registros.** `Cierre registrado: mes=… transferencias=n ajustes=n metas_afectadas=n`; errores
    sin montos, notas ni nombres de metas.

## Delta de esquema (`0008_month_closures`)

```sql
CREATE TABLE month_closures (
  month CHAR(7) PRIMARY KEY CHECK (month ~ '^[0-9]{4}-(0[1-9]|1[0-2])$'),
  status TEXT NOT NULL DEFAULT 'cerrado' CHECK (status IN ('abierto','cerrado')),
  closed_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CHECK ((status = 'cerrado') = (closed_at IS NOT NULL))
);
CREATE TABLE closure_adjustments (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  month CHAR(7) NOT NULL REFERENCES month_closures(month) ON DELETE RESTRICT,
  pocket_id BIGINT NOT NULL REFERENCES pockets(id) ON DELETE RESTRICT,
  kind TEXT NOT NULL CHECK (kind IN ('sobrante_no_destinado','sobregasto_no_cubierto')),
  amount BIGINT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CHECK ((kind = 'sobrante_no_destinado' AND amount > 0)
      OR (kind = 'sobregasto_no_cubierto' AND amount < 0)),
  UNIQUE (month, pocket_id, kind)
);
ALTER TABLE transfers ADD CONSTRAINT ck_transfers_month_date CHECK (
  (reason <> 'cierre_de_mes' AND month = to_char(transfer_date, 'YYYY-MM'))
  OR (reason = 'cierre_de_mes' AND month <= to_char(transfer_date, 'YYYY-MM')));
-- Disparadores: trg_month_closures_guard (UPDATE que saque un mes de 'cerrado' o cambie su mes o
-- closed_at; DELETE) y trg_closure_adjustments_immutable (UPDATE y DELETE).
```

Downgrade protegido: aborta si hay filas en `month_closures` o `closure_adjustments`, salvo con
`ALLOW_DESTRUCTIVE_DOWNGRADE=true`. `pockets.surplus_target_pocket_id` ya existe (0003): se
reutiliza.

## Contrato de tools

Todas exigen OAuth vigente. Errores como `ToolError` en español, sin montos ni notas.

- **`preview_month_close(month?, covers?, destinations?)`** → `MonthClosePreview`: `month`,
  `closable`, `blocked_by` (extras pendientes `I-n`), `warnings` (siempre: el mes no admitirá más
  movimientos, ni de hoy; fijos pendientes; acumulables en negativo; coberturas desde saldo),
  `consumption` [`pocket`, `active`, `adjusted_budget`, `spent`, `available`, `situation`
  (`sobrante` | `deficit` | `cero`), `suggested_destination`], `accumulable` [`pocket`, `balance`,
  `goal` (`reference`, `percent`, `missing`) | null], `pending_recurring` (cantidad, `F-n`, total
  CRC, USD aparte). Con propuesta además: `covers`/`destinations` normalizados (con `from_balance`),
  `result` por bolsa (antes/después), `goal_effects` (RN-58), `unassigned_surplus`
  (`sobrante_no_destinado` por bolsa y total), `uncovered_overspend` (por bolsa y total),
  `transfers_to_create`, `preview_token`. Sin `month`: el primero cerrable; si no hay, `closable:
  false` y `next_closable_on`.
- **`close_month(month, covers?, destinations?, confirm=false, preview_token?, operation_id?)`** →
  sin `confirm` la misma vista previa; con `confirm=true` exige `operation_id` y la ficha →
  `MonthCloseResult`: `saved`, `month`, `closed_at`, `transfers` (`T-n`, origen, destino, monto),
  `adjustments`, `goal_effects`, `goals_achieved` (`M-n`), `next_steps` (ritual RN-51).
- **`set_surplus_destination(pocket, destination_pocket | null, operation_id)`** → `pocket`,
  `suggested_destination`. Consumo activa; destino acumulable activa o `null`.
- Cambian: `get_summary` y `list_bolsas` (+`pending_closure`; `get_summary` +`month_closed`,
  `closure_adjustments`), `get_bolsa_status` (+`month_closed`, `closure_adjustment`), y todas las
  escrituras de los Hitos 4 a 8 (rechazo por mes cerrado).

## Project Structure

```
src/puro_pockets/
  domain/closures.py        # is_closed/check_open, cerrable, pending_closure, plan_close, ficha
  domain/errors.py          # MonthClosed, MonthNotClosable, ExtrasPendingBlock, ClosureStateChanged
  domain/balances.py        # integrity_gap con meses cerrados y ajustes
  services/closing.py       # ClosingMixin: preview_month_close, close_month, set_surplus_destination
  services/ledger_core.py   # _ensure_open, _closures
  services/{ledger,extras,flex,transfers,budget}.py  # comprobación temprana con _ensure_open
  db/budget_store.py        # tablas, closure_state, _guard_months, guardia en sus escrituras
  db/ledger_store.py        # guardia en cada escritura, record_closure, set_surplus_target
  mcp/closing_tools.py      # las tres tools; instrucciones del servidor (ritual RN-51)
migrations/versions/0008_month_closures.py
```

## Autorrevisión (spec y plan contra la constitución)

- RN-44/48/53: una función central y la guardia en la transacción; sin tool de reapertura ni
  borrado; disparadores impiden reabrir y borrar. ✓
- RN-46: todo en una transacción; prueba de fallo a mitad. ✓ RN-47: salidas ≤ sobrante/saldo. ✓
- RN-49: `pending_closure`. ✓ RN-50: ajustes con signo, visibles en vista previa, respuesta y
  `get_summary`. ✓ RN-51 [DECIDIDO]: instrucciones del servidor. ✓ RN-52 + RN-58: cobertura desde
  acumulable opcional, solo con sobrantes de consumo usados, con efecto en la meta. ✓
- 10.2: destinos solo acumulable activa o no destinado; corrección: cubrir de más una bolsa de
  consumo se rechaza (sería un destino hacia consumo). ✓ 6.5: el destino sugerido siempre es
  acumulable (validado al guardar y filtrado si luego se archiva). ✓
- 11.4: el lado derecho usa "meses abiertos" = `not is_closed`, coherente con la regla 2a. ✓
- Principio 3.1: la vista previa sin propuesta no recomienda; el destino sugerido es un dato del
  propietario. ✓ Principio 3.2: vista previa sin guardar. ✓
- Reglas no negociables: datos sintéticos; dominio puro (prueba de arquitectura); invariante;
  pruebas del hito. ✓
- [PROPUESTO] revisados: ninguno contradice la constitución ni permite deshacer un cierre. El
  bloqueo global (decisión 2) refina el "bloqueo del mes" aprobado sin cambiar su efecto.
