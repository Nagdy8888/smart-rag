FROM python:3.11-slim-bookworm@sha256:d29f48a31a8b408ed19272ca1e7b10ebae13b240a27e862d3d4217c528e2e0c3 AS base

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH" \
    TIKTOKEN_CACHE_DIR=/app/.tiktoken

COPY --from=ghcr.io/astral-sh/uv:0.11.23 /uv /usr/local/bin/uv

RUN useradd --create-home --uid 10001 --shell /usr/sbin/nologin appuser

WORKDIR /app

COPY pyproject.toml uv.lock ./
COPY packages/core/pyproject.toml packages/core/pyproject.toml
COPY packages/core/src/smart_rag_core/retrieval/frozen/hybrid_default_v1.json \
    packages/core/src/smart_rag_core/retrieval/frozen/hybrid_default_v1.json
COPY apps/agents/pyproject.toml apps/agents/pyproject.toml
COPY apps/backend/pyproject.toml apps/backend/pyproject.toml
COPY apps/worker/pyproject.toml apps/worker/pyproject.toml

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --package smart-rag-worker --no-dev --no-install-project

COPY packages/core/src packages/core/src
COPY apps/agents/src apps/agents/src
COPY apps/worker/src apps/worker/src

# Worker has no public DNS (Compose `private` is internal). Prefetch tiktoken
# encodings at build so import/healthcheck cannot call openaipublic.blob.core.windows.net.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --package smart-rag-worker --no-dev \
    && mkdir -p /app/.tiktoken \
    && /app/.venv/bin/python -c "import tiktoken; tiktoken.get_encoding('cl100k_base'); tiktoken.encoding_for_model('gpt-4o-mini')" \
    && chown -R appuser:appuser /app

USER 10001:10001
CMD ["smart-rag-worker"]
