# syntax=docker/dockerfile:1

FROM python:3.11-slim-bookworm@sha256:d29f48a31a8b408ed19272ca1e7b10ebae13b240a27e862d3d4217c528e2e0c3 AS base

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH"

COPY --from=ghcr.io/astral-sh/uv:0.11.23 /uv /usr/local/bin/uv

RUN useradd --create-home --uid 10001 --shell /usr/sbin/nologin appuser

WORKDIR /app

COPY pyproject.toml uv.lock ./
COPY packages/core/pyproject.toml packages/core/pyproject.toml
COPY apps/agents/pyproject.toml apps/agents/pyproject.toml
COPY apps/backend/pyproject.toml apps/backend/pyproject.toml
COPY apps/worker/pyproject.toml apps/worker/pyproject.toml

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --package smart-rag-agents --no-dev --no-install-project

COPY packages/core/src packages/core/src
COPY apps/agents/src apps/agents/src
COPY apps/agents/langgraph.json apps/agents/langgraph.json

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --package smart-rag-agents --no-dev \
    && chown -R appuser:appuser /app

USER 10001:10001
WORKDIR /app/apps/agents
CMD ["python", "-c", "from langgraph_cli.config import validate_config_file; from pathlib import Path; print(validate_config_file(Path('langgraph.json')))"]
