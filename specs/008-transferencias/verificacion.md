# Verificación del Hito 8: Transferencias entre bolsas

**Fecha:** 2026-11-11 · **Rama:** `hito-8-transferencias` · **Equipo:** Windows 11, Docker Desktop

**Leyenda:** ✅ Claude = verificado por Claude en esta sesión · 👤 Propietario = te toca a ti.
Todos los datos usados por Claude son **sintéticos**. Nada se ejecutó contra la base del homelab.

## 1. Pruebas automáticas ✅ Claude

`uv run ruff check .` y `ruff format --check .`: limpios. `uv run pytest`: **537 passed** (474
unitarias + 63 de integración). Las de integración corren en bases temporales `pp_test_*` que se
crean y se borran; al terminar quedaron 0.

| Criterio | Positivas (debe funcionar) | Negativas (debe rechazar) | Pruebas |
|---|---|---|---|
| Cálculos 9.1 / 11.1 / 11.2 | ajustado = asignado + recibidas − enviadas; disponible = ajustado − gastado; saldo acumulable con todas las transferencias; % sobre ajustado y sobre original; **propiedad en 500 casos con semilla fija** | — | `test_transfers_domain` |
| Vista previa (principio 3.2) | no guarda nada; ambas bolsas antes y después; presupuesto ajustado en consumo; sin `confirm` devuelve la misma vista previa | — | `test_transfers_service`, `test_transfers_tools` |
| Confirmar | guarda `T-1` con nota; la suma de saldos y disponibles no cambia; reintento con la misma clave no duplica | **confirm sin vista previa** (sin ficha u otra ficha); **misma clave con otro contenido** | `test_transfers_service`, `test_transfers_sql_store` |
| RN-41 | — | **origen igual a destino**; **monto cero o negativo**; decimal; texto; booleano | `test_transfers_domain`, `test_transfers_service` |
| RN-42 | exactamente lo disponible sí | **más que el disponible en consumo** y **en acumulable**; **origen en negativo**; cambió el disponible entre la vista previa y la confirmación | `test_transfers_domain`, `test_transfers_service` |
| Concurrencia | transferencias cruzadas simultáneas sin interbloqueo | **dos transferencias concurrentes que sobregiran el origen**: de tres por 200 000 desde 500 000 pasan dos; quitando el bloqueo la prueba falla (comprobado); **archivar y transferir hacia la misma bolsa a la vez**: nunca queda archivada con dinero | `test_transfers_sql_store` |
| Bolsas y motivos | nombres sin distinguir mayúsculas | **bolsa archivada como origen o destino**; **bolsa inexistente**; **motivo inválido o `cierre_de_mes`**; nota de 141 | `test_transfers_service`, `test_transfers_tools` |
| Fecha | omitida u hoy | **fecha pasada o futura** | `test_transfers_domain`, `test_transfers_service` |
| RN-43 | corregir con una transferencia inversa deja todo igual | `void_transaction("T-1")`; **UPDATE o DELETE directos (rechazados por el disparador)** | `test_transfers_service`, `test_transfers_sql_store`, `test_migrations` |
| RN-58 y metas | baja de 30 % a 24 %; "completaría"; pasa a lograda en la transacción con fecha de hoy; sacar dinero después no la revierte; avance = saldo con transferencias; RN-28 incluye transferencias | el aviso nunca trae el nombre de la meta | `test_transfers_domain`, `test_transfers_service`, `test_transfers_sql_store` |
| RN-37 | la advertencia lista bolsas según los cálculos nuevos y guía hacia `preview_transfer` | una bolsa vaciada por transferencia ya no aparece como candidata | `test_transfers_service`, `test_transfers_tools` |
| Consultas | `get_bolsa_status`, `get_summary` y `get_allocation_context` con original, recibidas, enviadas, ajustado, gastado y disponible; `list_transactions` con tipo `transferencia` y filtro por bolsa, mismo límite | tipo inválido; bolsa con tipo `ingreso` | `test_transfers_service`, `test_transfers_tools` |
| RN-18 (pendientes del Hito 7) | acumulable con meta: se vacía con `reasignacion` y se archiva con su meta; consumo con disponible: se vacía y se archiva; consumo en negativo: se cubre y se archiva | archivar con saldo distinto de cero (el error indica transferir, sin montos); saldo que cambia entre la vista previa y la confirmación del archivado | `test_transfers_service`, `test_transfers_sql_store` |
| Invariante 11.4 | **200 conjuntos en memoria** (y 40 en Postgres) con ingresos, gastos, anulaciones, metas y transferencias: la suma no cambia, ajustado = asignado + recibidas − enviadas; semilla impresa al fallar | transferencias rechazadas en los conjuntos (más de 60) | `test_invariant`, `test_invariant_sql` |
| Migración `0007` | **conserva los datos del Hito 7** (bolsas, archivada, metas, ingresos, repartos, gastos, claves, plantillas, porcentajes, categorías); subir, bajar con la variable y volver a subir | **downgrade con transferencias se niega**; CHECK (monto 0 o negativo, mismo origen y destino, motivo, mes, nota de 141, bolsa inexistente); FK ON DELETE RESTRICT | `test_migrations` |
| Autenticación | con token, las 2 tools nuevas con esquema de salida; instrucciones con el flujo | **sin credencial → 401** | `test_transfers_tools` |
| Sin montos ni notas | — | **registros y errores sin montos, notas ni nombres de metas**; `sse_starlette` en INFO (prueba del Hito 5) | `test_transfers_service`, `test_transfers_tools` |

## 2. Pruebas manuales en la base de DESARROLLO

### ✅ Claude (contenedor reconstruido; `alembic upgrade head` → `0007_transfers`)

Antes de migrar: respaldo con `pg_dump -Fc` dentro del contenedor, comprobado con `pg_restore -l`
(15 tablas con datos) y copiado a una carpeta temporal fuera del repositorio. Con un token temporal
(revocado y borrado al terminar) y llamadas reales a `http://127.0.0.1:8000/mcp`. Se corrió dos
veces (la segunda tras validar el motivo en el dominio); resultados de la segunda:

| # | Prueba | Resultado |
|---|---|---|
| 0 | Base antes de la corrida | `0007_transfers`; los datos sintéticos de los Hitos 4 a 7 siguen ahí ✅ |
| 1 | Sin token | 401 ✅ |
| 2–3 | Instrucciones y tools | mencionan `preview_transfer`, `cubrir_sobregasto` y `T-n`; 2 tools nuevas (29 en total); `add_expense` guía la transferencia ✅ |
| 4–5 | Salario sintético del mes y gasto que deja Gustos en −7 531 | sobregasto avisado; candidatas Necesidades, Ahorro y Emergencia; la advertencia sugiere `preview_transfer` ✅ |
| 6 | `preview_transfer` Necesidades → Gustos | no guarda (filas antes y después iguales); Gustos −7 531 → 0; ajustado sube en 7 531 ✅ |
| 7–9 | Confirmar sin ficha; con ficha; reintento | rechazado; `T-n` guardada y Gustos en 0; el reintento devuelve la misma referencia ✅ |
| 10 | `get_bolsa_status` Gustos | original, recibidas, enviadas 0, ajustado, gastado, disponible 0, % 100 sobre ajustado y 107 sobre original ✅ |
| 11 | Negativas | mismo origen y destino; monto 0, negativo y decimal; más que el disponible; bolsa archivada; inexistente; `cierre_de_mes` ("reservado para el cierre de mes (Hito 9)"); motivo inválido; fecha de ayer y de mañana; nota de 141: todos rechazados en español, sin montos ✅ |
| 12 | Misma clave con otro monto | rechazado ✅ |
| 13–15 | Bolsa nueva con 20 000 y meta de 100 000 | `M-n` activa al 20 %; sacar 5 000: "baja de 20 % a 15 %"; meter 80 000: "alcanzaría su objetivo" ✅ |
| 16–17 | Archivar con saldo; vaciar con `reasignacion` y archivar | rechazado indicando la transferencia; archivada con su meta ✅ |
| 18 | Transferir a la bolsa archivada | rechazado ✅ |
| 19–21 | `list_transactions` (transferencias), `void_transaction` de una `T-n`, `get_summary` | las `T-n` con origen, destino y motivo; anular rechazado (RN-43); Gustos con original y ajustado ✅ |
| 22 | `UPDATE` y `DELETE` directos sobre `transfers` | rechazados por el disparador ✅ |
| 23 | Invariante 11.4 sobre toda la base de desarrollo | diferencia 0 ✅ |
| 24 | Registros del contenedor | 0 montos, 0 notas, 0 nombres de metas; solo eventos (`T-n`, mes, motivo, metas afectadas). Un nombre de bolsa aparece en un error ("no existe o está archivada"), como desde el Hito 4 ✅ |

Quedan en la base de desarrollo datos **sintéticos** de esta verificación: dos salarios del mes, dos
gastos en Gustos, bolsas "Fondo …" archivadas con sus metas y las transferencias `T-1` a `T-6`.

### 👤 Propietario (opcional, base de desarrollo)

| Paso | Resultado esperado |
|---|---|
| Desde Claude con el conector local: registra un gasto que deje Gustos en negativo | Claude avisa y **propone** cubrirlo con una transferencia, muestra la vista previa y **espera tu aprobación** |
| "Pasa 10 000 de Ahorro a Gustos" con una meta activa en Ahorro | la vista previa dice cuánto baja el avance de la meta |
| `docker compose exec mcp alembic downgrade 0006_pockets_goals` (sin la variable) | se niega: "Downgrade de 0007_transfers cancelado…" |

## 3. Pruebas en el HOMELAB 👤 Propietario

**Antes de actualizar: respaldo con `pg_dump`** (README, "Respaldo manual de la base") y verifica que
el archivo se puede leer (`pg_restore -l`). Nunca ejecutes `alembic downgrade` ni
`docker compose down -v` en el homelab.

| # | Paso | Resultado esperado |
|---|---|---|
| H1 | Respaldo con `pg_dump` a `~/respaldos` y `pg_restore -l` del archivo | archivo no vacío que lista las tablas |
| H2 | `git pull`, `docker compose up -d --build`, `docker compose exec mcp alembic upgrade head` | `alembic current` → `0007_transfers (head)` |
| H3 | Claude: "¿Cuánto tengo en cada bolsa?", `get_goal_progress`, `list_transactions` | todo igual que antes de migrar |
| H4 | Reconectar el conector en claude.ai | aparecen `preview_transfer` y `transfer_between_bolsas` |
| H5 | Un gasto real que deje una bolsa de consumo en negativo (o simúlalo con una vista previa) | Claude propone una transferencia, muestra la vista previa y **no la guarda** hasta que apruebes; al aprobar, la bolsa vuelve a cero (SC-001) |
| H6 | `get_bolsa_status` de esa bolsa | presupuesto original, recibidas, ajustado, gastado y disponible |
| H7 | Pedir mover más de lo disponible | rechazado, sin montos (SC-002) |
| H8 | Mover dinero fuera de una bolsa con meta activa (solo la vista previa) | muestra cuánto baja el avance (SC-003) |
| H9 | "Anula la transferencia T-1" | Claude explica que se corrige con una transferencia inversa |
| H10 | `docker compose logs --since 30m mcp` | sin montos, notas ni nombres de metas |
| H11 | Respaldo después de las pruebas | archivo `.dump` no vacío fuera del repositorio |
| H12 | Etiqueta `hito-8` sobre la fusión del PR, después de H1–H11 | `git show hito-8` muestra el merge |

## Resumen

| Bloque | Quién | Estado |
|---|---|---|
| Pruebas automáticas (537) | ✅ Claude | Pasan |
| Manual en desarrollo (24 pasos) | ✅ Claude | Pasan |
| Manual en desarrollo (flujo con Claude, meta, downgrade) | 👤 Propietario | Opcional |
| Homelab (H1 a H12) | 👤 Propietario | Pendiente |
