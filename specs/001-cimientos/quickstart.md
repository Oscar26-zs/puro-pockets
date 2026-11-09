# Quickstart de validación: Cimientos (001-cimientos)

Guía para comprobar el "Terminado cuando" del Hito 1. No reemplaza al README: el README es la guía
para el usuario; esta guía es para validar el hito. Contrato de `ping`:
[contracts/ping.md](contracts/ping.md).

## Requisitos

- Docker Desktop (con Compose) y uv instalados.
- Puertos `5432` y `8000` libres en `127.0.0.1`.

## 1. Desde cero (SC-001)

Cronometrar desde el primer comando hasta la respuesta de `ping` (objetivo: menos de 15 minutos):

```powershell
git clone <url-del-repo> puro-pockets
cd puro-pockets
copy .env.example .env      # y editar la contraseña
docker compose up -d --build
docker compose exec mcp alembic upgrade head
uv run python scripts/ping.py   # cliente de prueba: imprime la respuesta de ping
```

**Esperado:** `{"server": "ok", "database": "ok", "detail": null}`.

## 2. Arranque repetible (SC-002)

Repetir 5 veces, borrando los datos entre intentos:

```powershell
docker compose down -v
docker compose up -d --build
docker compose ps        # db healthy, mcp running
```

**Esperado:** 5 de 5 arranques sin errores.

## 3. Migraciones (SC-003, historia 1, escenario 6)

```powershell
docker compose exec mcp alembic upgrade head    # primera vez
docker compose exec mcp alembic upgrade head    # segunda vez: no hace nada, no falla
docker compose exec mcp alembic downgrade base
docker compose exec mcp alembic upgrade head
```

**Esperado:** los cuatro comandos terminan sin errores.

## 4. Base caída y recuperación (FR-007, historia 1, escenario 7)

```powershell
docker compose stop db
uv run python scripts/ping.py   # database: error, en menos de 5 s
docker compose start db
uv run python scripts/ping.py   # database: ok, sin reiniciar mcp
```

## 5. Persistencia (historia 1, escenario 5)

Crear una tabla temporal de prueba con `docker compose exec db psql ...`, ejecutar
`docker compose down` (sin `-v`) y `docker compose up -d`, y comprobar que la tabla sigue ahí. Después
borrar la tabla de prueba.

## 6. Pruebas y estilo (SC-005)

```powershell
uv run ruff check
uv run ruff format --check
uv run pytest                      # unitarias + integración (con servicios levantados)
uv run pytest -m "not integration" # lo mismo que corre en GitHub
```

## 7. Verificación en GitHub (SC-006, SC-008)

En una rama de prueba: subir un error de estilo deliberado y comprobar que el workflow falla;
revertirlo, subir una prueba unitaria rota y comprobar que falla; revertir y comprobar que pasa.

## 8. Arquitectura en capas (FR-010)

`uv run pytest tests/unit/test_architecture.py` pasa. Agregar temporalmente un `import sqlalchemy`
en un módulo de `domain/` hace fallar la prueba.

## 9. Memoria (FR-015, SC-007)

```powershell
docker compose up -d
# esperar unos 60 segundos
docker stats --no-stream
uv run python scripts/ping.py --times 20
docker stats --no-stream
```

Anotar el uso de memoria de `db` y `mcp` en ambos momentos en la tabla "Medición de memoria" de
`docs/plan-tecnico.md`, con fecha y equipo.

## 10. Accesible solo desde el equipo (FR-002)

`docker compose ps` muestra los puertos publicados como `127.0.0.1:5432` y `127.0.0.1:8000`, no
`0.0.0.0`.
