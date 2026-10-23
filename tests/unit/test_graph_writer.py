"""Unit tests for graph writer lock keys and workspace transition helpers."""

from __future__ import annotations

import subprocess
import sys

from smart_rag_core.jobs.graph_writer import (
    ADVISORY_LOCK_NAMESPACE,
    allowed_index_from_states,
    graph_advisory_lock_keys,
)
from smart_rag_core.retrieval.graph import (
    bind_graph_source_text,
    graph_chunker_config_snapshot,
    opaque_graph_source_basename,
)
from smart_rag_core.schema.enums import GraphWorkspaceState


def test_provider_model_alias_does_not_select_the_local_tokenizer() -> None:
    """All-Luna inference must start without changing the qualified chunk encoding."""
    probe = """
import os
os.environ['OPENAI_CHAT_MODEL_ID'] = 'gpt-6-luna'
os.environ['OPENAI_LIGHTRAG_MODEL_ID'] = 'gpt-6-luna'
from tiktoken.model import encoding_name_for_model
from smart_rag_core.retrieval.graph import LIGHTRAG_LLM_MODEL_ID, LIGHTRAG_TIKTOKEN_MODEL
assert LIGHTRAG_LLM_MODEL_ID == 'gpt-6-luna'
assert encoding_name_for_model(LIGHTRAG_TIKTOKEN_MODEL) == 'o200k_base'
"""
    result = subprocess.run(  # noqa: S603 - fixed interpreter and import-only probe
        (sys.executable, "-c", probe),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_advisory_lock_keys_are_stable_and_positive() -> None:
    """The same workspace key must hash to the same positive int4 pair."""

    first = graph_advisory_lock_keys("company_default")
    second = graph_advisory_lock_keys("company_default")
    other = graph_advisory_lock_keys("company_default__rebuild")
    assert first == second
    assert first != other
    assert first[0] >= 0
    assert first[1] >= 0
    assert ADVISORY_LOCK_NAMESPACE in "smart-rag-graph-writer-v1"


def test_index_from_states_exclude_quarantine() -> None:
    """Normal insert must not start from quarantined or retired."""

    allowed = allowed_index_from_states()
    assert GraphWorkspaceState.QUARANTINED not in allowed
    assert GraphWorkspaceState.RETIRED not in allowed
    assert GraphWorkspaceState.DISABLED not in allowed
    assert GraphWorkspaceState.UPDATING in allowed


def test_opaque_basename_is_unique_per_version() -> None:
    """Basename tokens must differ across versions and never be URLs."""

    first = opaque_graph_source_basename("11111111-1111-1111-1111-111111111111")
    second = opaque_graph_source_basename("22222222-2222-2222-2222-222222222222")
    assert first != second
    assert first.startswith("g-")
    assert first.endswith(".txt")
    assert "http" not in first
    snapshot = graph_chunker_config_snapshot()
    assert snapshot["chunk_token_size"] == 1200
    assert snapshot["chunk_overlap_token_size"] == 100
    assert snapshot["tiktoken_model_name"] == "gpt-4o-mini"


def test_envelope_binds_version_id() -> None:
    """Insert text must carry the identity envelope, not a random salt."""

    version_id = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    bound = bind_graph_source_text(
        document_version_id=version_id,
        normalized_text="canonical chunk text",
    )
    assert version_id in bound
    assert bound.endswith("canonical chunk text")
