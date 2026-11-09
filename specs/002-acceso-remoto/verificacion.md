# Verificación del Hito 2: Acceso remoto sin datos

**Fecha:** 2026-11-09 · **Rama:** `hito-2-acceso-remoto` · **Equipo:** Windows 11, Docker Desktop
(WSL 2)

Comandos completos en [quickstart.md](quickstart.md) y en el README ("Despliegue en el homelab").
**Leyenda:** ✅ Claude = verificado por Claude en esta sesión · 👤 Propietario = te toca a ti.

## Resumen

| # | Verificación | Quién | Estado |
|---|---|---|---|
| 1 | El SDK valida `Host` y `Origin`; nombre público permitido | ✅ Claude | Pasa |
| 2 | El túnel no arranca en el equipo de desarrollo | ✅ Claude | Pasa |
| 3 | Servicios healthy y puertos solo en 127.0.0.1 | ✅ Claude | Pasa |
| 4 | Pruebas (unitarias + integración) | ✅ Claude | 42/42 |
| 5 | Camino del túnel simulado por la red interna | ✅ Claude | Pasa |
| 6 | Túnel sin token: no sano, el resto sigue | ✅ Claude | Pasa |
| 7 | Ningún token en el repositorio | ✅ Claude | Pasa |
| 8 | Dominio, túnel y despliegue en el homelab | 👤 Propietario | Pendiente |
| 9 | `ping` desde Claude con datos móviles (SC-001) | 👤 Propietario | Pendiente |
| 10 | Reinicio del homelab sin reconfigurar (SC-002, SC-003) | 👤 Propietario | Pendiente |
| 11 | Memoria en el homelab (SC-006) | 👤 Propietario | Pendiente |

## 1. Validación de `Host` y `Origin` (FR-005, FR-006, SC-004) ✅ Claude

- Código del SDK `mcp==2.3.0` (`mcp/server/transport_security.py`): `Host` no permitido → 421;
  `Origin` presente y no permitido → 403; sin `Origin` → permitido.
- `build_transport_security` agrega `mcp.puropockets.space` (y `:*`) a los hosts y
  `https://mcp.puropockets.space` más `MCP_ALLOWED_ORIGINS` a los orígenes
  (`tests/unit/test_transport_security.py`).
- Contra el servidor levantado (`tests/integration/test_public_headers.py`): `Host` público → 200;
  `127.0.0.1:8000` → 200; `evil.example.com` → 421; `Origin` del propio dominio → 200;
  `Origin: https://claude.ai` → 200; `Origin: https://evil.example.com` → 403.

## 2. Túnel solo donde se activa (FR-003, SC-005) ✅ Claude

`docker compose config --services` → `db mcp`; con `--profile tunnel` → `db mcp cloudflared`.
`docker compose up -d` en el equipo de desarrollo no arranca el túnel ni falla por falta de token.

## 3. Salud y puertos (FR-004, FR-008, FR-009) ✅ Claude

`docker compose up -d --build --wait` → `db` y `mcp` **healthy** (el healthcheck de `mcp` llama a
`ping` dentro del contenedor). Puertos: `127.0.0.1:5432` y `127.0.0.1:8000`. `cloudflared` no publica
puertos. Los tres servicios tienen `restart: unless-stopped`.

## 4. Pruebas ✅ Claude

`uv run pytest` → **42 passed** (33 unitarias + 9 de integración); `ruff check` y
`ruff format --check` limpios.

## 5. Camino del túnel simulado ✅ Claude

Un contenedor temporal en la red de Compose llama a `http://mcp:8000/mcp` (lo mismo que hará
`cloudflared`): con `Host: mcp.puropockets.space` → **200**; con `Host: otro.example.com` → **421**.
Con la URL `http://mcp:8000/mcp` sin cambiar el `Host`, el servidor también rechaza (Host `mcp:8000`
no permitido): por eso el README pide no configurar *HTTP Host Header* en Cloudflare.

## 6. Túnel sin token ✅ Claude

`docker compose --profile tunnel up -d cloudflared` con `CF_TUNNEL_TOKEN` vacío: el contenedor se
reinicia (logs: `"cloudflared tunnel run" requires the ID or name of the tunnel`) y nunca queda sano;
`db` y `mcp` siguen healthy y `ping` responde `database: ok`. El contenedor de prueba se eliminó.

## 7. Token fuera del repositorio (FR-002) ✅ Claude

- `.env.example`: `CF_TUNNEL_TOKEN=` vacío. `.env` ignorado por Git.
- Búsqueda en todos los archivos versionables de patrones de token (`eyJ…` largos,
  `CF_TUNNEL_TOKEN=<valor>`, `TUNNEL_TOKEN=<valor>`): ninguno.
- En `docker-compose.yml` el token solo aparece como `${CF_TUNNEL_TOKEN:-}`; nunca en la línea de
  comandos del contenedor.
- El README advierte no ejecutar `docker compose config` sin opciones en el homelab (imprime el
  `.env`).

## 8 a 11. Pasos del propietario 👤

| Paso del README | Qué comprobar | Resultado esperado |
|---|---|---|
| 1 a 3 | Dominio activo en Cloudflare, túnel creado, `CNAME` `mcp` hacia `cfargotunnel.com` | Dominio **Active**; registro creado |
| 4 y 5 | Docker habilitado al arranque; `docker compose ps` en el homelab | Tres servicios **healthy**; túnel **Healthy** en Cloudflare |
| 6 | `docker compose exec mcp python scripts/ping.py` y `uv run python scripts/ping.py --url https://mcp.puropockets.space/mcp` | `database: ok` en ambos |
| 7 y 8 | Conector en claude.ai; `ping` desde el celular **sin wifi** | `database: ok` (SC-001) |
| 9 | `sudo reboot`; sin tocar nada, `ping` desde Claude | Responde, misma URL, sin reconfigurar (SC-002, SC-003) |
| 10 | `docker stats --no-stream` en reposo y tras 20 `ping` | Valores anotados en `docs/plan-tecnico.md` (SC-006) |

Cuando termines, anota aquí la fecha y el resultado de cada paso.
