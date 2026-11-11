# Quickstart: validar el Hito 4

## Requisitos

- Servicios locales levantados: `docker compose up -d --build` y
  `docker compose exec mcp alembic upgrade head` (migración `0003_budget`).
- `.env` con `DATABASE_URL` hacia `127.0.0.1`. Las pruebas de integración crean y borran su propia base
  temporal ([research.md](research.md) §7): no tocan tus datos de desarrollo.

## Pruebas automáticas

```bash
uv run ruff check . && uv run ruff format --check .
uv run pytest -m "not integration"      # dominio, servicio con almacén en memoria, invariante, tools
uv run pytest -m integration            # Postgres: migración, almacén SQL, cargas simultáneas, invariante
```

Esperado: todo pasa. Las pruebas cubren los escenarios de [spec.md](spec.md) (tabla en
[plan.md](plan.md), sección "Pruebas").

## Comprobación desde Claude (propietario, en el homelab)

Tras actualizar el homelab (`git pull`, `docker compose up -d --build`) y aplicar la migración con
`docker compose exec mcp alembic upgrade head` (**nunca** `downgrade` en el homelab: borraría datos
reales):

1. "Define los porcentajes de este mes: Necesidades 50, Ahorro 30, Gustos 20." → los guarda.
2. "Ahora pon Necesidades 50, Ahorro 30, Gustos 30." → rechazo: suman 110.
3. "¿Qué porcentajes tiene el mes siguiente?" → los de este mes, indicando que vienen de este mes.
4. "Define 40/40/20 para el mes siguiente" y luego "¿y los de este mes?" → siguen en 50/30/20.
5. "Muéstrame la vista previa del saldo inicial: …" → total y montos, sin guardar.
6. "Carga el saldo inicial." → `list_bolsas` muestra el saldo de cada bolsa.
7. "Carga otra vez el saldo inicial." → rechazo.

Anota el resultado en `verificacion.md`. El saldo inicial es real y se carga **una sola vez**: revisa
bien la vista previa. Corregirlo requiere la anulación del Hito 5.
