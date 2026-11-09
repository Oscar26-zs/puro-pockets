# Implementation Plan: Autenticación (OAuth con servidor propio)

**Branch**: `hito-3-autenticacion` | **Date**: 2026-11-09 | **Spec**: [spec.md](spec.md)

> **Plan delgado (Puro Pockets).** Referencia la constitución y `docs/plan-tecnico.md`; solo registra
> lo nuevo. Las reglas se citan por su identificador.

## Summary

El servidor MCP pasa a ser también servidor de autorización OAuth 2.1 para un único usuario, usando el
módulo de autenticación del SDK (`/authorize`, `/token`, `/register`, `/revoke`, metadatos RFC 8414 y
RFC 9728, PKCE S256, middleware Bearer). Lo propio: el proveedor (almacenamiento de clientes, códigos
y tokens con hash en Postgres, rotación y revocación de cadenas), la página de inicio de sesión con
argon2 y límite de intentos, y la configuración. Revisión previa: [research.md](research.md).

## Technical Context

**Dependencias nuevas**: `argon2-cffi` (instala solo con binarios en `python:3.14-slim`; verificado).

**Cambios al esquema**: migración `0002_oauth`: `oauth_clients`, `oauth_authorization_codes`,
`oauth_access_tokens`, `oauth_refresh_tokens`.

**Tools MCP**: `ping` sin cambios, ahora detrás de autenticación.

**Configuración nueva**: `OWNER_PASSWORD_HASH`, `OAUTH_ISSUER_URL`, `OAUTH_RESOURCE_URL`,
`OAUTH_ALLOWED_REDIRECT_URIS`, `OAUTH_REGISTRATION_ENABLED`, `OAUTH_MAX_CLIENTS`,
`OAUTH_ACCESS_TOKEN_TTL_SECONDS`, `OAUTH_REFRESH_TOKEN_TTL_SECONDS`, `OAUTH_AUTH_CODE_TTL_SECONDS`,
`OAUTH_SHORT_LIFETIMES`.

## Constitution Check

- **Reglas `RN-xx`**: ninguna. Principio 3.10 (minimización en registros).
- **No negociables**: ✓ la regla 1 se cumple al cerrar este hito (a partir de aquí se permiten datos
  reales); ✓ capa de negocio: la lógica pura (hash de tokens, lista blanca, límite de intentos) va en
  `domain/auth.py`, sin MCP ni base; ✓ pruebas: unitarias del dominio, del proveedor y del flujo HTTP
  completo en proceso, e integración con Postgres y el contenedor.
- **[PROPUESTO] asumidos**: límites de intentos (5 fallos por IP en 15 min; 20 globales en 15 min →
  bloqueo global de 5 min; registro: 5 por hora); duraciones del modo corto (acceso 2 min, refresco
  15 min); solo clientes públicos.
- **[ABIERTO]**: ninguno.

## Project Structure

```text
src/puro_pockets/domain/auth.py            # hash de tokens, lista blanca, límite de intentos (puro)
src/puro_pockets/services/oauth.py         # proveedor OAuth (protocolo del SDK) + interfaz de almacén
src/puro_pockets/services/passwords.py     # verificación argon2 (en un hilo)
src/puro_pockets/db/oauth_store.py         # almacén SQL (SQLAlchemy Core)
src/puro_pockets/mcp/login.py              # página y rutas de inicio de sesión
src/puro_pockets/mcp/server.py             # AuthSettings, rutas, wiring
src/puro_pockets/config.py                 # configuración OAuth
migrations/versions/0002_oauth.py
scripts/hash_password.py, scripts/revoke_tokens.py, scripts/register_client.py
tests/unit/...                             # dominio, proveedor, flujo HTTP con almacén en memoria
tests/integration/...                      # almacén SQL y 401 del contenedor
```

## Pruebas

| Criterio | Prueba |
|---|---|
| Sin token / token inválido → 401 con `resource_metadata` | `test_oauth_http.py` (unitaria, en proceso) y `test_ping_http.py` (contenedor) |
| Flujo completo con cliente de prueba | `test_oauth_http.py` |
| URL de retorno no permitida, registro cerrado, máximo de clientes | `test_oauth_provider.py`, `test_oauth_http.py` |
| Refresco con rotación, reutilización revoca la cadena | `test_oauth_provider.py`, `test_oauth_http.py` |
| Revocación | `test_oauth_http.py`, `test_oauth_sql_store.py` |
| Límite de intentos | `test_auth_domain.py`, `test_oauth_http.py` |
| Almacén SQL real (solo hashes) | `test_oauth_sql_store.py` (integración) |
| claude.ai, reconexión, tiempo en el homelab | manual del propietario |

## Actualización del plan técnico al cerrar

Decisión del servidor de autorización, endpoints, duraciones, tablas, límites y procedimiento del
conector.

## Complexity Tracking

Sin violaciones.
