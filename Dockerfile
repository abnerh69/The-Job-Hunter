# Stage 1: Builder
FROM ghcr.io/astral-sh/uv:0.5.11-python3.12-bookworm-slim AS builder

ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy

WORKDIR /app

# Install dependencies (no dev, no project) using uv lockfile
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --frozen --no-install-project --no-dev

# Stage 2: Runner
FROM python:3.12-slim-bookworm

WORKDIR /app

# Virtualenv from builder
COPY --from=builder /app/.venv /app/.venv

# Application code + assets needed at runtime
COPY src ./src
COPY alembic ./alembic
COPY prompts ./prompts
COPY cv_variants ./cv_variants
COPY pyproject.toml uv.lock alembic.ini ./

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH="/app/src" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# 8000 = FastAPI sidecar (health/readiness)
# 8080 = Streamlit dashboard
EXPOSE 8000 8080

# Default command = API sidecar (long-running, healthcheck-friendly).
# docker-compose.yml overrides `command:` per service (migrate, dashboard).
# CLI one-shot:  docker compose exec app python -m jobhunter <comando>
CMD ["python", "-m", "jobhunter", "api", "run", "--host", "0.0.0.0", "--port", "8000"]
