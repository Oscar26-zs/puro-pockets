# Plan técnico de Puro Pockets

**Versión:** 0.5
**Fecha:** 2026-11-09
**Capa:** 2 en la gobernanza de `.specify/memory/constitution.md`. Decide la técnica; si contradice a
la constitución, gana la constitución y se corrige este documento.

Este documento contiene el stack, la arquitectura, el catálogo de tools y el esquema de datos. Las
reglas de negocio no se repiten aquí: se citan por su identificador (`RN-xx`). La numeración de las
secciones 12, 13, 15, 16 y 17 conserva la del documento de origen v0.3
(`docs/origen/CONSTITUCION-origen.md`, archivado). Se actualiza al cerrar cada hito si cambió el
esquema o la arquitectura.

**Hoja de ruta:** el alcance, el orden y los criterios de cierre de cada hito están en
[`HITOS.md`](../HITOS.md). Este documento no copia el mapa de hitos.

---

## Stack

| Área | Elección | Estado |
|---|---|---|
| Lenguaje | Python (3.12 o superior); el proyecto fija 3.14 en `.python-version` y en la imagen `python:3.14-slim` | [DECIDIDO] (decisión 10, Hito 1) |
| Gestor de entornos y dependencias | uv 0.12.5 (fijado en el `Dockerfile` y en el CI), con dependencias fijadas en `uv.lock` | [DECIDIDO] (Hito 1) |
| Base de datos | PostgreSQL **18** en Docker (Docker Compose), imagen `postgres:18-alpine` (nunca `latest`), con volumen persistente y puerto atado a `127.0.0.1` | [DECIDIDO] (Hito 1) |
| Acceso a datos | SQLAlchemy 2.x con el driver psycopg 3, en modo síncrono (las comprobaciones bloqueantes corren en un hilo; ver `specs/001-cimientos/research.md`, R3) | [DECIDIDO] (Hito 1) |
| Migraciones | Alembic | [DECIDIDO] |
| Servidor MCP | Transporte Streamable HTTP desde el Hito 1, publicado solo en `127.0.0.1`; remoto por HTTPS desde el Hito 2 | [DECIDIDO] (decisión 9, Hito 1) |
| SDK de MCP | `mcp==2.3.0` (versión exacta); servidor con `MCPServer` importada desde `mcp.server.mcpserver`. Verificado el 2026-11-09 en PyPI y en la guía oficial de migración v1 → v2, y confirmado al implementar el Hito 1 (prueba de humo `tests/unit/test_sdk_import.py`). Protección contra DNS rebinding configurada de forma explícita para hosts locales. | [DECIDIDO] (Hito 1) |
| Verificación automática (CI) | En cada push a GitHub: ruff y pruebas unitarias. Las pruebas de integración corren en local. | [DECIDIDO] (Hito 1) |
| Publicación | Túnel con nombre de Cloudflare (remotamente administrado), contenedor `cloudflare/cloudflared:2026.10.3`, hacia `https://mcp.puropockets.space` (ver "Acceso remoto") | [DECIDIDO] (decisión 9, Hito 2) |
| Autenticación del MCP | OAuth 2.1: el MCP es servidor de recursos y también servidor de autorización (ver "Autenticación OAuth") | [DECIDIDO] (Hito 3) |
| Servidor de autorización de OAuth | Propio y mínimo, para un único usuario, sobre el módulo de autenticación del SDK `mcp==2.3.0`; contraseña con argon2 (`argon2-cffi`) | [DECIDIDO] (Hito 3) |
| Pruebas y estilo | pytest y ruff; CI en GitHub Actions | [DECIDIDO] (Hito 1) |
| Dashboard | React + Vite + TypeScript + Tailwind, con una librería de gráficos | [PROPUESTO] (sección 16) |
| API del dashboard | Framework por decidir | [ABIERTO]: se resuelve en el Hito 10 |
| Ejecución | Homelab del propietario | [DECIDIDO] |

### Convención de idioma [DECIDIDO] (Hito 1)

- **En inglés:** nombres de código (módulos, clases, funciones, variables), tablas, columnas y tools
  MCP.
- **En español:** documentación y mensajes que ve el usuario (incluidos los mensajes de error que
  devuelven las tools).
- El esquema de referencia de la sección 17 y la tabla concepto → tabla todavía usan nombres del
  borrador en español; se pasan al inglés antes de crear cada tabla.

### Actualizar el SDK de MCP

Actualizar el SDK es una decisión deliberada, nunca automática:

1. Cambiar el número de versión de `mcp` en `pyproject.toml` y regenerar `uv.lock`.
2. Correr todas las pruebas (unitarias, de integración y la prueba de humo que importa `MCPServer`
   desde `mcp.server.mcpserver`).
3. Anotar en este documento la nueva versión, la fecha de verificación y la ruta de importación.

### Medición de memoria

- **Cuándo:** con los servicios `db` y `mcp` recién levantados y estabilizados (en reposo), y otra
  vez después de 20 llamadas a `ping`.
- **Cómo:** `docker stats --no-stream`, tomando la columna de uso de memoria de cada servicio.
- **Dónde:** en la tabla siguiente, con fecha y equipo. La medición en el homelab se agrega en el
  Hito 2.

| Fecha | Equipo | Servicio | En reposo | Tras 20 `ping` |
|---|---|---|---|---|
| 2026-11-09 | Equipo de desarrollo (Windows 11, Docker Desktop con WSL 2, 7,7 GiB para Docker) | `db` | 25,1 MiB | 27,8 MiB |
| 2026-11-09 | Equipo de desarrollo (Windows 11, Docker Desktop con WSL 2, 7,7 GiB para Docker) | `mcp` | 75,7 MiB | 78,6 MiB |

### Estructura del código (Hito 1)

```text
src/puro_pockets/
├── __main__.py    # arranque: configuración, motor, servicios y servidor MCP
├── config.py      # variables de entorno; error en español si falta alguna
├── domain/        # reglas puras: no importa MCP ni base de datos (prueba de arquitectura)
├── services/      # casos de uso (p. ej. comprobación de salud con tiempo límite)
├── db/            # motor de SQLAlchemy y acceso a la base
└── mcp/           # MCPServer y tools delgadas que llaman a services
migrations/        # Alembic (0001_base sin tablas)
tests/unit/        # corren en el CI
tests/integration/ # requieren docker compose up; corren en el equipo de desarrollo
scripts/ping.py    # cliente de prueba por Streamable HTTP
```

Servicios de Docker Compose: `db` (`postgres:18-alpine`, volumen `pgdata` en `/var/lib/postgresql`,
puerto `127.0.0.1:5432`, healthcheck con `pg_isready`) y `mcp` (imagen propia, puerto
`127.0.0.1:8000`, arranca cuando `db` está healthy). Desde el equipo, la URL de la base usa
`127.0.0.1` y no `localhost` (en Windows, `localhost` intenta IPv6 primero y cada conexión tardaba
5 segundos).

### Acceso remoto [DECIDIDO] (Hito 2)

- **Dominio:** `puropockets.space`, registrado en Namecheap, con el DNS gestionado por Cloudflare.
- **Subdominio del MCP:** `mcp.puropockets.space`. URL del conector de claude.ai:
  `https://mcp.puropockets.space/mcp` (sin autenticación hasta el Hito 3).
- **Recorrido:** Claude → Cloudflare → túnel (servicio `cloudflared` de Compose, en el homelab) →
  `http://mcp:8000` por la red interna de Docker → servidor MCP. El homelab no abre puertos hacia
  internet; `mcp` y `db` solo publican puertos en `127.0.0.1`.
- **Túnel:** remotamente administrado (nombre público configurado en el panel de Cloudflare:
  `mcp.puropockets.space` → `HTTP mcp:8000`, sin cambiar el *HTTP Host Header*). Imagen
  `cloudflare/cloudflared:2026.10.3`, comando `tunnel --no-autoupdate --metrics 0.0.0.0:20241 run`.
  El token se lee de `CF_TUNNEL_TOKEN` en el `.env` del homelab y llega al contenedor como
  `TUNNEL_TOKEN`; nunca se guarda en el repositorio.
- **Activación:** el servicio `cloudflared` tiene el perfil `tunnel`; solo arranca donde
  `COMPOSE_PROFILES=tunnel` (el homelab). En el equipo de desarrollo no arranca.
- **Hosts y orígenes permitidos** (protección contra DNS rebinding del SDK; `Host` inválido → 421,
  `Origin` inválido → 403, sin `Origin` → permitido):
  - Hosts: `127.0.0.1:*`, `localhost:*`, `[::1]:*` y el valor de `MCP_PUBLIC_HOSTNAME`
    (`mcp.puropockets.space` y `mcp.puropockets.space:*`).
  - Orígenes: los locales (`http://127.0.0.1:*`, etc.), `https://mcp.puropockets.space` y los de
    `MCP_ALLOWED_ORIGINS` (documentado: `https://claude.ai,https://claude.com`).
- **Reinicio:** `restart: unless-stopped` en `db`, `mcp` y `cloudflared`; Docker habilitado al
  arranque del sistema en el homelab.
- **Salud:** `db` con `pg_isready`; `mcp` con `python scripts/ping.py` dentro del contenedor;
  `cloudflared` con `cloudflared tunnel --metrics 127.0.0.1:20241 ready` (consulta `/ready`). El túnel
  arranca cuando `mcp` está healthy.
- **Operación:** pasos manuales, actualización del despliegue y comprobación de salud en el README
  ("Despliegue en el homelab").


### Autenticación OAuth [DECIDIDO] (Hito 3)

- **Servidor de autorización:** propio y mínimo, para un único usuario (el propietario), dentro del
  mismo servidor MCP. El SDK aporta los endpoints, PKCE S256 y la validación Bearer; el proyecto aporta
  el proveedor (`services/oauth.py`), el almacén SQL (`db/oauth_store.py`) y la página de inicio de
  sesión (`mcp/login.py`).
- **Endpoints** (emisor `https://mcp.puropockets.space`): `/authorize`, `/token`, `/revoke`,
  `/register` (solo con el registro abierto), `/login`, `/.well-known/oauth-authorization-server`
  (RFC 8414) y `/.well-known/oauth-protected-resource/mcp` (RFC 9728, recurso
  `https://mcp.puropockets.space/mcp`). Sin token, `/mcp` responde 401 con
  `WWW-Authenticate: Bearer ..., resource_metadata="…"`.
- **Clientes:** registro dinámico (RFC 7591) cerrado por defecto (`OAUTH_REGISTRATION_ENABLED`); solo
  clientes públicos (sin secreto), solo URL de retorno de `OAUTH_ALLOWED_REDIRECT_URIS`
  (`https://claude.ai/api/mcp/auth_callback`, `https://claude.com/api/mcp/auth_callback`), máximo
  `OAUTH_MAX_CLIENTS` (10) y 5 registros por hora. Alternativa: cliente propio con
  `scripts/register_client.py`. Claude Code (redirecciones locales) queda fuera.
- **Duraciones** (configurables): acceso 1 hora, refresco 30 días con rotación, código 5 minutos de un
  solo uso. Reutilizar un refresco ya rotado revoca toda su cadena. `OAUTH_SHORT_LIFETIMES=true`:
  acceso 2 minutos y refresco 15 minutos, solo para pruebas.
- **Scopes:** `mcp` (requerido) y `offline_access` (anunciado, para que Claude pida refresco). Los
  tokens se ligan al recurso y se rechazan los de otro recurso (`validate_token_resource=True`).
- **Almacenamiento** (migración `0002_oauth`): `oauth_clients`, `oauth_authorization_codes`,
  `oauth_access_tokens`, `oauth_refresh_tokens`. Solo hashes SHA-256 de códigos y tokens (tokens
  opacos de 256 bits con prefijo `ppc_`, `ppa_`, `ppr_`).
- **Contraseña:** hash argon2id en `OWNER_PASSWORD_HASH` (entre comillas simples en `.env`), generado
  con `scripts/hash_password.py`; los parámetros viajan dentro del hash y se ajustan para que la
  verificación tarde menos de 1 segundo en el homelab (`--benchmark`). Sin hash válido, el inicio de
  sesión queda deshabilitado.
- **Límite de intentos (solo inicio de sesión):** 5 fallos por IP (`CF-Connecting-IP`) en 15 minutos
  bloquean esa IP; 20 fallos globales en 15 minutos bloquean el inicio de sesión 5 minutos. Nunca
  afecta a `/mcp` con token válido.
- **Revocación:** endpoint `/revoke` (RFC 7009) y `scripts/revoke_tokens.py --yes` (todo).
- **Registros:** sin contraseñas, hashes, códigos ni tokens; se registran el dominio de retorno, los
  registros de clientes, los inicios de sesión, los refrescos, las reutilizaciones y las revocaciones.
- **Observaciones del SDK:** el endpoint `/revoke` exige `client_secret` aunque sea vacío para clientes
  públicos (defecto de `RevocationRequest`); se deja documentado y cubierto por una prueba que avisará
  cuando se corrija. La comparación de PKCE y los metadatos `client_secret_*` se dejan como están.
---

## 12. Integración con Claude (MCP)

### 12.1 Catálogo de tools

| Tool | Función | Estado |
|---|---|---|
| `load_initial_balance` | Cargar el saldo inicial repartido por montos entre bolsas (una sola vez). | [DECIDIDO] |
| `add_expense` | Registrar gasto (con moneda y, si es USD, tipo de cambio). Si deja una bolsa en negativo, devuelve advertencia con las bolsas disponibles. | [DECIDIDO] |
| `add_income` | Registrar ingreso base (con moneda y tipo de cambio si aplica). | [DECIDIDO] |
| `register_extra_income` | Registrar ingreso extra en estado pendiente. | [DECIDIDO] |
| `get_allocation_context` | Entregar a Claude el panorama del mes: presupuesto vs gastado por bolsa, fijos pendientes, metas y repartos previos. | [DECIDIDO] |
| `confirm_allocation` | Confirmar el reparto de un extra (valida suma = 100). | [DECIDIDO] |
| `void_transaction` | Anular un ingreso o gasto con motivo, solo en mes abierto. Reemplaza a `update_transaction` y `delete_transaction`. | [DECIDIDO] |
| `get_bolsa_status` | Estado de una bolsa: asignado, transferencias, gastado, disponible y avance de su meta si la tiene. | [DECIDIDO] |
| `get_summary(mes)` | Resumen mensual. | [DECIDIDO] |
| `top_categories` | En qué se gasta más. | [DECIDIDO] |
| `list_transactions` | Listar movimientos con filtros. | [DECIDIDO] |
| `manage_recurring` | Crear, listar y modificar gastos fijos. | [DECIDIDO] |
| `set_allocation` / `update_allocation` | Cambiar porcentajes de un mes. | [DECIDIDO] |
| `preview_rebalance` | Calcular reajuste de porcentajes sin guardar. | [DECIDIDO] |
| `create_bolsa` | Crear bolsa y reajustar porcentajes (atómico). | [DECIDIDO] |
| `archive_bolsa` | Archivar bolsa (exige saldo cero, mediante transferencia previa) y redistribuir porcentaje. | [DECIDIDO] |
| `create_goal` | Crear meta asociada a una bolsa acumulable. | [DECIDIDO] |
| `get_goal_progress` | Avance, faltante, % y fecha estimada de una meta. | [DECIDIDO] |
| `update_goal` | Cambiar monto o fecha, pausar o reactivar. | [DECIDIDO] |
| `preview_transfer` | Simular movimiento entre bolsas (con aviso de efecto en metas). | [DECIDIDO] |
| `transfer_between_bolsas` | Registrar movimiento entre bolsas. | [DECIDIDO] |
| `preview_month_close` | Calcular déficits y sobrantes del mes, con propuesta. | [DECIDIDO] |
| `close_month` | Ejecutar el cierre (atómico). | [DECIDIDO] |

**Tools eliminadas en v0.2:** `contribute_to_goal`, `withdraw_from_goal`, `spend_from_goal`, `update_transaction`, `delete_transaction`. Las metas ya no reciben ni entregan dinero por separado (sección 7), y las correcciones se hacen por anulación (RN-53).

### 12.2 Reglas para las tools
1. Las tools devuelven datos exactos y validan reglas. No dan consejos.
2. Las tools que modifican dinero deben ser **idempotentes** o aceptar una clave de operación, para que una llamada repetida por Claude no duplique un movimiento. **[PROPUESTO]**
3. Las tools destructivas o de reparto piden confirmación del usuario antes de ejecutarse.
4. Las respuestas de error deben ser claras para que Claude pueda explicarlas.
5. Toda tool que reciba un monto en dólares exige el tipo de cambio (RN-57). Si falta, devuelve error en lugar de asumirlo.

---

## 13. Estadísticas y dashboard **[DECIDIDO en intención; detalle PROPUESTO]**

### 13.1 Preguntas que debe responder
- ¿En qué gasto más?
- ¿Cuánto de cada bolsa llevo gastado este mes (% del presupuesto)?
- ¿Cuánto he ingresado al ahorro, y de dónde vino (asignación mensual, extras, sobrantes de cierre)?
- ¿Cuánto ingreso tengo en el mes? (sin contar el saldo inicial)
- ¿Cuáles son mis gastos necesarios y cuáles son fijos?
- ¿Cómo voy en cada meta?

### 13.2 Componentes
- Tarjetas: ingreso del mes, gastado, disponible, ahorrado, ingresos **sin asignar**.
- Barras de progreso por bolsa (usado vs. presupuesto ajustado, con el original como referencia).
- Dona de gasto por categoría.
- Evolución mensual (línea o barras).
- Tabla de últimos movimientos con filtros (los anulados se distinguen visualmente).
- Lista de gastos fijos: pagados y pendientes.
- Tarjeta por meta: barra de progreso basada en el saldo de su bolsa, "faltan ₡X" y fecha estimada.
- Alertas: bolsa por encima de 80 % y 100 %, bolsa en negativo (rojo), cierre de mes pendiente, ingreso pendiente de repartir.
- Totales en colones, con equivalente en dólares opcional.


## 15. Requerimientos no funcionales

- **Privacidad:** Los datos se almacenan en el servidor del propietario. Al usar Claude mediante MCP, la información consultada y registrada transita por Cloudflare y Anthropic, y el propietario acepta ese tránsito. Las tools devuelven solo la información necesaria para cada consulta (minimización).
- **Autenticación:** el endpoint del MCP y el dashboard requieren token o login, aunque sea uso personal.
- **Respaldo:** copia automática y periódica de la base de datos.
- **Simplicidad de uso:** registrar un gasto debe tomar una sola frase a Claude.
- **Liviandad:** debe correr cómodamente en el hardware del homelab (laptop vieja, pocos recursos). Postgres corre en Docker; su consumo de memoria se mide con `docker stats` desde el Hito 1.
- **Calidad:** el invariante de la sección 11.4, las validaciones de sumas (porcentajes = 100) y la conversión de monedas deben estar cubiertos por tests automáticos.

---

## 16. Arquitectura propuesta **[PROPUESTO]**

```
Claude (chat) ──► Servidor MCP ──► PostgreSQL ◄── API ◄── Dashboard (React)
                  (tools)          (datos)
```

- **Base de datos:** PostgreSQL en un contenedor Docker, con volumen persistente.
- **MCP:** en Python, remoto por HTTPS mediante un túnel de Cloudflare (decisiones 9 y 10). El servidor de autorización de OAuth se decide en el Hito 3.
- **Dashboard:** React + Vite + TypeScript + Tailwind, con una librería de gráficos (por ejemplo Recharts).
- **Ejecución:** en el homelab del propietario.

---

## 17. Esquema de datos de referencia (v0.3, borrador, PostgreSQL)

Consolida y reemplaza los borradores anteriores. Es una propuesta técnica: puede ajustarse al implementar, siempre que respete las reglas de este documento.

Convenciones de tipos: identificadores y montos en `BIGINT`; banderas en `BOOLEAN`; fechas de calendario en `DATE`; instantes en `TIMESTAMPTZ`; el mes se guarda como texto de 7 caracteres `'YYYY-MM'` con un `CHECK` de formato.

```sql
-- Bolsas flexibles
CREATE TABLE bolsas (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  nombre TEXT NOT NULL UNIQUE,
  comportamiento TEXT NOT NULL CHECK (comportamiento IN ('consumo','acumulable')),
  grupo TEXT,                                          -- opcional, solo estadísticas
  destino_sobrante_id BIGINT REFERENCES bolsas(id),    -- opcional; debe ser acumulable (se valida en código)
  activa BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE categorias (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  nombre TEXT NOT NULL UNIQUE,
  bolsa_id BIGINT NOT NULL REFERENCES bolsas(id),
  activa BOOLEAN NOT NULL DEFAULT TRUE
);

-- Porcentajes por mes (historial). La app valida que cada mes sume 100.
CREATE TABLE budget_month_allocations (
  mes CHAR(7) NOT NULL CHECK (mes ~ '^[0-9]{4}-(0[1-9]|1[0-2])$'),  -- 'YYYY-MM'
  bolsa_id BIGINT NOT NULL REFERENCES bolsas(id),
  porcentaje INTEGER NOT NULL CHECK (porcentaje BETWEEN 0 AND 100),
  PRIMARY KEY (mes, bolsa_id)
);

-- Ingresos (incluye el saldo inicial como registro especial)
CREATE TABLE ingresos (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  fecha DATE NOT NULL,
  tipo TEXT NOT NULL CHECK (tipo IN ('base','extra','saldo_inicial')),
  fuente TEXT,
  mes_presupuesto CHAR(7) NOT NULL                     -- salario de fin de mes -> mes siguiente
    CHECK (mes_presupuesto ~ '^[0-9]{4}-(0[1-9]|1[0-2])$'),
  moneda TEXT NOT NULL DEFAULT 'CRC' CHECK (moneda IN ('CRC','USD')),
  monto_original BIGINT NOT NULL CHECK (monto_original > 0),  -- CRC: colones; USD: centavos
  tipo_cambio BIGINT,                                  -- colones por USD x100; NULL si moneda = CRC
  monto BIGINT NOT NULL CHECK (monto > 0),             -- equivalente en colones (base de todos los cálculos)
  estado_reparto TEXT NOT NULL DEFAULT 'pendiente'
    CHECK (estado_reparto IN ('pendiente','repartido')),
  nota TEXT,
  anulado BOOLEAN NOT NULL DEFAULT FALSE,
  anulado_en TIMESTAMPTZ,
  motivo_anulacion TEXT,
  CHECK ((moneda = 'CRC' AND tipo_cambio IS NULL) OR (moneda = 'USD' AND tipo_cambio IS NOT NULL))
);

-- Reparto de cada ingreso por bolsa
CREATE TABLE income_allocations (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  ingreso_id BIGINT NOT NULL REFERENCES ingresos(id),
  bolsa_id BIGINT NOT NULL REFERENCES bolsas(id),
  porcentaje INTEGER CHECK (porcentaje BETWEEN 0 AND 100),  -- NULL en el saldo inicial (monto explícito)
  monto BIGINT NOT NULL CHECK (monto >= 0)             -- colones; la última bolsa absorbe el residuo
);

-- Metas: objetivo asociado a una bolsa acumulable. No guardan dinero ni avance.
CREATE TABLE savings_goals (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  bolsa_id BIGINT NOT NULL REFERENCES bolsas(id),      -- debe ser acumulable (se valida en create_goal)
  nombre TEXT NOT NULL,
  monto_objetivo BIGINT NOT NULL CHECK (monto_objetivo > 0),  -- en colones
  fecha_objetivo DATE,                                 -- opcional
  estado TEXT NOT NULL DEFAULT 'activa'
    CHECK (estado IN ('activa','lograda','pausada')),
  fecha_logro DATE                                     -- se llena al pasar a 'lograda'
);
-- Una sola meta activa por bolsa (RN-22, pendiente de confirmar en decisión #11)
CREATE UNIQUE INDEX ux_meta_activa_por_bolsa
  ON savings_goals(bolsa_id) WHERE estado = 'activa';

-- Gastos
CREATE TABLE gastos (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  fecha DATE NOT NULL,
  mes CHAR(7) NOT NULL                                 -- mes calendario de la fecha
    CHECK (mes ~ '^[0-9]{4}-(0[1-9]|1[0-2])$'),
  bolsa_id BIGINT NOT NULL REFERENCES bolsas(id),
  categoria_id BIGINT REFERENCES categorias(id),
  descripcion TEXT,
  moneda TEXT NOT NULL DEFAULT 'CRC' CHECK (moneda IN ('CRC','USD')),
  monto_original BIGINT NOT NULL CHECK (monto_original > 0),
  tipo_cambio BIGINT,
  monto BIGINT NOT NULL CHECK (monto > 0),             -- equivalente en colones
  anulado BOOLEAN NOT NULL DEFAULT FALSE,
  anulado_en TIMESTAMPTZ,
  motivo_anulacion TEXT,
  CHECK ((moneda = 'CRC' AND tipo_cambio IS NULL) OR (moneda = 'USD' AND tipo_cambio IS NOT NULL))
);

-- Gastos fijos mensuales (plantillas)
CREATE TABLE gastos_recurrentes (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  nombre TEXT NOT NULL,
  moneda TEXT NOT NULL DEFAULT 'CRC' CHECK (moneda IN ('CRC','USD')),
  monto_original BIGINT NOT NULL CHECK (monto_original > 0),
  dia_del_mes INTEGER NOT NULL CHECK (dia_del_mes BETWEEN 1 AND 31),
  bolsa_id BIGINT NOT NULL REFERENCES bolsas(id),
  categoria_id BIGINT REFERENCES categorias(id),
  activo BOOLEAN NOT NULL DEFAULT TRUE
);

-- Libro mayor de transferencias entre bolsas (inmutable; siempre en colones)
CREATE TABLE transfers (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  fecha DATE NOT NULL,
  mes CHAR(7) NOT NULL                                 -- mes presupuestario
    CHECK (mes ~ '^[0-9]{4}-(0[1-9]|1[0-2])$'),
  from_bolsa_id BIGINT NOT NULL REFERENCES bolsas(id),
  to_bolsa_id BIGINT NOT NULL REFERENCES bolsas(id),
  monto BIGINT NOT NULL CHECK (monto > 0),
  motivo TEXT NOT NULL CHECK (motivo IN
    ('cubrir_sobregasto','reasignacion','cierre_de_mes','ajuste')),
  nota TEXT,
  CHECK (from_bolsa_id <> to_bolsa_id)
);

-- Estado de cada mes
CREATE TABLE month_closures (
  mes CHAR(7) PRIMARY KEY CHECK (mes ~ '^[0-9]{4}-(0[1-9]|1[0-2])$'),
  estado TEXT NOT NULL DEFAULT 'abierto' CHECK (estado IN ('abierto','cerrado')),
  cerrado_en TIMESTAMPTZ
);

-- Sobrantes no destinados y sobregastos no cubiertos al cerrar
CREATE TABLE closure_adjustments (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  mes CHAR(7) NOT NULL REFERENCES month_closures(mes),
  bolsa_id BIGINT NOT NULL REFERENCES bolsas(id),
  tipo TEXT NOT NULL CHECK (tipo IN ('sobrante_no_destinado','sobregasto_no_cubierto')),
  monto BIGINT NOT NULL                                -- con signo: sobrante +, sobregasto -
);
```

**Cambios en v0.3:** traducción técnica a PostgreSQL (sin `PRAGMA`; `BOOLEAN`, `DATE`/`TIMESTAMPTZ`, `BIGINT`; mes como `CHAR(7)` con `CHECK` de formato). No cambia ninguna regla.

**Cambios respecto a v0.1:** se eliminan `goal_movements` y los campos `goal_id` de `gastos` y `transfers` (la meta ya no tiene dinero propio); se agregan campos de moneda, anulación y saldo inicial; se agrega `fecha_logro` a las metas.

**Validaciones que viven en el código (no en el esquema):**
- Cada mes suma 100 % en `budget_month_allocations` (RN-01).
- Las metas solo se asocian a bolsas `acumulable` (RN-21).
- No se transfiere más del saldo o disponible de la bolsa de origen (RN-42).
- Un mes cerrado no admite movimientos nuevos ni anulaciones (RN-44, RN-48, RN-53).
- Una bolsa solo se archiva con saldo cero (RN-18).
- El saldo inicial se carga una sola vez (RN-54).
- La conversión USD → CRC usa el tipo de cambio guardado y redondeo half-up (RN-57).
- Las operaciones compuestas (crear bolsa, cerrar mes, anular un ingreso ya repartido) se ejecutan en una sola transacción.

---

## Concepto → tabla

La constitución habla en conceptos de negocio; esta tabla los lleva a las tablas y columnas del
esquema de la sección 17, con los valores que se guardan para estados, tipos y motivos.

| Concepto (constitución) | Tabla / columna | Valores que se guardan |
|---|---|---|
| Bolsa | `bolsas` | — |
| Comportamiento de la bolsa (RN-10) | `bolsas.comportamiento` | `consumo`, `acumulable` |
| Bolsa inactiva (archivada, RN-16) | `bolsas.activa` | `TRUE` activa, `FALSE` archivada |
| Grupo de la bolsa | `bolsas.grupo` | texto libre u omitido |
| Destino de sobrante sugerido (6.5) | `bolsas.destino_sobrante_id` | id de una bolsa acumulable u omitido |
| Categoría | `categorias` (`activa`) | `TRUE`, `FALSE` |
| Los porcentajes de cada mes (RN-01 a 03) | `budget_month_allocations` | `porcentaje` entre 0 y 100 |
| Ingreso | `ingresos` | — |
| Tipo de ingreso: base, extra, saldo inicial (5.1, 5.3, RN-54) | `ingresos.tipo` | `base`, `extra`, `saldo_inicial` |
| Mes presupuestario (5.1, RN-09) | `ingresos.mes_presupuesto` | `'YYYY-MM'` |
| Estado del reparto de un ingreso (RN-06) | `ingresos.estado_reparto` | `pendiente`, `repartido` |
| Moneda (RN-55) | `ingresos.moneda`, `gastos.moneda`, `gastos_recurrentes.moneda` | `CRC`, `USD` |
| Monto original y tipo de cambio (RN-57) | `monto_original`, `tipo_cambio`, `monto` | CRC en colones; USD en centavos; tipo de cambio en colones por USD × 100 |
| Lo asignado a la bolsa por los ingresos del mes (11.1) | `income_allocations.monto` | colones enteros |
| Gasto | `gastos` | — |
| Mes calendario del gasto (RN-32) | `gastos.mes` | `'YYYY-MM'` |
| Anulación con registro (RN-53) | `anulado`, `anulado_en`, `motivo_anulacion` en `ingresos` y `gastos` | `anulado`: `TRUE`, `FALSE` |
| Gasto fijo mensual (8.1) | `gastos_recurrentes` (`activo`) | `TRUE`, `FALSE` |
| Meta de ahorro (sección 7) | `savings_goals` | — |
| Estado de una meta (RN-24) | `savings_goals.estado` | `activa`, `lograda`, `pausada` |
| El registro de transferencias (RN-40) | `transfers` | — |
| Motivo de una transferencia (sección 9) | `transfers.motivo` | `cubrir_sobregasto`, `reasignacion`, `cierre_de_mes`, `ajuste` |
| Estado del mes (RN-49) | `month_closures.estado` | `abierto`, `cerrado` |
| Ajustes de cierre (RN-50, 10.2) | `closure_adjustments.tipo` | `sobrante_no_destinado`, `sobregasto_no_cubierto` |

**Idioma de los nombres:** decidido en el Hito 1: inglés (ver "Convención de idioma"). Los nombres
de esta tabla y de la sección 17 son los del borrador de referencia y se pasan al inglés antes de
crear cada tabla.

---

## Registro de cambios

| Versión | Fecha | Cambio |
|---|---|---|
| 0.1 | 2026-11-09 | Primera versión: secciones 12, 13, 15, 16 y 17 del documento de origen v0.3, stack decidido, tabla concepto → tabla y enlace a `HITOS.md`. |
| 0.2 | 2026-11-09 | Decisiones del Hito 1 (clarificación de `specs/001-cimientos`): SDK `mcp==2.3.0` con `MCPServer`, Streamable HTTP desde el Hito 1, uv, PostgreSQL 18, alcance del CI, convención de idioma (inglés en código y base; español en documentación y mensajes), procedimiento para actualizar el SDK y medición de memoria. |
| 0.3 | 2026-11-09 | Cierre del Hito 1: Python 3.14 y uv 0.12.5 fijados, driver psycopg 3 en modo síncrono, confirmación del SDK al implementar, medición de memoria en el equipo de desarrollo, estructura del código y servicios de Compose. |
| 0.4 | 2026-11-09 | Hito 2: dominio `puropockets.space` y subdominio `mcp.puropockets.space`; túnel de Cloudflare como servicio de Compose (perfil `tunnel`, cloudflared 2026.10.3); hosts y orígenes públicos permitidos; reinicio automático y healthchecks. |
| 0.5 | 2026-11-09 | Hito 3: servidor de autorización OAuth propio (decisión pendiente resuelta), endpoints, clientes, duraciones, scopes, tablas `0002_oauth`, argon2, límite de intentos y revocación. |
