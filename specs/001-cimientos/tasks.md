# Tasks: Cimientos del proyecto

**Input**: Design documents from `/specs/001-cimientos/`
**Prerequisites**: plan.md, spec.md, research.md, contracts/ping.md, quickstart.md

**Tests**: OBLIGATORIAS. La spec las pide de forma explícita (FR-010, FR-011, FR-012, FR-018) y la
gobernanza las exige (regla no negociable 4). Dentro de cada historia, las pruebas se escriben
antes que la implementación y deben fallar primero.

**Organization**: tareas agrupadas por historia de usuario (US1 a US4 de spec.md).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: se puede hacer en paralelo (archivos distintos, sin dependencias pendientes)
- **[Story]**: historia a la que pertenece (US1, US2, US3, US4)

## Path Conventions

Proyecto único con layout `src/`: `src/puro_pockets/`, `tests/unit/`, `tests/integration/`,
`migrations/` y `scripts/` en la raíz. Nombres de código en inglés; mensajes al usuario y
documentación en español (FR-016).

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: inicializar el proyecto Python y su configuración.

- [X] T001 Crear `pyproject.toml`: nombre `puro-pockets`, paquete `puro_pockets` en `src/`, `requires-python = ">=3.12"`, dependencias `mcp==2.3.0` (exacta, FR-018), `sqlalchemy>=2.0`, `psycopg[binary]>=3.2`, `alembic>=1.13`; grupo `dev` con `pytest` y `ruff`; `[tool.ruff]` con `line-length = 100` y reglas `E,F,I,UP,B`; `[tool.pytest.ini_options]` con `testpaths = ["tests"]`, `pythonpath = ["src"]` y marcador `integration` ("requiere los servicios levantados")
- [X] T002 Crear el esqueleto de paquetes con `__init__.py` en `src/puro_pockets/`, `src/puro_pockets/domain/`, `src/puro_pockets/services/`, `src/puro_pockets/db/`, `src/puro_pockets/mcp/`, y las carpetas `tests/unit/`, `tests/integration/`, `scripts/`
- [X] T003 Generar `uv.lock` con `uv lock` y comprobar `uv sync` (FR-013)
- [X] T004 [P] Actualizar `.env.example`: `DATABASE_URL` con driver `postgresql+psycopg://`, variante para el equipo (`localhost`) y nota de que dentro de Compose el host es `db`; agregar `MCP_HOST`/`MCP_PORT` y `DB_CONNECT_TIMEOUT` (por defecto 2); sin valores reales (FR-009)
- [X] T005 [P] Verificar que `.gitignore` excluye `.env` y no excluye `.env.example` (`git check-ignore`)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: piezas que necesitan todas las historias.

- [X] T006 Implementar `src/puro_pockets/config.py`: `Settings` (dataclass) leída de variables de entorno (`DATABASE_URL`, `MCP_HOST` por defecto `127.0.0.1`, `MCP_PORT` por defecto `8000`, `DB_CONNECT_TIMEOUT` por defecto `2`); si falta `DATABASE_URL`, lanzar un error con mensaje en español que nombre la variable sin mostrar valores. Prueba unitaria en `tests/unit/test_config.py`: variable faltante → error que nombra `DATABASE_URL`; valores por defecto de host, puerto y tiempo límite (caso borde de la spec)
- [X] T007 [P] Implementar `src/puro_pockets/domain/health.py`: `HealthStatus` (dataclass inmutable) con `server: Literal["ok"]`, `database: Literal["ok", "error"]`, `detail: str | None`, y constructores `HealthStatus.database_ok()` y `HealthStatus.database_error(detail)`; sin importar `mcp`, `sqlalchemy`, `psycopg` ni otras capas (FR-010)
- [X] T008 [P] Implementar `src/puro_pockets/db/engine.py`: `create_engine_from_settings(settings)` con `create_engine` (modo síncrono, ver R3), `pool_pre_ping=True` y `connect_args={"connect_timeout": settings.db_connect_timeout}` (R3); función `check_database(engine) -> None` que ejecuta `SELECT 1` y deja propagar la excepción
- [X] T009 [P] Crear `Dockerfile`: base `python:3.14-slim`, binario de uv copiado desde `ghcr.io/astral-sh/uv` con versión fijada, `uv sync --frozen --no-dev`, copiar `src/`, `migrations/`, `alembic.ini`; usuario no root; `CMD` que ejecuta `python -m puro_pockets`
- [X] T010 Crear `docker-compose.yml`: servicio `db` con `postgres:18-alpine` (FR-021), variables `POSTGRES_*` desde `.env`, volumen nombrado `pgdata` montado en `/var/lib/postgresql` (R4), puerto `127.0.0.1:${POSTGRES_PORT:-5432}:5432` (FR-002), healthcheck `pg_isready`; servicio `mcp` con `build: .`, `DATABASE_URL` apuntando al host `db`, `MCP_HOST=0.0.0.0` dentro del contenedor, puerto `127.0.0.1:${MCP_PORT:-8000}:8000`, `depends_on: db: condition: service_healthy` (FR-004)
- [X] T011 Inicializar Alembic: `alembic.ini` (sin URL fija), `migrations/env.py` que toma la URL de `DATABASE_URL` (modo síncrono con psycopg), `migrations/script.py.mako`

**Checkpoint**: `docker compose up -d --build` levanta `db` (healthy) y `mcp` arranca.

---

## Phase 3: User Story 1 - Levantar el proyecto y comprobar que está vivo (Priority: P1) 🎯 MVP

**Goal**: un comando levanta todo, las migraciones se aplican y revierten, y `ping` informa el estado del servidor y de la base (contrato en `contracts/ping.md`).

**Independent Test**: `docker compose up -d --build`, `docker compose exec mcp alembic upgrade head`, `uv run python scripts/ping.py` → `{"server": "ok", "database": "ok", "detail": null}`.

### Tests for User Story 1 ⚠️

> Escribir primero y comprobar que fallan.

- [X] T012 [P] [US1] Prueba unitaria del dominio en `tests/unit/test_domain_health.py`: `database_ok()` da `server="ok"`, `database="ok"`, `detail=None`; `database_error("x")` da `database="error"`, `detail="x"`
- [X] T013 [P] [US1] Prueba de humo en `tests/unit/test_sdk_import.py`: `from mcp.server.mcpserver import MCPServer` funciona y la versión instalada de `mcp` es `2.3.0` (FR-018)
- [X] T014 [P] [US1] Prueba unitaria de la tool en `tests/unit/test_ping_tool.py`: con `Client(build_server(HealthService(comprobador_falso, timeout_seconds=2)))` en memoria, donde el comprobador falso (a) no falla → `structured_content == {"server": "ok", "database": "ok", "detail": None}`; (b) lanza error → `database == "error"`, `detail` en español y sin la URL, el usuario ni la contraseña (FR-007, FR-008); (c) tarda más que el límite → `database == "error"` en menos de 5 s
- [X] T015 [P] [US1] Prueba de integración en `tests/integration/test_ping_http.py` (marcador `integration`): `Client("http://127.0.0.1:8000/mcp")` llama a `ping` → `database == "ok"` en menos de 2 s (SC-004)
- [X] T016 [P] [US1] Prueba de integración en `tests/integration/test_ping_db_down.py` (marcador `integration`): servicio de salud con un motor apuntando a un puerto cerrado de `127.0.0.1` → `database == "error"` en menos de 5 s y `detail` sin datos de conexión (FR-007, SC-004)
- [X] T017 [P] [US1] Prueba de integración en `tests/integration/test_migrations.py` (marcador `integration`): con la API de comandos de Alembic contra la base levantada: `upgrade head` dos veces, `downgrade base`, `upgrade head`, sin errores; al final la versión es la de `0001_base` (FR-005, SC-003)

### Implementation for User Story 1

- [X] T018 [US1] Implementar `src/puro_pockets/services/health.py`: `HealthService(checker, timeout_seconds)` con `async check() -> HealthStatus`; ejecuta el comprobador dentro de `asyncio.timeout`; ante tiempo agotado o cualquier excepción devuelve `HealthStatus.database_error(...)` con mensaje fijo en español ("La base de datos no respondió en N segundos." o "No se pudo conectar con la base de datos."), nunca el texto de la excepción (FR-008)
- [X] T019 [US1] Implementar `src/puro_pockets/mcp/server.py`: modelo Pydantic `PingResult` (`server`, `database`, `detail`), `build_server(health_service) -> MCPServer` que registra la tool `ping` (`@mcp.tool()`, `async`, docstring en español) y devuelve `PingResult`; `run(settings)` con `transport="streamable-http"`, `host`, `port` (FR-006); revisar `transport_security` para aceptar `Host` `127.0.0.1`/`localhost` (R1)
- [X] T020 [US1] Implementar `src/puro_pockets/__main__.py`: carga `Settings`, crea el motor y el `HealthService`, construye y arranca el servidor
- [X] T021 [US1] Crear la migración base `migrations/versions/0001_base.py` (`revision = "0001_base"`), sin tablas; `upgrade` y `downgrade` vacíos
- [X] T022 [US1] Crear el cliente de prueba `scripts/ping.py`: llama a `ping` por HTTP (URL desde `MCP_PORT`, por defecto `http://127.0.0.1:8000/mcp`), imprime el resultado en JSON; opción `--times N` para repetir (se usa en la medición de memoria)
- [X] T023 [US1] Validar US1: `docker compose up -d --build`, `docker compose exec mcp alembic upgrade head`, `uv run python scripts/ping.py`, `uv run pytest` (unitarias + integración) en verde; base detenida y recuperada (quickstart §4); persistencia tras `down`/`up` (quickstart §5)

**Checkpoint**: US1 completa y demostrable.

---

## Phase 4: User Story 2 - Calidad comprobada en cada cambio (Priority: P2)

**Goal**: estilo y pruebas en local y en cada push, y capas verificadas.

**Independent Test**: `uv run ruff check`, `uv run ruff format --check` y `uv run pytest -m "not integration"` pasan; el workflow de GitHub falla con un error de estilo o una prueba rota.

### Tests for User Story 2 ⚠️

- [X] T024 [US2] Prueba de arquitectura en `tests/unit/test_architecture.py`: analiza con `ast` todos los `.py` de `src/puro_pockets/domain/` y falla si importa `mcp`, `sqlalchemy`, `psycopg`, `alembic`, `puro_pockets.db`, `puro_pockets.mcp` o `puro_pockets.services`; incluir un caso que compruebe que el detector reconoce un `import sqlalchemy` en un fuente de ejemplo (FR-010)

### Implementation for User Story 2

- [X] T025 [US2] Crear `.github/workflows/ci.yml`: en cada `push` y `pull_request`, Ubuntu, `astral-sh/setup-uv` con versión fijada, `uv sync --frozen`, `uv run ruff check`, `uv run ruff format --check`, `uv run pytest -m "not integration"` (FR-012)
- [X] T026 [US2] Dejar el código limpio: `uv run ruff format` y `uv run ruff check` sin errores en todo el repositorio

**Checkpoint**: verificaciones locales en verde; el CI se comprueba en GitHub tras el push del propietario.

---

## Phase 5: User Story 3 - Levantar desde cero solo con el README (Priority: P3)

**Goal**: un tercero llega a `ping` siguiendo solo el README.

**Independent Test**: seguir el README en un clon limpio hasta obtener `database: ok`.

- [X] T027 [US3] Reescribir `README.md` en español: qué es, requisitos (Docker con Compose, uv), configuración (`copy .env.example .env` y cambiar la contraseña), arranque, migraciones (subir y bajar), llamada a `ping`, pruebas (`pytest`, `pytest -m "not integration"`, `ruff`), detener y borrar datos (`docker compose down -v`, con advertencia), cómo actualizar el SDK de MCP (remite a `docs/plan-tecnico.md`) (FR-014, FR-020)

---

## Phase 6: User Story 4 - Saber cuánta memoria consume (Priority: P3)

**Goal**: valor de referencia de memoria registrado.

**Independent Test**: la tabla "Medición de memoria" de `docs/plan-tecnico.md` tiene valores de `db` y `mcp` en reposo y tras 20 `ping`.

- [ ] T028 [US4] Medir con `docker stats --no-stream` unos 60 s después de levantar y otra vez tras `uv run python scripts/ping.py --times 20`; registrar fecha, equipo y valores en la tabla "Medición de memoria" de `docs/plan-tecnico.md` (FR-015, SC-007)

---

## Phase 7: Polish & Cross-Cutting Concerns

- [ ] T029 Actualizar `docs/plan-tecnico.md` al cerrar el hito: driver psycopg 3, imagen `python:3.14-slim` y versión de uv fijada en el stack; estructura en capas real; confirmar versión, fecha de verificación y ruta de importación del SDK (FR-019); registro de cambios
- [ ] T030 Crear `specs/001-cimientos/verificacion.md` a partir de `quickstart.md`: cada paso con comandos, resultado esperado y quién lo verificó (Claude o el propietario)
- [ ] T031 Validación final: `docker compose down -v` y arranque desde cero, migraciones, `ping`, `uv run pytest` completo, `ruff`, `git check-ignore .env`, puertos publicados en `127.0.0.1`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: sin dependencias.
- **Foundational (Phase 2)**: depende de Setup; bloquea todas las historias.
- **US1 (Phase 3)**: depende de Foundational. Es el MVP.
- **US2 (Phase 4)**: depende de Foundational; la prueba de arquitectura necesita `domain/` (T007). El CI necesita las pruebas unitarias de US1 para tener algo que correr.
- **US3 (Phase 5)**: depende de US1 (el README describe comandos que deben funcionar).
- **US4 (Phase 6)**: depende de US1 (necesita `ping` y `scripts/ping.py`).
- **Polish (Phase 7)**: depende de todas las historias.

### Within Each User Story

- Pruebas primero (deben fallar), después dominio → servicios → MCP → arranque.
- T018 (servicio) antes que T019 (servidor) antes que T020 (arranque).

### Parallel Opportunities

- T004 y T005; T007, T008 y T009.
- Todas las pruebas de US1 (T012 a T017) son archivos distintos.

---

## Parallel Example: User Story 1

```text
T012 tests/unit/test_domain_health.py
T013 tests/unit/test_sdk_import.py
T014 tests/unit/test_ping_tool.py
T015 tests/integration/test_ping_http.py
T016 tests/integration/test_ping_db_down.py
T017 tests/integration/test_migrations.py
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Phase 1 y Phase 2.
2. Phase 3 (US1): pruebas en rojo, implementación, pruebas en verde.
3. Validar con el quickstart §1 a §5.

### Incremental Delivery

US1 → US2 (calidad y CI) → US3 (README) → US4 (memoria) → Polish. Un commit pequeño por tarea o
grupo de tareas relacionadas, siempre con las pruebas pasando.

---

## Notes

- Nunca guardar datos financieros (FR-017, regla no negociable 1).
- `detail` de `ping` nunca expone datos de conexión (FR-008).
- Quedan para el propietario: push, verificación del CI en GitHub (SC-006, SC-008), prueba de los
  15 minutos por un tercero (SC-001).
