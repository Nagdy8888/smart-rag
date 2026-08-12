# syntax=docker/dockerfile:1

FROM python:3.11-slim-bookworm@sha256:d29f48a31a8b408ed19272ca1e7b10ebae13b240a27e862d3d4217c528e2e0c3 AS base

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH"

COPY --from=ghcr.io/astral-sh/uv:0.11.23 /uv /usr/local/bin/uv

RUN useradd --create-home --uid 10001 --shell /usr/sbin/nologin appuser

WORKDIR /app

# Cache dependency resolution from workspace metadata only.
COPY pyproject.toml uv.lock ./
COPY packages/core/pyproject.toml packages/core/pyproject.toml
COPY apps/agents/pyproject.toml apps/agents/pyproject.toml
COPY apps/backend/pyproject.toml apps/backend/pyproject.toml
COPY apps/worker/pyproject.toml apps/worker/pyproject.toml

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --package smart-rag-backend --no-dev --no-install-project

COPY packages/core/src packages/core/src
COPY apps/agents/src apps/agents/src
COPY apps/backend/src apps/backend/src

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --package smart-rag-backend --no-dev \
    && chown -R appuser:appuser /app

USER 10001:10001
EXPOSE 8000
CMD ["uvicorn", "smart_rag_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
