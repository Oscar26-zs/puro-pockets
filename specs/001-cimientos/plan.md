# Implementation Plan: Cimientos del proyecto

**Branch**: `001-cimientos` | **Date**: 2026-11-09 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/001-cimientos/spec.md`

> **Plan delgado (Puro Pockets).** Este plan no repite lo que ya está en
> `.specify/memory/constitution.md` ni en `docs/plan-tecnico.md`: lo referencia. Solo registra lo
> que este hito agrega o cambia. Las reglas se citan por su identificador (`RN-xx`), nunca se
> reescriben.

## Summary

Proyecto base que se levanta con `docker compose up` (servicios `db` y `mcp`), con migraciones de
Alembic reversibles y una tool MCP `ping` por Streamable HTTP en `127.0.0.1` que informa el estado
del servidor y de la base. Incluye estructura en capas, pruebas unitarias y de integración, CI con
ruff y pruebas unitarias, README para levantar desde cero y registro de memoria. Decisiones técnicas
y su verificación: [research.md](research.md).

## Technical Context

**Base**: stack, arquitectura y esquema en `docs/plan-tecnico.md` (v0.2). Aquí solo va lo nuevo o distinto.

**Dependencias nuevas o cambiadas**:

- Ejecución: `mcp==2.3.0` (exacta, FR-018), `sqlalchemy` 2.x, `psycopg[binary]` 3.x, `alembic`.
  Versiones exactas congeladas en `uv.lock` (FR-013).
- Desarrollo: `pytest`, `ruff` (pruebas asíncronas con el plugin de anyio, que ya trae `mcp`).
- Imágenes: `python:3.14-slim` + binario de uv con versión fijada; `postgres:18-alpine` (FR-021).
- Python del proyecto: `requires-python = ">=3.12"`.

**Cambios al esquema**: ninguna tabla. Solo la migración `base` de Alembic (crea la tabla de versión).

**Tools MCP nuevas o modificadas**: `ping` (nueva). Contrato: [contracts/ping.md](contracts/ping.md).

**Decisiones pendientes de las que depende**: ninguna. La decisión del SDK de MCP (`HITOS.md`,
sección 3) quedó resuelta en la clarificación.

## Constitution Check

*GATE: debe pasar antes de la fase 0 y revisarse de nuevo después del diseño.*

- **Reglas que implementa este hito**: ninguna `RN-xx` (no hay reglas de negocio en este hito).
  Aplica el principio 3.10 (minimización) en la respuesta de `ping`.
- **Reglas no negociables** (Gobernanza):
  - ✓ Datos reales: no se crean tablas de negocio ni se guardan datos financieros (FR-017).
  - ✓ Capa de negocio: `domain/` no importa MCP ni base de datos; lo verifica una prueba
    automática (FR-010).
  - ✓ Invariante de integridad: no aplica todavía (este hito no registra movimientos de dinero).
  - ✓ Pruebas por hito: unitarias, de integración, de humo y de arquitectura; CI en cada push.
- **[PROPUESTO] que se asumen**: ninguno de la constitución. Decisiones técnicas tomadas en el plan
  (para confirmar): Python 3.14 en la imagen, driver psycopg 3, plugin de anyio para pruebas
  asíncronas, prueba de arquitectura propia en lugar de import-linter.
- **[ABIERTO] de los que depende**: ninguno.

**Re-evaluación tras el diseño (fase 1):** sin cambios; el gate sigue pasando.

## Project Structure

### Documentation (this feature)

```text
specs/001-cimientos/
├── plan.md              # Este archivo
├── research.md          # Decisiones técnicas y verificación del SDK y de Postgres 18
├── contracts/
│   └── ping.md          # Contrato de la tool ping
├── quickstart.md        # Cómo comprobar el "Terminado cuando" del hito
└── tasks.md             # Lo crea /speckit-tasks
```

No hay `data-model.md`: este hito no crea tablas (el plan delgado lo pide solo si cambia el esquema).

### Source Code (repository root)

La estructura en capas está en `HITOS.md` (Hito 1) y pasa a `docs/plan-tecnico.md` al cerrar este
hito. Archivos que este hito crea o modifica:

```text
pyproject.toml                       # proyecto, dependencias, configuración de ruff y pytest
uv.lock                              # dependencias congeladas
Dockerfile                           # imagen del servidor MCP
docker-compose.yml                   # servicios db y mcp, puertos en 127.0.0.1, volumen, healthcheck
alembic.ini                          # configuración de Alembic
.env.example                         # ajuste: DATABASE_URL con driver; host db dentro de Compose
README.md                            # cómo levantar desde cero
.github/workflows/ci.yml             # ruff + pruebas unitarias en cada push

src/puro_pockets/
├── __init__.py
├── __main__.py                      # arranca el servidor MCP (Streamable HTTP)
├── config.py                        # variables de entorno; error claro si falta alguna
├── domain/
│   └── health.py                    # estado de salud (puro, sin MCP ni base)
├── services/
│   └── health.py                    # caso de uso: comprobar la base y armar el estado
├── db/
│   └── engine.py                    # motor de SQLAlchemy, tiempo límite de conexión
└── mcp/
    └── server.py                    # MCPServer y tool ping (delgada: llama a services)

migrations/
├── env.py
└── versions/
    └── 0001_base.py                 # migración base, sin tablas de negocio

scripts/
└── ping.py                          # cliente de prueba por HTTP (usado en README y quickstart)

tests/
├── unit/
│   ├── test_domain_health.py
│   ├── test_sdk_import.py           # prueba de humo de MCPServer (FR-018)
│   ├── test_architecture.py         # domain/ no importa mcp ni db (FR-010)
│   └── test_ping_tool.py            # ping en memoria con base simulada
└── integration/
    ├── test_ping_http.py            # ping por HTTP con servicios levantados
    ├── test_ping_db_down.py         # base inalcanzable: error en menos de 5 s
    └── test_migrations.py           # upgrade head (x2), downgrade base, upgrade head
```

## Pruebas

| Criterio | Prueba automática |
|---|---|
| FR-006, FR-007 (estado estructurado) | `test_ping_tool.py` (unitaria, en memoria), `test_ping_http.py` (integración) |
| FR-007, SC-004 (base caída, menos de 5 s) | `test_ping_db_down.py` (integración) |
| FR-008 (sin datos internos) | `test_ping_tool.py` y `test_ping_db_down.py` revisan que `detail` no contenga host, usuario ni contraseña |
| FR-010 (capas) | `test_architecture.py` |
| FR-018 (ruta de importación) | `test_sdk_import.py` |
| FR-012, SC-006, SC-008 (CI) | workflow de GitHub Actions; comprobación manual con error de estilo y prueba rota (quickstart §7) |
| FR-005, SC-003 (migraciones reversibles) | `test_migrations.py` (integración, con la API de comandos de Alembic) |
| Recuperación de `ping` (historia 1, escenario 7) | quickstart §4 (manual: detener y arrancar `db`) |
| SC-001, SC-002, FR-015 | quickstart §1, §2 y §9 (manuales, cronometrados o medidos) |

Las pruebas marcadas como manuales dependen de controlar Docker o GitHub desde fuera del proceso de
pruebas; quedan como pasos del quickstart y se marcan en el reporte de cierre.

## Actualización del plan técnico al cerrar

- **Stack:** driver psycopg 3, imagen `python:3.14-slim` y versión de uv fijada.
- **Arquitectura:** estructura en capas real del código.
- **Medición de memoria:** valores medidos en reposo y tras 20 `ping`.
- **SDK de MCP:** confirmar versión, fecha de verificación y ruta de importación (FR-019).

## Complexity Tracking

> Solo si el Constitution Check tiene violaciones que deban justificarse.

Sin violaciones.
