# Plan del Hito 10: Dashboard y estadísticas

**Rama:** `hito-10-dashboard` · **Spec:** [spec.md](spec.md) · **Progreso:** [progreso.md](progreso.md)

Plan delgado (sección 1 de `HITOS.md`): decisiones técnicas, contrato de la API y estructura. Sin
migración: el hito no cambia el esquema.

## 1. Decisiones técnicas

| Tema | Decisión |
|---|---|
| Framework de la API | FastAPI (`fastapi>=0.162.5`, sobre el Starlette 1.10 que ya trae `mcp==2.3.0`) servido con uvicorn. [DECIDIDO] por el propietario |
| Capa de lectura | `services/dashboard.py` (`DashboardService`) compone `LedgerService` y llama a sus lecturas públicas (`get_summary`, `get_bolsa_status`, `get_goal_progress`, `list_transactions`, `top_categories`, `list_pending_recurring`). No hubo que extraer nada de las tools: ya eran delgadas. Ninguna lectura escribe (el almacén lee con `engine.connect()`) |
| Cálculos nuevos | Funciones puras en `domain/stats.py`: `month_saved` (P2), `estimate_goal_month` (P1), `pocket_alert` (P4), `trailing_months`. Sin `float`; reciben las mismas entradas que `pocket_figures`. P3 es una suma de los `available` que ya entrega `get_summary`, en el servicio |
| Transferencias con motivo | "Ahorrado" necesita distinguir `cierre_de_mes`: se leen con `list_transfers(mes, None, límite)` del almacén existente (ya devuelve el motivo) |
| Evolución | Ingresos con `base_income_total + extra_income_total` (lo mismo que `get_summary`), gastado con los gastos vigentes del mes, ahorrado con `month_saved` |
| Sesión | Cookie `pp_session` = `base64url(json{sid, exp}).base64url(HMAC-SHA256)` con `DASHBOARD_SESSION_SECRET`; `hmac.compare_digest`; 12 h; HttpOnly, SameSite=Strict, Path=/, Secure = `DASHBOARD_COOKIE_SECURE` (por defecto `true`). Cierre de sesión: borra la cookie y revoca `sid` en memoria (P8). Sin tablas |
| Contraseña | `services.passwords.PasswordVerifier` con `OWNER_PASSWORD_HASH` (Hito 3) y `scripts/hash_password.py`. Sin hash válido, la API no arranca |
| Límite de intentos | `domain.auth.LoginRateLimiter` (Hito 3), instancia propia: 5 fallos por IP en 15 min y 20 globales. La IP es la del socket (`request.client.host`); no se confía en `X-Forwarded-For` ni `CF-Connecting-IP` porque no hay proxy delante. 429 con `Retry-After` |
| CSRF | SameSite=Strict, `POST` solo con `Content-Type: application/json` (login) y, si llega `Origin`, debe ser el mismo origen (403) |
| Verbos | Middleware: en `/api`, `GET` (y `HEAD`) salvo `POST /api/session/login` y `POST /api/session/logout`; cualquier otro → 405. Fuera de `/api`, solo `GET`/`HEAD`. Luego, sin sesión → 401 (también rutas inexistentes, para no revelar cuáles existen) |
| Rol de solo lectura | `api/readonly.py` comprueba al arrancar, con `pg_catalog` (ve también las tablas sin permiso): ninguna tabla de `public` con `INSERT`, `UPDATE`, `DELETE`, `TRUNCATE`, `REFERENCES` o `TRIGGER`; ninguna `oauth_*` con `SELECT`; ninguna secuencia con `USAGE`/`UPDATE`; sin `CREATE` en `public`; no superusuario. Si falla, sale con error y sin servir. Conexiones con `default_transaction_read_only=on`. `DASHBOARD_DATABASE_URL` es obligatoria y no cae a `DATABASE_URL` |
| `scripts/create_dashboard_role.sql` | Crea `puro_dashboard` (LOGIN, sin superusuario, sin crear bases ni roles, `NOINHERIT`), `default_transaction_read_only`, `CONNECT`, `USAGE` en `public` y `SELECT` solo en las 12 tablas de negocio que se leen (sin `idempotency_keys`, `alembic_version` ni `oauth_*`). Sin contraseñas: el propietario la fija con `\password` |
| Cabeceras | Middleware: `Content-Security-Policy: default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'; object-src 'none'`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`, `X-Frame-Options: DENY`, `Cache-Control: no-store` en `/api`. `'unsafe-inline'` en estilos porque Recharts escribe atributos `style`; scripts sin excepciones. Sin CORS |
| Registros | Sin registro de acceso de uvicorn (la consulta lleva nombres de bolsa); una línea propia por petición: método, ruta sin consulta, estado y duración. Errores de dominio → 400 con el mensaje en español (ya sin montos); otros → 500 genérico |
| Frontend | `web/`: React 19 + Vite + TypeScript + Tailwind 4 (`@tailwindcss/vite`) + convenciones de shadcn/ui (`components.json`, `cn` con `clsx` y `tailwind-merge`, tokens de `globals.css`) + Recharts + `lucide-react`. Sin fuentes externas (pila del sistema), sin analíticas. Datos solo en memoria; el mes en `?month=`; el tema en `localStorage` (`pp-theme`) |
| Datos de ejemplo | `web/src/test/fixtures.ts` (de `docs/dashboard.md` §15) solo lo importan las pruebas; una prueba comprueba que la compilación no los contiene |
| Despliegue | `Dockerfile.dashboard` en dos etapas (`node:22-alpine` compila `web/`; `python:3.14-slim` con uv sirve la API y `web/dist`). Servicio `dashboard` con perfil `dashboard`, puerto `${DASHBOARD_BIND_IP:-127.0.0.1}:${DASHBOARD_PORT:-8080}:8080`, healthcheck a `/healthz`, `restart: unless-stopped`, `depends_on: db`. El túnel no lo conoce (su nombre público solo apunta a `mcp:8000`) |
| Memoria del homelab | La compilación de Vite usa < 1 GB en la PC; si en el homelab no cabe, se compila la imagen en la PC y se copia con `docker save | ssh … docker load` (P5, README) |
| CI | Job nuevo `web`: `npm ci`, `lint`, `typecheck`, `vitest`. Las pruebas de la API (unitarias) corren con `pytest -m "not integration"`. Playwright y axe solo en el equipo de desarrollo (P6) |

## 2. Fórmulas (plan técnico, sección 13.3)

```
Ahorrado(M) = base(M) + extras(M) + recibidas(M) − enviadas(M) + sobrantes_cierre(M)
  base(M), extras(M)  = Σ asignado a bolsas acumulables por ingresos vigentes base / extra con mes
                        presupuestario M (el saldo inicial no cuenta)
  sobrantes_cierre(M) = Σ transferencias cierre_de_mes con mes M de una bolsa de consumo a una
                        acumulable (sobrantes del cierre de M, RN-47)
  recibidas(M)        = Σ demás transferencias del mes M hacia una acumulable
  enviadas(M)         = Σ transferencias del mes M desde una acumulable (incluye coberturas de
                        cierre desde una acumulable, RN-52)
  Entre dos acumulables, recibida y enviada se anulan. Bolsas archivadas incluidas.
Disponible(M)       = Σ available de las bolsas de consumo de get_summary(M)
Fecha estimada      = mes_actual + ⌈faltante ÷ promedio⌉, solo si projectable y faltante > 0
Alerta de bolsa     = danger si percent_used ≥ 100 o negative; warning si percent_used ≥ 80
```

## 3. Contrato de la API

Todo `GET` acepta `month=AAAA-MM` (por defecto el mes actual en `APP_TIMEZONE`). Montos en colones
enteros; USD como texto (`"25.00"`), igual que las tools. Errores: `{"detail": "<mensaje>"}`.

| Método y ruta | Respuesta (campos) | Fuente |
|---|---|---|
| `GET /healthz` | `{status}`; 503 si la base no responde. Fuera de `/api`, sin sesión | `check_database` |
| `GET /api/session` | `{current_month}` | reloj |
| `POST /api/session/login` | cuerpo `{password}` → 204 y cookie; 401, 429, 400, 403 | Hito 3 |
| `POST /api/session/logout` | 204 y cookie borrada | — |
| `GET /api/summary` | `month, current_month, month_closed, income, extra_income, spent, available, saved, saved_breakdown{base, extra, transfers_in, transfers_out, closure_surplus}, unassigned{count, total_crc, crc_count, crc_total, usd_count, usd_total}, closure_adjustments[{pocket, kind, amount}], pending_closure[{month, has_movements}], alerts[{kind, month?, pocket?, amount?, percent?, count?, crc_total?, usd_total?}]` | `get_summary`, P2, P3, P4 |
| `GET /api/pockets` | `month, month_closed, items[{name, kind, assigned, received, sent, adjusted, spent, available, used, used_original, balance, negative, alert, goal{reference, name, status, target, balance, progress, remaining, excess, monthly_average, projectable, estimated_month} \| null}]` | `get_summary`, `get_bolsa_status`, `get_goal_progress`, P1 |
| `GET /api/movements` | filtros `type, pocket, include_voided (false), page (1..10)` → `items[{ref, type, kind, date, month, description, pocket, from_pocket, to_pocket, category, currency, original_amount, amount_crc, voided, void_reason, pending, reason, note, recurring}], page, page_size, has_more` | `list_transactions` |
| `GET /api/categories` | `month, total, items[{name, value, count, percent}]` (hasta 20) | `top_categories` |
| `GET /api/history` | `months[{month, income, spent, saved}]` (6, el último = `month`) | P2 y totales de `get_summary` |
| `GET /api/fixed` | `month, pending_count, overdue_count, items[{reference, name, currency, amount, amount_crc, status (paid\|pending\|overdue), due_date, expense_reference}]` | `list_pending_recurring` |
| `GET /api/closures/pending` | `items[{month, has_movements}]` | `get_summary` (RN-49) |

## 4. Estructura

```text
src/puro_pockets/
├── domain/stats.py            # P1–P4, evolución (puro)
├── services/dashboard.py      # DashboardService: compone LedgerService
└── api/
    ├── __init__.py
    ├── __main__.py            # python -m puro_pockets.api (uvicorn, sin access log)
    ├── config.py              # DashboardSettings (variables DASHBOARD_*)
    ├── app.py                 # build_app: rutas, middlewares, estáticos
    ├── session.py             # cookie firmada y revocación en memoria
    └── readonly.py            # comprobación del rol al arrancar
scripts/create_dashboard_role.sql
Dockerfile.dashboard
web/                           # frontend (Vite)
├── src/styles/globals.css     # tokens literales (§3)
├── src/lib/{copy,format,labels,utils,api,types,theme}.ts
├── src/components/            # PuroDashboard, Header, Sidebar, Card, … (nombres de §7)
├── src/test/                  # fixtures (mock §15) y pruebas de componentes
└── e2e/                       # Playwright + axe (equipo de desarrollo)
tests/unit/test_stats_domain.py, test_dashboard_service.py, test_dashboard_api.py
tests/integration/test_dashboard_readonly.py
```

## 5. Pruebas

- **Unitarias (CI):** `domain/stats.py` (ahorrado con base, extra, saldo inicial excluido, anulados,
  transferencias, cierre; estimación; alertas); `DashboardService` con `InMemoryLedgerStore`;
  API con `TestClient`: 401 en todas las rutas, 405, login malo y 429, cookie, cabeceras, logout,
  identidad con las tools llamadas por MCP (mismo almacén), anulados, mes cerrado, registros sin
  montos, el MCP sin `/` ni `/api`.
- **Integración (equipo de desarrollo, Postgres temporal):** rol de solo lectura creado en la base
  temporal (rol único `pp_test_dash_*`, borrado al final): arranca y lee; se niega con el rol
  propietario, con `SELECT` en `oauth_*` y con `INSERT` en una tabla de negocio; la API con ese rol
  devuelve lo mismo que las tools.
- **Frontend:** Vitest + Testing Library (formatos, alertas, barras, metas, estados, tema), `tsc`,
  `eslint`; Playwright + axe (anchos, 44 px, claro y oscuro) contra `vite preview` con la API simulada
  por `page.route`.

## 6. Autorrevisión (antes del código)

- **Reglas no negociables:** (1) sin datos reales: todo sintético; (2) las reglas siguen en
  `domain/` y la API no calcula cifras de bolsa: llama a `LedgerService`; los cálculos nuevos van a
  `domain/stats.py`; (3) el invariante 11.4 no se toca (sin escrituras) y su prueba sigue pasando;
  (4) el hito trae sus pruebas, también negativas.
- **RN citadas:** 9.1 y 11.1–11.3 se leen de `pocket_figures`; RN-06, RN-38, RN-48, RN-49, RN-50 y
  RN-53 se muestran tal como las entregan las tools.
- **RN-28 [PROPUESTO]** dice que Claude proyecta la fecha con los números de la app. El propietario
  decidió que la API del dashboard la calcule (P1). No contradice la regla: el MCP sigue sin estimar
  y el dashboard es otro consumidor; se lista como [PROPUESTO] para que el propietario lo confirme.
- **"Ahorrado" y "Disponible"** no son reglas de negocio nuevas: son agregados de cifras oficiales
  (11.1, 11.2, 9) para la pregunta de 13.1; se registran en el plan técnico como [PROPUESTO].
- **Contradicciones de capa alta:** ninguna. `docs/dashboard.md` manda en lo visual; donde describe
  un prototipo (login, avisos fijos, mock) se sigue la constitución y el encargo (tabla D de la
  spec).
