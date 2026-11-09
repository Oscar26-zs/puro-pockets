# Research: Acceso remoto sin datos (002-acceso-remoto)

**Fecha:** 2026-11-09 · **Spec:** [spec.md](spec.md) · **Plan:** [plan.md](plan.md)

## R1. Validación de `Host` y `Origin` en el SDK de MCP (2.3.0)

- **Hallazgo (código de `mcp/server/transport_security.py`):** con la protección contra DNS rebinding
  activa, el SDK valida `Host` (coincidencia exacta o patrón `host:*`; si no, **421**) y `Origin`
  (solo si viene en la petición; si no está permitido, **403**). Las peticiones sin `Origin` pasan.
- **Decision:** agregar a la configuración explícita del Hito 1 el nombre público
  `mcp.puropockets.space` (exacto y `:*`) en `allowed_hosts`, y `https://mcp.puropockets.space` más
  los orígenes de `MCP_ALLOWED_ORIGINS` en `allowed_origins`. Valor documentado de
  `MCP_ALLOWED_ORIGINS`: `https://claude.ai,https://claude.com`, por si el conector envía `Origin`
  (las llamadas del conector salen de los servidores de Anthropic y normalmente no lo envían).
- **Rationale:** cloudflared reenvía al servidor el `Host` público original; sin agregarlo, todas
  las llamadas por el túnel recibirían 421.
- **Alternatives considered:** desactivar la protección (descartado: el MCP la recomienda para
  servidores HTTP); `allowed_hosts` con comodín total (descartado).

## R2. cloudflared en Docker Compose

- **Decision:** imagen `cloudflare/cloudflared:2026.10.3` (publicada el 2026-10-21; la última, 2026.10.7,
  tiene menos de dos semanas). Comando `tunnel --no-autoupdate --metrics 0.0.0.0:20241 run`, con el
  token en la variable de entorno `TUNNEL_TOKEN` tomada de `CF_TUNNEL_TOKEN` (nunca en la línea de
  comandos ni en archivos del repositorio). Puerto de métricas sin publicar.
- **Healthcheck:** `cloudflared tunnel --metrics 127.0.0.1:20241 ready`, que consulta `/ready` y
  devuelve código de salida 0 solo con el túnel conectado. Verificado en el binario de la imagen
  2026.10.3 (`tunnel ready --help`, `--token [$TUNNEL_TOKEN]`, `--metrics`). La imagen es distroless,
  corre como usuario no root y no trae healthcheck propio.
- **Activación solo en el homelab:** el servicio lleva `profiles: ["tunnel"]`; en el homelab se
  activa con `COMPOSE_PROFILES=tunnel` en `.env`, de modo que los comandos son los mismos en los dos
  equipos (`docker compose up -d`).
- **Ingress:** túnel remotamente administrado; el nombre público `mcp.puropockets.space` se configura
  en el panel de Cloudflare apuntando a `http://mcp:8000` (nombre del servicio en la red de Compose).
- **Alternatives considered:** túnel con archivo de credenciales y `config.yml` en el repositorio
  (más archivos sensibles); publicar el puerto del MCP en el homelab (prohibido por FR-004).

## R3. Reinicio automático y salud del servidor

- **Decision:** `restart: unless-stopped` en `db`, `mcp` y `cloudflared`. Healthcheck de `mcp` que
  ejecuta `python scripts/ping.py` dentro del contenedor (éxito = el servidor responde a un cliente
  MCP). `cloudflared` espera a que `mcp` esté healthy. El script se copia en la imagen, lo que además
  permite llamar a `ping` en el homelab sin instalar uv (FR-013).
- **Requisito del homelab:** Docker debe arrancar con el sistema (`systemctl enable docker`).

## R4. Conector de claude.ai

- **Hallazgo (documentación oficial de conectores personalizados):** Customize → Connectors → Add
  custom connector → URL del servidor MCP remoto; la opción "No sign-in" permite servidores sin
  autenticación.
- **Decision:** URL del conector `https://mcp.puropockets.space/mcp`, sin inicio de sesión (hasta el
  Hito 3).

## Fuentes

- Código del SDK `mcp==2.3.0`: `mcp/server/transport_security.py` (instalado en `.venv`).
- Versiones de cloudflared: https://github.com/cloudflare/cloudflared/releases
- Métricas de túneles: https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/monitor-tunnels/metrics/index.md
- Conectores personalizados de Claude: https://claude.com/docs/connectors/custom
