# Tasks: Autenticación (OAuth con servidor propio)

**Tests**: OBLIGATORIAS (gobernanza, regla 4). Pruebas antes que la implementación.

## Phase 1: Setup

- [X] T001 Agregar `argon2-cffi` a `pyproject.toml` y actualizar `uv.lock`
- [X] T002 [P] `.env.example`: variables OAuth (sin valores secretos; `OWNER_PASSWORD_HASH` vacío con instrucciones)

## Phase 2: Foundational

- [X] T003 [P] Pruebas en `tests/unit/test_auth_domain.py` (hash de tokens, lista blanca, límite de intentos)
- [X] T004 Implementar `src/puro_pockets/domain/auth.py`
- [X] T005 [P] Pruebas de configuración OAuth en `tests/unit/test_config.py`
- [X] T006 Configuración OAuth en `src/puro_pockets/config.py` (duraciones, modo corto, lista blanca, registro)
- [X] T007 Migración `migrations/versions/0002_oauth.py` (tablas en inglés, solo hashes)

## Phase 3: US1 + US2 - Solo el propietario; conector (P1)

- [X] T008 [P] [US1] Pruebas del proveedor en `tests/unit/test_oauth_provider.py` con almacén en memoria (`tests/fakes.py`)
- [X] T009 [P] [US1] Pruebas del flujo HTTP en `tests/unit/test_oauth_http.py` (401, token inválido, flujo completo, retorno no permitido, registro cerrado, máximo de clientes, límite de intentos, refresco, reutilización, revocación)
- [X] T010 [US1] `src/puro_pockets/services/passwords.py` (argon2 en un hilo)
- [X] T011 [US1] `src/puro_pockets/services/oauth.py` (proveedor + interfaz de almacén)
- [X] T012 [US1] `src/puro_pockets/db/oauth_store.py` (almacén SQL)
- [X] T013 [US2] `src/puro_pockets/mcp/login.py` (página con dominio de retorno, límite de intentos, registros sin secretos)
- [X] T014 [US1] `src/puro_pockets/mcp/server.py` y `__main__.py` (AuthSettings, rutas, wiring)

## Phase 4: US3 - Sesiones y revocación (P2)

- [X] T015 [US3] `scripts/revoke_tokens.py` y `scripts/register_client.py` (alternativa "cliente propio")
- [X] T016 [US3] Prueba de integración `tests/integration/test_oauth_sql_store.py`

## Phase 5: Operación

- [X] T017 `scripts/hash_password.py` (getpass, solo imprime el hash, `--benchmark`)
- [X] T018 `docker-compose.yml`: variables OAuth; healthcheck por metadatos; `scripts/ping.py` con token opcional
- [X] T019 Actualizar pruebas de integración del Hito 1 y 2 al nuevo comportamiento (401 sin token) (las comprobaciones de 401 y metadatos quedaron en `tests/integration/test_ping_http.py`)

## Phase 6: Polish

- [X] T020 README (Hito 3: hash, .env, conector, registro abierto y cerrado, revocación, duraciones cortas, medir argon2 en el homelab, cliente propio)
- [X] T021 `docs/plan-tecnico.md` (decisión, endpoints, duraciones, tablas, límites) y `HITOS.md` sección 3
- [X] T022 `verificacion.md`; validación final (ruff, pytest, sin secretos en registros ni archivos)
