# Verificación del Hito 4: Bolsas y porcentajes

**Fecha:** 2026-11-10 · **Rama:** `hito-4-bolsas` · **Equipo:** Windows 11, Docker Desktop

**Leyenda:** ✅ Claude = verificado por Claude en esta sesión · 👤 Propietario = te toca a ti.
Todos los datos usados por Claude son **sintéticos**. Nada se ejecutó contra la base del homelab.

## 1. Pruebas automáticas ✅ Claude

`uv run ruff check .` y `ruff format --check .`: limpios. `uv run pytest`: **194 passed**
(172 unitarias + 22 de integración). Las de integración corren en una base temporal `pp_test_*` que
se crea y se borra; después de la suite no quedó ninguna.

| Criterio | Positivas (debe funcionar) | Negativas (debe rechazar) | Pruebas |
|---|---|---|---|
| US1 · RN-01 | 50/30/20 se guarda y se consulta; reemplazo del mes; 0 % válido | suma 110 y 90 (mensaje con la suma), bolsa faltante, repetida (otra capitalización), inexistente, archivada, porcentaje decimal/texto/booleano/fuera de rango; nada se guarda | `test_allocation.py`, `test_budget_service.py`, `test_budget_tools.py`, `test_budget_sql_store.py` |
| US1 · meses | mes actual y futuros editables | mes pasado (aunque no tuviera porcentajes), formato `2026-13`, `26-01`, `2026-1` | `test_months.py`, `test_allocation.py`, `test_budget_service.py` |
| US2 · RN-02 / RN-03 | cambiar M+1 no altera M; un mes sin porcentajes hereda del anterior más cercano e indica el origen | consultar no escribe nada (filas iguales antes y después); sin porcentajes → `defined=false` | `test_allocation.py`, `test_budget_service.py`, `test_budget_sql_store.py` |
| US3 · RN-54 | vista previa; carga atómica (ingreso + repartos); `list_bolsas` con saldos; en el mes siguiente consumo = 0 y acumulable conserva | `confirm=false` no guarda; segunda carga; **dos cargas simultáneas** (solo una se guarda, sin repartos huérfanos); montos negativos/decimales/todo en 0; bolsa inexistente o archivada | `test_initial_balance.py`, `test_balances.py`, `test_budget_service.py`, `test_budget_tools.py`, `test_budget_sql_store.py` |
| US4 · RN-08 | ₡10.001 → 5.000 / 3.000 / 2.001; 2.000 repartos generados con suma exacta y sin negativos | monto negativo o decimal, porcentajes que no suman 100, sin bolsas | `test_allocation.py` |
| Invariante 11.4 | 200 conjuntos sintéticos en memoria y 40 en Postgres cuadran (semilla fija, se imprime si falla) | un reparto alterado en ₡1 se detecta | `test_invariant.py`, `test_invariant_sql.py` |
| Autenticación | con token, las 5 tools responden con esquema de salida | sin token y con token inventado → 401 | `test_budget_tools.py` |
| Sin montos | — | registros y mensajes de error sin los montos sintéticos; bibliotecas que registran cuerpos fijadas en INFO | `test_budget_service.py`, `test_budget_tools.py` |
| Base de datos | datos iniciales: solo las 3 bolsas, sin porcentajes; subir dos veces; bajar y subir sin datos | nombre de bolsa repetido sin distinguir mayúsculas, comportamiento inválido, mes inválido, porcentaje > 100, monto 0, segundo saldo inicial (índice único) | `test_migrations.py`, `test_budget_sql_store.py` |
| Downgrade protegido | con `ALLOW_DESTRUCTIVE_DOWNGRADE=true` baja | con datos (porcentajes o bolsas modificadas) se niega y no borra nada | `test_migrations.py` |
| Guardián de pruebas | acepta solo la base temporal creada | base de desarrollo, otra `pp_test_*`, host `db` o de otra máquina | `test_temp_database_guard.py` |
| Capas | — | `domain/` no importa MCP ni la base | `test_architecture.py` |

## 2. Pruebas manuales en la base de DESARROLLO

### ✅ Claude (contenedor local reconstruido, `alembic upgrade head` → `0003_budget`)

Con un token temporal emitido en la base de desarrollo (cliente "Verificación Hito 4", revocado y
borrado al terminar) y llamadas reales a `http://127.0.0.1:8000/mcp`:

| # | Prueba | Resultado |
|---|---|---|
| 1 | Sin token | 401 ✅ |
| 2 | Tools publicadas | `get_allocation`, `list_bolsas`, `load_initial_balance`, `ping`, `preview_initial_balance`, `set_allocation` ✅ |
| 3 | `get_allocation` sin porcentajes | `defined=false` ✅ |
| 4 | `set_allocation` 50/30/20 (nombres con otra capitalización) | guardado para 2026-11 ✅ |
| 5 | Suma 110 | "Los porcentajes deben sumar exactamente 100; suman 110." ✅ |
| 6 | `get_allocation` 2026-12 | hereda 50/30/20, `source_month=2026-11` ✅ |
| 7 | `set_allocation` 40/40/20 para 2026-12 | guardado ✅ |
| 8 | `get_allocation` 2026-11 | sigue 50/30/20 ✅ |
| 9 | Mes pasado (2026-10) | rechazado con mensaje claro ✅ |
| 10 | Bolsa inexistente | "La bolsa 'Viaje' no existe o está archivada." ✅ |
| 11 | `preview_initial_balance` (₡111 / ₡222 sintéticos) | total 333, Gustos 0, `saved=false` ✅ |
| 12 | `load_initial_balance` sin `confirm` | vista previa, `saved=false`, nada guardado ✅ |
| 13 | Monto negativo | rechazado sin mostrar el monto ✅ |
| 14 | `list_bolsas` | tres bolsas en 0, acumulable `saldo`, consumo `disponible_del_mes` ✅ |
| 15 | Registros del contenedor | solo eventos ("Porcentajes guardados: mes=… bolsas=3"); 0 apariciones de montos ✅ |
| 16 | Respaldo con `pg_dump` (comando del README) | archivo de 21 KB con 10 tablas, en una carpeta temporal fuera del repo (borrado después) ✅ |

Quedan en la base de desarrollo los porcentajes sintéticos de 2026-11 y 2026-12. **No** se cargó
saldo inicial en la base de desarrollo: queda para ti (abajo).

### 👤 Propietario (opcional, base de desarrollo)

| Paso | Resultado esperado |
|---|---|
| Con el conector apuntando a tu entorno local, o con un cliente MCP, cargar un saldo inicial **sintético** con `confirm=true` | `saved=true`; `list_bolsas` muestra los montos |
| Repetir la carga | "El saldo inicial ya fue cargado; solo se carga una vez." |
| `docker compose exec mcp alembic downgrade 0002_oauth` (sin la variable) | se niega: "Downgrade de 0003_budget cancelado…"; luego `alembic upgrade head` no hace nada |

## 3. Pruebas en el HOMELAB 👤 Propietario

**Antes de actualizar:** haz el respaldo manual (README, "Respaldo manual de la base"). Nunca
ejecutes `alembic downgrade` ni `docker compose down -v` en el homelab.

| # | Paso | Resultado esperado |
|---|---|---|
| H1 | `git pull` (rama o etiqueta del Hito 4), `docker compose up -d --build`, `docker compose exec mcp alembic upgrade head` | `alembic current` → `0003_budget (head)`; registro `Presupuesto: zona horaria=America/Costa_Rica` |
| H2 | Claude: "Define los porcentajes de este mes: Necesidades 50, Ahorro 30, Gustos 20" | guardados (SC-001) |
| H3 | Claude: "Ponlos en Necesidades 50, Ahorro 30, Gustos 30" | rechazo: suman 110 (SC-001) |
| H4 | Claude: "¿Qué porcentajes tiene el mes siguiente?" | los de este mes, indicando que vienen de este mes |
| H5 | Claude: "Define 40/40/20 para el mes siguiente" y luego "¿y los de este mes?" | este mes sigue en 50/30/20 (SC-003) |
| H6 | Claude: vista previa de tu saldo inicial **real** | total y monto por bolsa; revisa con calma |
| H7 | Claude: cargar el saldo inicial (confirmando) | `list_bolsas` muestra el saldo de cada bolsa (SC-002) |
| H8 | Claude: cargarlo otra vez | rechazo (SC-002) |
| H9 | `docker compose logs --since 30m mcp` | sin montos ni saldos, solo eventos |
| H10 | Respaldo después de cargar el saldo inicial | archivo `.dump` no vacío fuera del repositorio |

## Resumen

| Bloque | Quién | Estado |
|---|---|---|
| Pruebas automáticas (194) | ✅ Claude | Pasan |
| Manual en desarrollo (16 pasos) | ✅ Claude | Pasan |
| Manual en desarrollo (carga real sintética, downgrade protegido) | 👤 Propietario | Opcional |
| Homelab (H1 a H10) | 👤 Propietario | Pendiente |
