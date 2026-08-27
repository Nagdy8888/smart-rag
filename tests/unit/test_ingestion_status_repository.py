"""Ingestion status repository SQL contracts."""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
REPOSITORY = (
    REPO_ROOT
    / "packages"
    / "core"
    / "src"
    / "smart_rag_core"
    / "repositories"
    / "ingestion_status.py"
)


def test_ingestion_status_rpc_uses_explicit_casts() -> None:
    """Pooler-inferred smallint must still match ``bigint`` authorization_version."""

    source = REPOSITORY.read_text(encoding="utf-8")
    assert "%s::uuid, %s::text, %s::bigint, %s::uuid" in source
    assert "app.get_version_ingestion_status" in source
