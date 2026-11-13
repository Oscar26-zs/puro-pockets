# Verificación del Hito 10: Dashboard y estadísticas

**Fecha:** 2026-11-12 · **Rama:** `hito-10-dashboard` (desde `origin/main` 79419fc) · **Equipo:**
Windows 11, Docker Desktop

**Leyenda:** ✅ Claude = verificado por Claude en esta sesión · 👤 Propietario = te toca a ti.
Todos los datos usados por Claude son **sintéticos** (`tests/dashboard_world.py`,
`web/src/test/fixtures.ts`). Nada se ejecutó contra la base del homelab ni con datos reales.

## 1. Equipo de desarrollo: pruebas automáticas ✅ Claude

- `uv run ruff check .` y `ruff format --check .`: limpios.
- `uv run pytest`: **761 passed, 1 failed** de 762 (676 unitarias + 86 de integración; el Hito 9
  cerró con 608). Las **154 pruebas nuevas** de este hito pasan todas. La falla es
  `test_transfers_sql_store.py::test_archivar_y_transferir_hacia_ella_a_la_vez` (Hito 8), que es
  **intermitente** (≈1 de 4 corridas) por un `DeadlockDetected` real de Postgres entre
  `archive_bolsa` y `transfer_between_bolsas` simultáneos. Este hito no modifica ningún archivo
  existente de `src/`; ver sección 4.
- `web`: `npm run lint` (eslint), `npm run typecheck` (tsc), `npm test` (**21 pruebas** de
  Vitest + Testing Library), `npm run build` (con `check-bundle`) y `npm run e2e` (**16 pruebas** de
  Playwright + axe; 1 de capturas, omitida por defecto): todo en verde.

| Criterio | Positivas (debe funcionar) | Negativas (debe rechazar) | Pruebas |
|---|---|---|---|
| Identidad con las tools (SC-001) | resumen = `get_summary` (noviembre abierto y octubre cerrado); cada bolsa = `get_bolsa_status`; cada meta = `get_goal_progress`; movimientos = `list_transactions` con 8 combinaciones de filtros; categorías = `top_categories`; evolución = totales de `get_summary` de cada mes. Las tools se llaman **por MCP con OAuth** sobre el mismo almacén | — | `test_dashboard_api` |
| Sesión (FR-005) | inicio de sesión → 204 y cookie `HttpOnly; SameSite=strict; Secure; Max-Age=43200; Path=/`; Secure configurable; la sesión vence a las 12 h; cierre de sesión borra y revoca | **sin sesión 401 en las 8 rutas, en `/api` y en una ruta inexistente**; cookie falsa, alterada, vacía o firmada con otro secreto → 401; **contraseña mala → 401**; **5 fallos → 429 con `Retry-After`** (también con la contraseña correcta); se desbloquea al pasar la ventana; **login sin JSON → 400**; **otro `Origin` → 403**; cookie reutilizada tras cerrar sesión → 401 | `test_dashboard_api`, `test_dashboard_config` |
| Verbos | `GET`; `POST` en login y logout | **`POST`/`PUT`/`PATCH`/`DELETE` → 405** en las 8 rutas, `/`, `/healthz` y cualquier ruta, con `Allow: GET`; `GET`/`PUT`/`DELETE` en login y logout → 405 (`Allow: POST`); `OPTIONS` → 405 (sin preflight de CORS) | `test_dashboard_api` |
| Cabeceras (FR-007) | CSP con `default-src 'self'` y `frame-ancestors 'none'`, `nosniff`, `no-referrer`, `Cache-Control: no-store` en `/api` y en el HTML; también en las respuestas 401 | **sin `Access-Control-Allow-Origin`** aunque llegue otro `Origin` | `test_dashboard_api` |
| Anulados (RN-53) | gastado del mes sin el gasto anulado (310 000); con «incluir anulados» aparece marcado con su motivo | **por defecto no aparecen**; la bolsa no los suma | `test_dashboard_api` |
| Mes cerrado (RN-48, RN-50) | octubre `month_closed` con su ajuste (sobrante no destinado 5 000); noviembre abierto | — | `test_dashboard_api` |
| Ahorrado y evolución (P2, SC-004) | noviembre 150 000 con desglose; octubre 310 000 (incluye el sobrante de cierre); 6 meses con meses vacíos en cero; dominio: base, extra, recibidas, enviadas, entre acumulables, sobrante de cierre, cobertura desde acumulable, bolsa archivada | **el saldo inicial no cuenta**; otro mes no cuenta; cierre de otro mes no cuenta; puede ser negativo | `test_stats_domain`, `test_dashboard_api` |
| Fecha estimada (P1) | ⌈40 000 ÷ 310 000⌉ = diciembre 2026; ejemplos de `docs/dashboard.md` (diciembre 2026, mayo 2027); techo con un colón más | **no proyectable, promedio nulo, 0 o negativo, faltante 0 → sin fecha** | `test_stats_domain`, `test_dashboard_api` |
| Alertas (P4) | uso alto 81 %; sobregasto con el monto (4 500); extra sin asignar en USD; cierre pendiente con el reloj en diciembre (RN-49) | 79 % sin alerta | `test_stats_domain`, `test_dashboard_api` |
| Gastos fijos | pagado (con `G-n`), pendiente y atrasado; USD sin convertir | — | `test_dashboard_api` |
| Paginación (P9) | 10 por página, páginas sin repetir | **página 0 u 11 → 400** | `test_dashboard_api` |
| Entradas inválidas | — | tipo desconocido → 400 **sin repetir la entrada**; mes `2026-13` → 400 | `test_dashboard_api` |
| Registros (FR-008, SC-005) | se registra método, ruta y estado | **ninguna línea del servidor contiene la descripción, la nota, el nombre de la meta, el nombre de bolsa de la consulta, montos ni la contraseña** | `test_dashboard_api` |
| Rol de solo lectura (FR-006, SC-003) | el rol creado con `scripts/create_dashboard_role.sql` pasa la comprobación, lee y la API devuelve lo mismo que las tools (Postgres real); transacciones de solo lectura | **rol propietario → se niega**; con `SELECT` en `oauth_clients` u `oauth_access_tokens`, `INSERT` en `expenses`, `UPDATE` en `pockets`, `USAGE` en una secuencia o `CREATE` en `public` → **se niega**; el rol no puede insertar ni leer `oauth_clients` ni `idempotency_keys` | `test_dashboard_readonly` (integración) |
| Arranque | configuración por defecto segura (Secure, 127.0.0.1, 12 h) | **sin `DASHBOARD_DATABASE_URL` no cae a `DATABASE_URL`**; secreto < 32 bytes; hash que no es argon2; rol que puede escribir → sale con código 2 sin servir; base inalcanzable → código 3 sin mostrar la URL | `test_dashboard_config` |
| El MCP no sirve el dashboard | — | **la app del MCP con `Host: mcp.puropockets.space` responde 404 en `/`, `/api`, `/api/summary`, `/api/session` e `/index.html`** | `test_dashboard_api` |
| Estáticos | `/` y rutas de la SPA sirven el `index.html` con CSP y `no-store`; `/assets/*` | `/api/*` nunca cae al `index.html` (401 sin sesión, 404 con sesión) | `test_dashboard_api` |
| Arquitectura | — | `domain/` no importa `api`, FastAPI ni Starlette | `test_architecture` |
| Frontend: formatos y textos | salidas exactas de `docs/dashboard.md` §9; plantillas de avisos de §11 | — | Vitest |
| Frontend: componentes | avisos (descartar, «Todo está al día.», solo lectura en mes cerrado); barras (`aria-valuenow` con tope 100 y `aria-valuetext` real); tarjetas de meta (estimado y «Sin estimación»); métricas en orden; sin asignar por moneda; fijos con estado; movimientos con signo, «Anulado» y «Pendiente»; estados de carga, vacío y error con «Reintentar»; insignia; tema (aria-pressed, Escape devuelve el foco, clases, solo `pp-theme` en `localStorage`) | inicio de sesión con contraseña mala muestra el error y limpia el campo; no muestra «La autenticación se habilitará más adelante.» | Vitest |
| Frontend: aplicación | inicio de sesión → resumen; navegación con `aria-current`; el mes va a `?month=` | **nada en `sessionStorage`, nada financiero en `localStorage` ni en la URL** | Vitest |
| Responsive y accesibilidad (SC-006, P6) | 320, 360, 768, 1024, 1280 y 1920 px × claro y oscuro × Resumen, Bolsas y Movimientos; «Sistema» con el sistema oscuro; pantalla de contraseña; filtros móviles como diálogo (foco inicial y Escape) | **sin scroll horizontal; botones de navegación < 44 px; violaciones serious/critical de axe (WCAG 2.1 AA)**: cero; producción **sin panel de desarrollo** y **sin peticiones a otros orígenes** | Playwright + axe |
| Compilación | — | **la compilación no contiene los datos de ejemplo** ni recursos de otros orígenes (`check-bundle.mjs`) | `npm run build` |

Hallazgos de axe corregidos durante el hito: estructura de `<dl>` inválida en las tarjetas de bolsa,
nombre accesible del selector de mes sin el texto visible bajo 400 px, contraste de las insignias
«Sobregasto» y «Anulado».

## 2. Equipo de desarrollo: contenedor real ✅ Claude

Con la imagen de `Dockerfile.dashboard` construida en la PC, una base temporal `pp_test_*` con el
mundo sintético y un rol temporal creado con el script (ambos borrados al final):

- Arranque: "rol de solo lectura comprobado"; `/healthz` 200 con las cabeceras de seguridad.
- `/api/summary` sin sesión 401; `POST /api/summary` 405; contraseña mala 401; contraseña correcta
  204 con `HttpOnly; Max-Age=43200; Path=/; SameSite=strict`.
- Resumen de noviembre: ingresos 500 000, gastado 310 000, disponible 40 000, ahorrado 150 000.
- `/` sirve el frontend compilado.
- Registros del contenedor: solo método, ruta, estado y "inicio de sesión fallido/correcto".
- Con la URL del rol propietario, el contenedor **no arranca** y lista los permisos que sobran.
- Memoria: 69,5 MiB en reposo y 71,1 MiB tras 20 consultas (anotado en el plan técnico).

## 3. Homelab 👤 Propietario

Empieza **siempre** con un respaldo:

```bash
mkdir -p ~/respaldos
docker compose exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > ~/respaldos/puro-pockets-$(date +%Y%m%d-%H%M).dump
ls -lh ~/respaldos   # no debe pesar 0 bytes
```

| # | Paso | Positiva (debe pasar) | Negativa (debe fallar) |
|---|---|---|---|
| 1 | `git pull` de la rama y `docker compose up -d` (sin el perfil `dashboard`) | `db`, `mcp` y `cloudflared` siguen sanos; Claude responde igual (este hito no cambia el MCP) | — |
| 2 | Crear el rol (README, "Dashboard", paso 1) y fijar su contraseña con `\password` | el script termina sin error | `docker compose exec db psql -U puro_dashboard -d "$POSTGRES_DB" -c "INSERT INTO categories (name, pocket_id) VALUES ('x', 1)"` → error de permiso o de solo lectura; `-c "SELECT * FROM oauth_clients"` → permiso denegado |
| 3 | `.env`: `COMPOSE_PROFILES=tunnel,dashboard`, `DASHBOARD_DATABASE_URL`, `DASHBOARD_SESSION_SECRET` (genéralo tú), `DASHBOARD_BIND_IP`, `DASHBOARD_COOKIE_SECURE` | — | — |
| 4 | `docker compose build dashboard` (si falla por memoria, compílalo en la PC: README) y `docker compose up -d dashboard` | `docker compose ps dashboard` → healthy; el registro dice "rol de solo lectura comprobado" | prueba una vez con `DASHBOARD_DATABASE_URL` del rol propietario: el servicio **no arranca** y dice qué permisos sobran (luego vuelve a la correcta) |
| 5 | Entrar por túnel SSH o Tailscale (README, paso 5) | la pantalla de contraseña; con tu contraseña ves el mes actual | contraseña mala → «Contraseña incorrecta.»; 5 fallos → bloqueo 15 min |
| 6 | Comparar con Claude | los totales del mes coinciden con `get_summary`; bolsas con `get_bolsa_status`; metas con `get_goal_progress`; movimientos con `list_transactions` | un gasto anulado se ve marcado y no suma |
| 7 | Acceso público | — | desde datos móviles **sin** Tailscale: `https://mcp.puropockets.space/` y `/api/summary` → 404; `http://<IP pública>:8080` no responde; `curl -I http://127.0.0.1:8080/api/summary` en el homelab → 401 |
| 8 | Navegador | en las herramientas de desarrollo: `localStorage` solo con `pp-theme`, sin cookies legibles por JavaScript (`document.cookie` vacío), sin peticiones a otros dominios | — |
| 9 | Memoria | `docker stats --no-stream` del servicio `dashboard` (anótalo en la tabla del plan técnico) | — |
| 10 | Reinicio | tras reiniciar el homelab, `dashboard` vuelve solo (`restart: unless-stopped`) | — |

## 4. Hallazgo fuera del alcance (para decidir) 👤 Propietario

`test_archivar_y_transferir_hacia_ella_a_la_vez` (Hito 8) falla de forma intermitente porque
Postgres detecta un **interbloqueo** entre `archive_bolsa` y `transfer_between_bolsas` lanzados a la
vez sobre la misma bolsa (`psycopg.errors.DeadlockDetected` en el hilo de la transferencia, que la
prueba no captura). Postgres aborta una de las dos operaciones, así que **no queda nada a medias** y
el invariante cuadra, pero la operación abortada termina con un error interno
(`OperationalError`) y no con un mensaje de negocio.
El código involucrado (`services/flex.py`, `db/ledger_store.py`) es de los Hitos 7 a 9 y este hito
no lo toca (sin cambios en archivos existentes de `src/`); por la regla de no modificar hitos
anteriores, queda sin corregir. Sugerencia para un hito siguiente: revisar que `archive_bolsa` siga el
mismo orden de bloqueos que las transferencias ("guardia, bolsas, filas", plan técnico, Hito 9) y
que la prueba capture cualquier excepción del hilo.

## 5. Publicación por Cloudflare + Access (decisión del 2026-11-12)

### Equipo de desarrollo ✅ Claude

`tests/unit/test_dashboard_cloudflare.py` (**32 pruebas**, tokens firmados con claves RSA de prueba):

| Positivas | Negativas |
|---|---|
| con token válido (cabecera o cookie `CF_Authorization`) se llega a la contraseña, que sigue siendo obligatoria (401 sin sesión); el inicio de sesión acepta el origen `https://dash.puropockets.space`; cookie Secure; HSTS; el acceso local (túnel SSH) funciona sin Access; configuración completa | **sin token → 403** en `/`, `/healthz`, `/api/*`, estáticos y en el inicio de sesión con la contraseña correcta (sin cookie); **token vencido, de otra aplicación (AUD), de otro equipo (emisor), firmado con otra clave, HS256, sin `exp` o basura → 403**; **sin claves de Cloudflare (sin red) → 403** (falla cerrada); cabecera de Cloudflare en otro nombre exige Access; **sin modo público, cualquier petición con `CF-Ray`, `CF-Connecting-IP` o `Cf-Access-Jwt-Assertion` → 403**; otro origen en el inicio de sesión → 403; **el límite de intentos cuenta por `CF-Connecting-IP`** (una IP bloqueada no bloquea a otra); configuración incompleta o inválida (sin AUD, sin equipo, equipo con `https://` o fuera de `cloudflareaccess.com`, nombre con esquema) → no arranca |

### Homelab 👤 Propietario

Respaldo con `pg_dump` primero (sección 3). Luego `git pull`, `docker compose build dashboard` y los
pasos del README, "Dashboard", sección 6 (Access **antes** que el nombre público).

| # | Positiva | Negativa |
|---|---|---|
| 1 | El registro dice "Publicado por Cloudflare … con Cloudflare Access obligatorio" | Antes de crear la aplicación de Access, con el nombre público ya puesto: `https://dash.puropockets.space` → 403 «Acceso no autorizado.» (no deberías hacerlo en ese orden, pero si pasa, no se expone nada) |
| 2 | Desde el celular con datos móviles: correo → código → contraseña → resumen | Con otro correo: Cloudflare no da acceso |
| 3 | Los totales coinciden con `get_summary` | `curl` sin pasar Access a `/api/summary` → 302 a Cloudflare, nunca datos |
| 4 | El túnel SSH sigue funcionando | `https://mcp.puropockets.space/` → 404 |
| 5 | Tras 5 contraseñas malas desde el celular, ese dispositivo queda bloqueado 15 min y la PC no | — |
