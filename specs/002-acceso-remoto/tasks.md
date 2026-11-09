# Tasks: Acceso remoto sin datos

**Input**: Design documents from `/specs/002-acceso-remoto/`
**Prerequisites**: plan.md, spec.md, research.md

**Tests**: OBLIGATORIAS (gobernanza, regla no negociable 4). Pruebas antes que la implementación.

## Format: `[ID] [P?] [Story] Description`

---

## Phase 1: Setup

- [X] T001 Actualizar `.env.example`: renombrar `CLOUDFLARE_TUNNEL_TOKEN` a `CF_TUNNEL_TOKEN` (vacío), agregar `COMPOSE_PROFILES` (vacío; `tunnel` en el homelab), `MCP_PUBLIC_HOSTNAME=mcp.puropockets.space` y `MCP_ALLOWED_ORIGINS=https://claude.ai,https://claude.com`

---

## Phase 2: Foundational

- [X] T002 [P] Prueba unitaria en `tests/unit/test_config.py`: `MCP_PUBLIC_HOSTNAME` (por defecto vacío) y `MCP_ALLOWED_ORIGINS` separado por comas, sin espacios ni elementos vacíos
- [X] T003 Implementar en `src/puro_pockets/config.py` los campos `public_hostname: str | None` y `allowed_origins: tuple[str, ...]`

---

## Phase 3: User Story 1 - `ping` desde Claude fuera de casa (P1) 🎯

**Independent Test**: un cliente MCP llama a `https://mcp.puropockets.space/mcp` desde otra red.

- [X] T004 [P] [US1] Prueba unitaria en `tests/unit/test_transport_security.py`: `build_transport_security(settings)` incluye siempre los hosts locales; con `public_hostname` agrega `mcp.puropockets.space` y `mcp.puropockets.space:*` a los hosts y `https://mcp.puropockets.space` a los orígenes; agrega `allowed_origins`; mantiene la protección activa
- [X] T005 [P] [US1] Prueba de integración en `tests/integration/test_public_headers.py` (marcador `integration`): `POST /mcp` de `initialize` a `127.0.0.1:8000` con `Host: mcp.puropockets.space` → 200; `Host: evil.example.com` → 421; `Origin: https://evil.example.com` → 403; `Origin: https://claude.ai` → 200; sin `Origin` → 200
- [X] T006 [US1] Implementar `build_transport_security(settings)` en `src/puro_pockets/mcp/server.py` y usarla en `run_server`
- [X] T007 [US1] `docker-compose.yml`: pasar `MCP_PUBLIC_HOSTNAME` (por defecto `mcp.puropockets.space`) y `MCP_ALLOWED_ORIGINS` al servicio `mcp`; mantener su puerto solo en `127.0.0.1`
- [X] T008 [US1] `docker-compose.yml`: servicio `cloudflared` con `cloudflare/cloudflared:2026.10.3`, `profiles: ["tunnel"]`, comando `tunnel --no-autoupdate --metrics 0.0.0.0:20241 run`, `TUNNEL_TOKEN: ${CF_TUNNEL_TOKEN:-}`, sin puertos publicados, `depends_on: mcp: condition: service_healthy`
- [X] T009 [US1] Validar: reconstruir, pasar las pruebas, y llamar a `http://mcp:8000/mcp` con `Host: mcp.puropockets.space` desde un contenedor temporal en la red de Compose (simula el túnel)

---

## Phase 4: User Story 2 - El servicio vuelve solo (P1)

- [X] T010 [US2] `restart: unless-stopped` en `db`, `mcp` y `cloudflared` en `docker-compose.yml`
- [X] T011 [US2] `Dockerfile`: copiar `scripts/`; healthcheck de `mcp` en `docker-compose.yml` con `python scripts/ping.py`

---

## Phase 5: User Story 3 - Salud del túnel y actualización (P2)

- [X] T012 [US3] Healthcheck de `cloudflared` en `docker-compose.yml`: `cloudflared tunnel --metrics 127.0.0.1:20241 ready`
- [X] T013 [US3] Validar sin token: con el perfil `tunnel`, `cloudflared` no queda sano y el resto sigue funcionando; sin perfil, no arranca (`docker compose config --services`)

---

## Phase 6: User Story 4 - Pasos manuales guiados (P2)

- [X] T014 [US4] README: sección de despliegue en el homelab con los pasos manuales en orden (Cloudflare y registros DNS, DNSSEC y nameservers en Namecheap, túnel y nombre público, Docker en el homelab, despliegue, conector en claude.ai, prueba con datos móviles, reinicio, memoria), cómo actualizar y cómo comprobar la salud del túnel

---

## Phase 7: Polish

- [X] T015 `docs/plan-tecnico.md`: dominio, subdominio, arquitectura del túnel, hosts/orígenes, versión de cloudflared, perfil, healthchecks; registro de cambios
- [X] T016 Crear `specs/002-acceso-remoto/quickstart.md` y `verificacion.md` (qué verificó Claude y qué le toca al propietario)
- [X] T017 Validación final: `ruff`, `pytest` completo, `git check-ignore .env`, que ningún archivo versionado contenga un token

## Dependencies

Setup → Foundational → US1 → US2 → US3 → US4 → Polish. T004 y T005 en paralelo.
