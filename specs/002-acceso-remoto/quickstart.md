# Quickstart de validación: Acceso remoto sin datos (002-acceso-remoto)

Los pasos del propietario (Cloudflare, Namecheap, homelab, claude.ai) están en el README, sección
"Despliegue en el homelab". Esta guía lista las comprobaciones del hito; los resultados van en
[verificacion.md](verificacion.md).

## Locales (equipo de desarrollo, sin token)

1. **Servicios por perfil:** `docker compose config --services` → `db mcp`;
   `docker compose --profile tunnel config --services` → `db mcp cloudflared`.
2. **Arranque y salud:** `docker compose up -d --build --wait`; `docker compose ps` → `db` y `mcp`
   healthy, puertos solo en `127.0.0.1`.
3. **Pruebas:** `uv run pytest` (incluye `tests/integration/test_public_headers.py`).
4. **Camino del túnel simulado:** contenedor temporal en la red de Compose que llama a
   `http://mcp:8000/mcp` con `Host: mcp.puropockets.space` → 200; con otro `Host` → 421.
5. **Túnel sin token:** `docker compose --profile tunnel up -d cloudflared` → se reinicia sin quedar
   sano; `db`, `mcp` y `ping` siguen funcionando. Limpiar con
   `docker compose --profile tunnel rm -sf cloudflared`.

## Del propietario (homelab y cuentas)

6. README pasos 1 a 5: dominio activo en Cloudflare, túnel creado, despliegue con los tres servicios
   healthy.
7. README paso 6: `ping` en el homelab y desde fuera por `https://mcp.puropockets.space/mcp`.
8. README pasos 7 y 8: conector en claude.ai y `ping` con datos móviles (SC-001).
9. README paso 9: reinicio del homelab sin reconfigurar el conector (SC-002, SC-003).
10. README paso 10: memoria en el homelab (SC-006).
