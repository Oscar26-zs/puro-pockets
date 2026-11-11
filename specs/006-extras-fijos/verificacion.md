# Verificación del Hito 6: Extras y gastos fijos

**Fecha:** 2026-11-11 · **Rama:** `hito-6-extras-fijos` · **Equipo:** Windows 11, Docker Desktop

**Leyenda:** ✅ Claude = verificado por Claude en esta sesión · 👤 Propietario = te toca a ti.
Todos los datos usados por Claude son **sintéticos**. Nada se ejecutó contra la base del homelab.

## 1. Pruebas automáticas ✅ Claude

`uv run ruff check .` y `ruff format --check .`: limpios. `uv run pytest`: **399 passed** (355
unitarias + 44 de integración). Las de integración corren en bases temporales `pp_test_*` que se crean
y se borran; al terminar quedaron 0.

| Criterio | Positivas (debe funcionar) | Negativas (debe rechazar) | Pruebas |
|---|---|---|---|
| Extra pendiente (RN-06, RN-09) | queda `pendiente` en el mes de su fecha; no suma a bolsas ni al invariante; "sin asignar" en resumen y listado (cantidad, total CRC, USD aparte) | USD sin tipo de cambio; fecha futura; sin `operation_id`; misma clave con otro monto | `test_extras_service`, `test_extras_tools` |
| Contexto (RN-05, RN-36) | bolsas activas con %, presupuesto, gastado, disponible o saldo; fijos pendientes con USD aparte sin convertir; % de extras previos; sin descripciones ni ids | algo que no es extra (`I-` base, `G-`); referencia inexistente | `test_extras_service` |
| Reparto (RN-01, RN-07, RN-08) | vista previa sin guardar; ₡40.001 al 50/50 → 20.000 / 20.001; 100 % a una bolsa personalizada; porcentaje guardado; suma = monto | **no suma 100** (90, 110); **bolsa inexistente o inactiva**; porcentaje decimal (sin mostrar el valor); **confirm sin vista previa** (sin ficha o con la de otro reparto); sin `operation_id` | `test_recurring_domain`, `test_extras_service`, `test_extras_tools` |
| Repartir una sola vez (RN-53, RN-59) | reintento con la misma clave → misma respuesta; anular el extra revierte su reparto y advierte negativos; registrar de nuevo | **repartir dos veces el mismo extra** (vista previa y confirmación); repartir un extra anulado; **dos confirmaciones simultáneas en Postgres** → una sola | `test_extras_service`, `test_extras_sql_store` |
| Plantillas (RN-35) | crear (F-n), listar, actualizar, desactivar; nombre libre al desactivar; monto nuevo desde el mes siguiente | nombre repetido sin mayúsculas; cambiar moneda; nada que cambiar; acción inválida; **plantilla desactivada** (pagar, actualizar, desactivar otra vez) | `test_extras_service`, `test_extras_sql_store` |
| Pendientes | activas desde su inicio sin pago vigente; vencimiento; atrasado según hoy; pagados con su `G-n`; USD sin convertir | — | `test_recurring_domain`, `test_extras_service` |
| Día del mes | **día 31 en febrero → 28** (29 en bisiesto); 30 en abril | día 0, 32, decimal, texto | `test_recurring_domain`, `test_extras_service` |
| Pago de un fijo | sin monto usa el de la plantilla; con otro monto; por nombre o F-n; anulado → vuelve a pendiente | **dos pagos vigentes en un mes** (también **simultáneos en Postgres**); pago antes del inicio; **USD sin tipo de cambio en el pago** (y no reutiliza el del mes anterior) | `test_extras_service`, `test_extras_tools`, `test_extras_sql_store` |
| Idempotencia | misma clave y contenido → misma respuesta en extra, reparto, pago y plantillas | misma clave con otro contenido | `test_extras_service` |
| Invariante 11.4 | 200 conjuntos en memoria y 40 en Postgres con extras pendientes, repartidos y anulados, y pagos de fijos (algunos anulados y vueltos a pagar); semilla impresa al fallar | detecta un extra pendiente contado como repartido | `test_invariant`, `test_invariant_sql` |
| Migración `0005` | **conserva los datos del Hito 5** (ingresos CRC/USD/anulados, repartos, gastos, claves); subir, bajar con la variable y volver a subir | **downgrade con una plantilla o un extra se niega**; upgrade con un ingreso no extra pendiente se niega; CHECK (día, moneda, monto 0, pendiente solo en extras, largo del origen) | `test_migrations` |
| Libro mayor | anular un pago libera el mes | borrar plantillas o montos; cambiar moneda o inicio; reactivar; quitar `recurring_id`; volver a pendiente; repartir un anulado | `test_migrations` |
| Autenticación | con token, las 5 tools nuevas responden con esquema de salida; instrucciones en `initialize` | **sin credencial → 401**; token inventado → 401 | `test_extras_tools` |
| Sin montos | — | **registros y errores sin montos, descripciones, orígenes ni nombres de plantillas**; `sse_starlette` y `mcp.server.streamable_http` fijados en INFO (prueba del Hito 5) | `test_extras_service`, `test_extras_tools` |

## 2. Pruebas manuales en la base de DESARROLLO

### ✅ Claude (contenedor local reconstruido; `alembic upgrade head` → `0005_extras_recurring`)

Antes de migrar: respaldo con `pg_dump -Fc` dentro del contenedor, comprobado con `pg_restore -l`
(12 tablas con datos) y copiado a una carpeta temporal fuera del repositorio. La base de desarrollo
tenía datos sintéticos del Hito 5 (2 ingresos, 6 gastos, 12 claves) y la migración los conservó. Con
un token temporal (cliente "Verificación Hito 6", revocado y borrado al terminar) y llamadas reales a
`http://127.0.0.1:8000/mcp`:

| # | Prueba | Resultado |
|---|---|---|
| 1 | Sin token | 401 ✅ |
| 2 | Instrucciones del servidor en `initialize` | presentes; piden aprobación explícita ✅ |
| 3 | Tools publicadas | las 5 nuevas + las anteriores (21) ✅ |
| 4–5 | Extra ₡40.000 | `I-3`, pendiente, mes 2026-11; "sin asignar" = 1 / ₡40.000 ✅ |
| 6 | Extra USD sin tipo de cambio | "Falta el tipo de cambio… No se asume ninguno." ✅ |
| 7 | `get_allocation_context` | bolsas con % (50/30/20), disponible o saldo, fijos, extras previos ✅ |
| 8 | Vista previa 70/30 | Ahorro 28.000, Gustos 12.000, `saved=false`, con ficha ✅ |
| 9 | Confirmar sin ficha | rechazado: pide la vista previa y la aprobación explícita ✅ |
| 10–11 | Suma 90; bolsa inexistente | rechazados ✅ |
| 12–13 | Confirmar con ficha; reintento con la misma clave | repartido, suma = monto; respuesta idéntica ✅ |
| 14 | Repartir otra vez con otra clave | "ya se repartió… anúlalo" ✅ |
| 15–16 | Crear fijos CRC (día 31) y USD; nombre repetido | `F-1`, `F-2`; repetido rechazado ✅ |
| 17 | `list_pending_recurring` | F-2 USD 9,99 sin convertir, vencido el 5 (atrasado); F-1 vence el 30 ✅ |
| 18 | Día 31 en febrero de 2027 | vence 2027-02-28 ✅ |
| 19–20 | Pagar F-1 sin monto; segundo pago | ₡18.500 en Necesidades; segundo rechazado ✅ |
| 21–22 | Pagar F-2 sin / con tipo de cambio | rechazado; 9,99 × 505,50 = ₡5.050 (half-up) ✅ |
| 23–24 | Anular el pago de F-1 | advierte y F-1 vuelve a pendiente ✅ |
| 25 | Cambiar el monto de F-1 | noviembre conserva 18.500; 19.000 desde 2026-12 ✅ |
| 26–27 | Desactivar F-2; pagarlo | desactivado; pago rechazado ✅ |
| 28 | Anular el extra repartido | revierte y avisa bolsas en negativo (Gustos) ✅ |
| 29 | `list_transactions` | estado del extra, fijo de cada pago, anulados marcados ✅ |
| 30 | `DELETE FROM recurring_expenses` directo | rechazado por el disparador ✅ |
| 31 | Registros del contenedor (15 min) | solo eventos con referencias, mes y moneda; 0 montos, 0 descripciones, 0 nombres ✅ |

Quedan en la base de desarrollo datos **sintéticos** de esta verificación (un extra anulado, dos
gastos fijos con nombres "… sintético …", dos pagos).

### 👤 Propietario (opcional, base de desarrollo)

| Paso | Resultado esperado |
|---|---|
| Desde Claude con el conector local: "Me entraron ₡40.000 extra" (sintético) | Claude registra, pide contexto, propone con explicación, muestra la vista previa y **espera tu aprobación** antes de confirmar |
| Responder algo ambiguo ("puede ser") a la propuesta | Claude no confirma; vuelve a preguntar |
| `docker compose exec mcp alembic downgrade 0004_movements` (sin la variable) | se niega: "Downgrade de 0005_extras_recurring cancelado…" |

## 3. Pruebas en el HOMELAB 👤 Propietario

**Antes de actualizar: respaldo con `pg_dump`** (README, "Respaldo manual de la base") y verifica que
el archivo se puede leer (`pg_restore -l`). Nunca ejecutes `alembic downgrade` ni
`docker compose down -v` en el homelab.

| # | Paso | Resultado esperado |
|---|---|---|
| H1 | Respaldo con `pg_dump` a `~/respaldos` y `pg_restore -l` del archivo | archivo no vacío que lista las tablas |
| H2 | `git pull`, `docker compose up -d --build`, `docker compose exec mcp alembic upgrade head` | `alembic current` → `0005_extras_recurring (head)` |
| H3 | Claude: "¿Cuánto tengo en cada bolsa?" y `list_transactions` | tus saldos y movimientos del Hito 5 siguen iguales |
| H4 | Reconectar el conector en claude.ai (para que lea las instrucciones nuevas) | las tools nuevas aparecen |
| H5 | Claude: registrar un extra real | queda pendiente y "sin asignar" (SC-001) |
| H6 | Pedir a Claude que proponga el reparto | explica en pocas palabras con tus datos del mes; muestra la vista previa; **no confirma** hasta que apruebes |
| H7 | Aprobar | la suma del reparto es exactamente el monto (SC-002); "sin asignar" baja a 0 |
| H8 | Registrar tus gastos fijos reales (alquiler, internet, suscripciones) | cada uno con su `F-n` |
| H9 | "¿Qué fijos me faltan este mes?" | `list_pending_recurring` con vencimientos y atrasos |
| H10 | Pagar un fijo en dólares sin decir el tipo de cambio | Claude te lo pide o la tool lo rechaza; nunca lo asume (decisión #12d) |
| H11 | Pagar un fijo y pedir de nuevo los pendientes | ya no aparece; un segundo pago del mes se rechaza |
| H12 | `docker compose logs --since 30m mcp` | sin montos ni descripciones, solo eventos |
| H13 | Respaldo después de las pruebas | archivo `.dump` no vacío fuera del repositorio |
| H14 | Etiqueta `hito-6` sobre la fusión del PR, después de H1–H13 | `git show hito-6` muestra el merge |

## Resumen

| Bloque | Quién | Estado |
|---|---|---|
| Pruebas automáticas (399) | ✅ Claude | Pasan |
| Manual en desarrollo (31 pasos) | ✅ Claude | Pasan |
| Manual en desarrollo (frase única, respuesta ambigua, downgrade) | 👤 Propietario | Opcional |
| Homelab (H1 a H14) | 👤 Propietario | Pendiente |
