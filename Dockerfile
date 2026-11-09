# Imagen del servidor MCP de Puro Pockets
FROM ghcr.io/astral-sh/uv:0.12.5 AS uv

FROM python:3.14-slim

COPY --from=uv /uv /usr/local/bin/uv

ENV PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/app/.venv

WORKDIR /app

# Dependencias primero (capa cacheable), exactamente las de uv.lock
COPY pyproject.toml uv.lock .python-version README.md ./
RUN uv sync --frozen --no-dev --no-install-project

# Código de la aplicación y migraciones
COPY src ./src
COPY migrations ./migrations
COPY alembic.ini ./
# Cliente de prueba: healthcheck del servicio y ping en el homelab sin instalar uv
COPY scripts ./scripts
RUN uv sync --frozen --no-dev

RUN useradd --create-home --uid 1000 app && chown -R app:app /app
USER app

ENV PATH="/app/.venv/bin:$PATH"
EXPOSE 8000

CMD ["python", "-m", "puro_pockets"]
