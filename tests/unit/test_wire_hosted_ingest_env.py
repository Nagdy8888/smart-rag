"""Hosted wire script writes separate transaction and session DSN names."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
WIRE_SCRIPT = REPO_ROOT / "scripts" / "ops" / "wire_hosted_ingest_env.py"


def test_wire_script_writes_session_checkpoint_and_lightrag_names() -> None:
    """The operator script maps session DSN to worker, checkpoint, and graph."""

    source = WIRE_SCRIPT.read_text(encoding="utf-8")
    assert (
        '_upsert_env(compose_path, "NEXT_PUBLIC_SUPABASE_URL", supabase_url)' in source
    )
    assert '_upsert_env(compose_path, "API_SUPABASE_DB_URL", api_dsn)' in source
    assert '_upsert_env(compose_path, "WORKER_SUPABASE_DB_URL", worker_dsn)' in source
    assert '_upsert_env(compose_path, "LANGGRAPH_CHECKPOINT_URL", worker_dsn)' in source
    assert '_upsert_env(compose_path, "LIGHTRAG_DB_URL", worker_dsn)' in source
    assert "Never prints passwords or full URIs" in source or "Never prints" in source
