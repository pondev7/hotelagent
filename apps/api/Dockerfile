# Build context is the repo root — pyproject.toml and uv.lock live there so the
# api and worker images share one dependency resolution.
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.5 /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# Dependencies resolve in their own layer so a source edit does not reinstall
# the world. --no-install-project: the app itself is mounted or copied below.
COPY pyproject.toml uv.lock* ./
RUN uv sync --frozen --no-install-project --no-dev 2>/dev/null \
    || uv sync --no-install-project --no-dev

COPY apps/api/src ./apps/api/src

ENV PYTHONPATH=/app/apps/api/src

EXPOSE 8000

CMD ["uvicorn", "hotelagent.main:app", "--host", "0.0.0.0", "--port", "8000"]
