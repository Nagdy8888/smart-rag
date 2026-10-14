"""Focused physical-line budgets for the query stream path."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
STREAM_FACADE_LIMIT = 100
STREAM_OWNER_LIMIT = 300
MAPPING_OWNER_LIMIT = 250

STREAM_FACADES: tuple[str, ...] = (
    "apps/backend/src/smart_rag_api/services/sse/executors.py",
    "apps/backend/src/smart_rag_api/services/query_sse_mapping.py",
    "apps/backend/src/smart_rag_api/services/sse/service_persist.py",
)

STREAM_OWNERS: tuple[str, ...] = (
    "apps/agents/src/smart_rag_agents/query/graph.py",
    "apps/agents/src/smart_rag_agents/query/runtime/bound_nodes.py",
    "apps/backend/src/smart_rag_api/services/sse/executor_protocol.py",
    "apps/backend/src/smart_rag_api/services/sse/fixture_executor.py",
    "apps/backend/src/smart_rag_api/services/sse/langgraph_runtime.py",
    "apps/backend/src/smart_rag_api/services/sse/stream_lifecycle.py",
    "apps/backend/src/smart_rag_api/services/sse/answer_persistence.py",
    "apps/backend/src/smart_rag_api/services/sse/langgraph_executor.py",
    "apps/backend/src/smart_rag_api/services/sse/langgraph_execute.py",
    "apps/backend/src/smart_rag_api/services/sse/langgraph_bindings.py",
    "apps/backend/src/smart_rag_api/services/sse/langgraph_stream_consume.py",
    "apps/backend/src/smart_rag_api/services/sse/stream_dispatch.py",
    "apps/backend/src/smart_rag_api/services/sse/stream_parts.py",
    "apps/backend/src/smart_rag_api/services/sse/service.py",
    "apps/backend/src/smart_rag_api/services/sse/run_access.py",
    "apps/backend/src/smart_rag_api/services/sse/run_executor.py",
    "apps/backend/src/smart_rag_api/services/sse/run_orchestration.py",
    "apps/backend/src/smart_rag_api/services/sse/run_heartbeat.py",
    "apps/backend/src/smart_rag_api/services/sse/event_append.py",
    "apps/backend/src/smart_rag_api/services/sse/run_settlement.py",
    "apps/backend/src/smart_rag_api/services/sse/replay_cancel.py",
    "apps/backend/src/smart_rag_api/services/sse/run_summary.py",
    "apps/backend/src/smart_rag_api/services/sse/event_writer.py",
)

MAPPING_OWNERS: tuple[str, ...] = (
    "apps/backend/src/smart_rag_api/services/sse/mapping/__init__.py",
    "apps/backend/src/smart_rag_api/services/sse/mapping/contracts.py",
    "apps/backend/src/smart_rag_api/services/sse/mapping/status.py",
    "apps/backend/src/smart_rag_api/services/sse/mapping/citations.py",
    "apps/backend/src/smart_rag_api/services/sse/mapping/usage.py",
    "apps/backend/src/smart_rag_api/services/sse/mapping/limitations.py",
    "apps/backend/src/smart_rag_api/services/sse/mapping/verified.py",
    "apps/backend/src/smart_rag_api/services/sse/mapping/mapper.py",
    "apps/backend/src/smart_rag_api/services/sse/mapping/progress.py",
    "apps/backend/src/smart_rag_api/services/sse/mapping/diagnostics.py",
)


def _physical_lines(relative: str) -> int:
    """Return the physical line count for one repository path.

    Args:
        relative: Repository-relative POSIX path.

    Returns:
        ``splitlines()`` count of the UTF-8 file.
    """

    return len((REPO_ROOT / relative).read_text(encoding="utf-8").splitlines())


def test_stream_facades_stay_at_or_under_one_hundred_lines() -> None:
    """Compatibility barrels stay at the facade budget."""

    over = {
        path: _physical_lines(path)
        for path in STREAM_FACADES
        if _physical_lines(path) > STREAM_FACADE_LIMIT
    }
    assert over == {}, over


def test_stream_owners_stay_at_or_under_three_hundred_lines() -> None:
    """Runtime stream-path owners stay at the owner budget."""

    over = {
        path: _physical_lines(path)
        for path in STREAM_OWNERS
        if _physical_lines(path) > STREAM_OWNER_LIMIT
    }
    assert over == {}, over


def test_mapping_owners_stay_at_or_under_two_hundred_fifty_lines() -> None:
    """Decomposed mapper modules stay at the mapping budget."""

    over = {
        path: _physical_lines(path)
        for path in MAPPING_OWNERS
        if _physical_lines(path) > MAPPING_OWNER_LIMIT
    }
    assert over == {}, over
