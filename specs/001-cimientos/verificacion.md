# Verificación del Hito 1: Cimientos

**Fecha:** 2026-11-09 · **Rama:** `hito-1-cimientos` · **Equipo:** Windows 11, Docker Desktop
(WSL 2), Python 3.14.3, uv 0.12.5

Este documento registra **qué se comprobó, cómo y con qué resultado**. Los comandos completos y el
orden están en [quickstart.md](quickstart.md); aquí solo se repiten los necesarios para entender cada
resultado.

**Leyenda:** ✅ Claude = verificado por Claude en esta sesión · 👤 Propietario = te toca a ti.

## Resumen

| # | Verificación | Quickstart | Quién | Estado |
|---|---|---|---|---|
| 1 | Desde cero: de `git clone` a `ping` | §1 | ✅ Claude (clon limpio) · 👤 tercero para SC-001 | 17 s con imágenes en caché |
| 2 | Arranque repetible: 5 arranques con `down -v` | §2 | ✅ Claude | 5/5 |
| 3 | Migraciones: subir, repetir, bajar, subir | §3 | ✅ Claude (prueba automática) | Pasa |
| 4 | `ping` con la base caída y su recuperación | §4 | ✅ Claude | Pasa |
| 5 | Persistencia tras reiniciar (volumen de Postgres 18) | §5 | ✅ Claude | Pasa |
| 6 | Pruebas y estilo en local | §6 | ✅ Claude | 31/31, ruff limpio |
| 7 | CI en GitHub: pasa, y falla con prueba rota o error de estilo | §7 | ✅ Claude (en local) · 👤 Propietario (en GitHub) | Pendiente en GitHub |
| 8 | Arquitectura en capas | §8 | ✅ Claude | Pasa y falla ante violaciones |
| 9 | Medición de memoria | §9 | ✅ Claude | Registrada |
| 10 | `.env` fuera de Git; base y MCP solo en 127.0.0.1 | §10 | ✅ Claude · 👤 Propietario (desde otro equipo, opcional) | Pasa |

---

## 1. Desde cero (SC-001) — quickstart §1

**Comandos:** `git clone` de la rama en una carpeta nueva, `copy .env.example .env` con una contraseña
nueva, `docker compose up -d --build`, `docker compose exec mcp alembic upgrade head`,
`uv run python scripts/ping.py`.

**Esperado:** `{"server": "ok", "database": "ok", "detail": null}` en menos de 15 minutos.

**Resultado ✅ Claude:** clon limpio del contenido en commit, **17 s** desde `git clone` hasta la
respuesta correcta de `ping` (con las imágenes de Docker ya descargadas), y las 31 pruebas pasaron en
el clon. Confirma que lo que está en commit basta para levantar el proyecto.

**👤 Propietario:** SC-001 pide que lo haga **una persona que no participó** (o tú en un equipo sin
las imágenes en caché), siguiendo solo el README y cronometrando.

> Hallazgo de esta prueba: el nombre del proyecto de Compose es fijo (`puro-pockets`), así que todas
> las copias del repositorio en un equipo comparten el volumen `puro-pockets_pgdata`, y Postgres solo
> aplica la contraseña con el volumen vacío. Quedó documentado en el README (problemas frecuentes).

## 2. Arranque repetible (SC-002) — quickstart §2

**Comando (5 veces):** `docker compose down -v` y `docker compose up -d --build --wait`.

**Esperado:** 5 de 5 arranques sin errores.

**Resultado ✅ Claude:** **5/5** (42 s el primero, con build; 9 a 10 s los siguientes), `db` y `mcp`
en ejecución en todos.

## 3. Migraciones: subir y bajar (FR-005, SC-003) — quickstart §3

**Prueba automática:** `uv run pytest tests/integration/test_migrations.py` ejecuta `upgrade head`
dos veces, `downgrade base` y `upgrade head`, y comprueba la versión en cada paso.

**Esperado:** sin errores; versión final `0001_base`; sin tabla de versión tras `downgrade base`.

**Resultado ✅ Claude:** pasa. A mano, `docker compose exec mcp alembic upgrade head` y
`alembic current` → `0001_base (head)`.

## 4. `ping` con la base caída y su recuperación (FR-007, SC-004) — quickstart §4

**Comandos:** `docker compose stop db`, `uv run python scripts/ping.py`, `docker compose start db`,
`uv run python scripts/ping.py`.

**Esperado:** primero `database: "error"` con mensaje en español en menos de 5 s; después
`database: "ok"` sin reiniciar `mcp`.

**Resultado ✅ Claude:**

- Base detenida: `{"server": "ok", "database": "error", "detail": "La base de datos no respondió a
  tiempo."}` en **4,59 s** medidos de punta a punta, incluido el arranque del cliente de Python
  (alrededor de 1 s); la tool corta a los 3 s (2 s de conexión + 1 s de margen).
- Base de nuevo arriba: `{"server": "ok", "database": "ok", "detail": null}`; la hora de inicio del
  contenedor `mcp` no cambió (no se reinició).
- Prueba automática complementaria: `tests/integration/test_ping_db_down.py` (base inalcanzable con el
  driver real → error en menos de 5 s, sin datos de conexión en `detail`).

## 5. Persistencia tras reiniciar (volumen de Postgres 18) — quickstart §5

**Comandos:** crear una tabla de prueba con un valor (`CREATE TABLE prueba_persistencia ...;
INSERT ... 42`), `docker compose down` (sin `-v`), `docker compose up -d`, consultar el valor y borrar
la tabla.

**Esperado:** el valor sigue ahí; los datos viven en el volumen montado en `/var/lib/postgresql`.

**Resultado ✅ Claude:** valor **42** después de `down`/`up`. Dentro del contenedor
`PGDATA=/var/lib/postgresql/18/docker`, dentro del volumen `pgdata` montado en `/var/lib/postgresql`
(el cambio de ruta de la imagen 18). La tabla de prueba se borró.

## 6. Pruebas y estilo en local (SC-005) — quickstart §6

**Comandos:** `uv run pytest`, `uv run ruff check .`, `uv run ruff format --check .`.

**Resultado ✅ Claude:** **31 pruebas pasan** (28 unitarias + 3 de integración) con los servicios
levantados; ruff sin errores; formato correcto.

## 7. CI en GitHub (FR-012, SC-006, SC-008) — quickstart §7

**Esperado:** el workflow `CI` pasa en el último commit; falla con un error de estilo y con una prueba
unitaria rota.

**Resultado ✅ Claude (en local, mismos comandos del workflow):**

- `uv sync --frozen`, `ruff check`, `ruff format --check`, `pytest -m "not integration"` → todo pasa.
- Con una prueba rota temporal (`assert 1 == 2`): `pytest` termina con código 1.
- Con un `import os` sin usar temporal: `ruff check` termina con código 1.
- Los archivos temporales se borraron; no quedaron en ningún commit.

**👤 Propietario (requiere push, que solo haces tú):**

1. `git push -u origin hito-1-cimientos` y comprobar en la pestaña **Actions** que `CI` pasa.
2. En una rama de prueba (por ejemplo `prueba-ci`): agregar `tests/unit/test_rota.py` con
   `def test_rota(): assert 1 == 2`, hacer push y comprobar que `CI` **falla** en "Pruebas unitarias".
3. Revertir; agregar un `import os` sin usar en `scripts/ping.py`, hacer push y comprobar que falla en
   "Estilo".
4. Borrar la rama de prueba.

## 8. Arquitectura en capas (FR-010) — quickstart §8

**Prueba automática:** `uv run pytest tests/unit/test_architecture.py`.

**Resultado ✅ Claude:** pasa (14 casos). Comprobado que **falla** al agregar temporalmente
`import sqlalchemy` o `from mcp.server.mcpserver import MCPServer` en `domain/health.py`
(`AssertionError: domain/ importa capas prohibidas`), y que el detector reconoce también imports
relativos como `from ..db import engine` y `from .. import services`. El archivo quedó sin cambios.

## 9. Medición de memoria (FR-015, SC-007) — quickstart §9

**Comandos:** `docker stats --no-stream` con los servicios estabilizados (varios minutos arriba),
`uv run python scripts/ping.py --times 20` y otra vez `docker stats --no-stream`.

**Resultado ✅ Claude** (registrado en `docs/plan-tecnico.md`, "Medición de memoria"):

| Servicio | En reposo | Tras 20 `ping` |
|---|---|---|
| `db` | 25,1 MiB | 27,8 MiB |
| `mcp` | 75,7 MiB | 78,6 MiB |

**👤 Propietario (Hito 2):** repetir la medición en el homelab.

## 10. `.env` fuera de Git; base y MCP solo en 127.0.0.1 (FR-002, FR-009) — quickstart §10

**Comandos y resultados ✅ Claude:**

- `git check-ignore .env` → ignorado; `git ls-files --error-unmatch .env` → no está en el índice;
  `git log --all -- .env` → nunca entró al historial.
- `.env.example` solo tiene el valor de ejemplo `cambia-esta-contrasena`.
- `docker compose ps` / `docker port`: `db` en `127.0.0.1:5432` y `mcp` en `127.0.0.1:8000` (no
  `0.0.0.0`).
- Protección contra DNS rebinding: un `POST /mcp` con `Host: 127.0.0.1:8000` responde 200; con
  `Host: evil.example.com` responde **421** (rechazado).
- `ping` nunca devuelve datos de conexión: comprobado por `test_ping_tool.py` y
  `test_ping_db_down.py`.

**👤 Propietario (opcional):** desde otro dispositivo de tu red, intentar conectarte a
`<IP-de-tu-equipo>:5432` y `:8000`; debe fallar.

---

## Pendiente para ti

1. Push de la rama y CI en verde en GitHub (§7, punto 1).
2. Comprobar que el CI falla con una prueba rota y con un error de estilo (§7, puntos 2 y 3).
3. SC-001 con una persona que no participó o en un equipo sin caché (§1).
4. Opcional: comprobar desde otro dispositivo que los puertos no son accesibles (§10).
5. Crear la etiqueta del hito y fusionar, cuando lo decidas.
