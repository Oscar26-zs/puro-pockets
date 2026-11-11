# Verificación del Hito 5: Ingresos base y gastos (MVP)

**Fecha:** 2026-11-10 · **Rama:** `hito-5-movimientos` · **Equipo:** Windows 11, Docker Desktop

**Leyenda:** ✅ Claude = verificado por Claude en esta sesión · 👤 Propietario = te toca a ti.
Todos los datos usados por Claude son **sintéticos**. Nada se ejecutó contra la base del homelab.

## 1. Pruebas automáticas ✅ Claude

`uv run ruff check .` y `ruff format --check .`: limpios. `uv run pytest`: **330 passed** (295
unitarias + 35 de integración). Las de integración corren en una base temporal `pp_test_*` que se crea
y se borra; antes y después de la suite quedaron 0.

| Criterio | Positivas (debe funcionar) | Negativas (debe rechazar) | Pruebas |
|---|---|---|---|
| Salario (5.1, RN-02/03/08) | mes siguiente por defecto; mes explícito; herencia con mes de origen; ₡1.000.001 → 500.000/300.000/200.001; porcentaje guardado por reparto; 50/50/0 → el residuo no va a la bolsa con 0 % | sin porcentajes (error que pide `set_allocation`, nada guardado); fecha futura; `confirm=true` sin clave | `test_ledger_service`, `test_ledger_tools`, `test_ledger_sql_store` |
| Vista previa (3.2) | `preview_income` y `add_income` sin `confirm` muestran el reparto | no guardan nada | `test_ledger_service`, `test_ledger_tools` |
| Monedas (RN-55 a 57) | USD 10,00 a 512,34 = ₡5.123; half-up (4,5 → 5; 4,4999 → 4); USD 1.000 a 512,34 = ₡512.340 guardado con centavos y tasa ×100 | USD sin tipo de cambio; tipo de cambio fuera de 300..1000; conversión a 0; 3 decimales; coma decimal; número JSON con decimales (`10.5`, `512.34`); CRC con decimales o con tipo de cambio; moneda EUR | `test_money`, `test_ledger_tools`, `test_ledger_sql_store` |
| Gastos (RN-31 a 34) | mes de la fecha; sin categoría = "pendiente de clasificar"; bolsa por defecto de la categoría; contra acumulable baja su saldo | monto 0 o negativo; bolsa o categoría inexistente; sin bolsa ni categoría; fecha futura; descripción > 120 | `test_ledger_service`, `test_ledger_domain` |
| Sobregasto (RN-37/38) | se guarda, `overspent=true`, advertencia con bolsas disponibles; resumen marca la bolsa | — | `test_ledger_service`, `test_ledger_tools` |
| Anulación (RN-53/59/54) | gasto anulado sale de los cálculos y sigue en el historial con motivo; salario anulado revierte su reparto y advierte negativos; saldo inicial anulado → nueva carga; vista previa sin `confirm` | anular dos veces; referencia inexistente o mal escrita; motivo vacío | `test_ledger_service`, `test_ledger_sql_store` |
| Idempotencia | misma clave y contenido → misma respuesta, un solo movimiento (salario, gasto, anulación); reintento al día siguiente sin fecha; **dos llamadas simultáneas en Postgres** → un solo gasto | misma clave con otro monto; misma clave en otra tool | `test_ledger_service`, `test_ledger_tools`, `test_ledger_sql_store` |
| Consultas (11.1, 11.2) | `get_bolsa_status` (asignado, ajustado = original, gastado, disponible, % usado / saldo); `get_summary` sin saldo inicial; `top_categories`; `list_transactions` (orden, filtros, `has_more`) | límite 0, 101, texto, decimal; filtro por bolsa con tipo ingreso | `test_ledger_service`, `test_ledger_tools` |
| Categorías | crear y listar con bolsa por defecto | nombre repetido sin distinguir mayúsculas; nombre reservado | `test_ledger_service`, `test_ledger_sql_store` |
| Invariante 11.4 | 200 conjuntos en memoria y 40 en Postgres con salarios CRC/USD, gastos, sobregastos, anulaciones y recarga del saldo inicial (semilla impresa al fallar) | detecta un reparto alterado en ₡1 y un gasto que no resta de ninguna bolsa | `test_invariant`, `test_invariant_sql` |
| Migración `0004` | conserva datos del Hito 4 (saldo inicial en CRC, monto original = monto, sin tasa; repartos y porcentajes intactos); subir, bajar y subir sin datos | downgrade con gastos o con un ingreso anulado se niega (con la variable, pasa); CHECK de moneda, tasa, anulación incompleta, descripción, mes | `test_migrations` |
| Libro mayor inmutable | anular un gasto se permite | `DELETE` en ingresos, repartos y gastos; `UPDATE` de repartos, montos, bolsa o mes; deshacer o cambiar una anulación | `test_migrations` |
| Autenticación | con token, las 10 tools nuevas responden con esquema de salida | sin token y con token inventado → 401 | `test_ledger_tools` |
| Sin montos | — | registros y mensajes de error sin montos ni descripciones (incluidos `float`, listas y tasas fuera de rango); `sse_starlette` y `mcp.server.streamable_http` fijados en INFO | `test_ledger_service`, `test_ledger_tools`, `test_budget_tools` |

## 2. Pruebas manuales en la base de DESARROLLO

### ✅ Claude (contenedor local reconstruido; `alembic upgrade head` → `0004_movements`)

Antes de migrar se hizo un respaldo de la base de desarrollo (datos sintéticos) en una carpeta
temporal fuera del repositorio. Con un token temporal (cliente "Verificación Hito 5", revocado y
borrado al terminar) y llamadas reales a `http://127.0.0.1:8000/mcp`:

| # | Prueba | Resultado |
|---|---|---|
| 1 | Sin token | 401 ✅ |
| 2 | Tools publicadas | las 10 del hito + las del Hito 4 + `ping` ✅ |
| 3 | `preview_income` ₡1.000.001 (porcentajes sintéticos 40/40/20 de 2026-12) | 400.000 / 400.000 / 200.001, `budget_month=2026-12`, `saved=false` ✅ |
| 4 | `add_income` con `confirm` | `I-n` guardado ✅ |
| 5 | Repetir con la misma clave | respuesta idéntica, sin duplicar ✅ |
| 6 | Gasto USD `"10.00"` a `"512.34"` | ₡5.123 ✅ |
| 7 | USD sin tipo de cambio | "Falta el tipo de cambio… No se asume ninguno." ✅ |
| 8 | Monto `10.5` como número | rechazado; pide texto, **sin mostrar el monto** ✅ (ver corrección C1) |
| 9 | Tipo de cambio 1500 | "debe estar entre 300 y 1000" ✅ |
| 10 | Sobregasto en Gustos | guardado, `overspent=true`, bolsas disponibles ✅ |
| 11–12 | Misma clave: igual → misma respuesta; otro monto → error | ✅ |
| 13–15 | Categoría nueva, repetida (error) y gasto solo con categoría → su bolsa por defecto | ✅ |
| 16–18 | Anulación: vista previa, confirmada, segunda vez (error "ya está anulado") | ✅ |
| 19 | `list_transactions` | anulados marcados, más recientes primero ✅ |
| 20–22 | `get_bolsa_status`, `get_summary`, `top_categories` | cuadran entre sí ✅ |
| 23 | `list_transactions limit=150` | "entre 1 y 100" ✅ |
| 24 | Anular el salario | revertido ✅ |
| 25 | `list_bolsas` | refleja gastos y anulaciones ✅ |
| 26 | `DELETE FROM expenses` directo en la base | rechazado por el disparador ✅ |
| 27 | Registros del contenedor | solo eventos (referencia, mes, moneda, sobregasto); 0 montos, 0 descripciones ✅ |

Quedan en la base de desarrollo movimientos **sintéticos** de esta verificación (dos salarios
anulados, gastos de prueba y dos categorías "Súper sintético …"). No se cargó ni anuló ningún saldo
inicial en la base de desarrollo.

### 👤 Propietario (opcional, base de desarrollo)

| Paso | Resultado esperado |
|---|---|
| Desde Claude con el conector local (o un cliente MCP): "Registra un gasto de ₡5.000 en Gustos" con datos sintéticos | una sola frase basta (SC-007); `G-n` |
| `docker compose exec mcp alembic downgrade 0003_budget` (sin la variable) | se niega: "Downgrade de 0004_movements cancelado…"; luego `alembic upgrade head` no hace nada |

## 3. Pruebas en el HOMELAB 👤 Propietario

**Antes de actualizar: respaldo con `pg_dump`** (README, "Respaldo manual de la base"), y verifica que
el archivo se puede leer (`pg_restore -l`). Nunca ejecutes `alembic downgrade` ni
`docker compose down -v` en el homelab.

| # | Paso | Resultado esperado |
|---|---|---|
| H1 | Respaldo con `pg_dump` a `~/respaldos` y `pg_restore -l` del archivo | archivo no vacío que lista las tablas |
| H2 | `git pull`, `docker compose up -d --build`, `docker compose exec mcp alembic upgrade head` | `alembic current` → `0004_movements (head)`; registro "tipo de cambio aceptado=300..1000" |
| H3 | Claude: "¿Cuánto tengo en cada bolsa?" | tu saldo inicial sigue igual que antes de migrar (la migración conserva los datos) |
| H4 | Claude: vista previa de tu salario real con fecha de fin de mes | mes presupuestario = el siguiente; reparto con tus porcentajes (SC-001) |
| H5 | Confirmar el salario | `I-n`; `get_summary` del mes siguiente muestra el ingreso |
| H6 | Claude: un gasto real en dólares con el tipo de cambio del día | convertido a colones con ese tipo de cambio (SC-002) |
| H7 | Claude: un gasto en dólares **sin** decir el tipo de cambio | Claude te lo pide o la tool lo rechaza; nunca lo asume |
| H8 | Un gasto que exceda una bolsa | se guarda y avisa con las bolsas disponibles (SC-003) |
| H9 | Anular un gasto mal registrado (con motivo) | desaparece de los cálculos y sigue en `list_transactions` como anulado (SC-004) |
| H10 | Pedir a Claude que repita exactamente el último gasto (reintento) | no se duplica (SC-005) |
| H11 | `docker compose logs --since 30m mcp` | sin montos ni descripciones, solo eventos |
| H12 | Respaldo después de las pruebas | archivo `.dump` no vacío fuera del repositorio |
| H13 | Una semana de uso real, anotando fricciones | criterio "Prueba de uso real" del Hito 5 en `HITOS.md` |

## Resumen

| Bloque | Quién | Estado |
|---|---|---|
| Pruebas automáticas (330) | ✅ Claude | Pasan |
| Manual en desarrollo (27 pasos) | ✅ Claude | Pasan |
| Manual en desarrollo (frase única, downgrade protegido) | 👤 Propietario | Opcional |
| Homelab (H1 a H13) | 👤 Propietario | Pendiente |
