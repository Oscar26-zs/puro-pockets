# Quickstart: validar el Hito 6

Datos siempre sintéticos. Nada contra la base del homelab desde aquí.

1. `uv run ruff check .` y `uv run ruff format --check .`.
2. `uv run pytest tests/unit` (en el CI).
3. Con `docker compose up -d db`: `uv run pytest -m integration` (bases temporales `pp_test_*`).
4. Base de desarrollo: respaldo con `pg_dump` (README), `docker compose up -d --build mcp`,
   `docker compose exec mcp alembic upgrade head` → `0005_extras_recurring (head)`.
5. Desde Claude o un cliente MCP con token: registrar un extra, pedir el contexto, vista previa,
   confirmar con la ficha; crear un fijo, listar pendientes, pagarlo, anular el pago.
6. `docker compose logs mcp`: solo eventos (referencias, mes, moneda), sin montos ni descripciones.

Resultados esperados y pasos del homelab: [verificacion.md](verificacion.md).
