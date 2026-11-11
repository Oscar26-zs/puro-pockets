# Quickstart: validar el Hito 8

Datos siempre sintéticos. Nada contra la base del homelab desde aquí.

1. `uv run ruff check .` y `uv run ruff format --check .`.
2. `uv run pytest tests/unit` (en el CI).
3. Con `docker compose up -d db`: `uv run pytest -m integration` (bases temporales `pp_test_*`;
   incluye la concurrencia).
4. Base de desarrollo: respaldo con `pg_dump` (README), `docker compose up -d --build mcp`,
   `docker compose exec mcp alembic upgrade head` → `0007_transfers (head)`.
5. Desde Claude o un cliente MCP con token: gasto que deja Gustos en negativo, `preview_transfer`
   desde Necesidades, confirmación con la ficha, `get_bolsa_status` con el presupuesto ajustado, meta
   con aviso del efecto, vaciar una bolsa y archivarla.
6. `docker compose logs mcp`: solo eventos (`T-n`, mes, motivo, cantidad de metas afectadas), sin
   montos, notas ni nombres de metas.

Resultados esperados y pasos del homelab: [verificacion.md](verificacion.md).
