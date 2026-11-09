# Implementation Plan: Acceso remoto sin datos

**Branch**: `hito-2-acceso-remoto` | **Date**: 2026-11-09 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/002-acceso-remoto/spec.md`

> **Plan delgado (Puro Pockets).** Este plan no repite lo que ya está en
> `.specify/memory/constitution.md` ni en `docs/plan-tecnico.md`: lo referencia. Solo registra lo
> que este hito agrega o cambia. Las reglas se citan por su identificador (`RN-xx`), nunca se
> reescriben.

## Summary

Publicar el servidor MCP del Hito 1 en `https://mcp.puropockets.space/mcp` mediante un túnel de
Cloudflare que corre como servicio de Compose (perfil `tunnel`), con reinicio automático,
comprobaciones de salud, `Host`/`Origin` públicos permitidos y una guía de pasos manuales, despliegue
y actualización en el README. Decisiones: [research.md](research.md).

## Technical Context

**Base**: `docs/plan-tecnico.md` (v0.3). Aquí solo va lo nuevo o distinto.

**Dependencias nuevas o cambiadas**: imagen `cloudflare/cloudflared:2026.10.3`. Sin dependencias de
Python nuevas (las pruebas de encabezados usan `http.client` de la biblioteca estándar).

**Cambios al esquema**: ninguno.

**Tools MCP nuevas o modificadas**: ninguna (`ping` sin cambios).

**Configuración nueva**: `MCP_PUBLIC_HOSTNAME`, `MCP_ALLOWED_ORIGINS`, `CF_TUNNEL_TOKEN` (renombra
`CLOUDFLARE_TUNNEL_TOKEN`), `COMPOSE_PROFILES`.

**Decisiones pendientes de las que depende**: ninguna.

## Constitution Check

*GATE: debe pasar antes de la fase 0 y revisarse de nuevo después del diseño.*

- **Reglas que implementa este hito**: ninguna `RN-xx`. Aplica el principio 3.10 (tránsito por
  Cloudflare y Anthropic aceptado; minimización sin cambios).
- **Reglas no negociables** (Gobernanza):
  - ✓ Datos reales: el servidor sigue exponiendo solo `ping` (FR-010).
  - ✓ Capa de negocio: sin cambios en `domain/`.
  - ✓ Invariante: no aplica.
  - ✓ Pruebas por hito: pruebas unitarias de configuración y seguridad del transporte; prueba de
    integración de encabezados contra el servidor levantado.
- **[PROPUESTO] que se asumen**: decisiones técnicas del plan (perfil de Compose `tunnel`,
  healthcheck de `mcp` con `scripts/ping.py`, orígenes de Claude permitidos por defecto).
- **[ABIERTO] de los que depende**: ninguno.
- **Observación sobre capas altas**: `docs/plan-tecnico.md` §15 dice que el endpoint del MCP requiere
  token o login. `HITOS.md` (Hito 2, riesgos) acepta el endpoint público sin autenticación, solo con
  `ping`, hasta el Hito 3, y el propietario lo confirmó al iniciar el hito. Se reporta al propietario
  para que decida si §15 debe precisar "desde el Hito 3"; no se modifica en este plan.

## Project Structure

### Documentation (this feature)

```text
specs/002-acceso-remoto/
├── plan.md
├── research.md
├── quickstart.md        # comprobaciones del hito (locales y del propietario)
├── tasks.md
└── verificacion.md      # al cerrar
```

Sin `data-model.md` (no cambia el esquema) ni `contracts/` (no hay tools nuevas).

### Source Code (repository root)

```text
src/puro_pockets/config.py          # + public_hostname, allowed_origins
src/puro_pockets/mcp/server.py      # transport_security construida desde la configuración
docker-compose.yml                  # restart, healthchecks, servicio cloudflared (perfil tunnel)
Dockerfile                          # copia scripts/ (ping dentro del contenedor)
.env.example                        # CF_TUNNEL_TOKEN vacío, COMPOSE_PROFILES, nombre público, orígenes
README.md                           # despliegue en el homelab, pasos manuales, actualización, salud
docs/plan-tecnico.md                # dominio, túnel, hosts/orígenes, versión de cloudflared
tests/unit/test_config.py           # nuevas variables
tests/unit/test_transport_security.py
tests/integration/test_public_headers.py
```

## Pruebas

| Criterio | Prueba |
|---|---|
| FR-005, FR-006, SC-004 | `test_transport_security.py` (unitaria) y `test_public_headers.py` (integración: `Host` público → 200; `Host` ajeno → 421; `Origin` ajeno → 403; `Origin` de Claude → 200) |
| FR-007 | `test_config.py` |
| FR-003, SC-005 | `docker compose config --services` sin y con perfil (verificación local, sin token) |
| FR-004 | `docker compose ps`/`docker port`: solo `127.0.0.1` |
| FR-009 | `docker compose ps` muestra `mcp` healthy; `cloudflared` sin token queda unhealthy |
| Ruta túnel → servidor | contenedor temporal en la red de Compose que llama a `http://mcp:8000/mcp` con `Host: mcp.puropockets.space` |
| SC-001, SC-002, SC-003, SC-006 | manuales del propietario (README y `verificacion.md`) |

## Actualización del plan técnico al cerrar

Dominio y subdominio, arquitectura del túnel, hosts y orígenes permitidos, versión de cloudflared,
perfil `tunnel`, healthchecks y (cuando el propietario la tome) la medición de memoria en el homelab.

## Complexity Tracking

Sin violaciones.
