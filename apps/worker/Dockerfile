FROM python:3.11-slim-trixie@sha256:9c900dea9e8fb7e16277c179b555cc72d29a352dbc33cff48ad5a0412fd5bfc7 AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH" \
    TIKTOKEN_CACHE_DIR=/app/.tiktoken

COPY --from=ghcr.io/astral-sh/uv:0.11.23 /uv /usr/local/bin/uv

RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get upgrade -y \
    && rm -rf /var/lib/apt/lists/*

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
    && /app/.venv/bin/python -c "import tiktoken; tiktoken.get_encoding('cl100k_base'); tiktoken.encoding_for_model('gpt-4o-mini')"

COPY infra/docker/collect_runtime_shared_libs.py /tmp/collect_runtime_shared_libs.py
RUN python /tmp/collect_runtime_shared_libs.py --output /runtime-so \
    --root /usr/local --root /app/.venv

FROM gcr.io/distroless/cc-debian13:nonroot@sha256:d97bc0a941b8d4be647dc0ee75b264ddbb772f1ac5ba690a4309c00723b23775

ENV PATH="/app/.venv/bin:/usr/local/bin:$PATH" \
    TIKTOKEN_CACHE_DIR=/app/.tiktoken \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY --from=builder --chown=10001:10001 /runtime-so/ /
COPY --from=builder --chown=10001:10001 /usr/local /usr/local
COPY --from=builder --chown=10001:10001 /etc/ssl/certs /etc/ssl/certs
COPY --from=builder --chown=10001:10001 /app /app

USER 10001:10001
CMD ["smart-rag-worker"]
