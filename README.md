# Puro Pockets

Aplicación personal de finanzas que se usa conversando con Claude a través de un servidor MCP.
Este repositorio está en el **Hito 1 (Cimientos)**: el servidor MCP y la base de datos se levantan
con un solo comando y una tool `ping` informa si ambos están operativos. Todavía no hay datos
financieros, acceso remoto ni autenticación (ver [HITOS.md](HITOS.md)).

Documentos del proyecto: [constitución](.specify/memory/constitution.md) (reglas),
[plan técnico](docs/plan-tecnico.md) (técnica) y [HITOS.md](HITOS.md) (hoja de ruta).

## Requisitos

- [Docker Desktop](https://docs.docker.com/desktop/) con Docker Compose (en Windows, con WSL 2).
- [uv](https://docs.astral.sh/uv/) (gestor de Python; instala la versión de Python que haga falta).
- Puertos `5432` y `8000` libres en `127.0.0.1`.

## 1. Configurar

```powershell
git clone <url-del-repositorio> puro-pockets
cd puro-pockets
copy .env.example .env        # en Linux o macOS: cp .env.example .env
```

Edita `.env` y cambia `cambia-esta-contrasena` por una contraseña propia, **en las dos líneas** donde
aparece (`POSTGRES_PASSWORD` y `DATABASE_URL`). Usa solo letras, números, `-` y `_`: otros caracteres
(como `@`, `:` o `/`) rompen la URL de conexión. `.env` nunca se sube al repositorio.

## 2. Levantar los servicios

```powershell
docker compose up -d --build
docker compose ps
```

Debe mostrar `db` como `healthy` y `mcp` como `running`, con los puertos publicados solo en
`127.0.0.1` (`127.0.0.1:5432` y `127.0.0.1:8000`).

## 3. Aplicar las migraciones

```powershell
docker compose exec mcp alembic upgrade head
```

Para revertir hasta el inicio y volver a aplicar:

```powershell
docker compose exec mcp alembic downgrade base
docker compose exec mcp alembic upgrade head
```

## 4. Comprobar que está vivo (`ping`)

```powershell
uv run python scripts/ping.py
```

Respuesta esperada:

```json
{"server": "ok", "database": "ok", "detail": null}
```

Si la base no responde, `ping` contesta igual, en menos de 5 segundos, con `"database": "error"` y un
motivo breve en `detail`. El servidor MCP escucha en `http://127.0.0.1:8000/mcp` (transporte
Streamable HTTP); cualquier cliente MCP local, como el MCP Inspector, puede conectarse a esa URL.

## 5. Pruebas y estilo

La primera vez, `uv sync` instala las dependencias exactas de `uv.lock`.

```powershell
uv sync
uv run pytest -m "not integration"   # pruebas unitarias (lo mismo que corre en GitHub)
uv run pytest                        # unitarias + integración (requiere los servicios levantados)
uv run ruff check .
uv run ruff format --check .
```

En cada push, GitHub Actions corre `ruff` y las pruebas unitarias
([.github/workflows/ci.yml](.github/workflows/ci.yml)).

## Detener y borrar datos

```powershell
docker compose down        # detiene; los datos se conservan en el volumen pgdata
docker compose down -v     # detiene y BORRA los datos de la base (irreversible)
```

## Estructura

```text
src/puro_pockets/
├── config.py      # configuración desde variables de entorno
├── domain/        # reglas puras (sin MCP ni base de datos)
├── services/      # casos de uso
├── db/            # conexión a la base (SQLAlchemy + psycopg 3)
└── mcp/           # servidor MCP y tools
migrations/        # Alembic
tests/unit/        # pruebas unitarias
tests/integration/ # pruebas con los servicios levantados
scripts/ping.py    # cliente de prueba
```

## Actualizar el SDK de MCP

La versión del SDK está fijada (`mcp==2.3.0`). Actualizarla es una decisión deliberada: sigue el
procedimiento "Actualizar el SDK de MCP" de [docs/plan-tecnico.md](docs/plan-tecnico.md).

## Problemas frecuentes

- **El puerto 5432 u 8000 ya está en uso:** `docker compose up` falla con un mensaje de puerto
  ocupado. Cierra el programa que lo usa o cambia `POSTGRES_PORT` / `MCP_PORT` en `.env` (y el puerto
  de `DATABASE_URL`).
- **Falta una variable en `.env`:** Docker Compose indica cuál (por ejemplo, `Falta POSTGRES_PASSWORD
  en .env`).
- **Conexiones lentas desde el equipo:** usa `127.0.0.1` y no `localhost` en `DATABASE_URL`.
