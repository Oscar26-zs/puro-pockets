# Verificación del Hito 3: Autenticación

**Fecha:** 2026-11-09 · **Rama:** `hito-3-autenticacion` · **Equipo:** Windows 11, Docker Desktop

**Leyenda:** ✅ Claude = verificado por Claude en esta sesión · 👤 Propietario = te toca a ti. Los
pasos del propietario están en el README, sección "Autenticación (Hito 3)".

## Resumen

| # | Verificación | Quién | Estado |
|---|---|---|---|
| 1 | Sin token → 401 con `WWW-Authenticate` y `resource_metadata` | ✅ Claude | Pasa (en proceso y contra el contenedor) |
| 2 | Token inválido, vencido o revocado → 401 | ✅ Claude | Pasa |
| 3 | Flujo completo con cliente de prueba (registro, PKCE, inicio de sesión, token, `ping`) | ✅ Claude | Pasa |
| 4 | URL de retorno no permitida rechazada; registro cerrado por defecto; máximo de clientes | ✅ Claude | Pasa |
| 5 | Refresco con rotación; reutilización revoca la cadena | ✅ Claude | Pasa (memoria y Postgres) |
| 6 | Revocación (endpoint y comando del propietario) | ✅ Claude | Pasa |
| 7 | Límite de intentos de inicio de sesión (por IP y global), sin afectar a `/mcp` con token | ✅ Claude | Pasa |
| 8 | Solo hashes en la base; registros sin secretos | ✅ Claude | Pasa |
| 9 | Hash argon2 con `$` llega intacto al contenedor | ✅ Claude | Pasa |
| 10 | Conector de claude.ai: registro, inicio de sesión, `ping` (SC-002) | 👤 Propietario | Pendiente |
| 11 | Desconectar y reconectar (SC-003) | 👤 Propietario | Pendiente |
| 12 | Inicio de sesión en menos de 1 s en el homelab (SC-006) | 👤 Propietario | Pendiente |
| 13 | Refresco real con duraciones cortas desde claude.ai | 👤 Propietario | Pendiente |

## Detalle de lo verificado por Claude

- **Pruebas:** `uv run pytest` → **80 passed** (71 unitarias + 9 de integración); `ruff` limpio.
  - `tests/unit/test_oauth_http.py`: la aplicación ASGI real (SDK + proveedor + página de inicio de
    sesión) con un cliente de prueba: 401 sin token y con token inventado; metadatos RFC 9728 y RFC 8414
    (`S256`, `offline_access`, registro y revocación); flujo completo y `tools/call ping` con el token;
    la página muestra "claude.ai" y su CSP permite volver a `https://claude.ai` y `https://claude.com`;
    contraseña incorrecta → 401 sin código; 5 fallos → 429 desde esa IP (otra IP entra); el bloqueo no
    afecta a `/mcp` con token; retorno no permitido → `invalid_redirect_uri`; registro cerrado → 404 y
    sin `registration_endpoint`; sin hash → inicio de sesión 503; refresco rota y la reutilización da
    `invalid_grant` y revoca la cadena; revocación → 401; `Host` ajeno → 421 y `Origin` ajeno → 403
    con token válido.
  - `tests/unit/test_oauth_provider.py`: reglas del proveedor (solo clientes públicos, máximo de
    clientes, límite de registros, recurso distinto → `invalid_target`, código de un solo uso y
    vencido, tokens vencidos, refresco de otro cliente).
  - `tests/integration/test_oauth_sql_store.py`: proveedor sobre Postgres; en la base solo están los
    hashes; el contenedor valida el token y `ping` responde con un cliente MCP real; refresco,
    reutilización y revocación se reflejan en el contenedor (401).
  - `tests/integration/test_ping_http.py` y `test_public_headers.py`: sin token, 401 con el puntero a
    `https://mcp.puropockets.space/.well-known/oauth-protected-resource/mcp` para cualquier `Host`.
- **Registros del contenedor:** ninguna aparición de `ppa_`, `ppr_`, `ppc_`, `argon2`, `Bearer `,
  `code=`, `refresh_token` ni `password`. Los registros de acceso de uvicorn incluyen la ruta
  `/login?request=<id>`: ese identificador es de un solo uso, vence en 10 minutos y no sirve sin la
  contraseña.
- **Hash en `.env`:** con un hash ficticio entre comillas simples, el contenedor recibe
  `$argon2id$v=19$...` sin alteraciones.
- **argon2:** `argon2-cffi` 25.1.0 se instala con binarios en `python:3.14-slim`; verificación con los
  parámetros por defecto: 0,072 s en el contenedor del equipo de desarrollo.
- **Defecto del SDK documentado:** `/revoke` exige `client_secret` (aunque sea vacío) para clientes
  públicos; la prueba de revocación lo deja registrado y avisará cuando se corrija.

## Pasos del propietario 👤

| Paso del README (Autenticación) | Qué comprobar | Resultado esperado |
|---|---|---|
| 1 | `hash_password.py --benchmark` en el homelab | Mediana < 1 s; hash en `.env` entre comillas simples |
| 2 | `docker compose logs mcp` tras actualizar | Línea `OAuth: emisor=...`, sin aviso de hash vacío |
| 3 | Conector con "Sign in now" y "Register automatically" | Página con "volverás a: claude.ai"; `ping` con `database: ok`; registro cerrado después |
| Desconectar/reconectar | Desde Customize → Connectors | Vuelve a pedir inicio de sesión y funciona (SC-003) |
| Refresco | `OAUTH_SHORT_LIFETIMES=true`, esperar > 2 min | `ping` sigue funcionando; registro `Refresco: ...` |
| Revocar | `scripts/revoke_tokens.py --yes` | El conector pide iniciar sesión de nuevo |

Si el conector no completa el flujo, guarda `docker compose logs --since 15m mcp` (sin secretos) y
repórtalo en lugar de cambiar la configuración.
