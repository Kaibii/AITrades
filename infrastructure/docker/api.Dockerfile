FROM python:3.12-slim
WORKDIR /app
COPY --from=ghcr.io/astral-sh/uv:0.12.23 /uv /usr/local/bin/uv
COPY pyproject.toml uv.lock ./
COPY packages ./packages
COPY apps/api ./apps/api
COPY alembic.ini ./
COPY migrations ./migrations
RUN --mount=type=secret,id=environment_ca \
    if [ -f /run/secrets/environment_ca ]; then \
      export SSL_CERT_FILE=/run/secrets/environment_ca UV_SYSTEM_CERTS=true; \
    fi; uv sync --frozen --no-dev
EXPOSE 8000
CMD ["sh", "-c", "uv run --no-sync alembic upgrade head && uv run --no-sync uvicorn app.main:app --host 0.0.0.0 --port 8000"]
