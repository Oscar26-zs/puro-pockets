# Quickstart: validar el Hito 5

Datos siempre sintéticos en desarrollo. Nada de esto se ejecuta contra el homelab (ver
`verificacion.md` para los pasos del propietario allí).

## Pruebas automáticas

```powershell
uv run ruff check . ; uv run ruff format --check .
docker compose up -d db          # las de integración crean y borran su base pp_test_*
uv run pytest                    # unitarias + integración
```

## Base de desarrollo

```powershell
docker compose up -d --build
docker compose exec mcp alembic upgrade head     # -> 0004_movements (head)
```

Con un cliente MCP autenticado contra `http://127.0.0.1:8000/mcp`:

1. `set_allocation` 50/30/20 para el mes siguiente.
2. `preview_income` ₡1.000.001 con fecha de hoy → reparto 500.000 / 300.000 / 200.001, `saved=false`.
3. `add_income` igual con `confirm=true` y una clave → `reference=I-n`.
4. `add_expense` USD `"10.00"` a `"512.34"` → `amount_crc=5123`.
5. `add_expense` que excede Gustos → `overspent=true` y `available_pockets`.
6. Repetir el paso 5 con la misma clave → misma respuesta, un solo gasto.
7. `void_transaction` del gasto con `confirm=true` → `list_transactions` lo muestra anulado.
8. `get_bolsa_status`, `get_summary`, `top_categories` cuadran entre sí.
