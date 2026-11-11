# Verificación del Hito 7: Bolsas flexibles y metas

**Fecha:** 2026-11-11 · **Rama:** `hito-7-bolsas-metas` · **Equipo:** Windows 11, Docker Desktop

**Leyenda:** ✅ Claude = verificado por Claude en esta sesión · 👤 Propietario = te toca a ti.
Todos los datos usados por Claude son **sintéticos**. Nada se ejecutó contra la base del homelab.

## 1. Pruebas automáticas ✅ Claude

`uv run ruff check .` y `ruff format --check .`: limpios. `uv run pytest`: **461 passed** (409
unitarias + 52 de integración). Las de integración corren en bases temporales `pp_test_*` que se crean
y se borran; al terminar quedaron 0.

| Criterio | Positivas (debe funcionar) | Negativas (debe rechazar) | Pruebas |
|---|---|---|---|
| Reajuste (RN-01, RN-14, RN-17) | proporcional 50/30/20 + 10 → 45/27/18/10; residuo en la última; desde una bolsa; manual; al archivar redistribuye; **propiedad: suma 100 y nada negativo** en 3 000 casos con semilla fija | **porcentajes que no suman 100** (manual 95, 96); bolsa faltante o de más; decimal; 101; no alcanza; proporcional imposible; única bolsa | `test_rebalance_goals_domain`, `test_pockets_goals_service`, `test_pockets_tools` |
| Crear bolsa (RN-13, RN-15) | vista previa sin guardar; mes siguiente por defecto; mes actual si se pide; conjunto completo escrito; el salario siguiente reparte con la bolsa nueva; atómica en Postgres | **nombre duplicado sin mayúsculas** (también contra una archivada); **mes pasado como destino**; sin porcentajes previos salvo manual; **confirm sin vista previa** (sin ficha u otra ficha) | `test_pockets_goals_service`, `test_pockets_tools`, `test_pockets_goals_sql_store` |
| Archivar bolsa (RN-16 a RN-18) | vacía → archivada, nunca borrada; reescribe el mes actual y los futuros con porcentajes propios; diciembre (heredado) sin la archivada; su meta se archiva | **archivar con saldo distinto de cero** (acumulable y consumo, sin montos); **archivar desde un mes futuro** (dejaría el mes actual repartiendo a una bolsa inactiva); mes pasado | `test_pockets_goals_service`, `test_pockets_goals_sql_store` |
| Bolsa archivada | el salario reparte el 100 % entre las activas | **gasto contra bolsa archivada**; reparto de extra; porcentajes; meta nueva; anular un movimiento que la toca | `test_pockets_goals_service` |
| Metas (RN-19 a RN-23, RN-25) | en acumulable; avance = saldo = `get_bolsa_status`; crear o cambiar no mueve saldos; metas en el contexto del extra y en `get_bolsa_status` | **meta en bolsa de consumo**; **segunda meta activa en la misma bolsa** (también **simultáneas en Postgres**); monto decimal o ≤ 0; fecha pasada | `test_pockets_goals_service`, `test_pockets_tools`, `test_pockets_goals_sql_store` |
| Lograda (RN-24) | al cruzar con un salario (fecha del ingreso); al anular un gasto; al bajar el objetivo; al crearla con el saldo ya alcanzado; al reactivar; nunca antes de la creación; en la transacción en Postgres | **meta lograda que no revierte al gastar**; ni al anular el movimiento que la cruzó; lograda no se pausa ni cambia | `test_rebalance_goals_domain`, `test_pockets_goals_service`, `test_pockets_goals_sql_store` |
| Pausar / reactivar | pausar libera el cupo; reactivar evalúa | **reactivar con otra activa**; meta archivada | `test_pockets_goals_service` |
| RN-28 / RN-29 | promedio de 3 meses completos; menos meses si hay menos; excedente informado | sin meses completos o promedio ≤ 0 → sin proyección | `test_rebalance_goals_domain`, `test_pockets_goals_service` |
| Idempotencia | misma clave y contenido → misma respuesta (crear bolsa, metas) | misma clave con otro contenido | `test_pockets_goals_service` |
| Invariante 11.4 | 200 conjuntos en memoria y 40 en Postgres con bolsas nuevas, metas y archivados; **la estructura no altera ningún saldo ni la suma**; **avance = saldo** en cada meta; **cambiar porcentajes no altera meses pasados** (60 conjuntos) | — | `test_invariant`, `test_invariant_sql` |
| Migración `0006` | **conserva los datos del Hito 6** (ingresos, repartos, gastos, claves, plantillas, montos, porcentajes); bolsas activas con `archived_at` nulo; subir, bajar con la variable y volver a subir | **downgrade con una meta o una bolsa archivada se niega**; CHECK (objetivo 0, lograda sin fecha, estado inválido, archivada sin fecha); índice de una activa | `test_migrations` |
| Base inmutable | una pausada libera el cupo | borrar bolsas o metas; cambiar comportamiento; cambiar la bolsa de una meta; deshacer una lograda; reactivar una bolsa | `test_migrations` |
| Autenticación | con token, las 6 tools nuevas con esquema de salida; instrucciones mencionan bolsas y metas | **sin credencial → 401** | `test_pockets_tools` |
| Sin montos | — | **registros y errores sin montos ni nombres de metas**; `sse_starlette` en INFO (prueba del Hito 5) | `test_pockets_goals_service`, `test_pockets_tools` |

## 2. Pruebas manuales en la base de DESARROLLO

### ✅ Claude (contenedor reconstruido; `alembic upgrade head` → `0006_pockets_goals`)

Antes de migrar: respaldo con `pg_dump -Fc` dentro del contenedor, comprobado con `pg_restore -l`
(14 tablas con datos) y copiado a una carpeta temporal fuera del repositorio. La migración conservó los
datos sintéticos del Hito 6 (3 ingresos, 8 gastos, 22 claves). Con un token temporal (revocado y
borrado al terminar) y llamadas reales a `http://127.0.0.1:8000/mcp`:

| # | Prueba | Resultado |
|---|---|---|
| 1 | Sin token | 401 ✅ |
| 2–3 | Instrucciones y tools | mencionan bolsas y metas; 6 tools nuevas (27 en total) ✅ |
| 4 | `preview_rebalance` Emergencia 10 % | 2026-12 (origen 2026-12): 40/40/20 → 36/36/18/10 ✅ |
| 5–7 | `create_bolsa`: vista previa, sin ficha, con ficha | sin guardar; rechazado; creada, suma 100 ✅ |
| 8–10 | Nombre en mayúsculas; mes pasado; manual que suma 96 | rechazados ✅ |
| 11–13 | Meta en Gustos; meta ₡50.000 en Emergencia; segunda meta | rechazada; `M-1` activa, faltante 50.000; rechazada ✅ |
| 14–15 | Salario de diciembre ₡600.000 | Emergencia recibe 60.000; la meta pasa a lograda; avance = saldo de la bolsa (60.000); excedente 10.000 ✅ |
| 16 | Gastar 20.000 de Emergencia | sigue lograda (saldo 40.000, 80 %) ✅ |
| 17 | Pausar la meta lograda | rechazado (RN-24) ✅ |
| 18 | Archivar Emergencia con saldo | rechazado, sin montos, remite al Hito 8 ✅ |
| 19 | Archivar Viaje (vacía) desde diciembre | rechazado: archivar es inmediato ✅ |
| 20–21 | Archivar Viaje | archivada; reajustó noviembre y diciembre; noviembre sin Viaje y suma 100 ✅ |
| 22 | Gasto contra Viaje | rechazado (archivada) ✅ |
| 23 | Contexto de un extra | sin metas activas (la única está lograda) ✅ |
| 24 | `DELETE FROM savings_goals` directo | rechazado por el disparador ✅ |
| 25 | Registros del contenedor | 0 montos, 0 nombres de metas; solo eventos (M-n, comportamiento, meses) ✅ |

Quedan en la base de desarrollo datos **sintéticos** de esta verificación (bolsas "Emergencia …" y
"Viaje …" (archivada), la meta M-1 lograda, un salario y un gasto).

### 👤 Propietario (opcional, base de desarrollo)

| Paso | Resultado esperado |
|---|---|
| Desde Claude con el conector local: "Quiero una bolsa Viaje con 10 %" | Claude muestra el reajuste, explica en pocas palabras y **espera tu aprobación** antes de crearla |
| "Crea una meta de ₡500.000 para el viaje" | Claude confirma bolsa, nombre y monto antes de crearla |
| `docker compose exec mcp alembic downgrade 0005_extras_recurring` (sin la variable) | se niega: "Downgrade de 0006_pockets_goals cancelado…" |

## 3. Pruebas en el HOMELAB 👤 Propietario

**Antes de actualizar: respaldo con `pg_dump`** (README, "Respaldo manual de la base") y verifica que
el archivo se puede leer (`pg_restore -l`). Nunca ejecutes `alembic downgrade` ni
`docker compose down -v` en el homelab.

| # | Paso | Resultado esperado |
|---|---|---|
| H1 | Respaldo con `pg_dump` a `~/respaldos` y `pg_restore -l` del archivo | archivo no vacío que lista las tablas |
| H2 | `git pull`, `docker compose up -d --build`, `docker compose exec mcp alembic upgrade head` | `alembic current` → `0006_pockets_goals (head)` |
| H3 | Claude: "¿Cuánto tengo en cada bolsa?", `list_transactions`, `list_pending_recurring` | todo igual que antes de migrar |
| H4 | Reconectar el conector en claude.ai | aparecen las 6 tools nuevas |
| H5 | Pedir una bolsa nueva real (por ejemplo Emergencia) | vista previa con los porcentajes anteriores y nuevos; **no se crea** hasta que apruebes; al aprobar suman 100 y aplican desde el mes siguiente (SC-001) |
| H6 | Crear una meta real en una bolsa acumulable | avance = saldo de la bolsa (compáralo con `get_bolsa_status`) (SC-002) |
| H7 | Intentar una meta en Necesidades o Gustos | rechazada (RN-21) |
| H8 | Intentar archivar una bolsa con saldo | rechazado sin montos |
| H9 | "¿Cuándo llego a mi meta?" | Claude usa el promedio del RN-28 o explica que aún no hay meses completos |
| H10 | `docker compose logs --since 30m mcp` | sin montos ni nombres de metas |
| H11 | Respaldo después de las pruebas | archivo `.dump` no vacío fuera del repositorio |
| H12 | Etiqueta `hito-7` sobre la fusión del PR, después de H1–H11 | `git show hito-7` muestra el merge |

Las pruebas de archivar una bolsa **con saldo** (vaciarla con una transferencia y luego archivarla)
quedan para el Hito 8, anotadas en `HITOS.md`.

## Resumen

| Bloque | Quién | Estado |
|---|---|---|
| Pruebas automáticas (461) | ✅ Claude | Pasan |
| Manual en desarrollo (25 pasos) | ✅ Claude | Pasan |
| Manual en desarrollo (frase única, meta, downgrade) | 👤 Propietario | Opcional |
| Homelab (H1 a H12) | 👤 Propietario | Pendiente |
| Archivar con saldo vía transferencia | Hito 8 | Pendiente (anotado) |
