"""Root Dockerignore keeps local env files out of image build context."""

from __future__ import annotations

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]


def test_dockerignore_excludes_env_local_and_keeps_example() -> None:
    """Frontend `.env.local` is ignored; tracked `.env.example` is not."""

    text = (_REPO_ROOT / ".dockerignore").read_text(encoding="utf-8")
    dockerfile = (_REPO_ROOT / "apps/frontend/Dockerfile").read_text(encoding="utf-8")
    compose = (_REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    assert ".env.*" in text
    assert "!.env.example" in text
    assert "**/.env.local" in text
    assert ".git" in text
    assert "**/node_modules" in text
    assert "**/.next" in text
    assert "ARG NEXT_PUBLIC_API_BASE_URL" in dockerfile
    assert "ARG NEXT_PUBLIC_SUPABASE_URL" in dockerfile
    assert "ARG NEXT_PUBLIC_SUPABASE_ANON_KEY" in dockerfile
    assert "\n  frontend:" not in compose
    assert "LANGGRAPH_CHECKPOINT_URL:" in compose
    assert "LIGHTRAG_DB_URL:" in compose
    assert "COPY" not in dockerfile or ".env.local" not in dockerfile
