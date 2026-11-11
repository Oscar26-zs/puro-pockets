# Quickstart: validar el Hito 7

Datos siempre sintéticos. Nada contra la base del homelab desde aquí.

1. `uv run ruff check .` y `uv run ruff format --check .`.
2. `uv run pytest tests/unit` (en el CI).
3. Con `docker compose up -d db`: `uv run pytest -m integration` (bases temporales `pp_test_*`).
4. Base de desarrollo: respaldo con `pg_dump` (README), `docker compose up -d --build mcp`,
   `docker compose exec mcp alembic upgrade head` → `0006_pockets_goals (head)`.
5. Desde Claude o un cliente MCP con token: vista previa del reajuste, crear una bolsa con la ficha,
   crear una meta, registrar un salario que la alcance, gastar y ver que sigue lograda, archivar una
   bolsa vacía.
6. `docker compose logs mcp`: solo eventos (referencias M-n, comportamiento, meses), sin montos ni
   nombres de metas.

Resultados esperados y pasos del homelab: [verificacion.md](verificacion.md).
