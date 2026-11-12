# Verificación del Hito 9: Cierre de mes

**Fecha:** 2026-11-11 · **Rama:** `hito-9-cierre-mes` (desde `origin/main` d2c6af9) · **Equipo:**
Windows 11, Docker Desktop

**Leyenda:** ✅ Claude = verificado por Claude en esta sesión · 👤 Propietario = te toca a ti.
Todos los datos usados por Claude son **sintéticos**. Nada se ejecutó contra la base del homelab y
no se cerró ningún mes en ninguna base real.

## 1. Pruebas automáticas ✅ Claude

`uv run ruff check .` y `ruff format --check .`: limpios. `uv run pytest`: **608 passed** (533
unitarias + 75 de integración; el Hito 8 cerró con 537). Las de integración corren en bases
temporales `pp_test_*` que se crean y se borran.

| Criterio | Positivas (debe funcionar) | Negativas (debe rechazar) | Pruebas |
|---|---|---|---|
| Regla única de mes cerrado (2a) | mes con fila cerrado; anterior al último cerrado = cerrado; sin fila y posterior = abierto | — | `test_closures_domain` |
| Qué mes se cierra (P1) | desde el último día; en orden; meses vacíos en medio en `pending_closure` con `has_movements=false`; mes por defecto = el más antiguo cerrable | **antes del último día**; **mes futuro**; **fuera de orden**; **ya cerrado**; anterior al último cerrado; anterior al primero con movimientos; sin movimientos | `test_closures_domain`, `test_closing_service` |
| Extras y fijos (P2) | fijos pendientes como aviso (`F-n`) | **extra pendiente bloquea** (error que pide `confirm_allocation` o `void_transaction`); tras anularlo, cierra | `test_closing_service` |
| Vista previa (3.2) | sin propuesta: datos y sin ficha, no guarda nada; con propuesta: cómo queda cada bolsa, metas (RN-58), no destinado, no cubierto, transferencias y ficha; aviso de que el mes no admitirá más movimientos; destino sugerido | — | `test_closing_service`, `test_closing_tools` |
| Validación (10.1, 10.2, RN-47, RN-52) | el sobrante cubre el déficit y el resto va a ahorro; `null` explícito y resto → no destinado; cobertura desde acumulable tras usar los sobrantes, con aviso de meta; rechazarla deja sobregasto no cubierto (2b) | **destino que no es acumulable activa**; **sobrante superior al disponible**; **cobertura desde acumulable con sobrante de consumo sin usar**; destino con déficit sin cubrir; cubrir de más; acumulable sin saldo; par repetido; monto 0, decimal o texto; bolsa archivada o inexistente | `test_closures_domain`, `test_closing_service` |
| Advertencias (2c) | acumulable en negativo: aviso con el camino (transferencia hacia ella); archivada con cifras: a ajustes | sin montos en los avisos | `test_closures_domain` |
| Confirmar y ficha | cierre con la ficha; reintento con la misma clave no duplica | **confirm sin vista previa** (sin ficha u otra propuesta); **ficha vencida porque cambió el estado** (gasto nuevo; también dentro de la transacción); **mismo `operation_id` con distinto contenido** | `test_closing_service`, `test_closing_sql_store` |
| Atomicidad (RN-46) | transferencias `cierre_de_mes` (mes cerrado, fecha hoy), ajustes, marca y clave en una transacción | **cierre interrumpido a mitad: no queda nada** (ni marca, ni transferencias, ni ajustes, ni clave) y después cierra bien | `test_closing_sql_store` |
| Concurrencia (punto 4) | gasto, transferencia y cierre simultáneos terminan sin interbloqueo ni `DeadlockDetected`, bajo un límite de tiempo | **gasto del mes mientras se cierra**: espera y se rechaza por mes cerrado; **cierre mientras entra un gasto**: espera y pide repetir la vista previa. Quitando la guardia, la prueba falla (comprobado y restaurado) | `test_closing_sql_store` |
| Mes cerrado (RN-44, 48, 53) | el salario del último día (mes siguiente) se acepta | **gasto, ingreso, extra, reparto, transferencia y anulación contra un mes cerrado**, también en meses anteriores; `set_allocation` y saldo inicial del mes cerrado; la guardia del almacén rechaza aunque se salte el servicio | `test_closing_service`, `test_closing_sql_store`, `test_closing_tools` |
| Mes actual cerrado (P4) | `create_bolsa` y `archive_bolsa` aplican desde el mes siguiente y lo dicen; archivar una acumulable la quita como destino sugerido | — | `test_closing_service` |
| Mes siguiente en cero | las bolsas de consumo de noviembre empiezan en 0 y luego suman lo que reciben | — | `test_closing_service`, `test_closing_sql_store` |
| Alerta y ritual (RN-49, RN-51) | `pending_closure` en `get_summary` y `list_bolsas`; desaparece al cerrar; instrucciones del servidor con el ritual y la nota de `confirm=true` | — | `test_closing_service`, `test_closing_tools` |
| Destino sugerido (6.5) | fijar, mostrar en la vista previa y quitar | destino de consumo; origen acumulable | `test_closing_service` |
| Metas | el cierre evalúa las metas (lograda con el destino) | — | `test_closing_service` |
| Disparadores | — | **reabrir (UPDATE de estado, mes o instante) o borrar en `month_closures`; editar o borrar `closure_adjustments`, directamente en la base** | `test_migrations`, `test_closing_sql_store` |
| Transferencias (2d) | `cierre_de_mes` con mes anterior a la fecha; las pruebas del Hito 8 siguen pasando | `ajuste` con mes distinto de la fecha; `cierre_de_mes` con mes posterior a la fecha | `test_migrations` |
| Invariante 11.4 | **200 conjuntos en memoria** (semilla impresa al fallar) y 40 en Postgres con ingresos, gastos, anulaciones, metas, transferencias y cierres (más de 200 meses cerrados, coberturas desde acumulable, déficits no cubiertos, sobrantes destinados y no destinados): **cerrar no cambia la suma total**; disponible de cada mes cerrado = suma de sus ajustes | escrituras rechazadas en meses cerrados dentro de los conjuntos | `test_invariant`, `test_invariant_sql` |
| Migración `0008` | **conserva los datos del Hito 8** y no cierra nada; subir, bajar con la variable y volver a subir | **downgrade con cierres se niega**; upgrade se niega si una transferencia no es de su mes; CHECK de formato, estado, signo, tipo, repetido; FK RESTRICT | `test_migrations` |
| Autenticación | con token, 3 tools nuevas con esquema de salida | **sin credencial → 401** | `test_closing_tools` |
| Sin montos ni notas | — | **registros y errores sin montos, notas ni nombres de metas**; `sse_starlette` en INFO (prueba del Hito 5) | `test_closing_service`, `test_closing_tools` |

## 2. Base de DESARROLLO

### ✅ Claude

| # | Paso | Resultado |
|---|---|---|
| D1 | Respaldo con `pg_dump -Fc` dentro del contenedor, copiado fuera del repositorio (carpeta temporal de la sesión, `dev-antes-hito9.dump`) | archivo de 59 868 bytes ✅ |
| D2 | Antes de migrar: transferencias con mes distinto del de su fecha | 0 (la migración puede aplicarse) ✅ |
| D3 | `docker compose up -d --build mcp` y `alembic upgrade head` | `0008_month_closures`; contenedor sano ✅ |
| D4 | Datos conservados | 7 ingresos, 11 gastos y 6 transferencias, igual que antes; 0 cierres y 0 ajustes ✅ |
| D5 | Comprobación de solo lectura con los servicios dentro del contenedor (sin imprimir montos) | meses con movimientos 2026-11 y 2026-12; ninguno cerrado; `pending_closure` vacío en `list_bolsas` y `get_summary`; `preview_month_close` sin mes: nada que cerrar, el siguiente desde 2026-11-30 ✅ |

No hice llamadas manuales por HTTP con un token temporal (en el Hito 8 sí): el flujo por HTTP con
OAuth lo cubren las pruebas en proceso de `test_closing_tools`. Quedó un archivo de comprobación
en `/tmp` del contenedor `mcp` de desarrollo (sin datos; desaparece al recrear el contenedor).

### 👤 Propietario (opcional, base de desarrollo)

| Paso | Resultado esperado |
|---|---|
| Con el conector local: "¿qué meses faltan cerrar?" | Claude usa `get_summary` o `list_bolsas` (hoy no hay ninguno) |
| `preview_month_close` con `month=2026-11` antes del 30 | datos del mes, `closable=false`, "se cierra desde su último día (2026-11-30)", sin ficha |
| `docker compose exec mcp alembic downgrade 0007_transfers` (sin la variable), solo si hubiera un cierre | se niega: "Downgrade de 0008_month_closures cancelado…" |

## 3. HOMELAB 👤 Propietario

**Antes de actualizar: respaldo con `pg_dump`** (README, "Respaldo manual de la base") y verifica
que el archivo se puede leer (`pg_restore -l`). Nunca ejecutes `alembic downgrade` ni
`docker compose down -v` en el homelab. **No cierres noviembre antes del 30.**

| # | Paso | Resultado esperado |
|---|---|---|
| H1 | Respaldo con `pg_dump` a `~/respaldos` y `pg_restore -l` del archivo | archivo no vacío que lista las tablas |
| H2 | `git pull`, `docker compose up -d --build`, `docker compose exec mcp alembic upgrade head` | `alembic current` → `0008_month_closures (head)`; si la migración se niega por una transferencia fuera de su mes, avísame (no se cambió nada) |
| H3 | Claude: "¿Cuánto tengo en cada bolsa?", `get_summary`, `list_transactions` | todo igual que antes; `month_closed=false`; `pending_closure` vacío hasta el 30 |
| H4 | Reconectar el conector en claude.ai | aparecen `preview_month_close`, `close_month` y `set_surplus_destination` |
| H5 | "Cierra noviembre" antes del 30 | Claude explica que se cierra desde su último día; no guarda nada |
| H6 | Opcional: "el sobrante de Gustos sugiérelo a Ahorro" | `set_surplus_destination`; no mueve dinero |
| H7 | **El 30 de noviembre o después:** "hagamos el cierre del mes" | Claude muestra la vista previa (sobrantes, déficits, metas, fijos pendientes), propone coberturas y destinos con una explicación breve y **espera tu aprobación explícita** |
| H8 | Si hay un extra pendiente de noviembre | el cierre se bloquea y Claude pide repartirlo o anularlo |
| H9 | Aprobar | `close_month` guarda: transferencias `T-n` con motivo `cierre_de_mes`, lo no destinado y lo no cubierto visibles; luego Claude sigue con el salario de diciembre |
| H10 | Después de cerrar: "registra un gasto de hoy" el mismo 30 | rechazado: el mes está cerrado. El salario del 30 (diciembre) sí se registra |
| H11 | `get_summary` de diciembre antes del salario | las bolsas de consumo en 0 |
| H12 | `docker compose logs --since 30m mcp` | sin montos, notas ni nombres de metas |
| H13 | Respaldo después del cierre | archivo `.dump` no vacío fuera del repositorio |
| H14 | Etiqueta `hito-8` corregida (hoy apunta a b7f0e3d, la fusión del Hito 7) y `hito-9` sobre la fusión de este PR, después de H1–H13 | `git show hito-9` muestra el merge |

## Resumen

| Bloque | Quién | Estado |
|---|---|---|
| Pruebas automáticas (608) | ✅ Claude | Pasan |
| Desarrollo: respaldo, migración y comprobación de solo lectura (D1–D5) | ✅ Claude | Pasan |
| Desarrollo con el conector (opcional) | 👤 Propietario | Opcional |
| Homelab (H1 a H14; el cierre real desde el 30 de noviembre) | 👤 Propietario | Pendiente |
