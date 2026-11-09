# Research: Cimientos del proyecto (001-cimientos)

**Fecha:** 2026-11-09
**Spec:** [spec.md](spec.md) · **Plan:** [plan.md](plan.md)

Las decisiones de producto ya están en la spec (Clarifications) y en `docs/plan-tecnico.md`. Aquí
solo van las decisiones técnicas de implementación y su verificación.

## R1. SDK de MCP: API concreta de la versión 2.3.0

- **Decision:** `mcp==2.3.0`. Servidor con `MCPServer` desde `mcp.server.mcpserver`; tool `ping`
  definida con `@mcp.tool()` como función `async` que devuelve un modelo Pydantic (salida
  estructurada). Pruebas con `mcp.Client`: en memoria con `Client(mcp)` y por HTTP con
  `Client("http://127.0.0.1:8000/mcp")`. Arranque con `run(transport="streamable-http", ...)`.
- **Rationale:** verificado el 2026-11-09 instalando `mcp==2.3.0` en un entorno aislado:
  - `from mcp.server.mcpserver import MCPServer` funciona y es el mismo objeto que
    `mcp.server.MCPServer` (el README de GitHub usa la segunda ruta; la guía de migración, la
    primera). Se usa la de la guía, como fija la spec (FR-018).
  - Una tool que devuelve un modelo Pydantic publica `outputSchema`, y el cliente recibe
    `structured_content` con los campos del modelo.
  - `run_streamable_http_async` acepta `host`, `port`, `streamable_http_path`, `json_response`,
    `stateless_http` y `transport_security`, entre otros.
- **Alternatives considered:** `FastMCP` de la línea 1.x (descartada en la clarificación);
  devolver texto libre en `ping` (descartado: la spec pide estado estructurado).
- **Verificar al implementar:** `transport_security` (protección contra DNS rebinding). Dentro del
  contenedor el servidor escucha en `0.0.0.0`; hay que confirmar que acepta el encabezado `Host`
  `127.0.0.1:8000` / `localhost:8000` y, si no, permitir esos hosts de forma explícita.

## R2. Python e imagen del servidor

- **Decision:** `requires-python = ">=3.12"` (constitución/plan técnico). Imagen del servidor basada
  en `python:3.14-slim`, con el binario de uv copiado desde la imagen oficial de uv con versión
  fijada. Dependencias instaladas con `uv sync --frozen --no-dev`.
- **Rationale:** el equipo de desarrollo tiene Python 3.14.3; usar la misma versión menor en el
  contenedor evita diferencias entre local y Docker. `--frozen` garantiza que se usa `uv.lock`
  (FR-013).
- **Alternatives considered:** imagen `python:3.12-slim` (diferente a la local); imágenes de uv con
  Python incluido (válidas, pero se prefiere la imagen oficial de Python con uv fijado).

## R3. Acceso a la base y tiempo límite de conexión

- **Decision:** SQLAlchemy 2.x con el driver psycopg 3 (`psycopg[binary]`) en modo **síncrono**, tanto
  para el servidor como para Alembic. La comprobación de `ping` corre en un hilo
  (`anyio.to_thread.run_sync`, con `abandon_on_cancel=True`) dentro de `anyio.fail_after`. Tiempo
  límite de conexión de 2 segundos con `connect_args={"connect_timeout": 2}`; el límite total de la
  comprobación es de 3 segundos, para que `ping` responda siempre en menos de 5 (SC-004).
- **Rationale:** psycopg en modo asíncrono no funciona con el event loop por defecto de Windows
  (Proactor), que es el que usan las pruebas en el equipo de desarrollo. El modo síncrono en un hilo
  funciona igual en Windows y en el contenedor Linux, y usa un solo driver para todo.
  (Ajuste hecho durante la implementación; la versión inicial del plan proponía el modo asíncrono.)
- **Alternatives considered:** modo asíncrono de psycopg (falla en Windows sin cambiar el event loop);
  asyncpg (solo asíncrono, obligaría a un segundo driver para Alembic); psycopg2 (sin soporte
  asíncrono y en mantenimiento).

## R4. PostgreSQL 18 en Docker

- **Decision:** imagen `postgres:18-alpine`. Volumen nombrado montado en `/var/lib/postgresql`
  (no en `/var/lib/postgresql/data`). Puerto publicado como `127.0.0.1:5432:5432`. Healthcheck con
  `pg_isready`. El servicio `mcp` declara `depends_on: db: condition: service_healthy`.
- **Rationale:** desde la versión 18 la imagen oficial cambió `PGDATA` a
  `/var/lib/postgresql/18/docker` y el `VOLUME` a `/var/lib/postgresql`; montar en la ruta antigua
  falla al arrancar o no persiste. La variante alpine es más liviana (requerimiento de liviandad).
- **Alternatives considered:** `postgres:18` (Debian, más pesada); `postgres:17-alpine` (versión
  mayor anterior); `latest` (prohibido por FR-021).

## R5. Arranque ordenado (FR-004)

- **Decision:** `depends_on` con `service_healthy` para que el servidor arranque solo cuando la base
  responde. Si la base cae después, `ping` lo informa (FR-007) y el pool reconecta solo
  (`pool_pre_ping=True`).
- **Rationale:** cubre el arranque y la recuperación sin lógica extra.
- **Alternatives considered:** healthcheck propio del servicio `mcp` (requiere un handshake MCP;
  innecesario en este hito).

## R6. Migraciones

- **Decision:** Alembic con la carpeta `migrations/` en la raíz. Primera migración `base` sin tablas
  de negocio (solo deja la tabla de versión de Alembic). Se ejecutan dentro del contenedor:
  `docker compose exec mcp alembic upgrade head`; reversibilidad con `alembic downgrade base` y
  `alembic upgrade head`.
- **Rationale:** dentro del contenedor no hace falta configurar la URL de la base para el equipo
  local; el README queda con un solo camino.
- **Alternatives considered:** migrar automáticamente al arrancar (oculta errores y la spec pide
  que el propietario las aplique como paso explícito).

## R7. Pruebas y verificación automática

- **Decision:** pytest con el plugin de anyio (ya es dependencia de `mcp`) para pruebas asíncronas.
  Marcador `integration` para las pruebas que necesitan la base real. Pruebas previstas:
  - Unitarias: estado de salud del dominio; prueba de humo de la importación de `MCPServer`
    (FR-018); prueba de arquitectura que analiza los `import` de `domain/` y falla si importa
    `mcp`, `sqlalchemy`, `psycopg`, `puro_pockets.db` o `puro_pockets.mcp` (FR-010); `ping` en
    memoria con `Client(mcp)` y una comprobación de base simulada.
  - Integración: `ping` por HTTP contra los servicios levantados (base `ok`); `ping` con una URL de
    base inalcanzable responde base `error` en menos de 5 segundos.
- CI en GitHub Actions: `uv sync --frozen`, `ruff check`, `ruff format --check`,
  `pytest -m "not integration"`.
- **Rationale:** cumple FR-011, FR-012 y la regla no negociable 4 sin dependencias de prueba extra.
- **Alternatives considered:** pytest-asyncio (otra dependencia); import-linter para la prueba de
  arquitectura (más potente, pero agrega una herramienta para una sola regla).

## R8. Configuración

- **Decision:** módulo `config.py` que lee variables de entorno con la biblioteca estándar y falla al
  arrancar con un mensaje en español que nombra la variable faltante, sin mostrar valores. Variables
  ya documentadas en `.env.example` (`POSTGRES_*`, `DATABASE_URL`, `MCP_HOST`, `MCP_PORT`).
- **Rationale:** pocas variables; no justifica una dependencia como pydantic-settings.
- **Alternatives considered:** pydantic-settings.
- **Ajuste a `.env.example`:** `DATABASE_URL` pasa a incluir el driver (`postgresql+psycopg://...`)
  y, dentro de Compose, el host de la base es `db`. Se documentan las dos variantes.

## R9. Medición de memoria

- **Decision:** `docker stats --no-stream` en reposo (unos 60 segundos después de levantar) y después
  de 20 llamadas a `ping` hechas con un script de cliente. Resultados en la tabla "Medición de
  memoria" de `docs/plan-tecnico.md`.
- **Rationale:** procedimiento ya registrado en el plan técnico; 60 segundos dejan estabilizar los
  procesos.

## Fuentes

- PyPI, paquete `mcp`: https://pypi.org/pypi/mcp/json
- Guía de migración v1 → v2 del SDK de Python: https://py.sdk.modelcontextprotocol.io/migration/index.md
- Documentación v2 del SDK: https://py.sdk.modelcontextprotocol.io/v2/llms-full.txt
- Imagen oficial de PostgreSQL (cambio de `PGDATA` en 18): https://hub.docker.com/_/postgres
- Política de versiones de PostgreSQL: https://www.postgresql.org/support/versioning/
