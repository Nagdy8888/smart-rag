"""Source bodies must not bypass compaction through pending-write sequences."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from copy import deepcopy
from typing import Any, cast

import pytest
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from smart_rag_agents.query.persistence.checkpointer import (
    CompactAsyncPostgresSaver,
    CompactPostgresSaver,
)

_SOURCE = "PRIVATE_SOURCE_BODY_MUST_NOT_REACH_CHECKPOINT_STORAGE " * 100
_CONFIG: RunnableConfig = {"configurable": {"thread_id": "fixture-thread"}}


def _writes(container: str) -> list[tuple[str, Any]]:
    """Build realistic retrieval writes plus ordered duplicate/scalar writes."""
    branch = {
        "hybrid_evidence": [
            {
                "chunk_id": "chunk-1",
                "document_id": "document-1",
                "citation_text": _SOURCE,
            }
        ]
    }
    value: object = branch
    if container == "list":
        value = [branch]
    elif container == "tuple":
        value = (branch,)
    return [
        ("branch_results", value),
        ("status", "branches_executed"),
        ("status", "fused"),
        ("remaining_model_calls", 3),
        ("optional_result", None),
    ]


def _assert_storage_safe(
    stored: Sequence[tuple[str, Any]],
    original: list[tuple[str, Any]],
    before: list[tuple[str, Any]],
) -> None:
    """Check storage privacy, metadata, order, shape, and live-state isolation."""
    assert original == before
    assert [channel for channel, _ in stored] == [channel for channel, _ in original]
    assert list(stored[1:]) == original[1:]
    value = stored[0][1]
    assert type(value) is type(original[0][1])
    branch = cast(
        dict[str, Any],
        cast(Sequence[Any], value)[0] if isinstance(value, (list, tuple)) else value,
    )
    evidence = cast(dict[str, Any], branch["hybrid_evidence"][0])
    assert evidence["chunk_id"] == "chunk-1"
    assert evidence["document_id"] == "document-1"
    assert evidence["citation_text_chars"] == len(_SOURCE)
    assert len(evidence["citation_text_sha256"]) == 16
    assert "citation_text" not in evidence
    serde = JsonPlusSerializer()
    kind, encoded = serde.dumps_typed(value)
    assert _SOURCE.encode() not in encoded
    decoded = serde.loads_typed((kind, encoded))
    assert decoded == (
        list(cast(Sequence[Any], value)) if isinstance(value, tuple) else value
    )
    assert len(encoded) < len(_SOURCE.encode()) // 10


@pytest.mark.parametrize("container", ["mapping", "list", "tuple"])
def test_sync_pending_writes_compact_nested_sources(
    monkeypatch: pytest.MonkeyPatch, container: str
) -> None:
    """Every supported state container is compacted at the sync saver boundary."""
    writes = _writes(container)
    before = deepcopy(writes)
    captured: list[tuple[str, Any]] = []

    def store(
        self: PostgresSaver,
        config: RunnableConfig,
        values: Sequence[tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        """Capture the compacted sync write without requiring a database."""
        assert config == _CONFIG
        assert (task_id, task_path) == ("task-1", "branch-1")
        captured.extend(values)

    monkeypatch.setattr(PostgresSaver, "put_writes", store)
    saver = object.__new__(CompactPostgresSaver)
    saver.put_writes(_CONFIG, writes, "task-1", "branch-1")
    _assert_storage_safe(captured, writes, before)


@pytest.mark.parametrize("container", ["mapping", "list", "tuple"])
def test_async_pending_writes_compact_nested_sources(
    monkeypatch: pytest.MonkeyPatch, container: str
) -> None:
    """The production async path has the same storage contract as sync writes."""
    writes = _writes(container)
    before = deepcopy(writes)
    captured: list[tuple[str, Any]] = []

    async def store(
        self: AsyncPostgresSaver,
        config: RunnableConfig,
        values: Sequence[tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        """Capture the compacted async write without requiring a database."""
        assert config == _CONFIG
        assert (task_id, task_path) == ("task-1", "branch-1")
        captured.extend(values)

    monkeypatch.setattr(AsyncPostgresSaver, "aput_writes", store)
    saver = object.__new__(CompactAsyncPostgresSaver)
    asyncio.run(saver.aput_writes(_CONFIG, writes, "task-1", "branch-1"))
    _assert_storage_safe(captured, writes, before)
