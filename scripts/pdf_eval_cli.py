"""Shared fail-closed helpers for private PDF eval CLIs.

Prints counts, hashes, and block reasons only. Never prints questions,
answers, glossary values, or excerpts.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from smart_rag_core.settings import set_process_environ, setdefault_process_environ

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from scripts.ops.ingest_demo_plot_slices import merged_env, require_env  # noqa: E402

VERIFIED = frozenset({"1", "true", "yes", "on"})


def apply_merged_env() -> dict[str, str]:
    """Load ``.env`` plus ``.env.compose`` into process env without override.

    Returns:
        Merged mapping.
    """

    env = merged_env()
    for key, value in env.items():
        setdefault_process_environ(key, value)
    return env


def matrix_verified(env: dict[str, str]) -> bool:
    """Return whether the operator signed the provider matrix.

    Args:
        env: Merged environment.

    Returns:
        True when ``SMART_RAG_SUBPROCESSOR_MATRIX_VERIFIED`` is truthy.
    """

    return env.get("SMART_RAG_SUBPROCESSOR_MATRIX_VERIFIED", "").strip().lower() in (
        VERIFIED
    )


def resolve_labels_path(labels: Path, ingest_ids: Path) -> Path:
    """Resolve the gitignored draft/sealed JSON from ingest identity.

    Args:
        labels: Caller path.
        ingest_ids: ``.private-eval/ingest-ids.json``.

    Returns:
        Existing labels path, or the caller path when no better candidate exists.
    """

    if not ingest_ids.is_file():
        return labels
    payload = json.loads(ingest_ids.read_text(encoding="utf-8"))
    digest = str(payload.get("content_hash", ""))
    if len(digest) < 12:
        return labels
    sealed = Path(".private-eval") / digest[:12] / "v1" / "sealed.json"
    if sealed.is_file():
        return sealed
    if labels.is_file():
        return labels
    draft = Path(".private-eval") / digest[:12] / "v1" / "draft.json"
    return draft if draft.is_file() else labels


def operator_url(env: dict[str, str]) -> str:
    """Return the hosted operator DSN.

    Args:
        env: Merged environment.

    Returns:
        Operator URL.

    Raises:
        RuntimeError: Missing URL.
    """

    return require_env(env, "OPERATOR_SUPABASE_DB_URL")


def require_live_models(env: dict[str, str]) -> None:
    """Force live OpenAI for overlay Hybrid eval. Mock cannot pass the gate.

    Args:
        env: Merged ``.env`` / ``.env.compose`` mapping.

    Raises:
        RuntimeError: Missing API key.
    """

    key = env.get("OPENAI_API_KEY", "")
    if not key.strip():
        raise RuntimeError("openai_api_key_required")
    set_process_environ("MOCK_MODEL_MODE", "false")
    set_process_environ("OPENAI_API_KEY", key)
    export_io = env.get("LANGSMITH_EXPORT_IO", "false").strip() or "false"
    set_process_environ("LANGSMITH_EXPORT_IO", export_io)
