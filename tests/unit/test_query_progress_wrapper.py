"""Truthful node-start wrappers emit only invoked production stages."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from smart_rag_agents.query.deps import QueryGraphDeps
from smart_rag_agents.query.graph import build_query_graph, production_stage_names
from smart_rag_agents.query.state import pending_query_state
from smart_rag_agents.query.streaming.progress import (
    PRODUCTION_PROGRESS_STAGES,
    wrap_progress_node,
)
from smart_rag_api.services.sse.stream_parts import (
    custom_mapping_from_part,
    parse_stream_part,
    updates_mapping_from_part,
)
from smart_rag_core.query_admission.context import AuthorizedRuntimeContext
from smart_rag_core.query_profile.phase6_map import Phase6RouteFamily
from smart_rag_core.security.identity import UserRole


def _runtime() -> AuthorizedRuntimeContext:
    """Return a Composite admission envelope for wrapper tests.

    Returns:
        Frozen authorized runtime context.
    """

    now = datetime.now(UTC)
    return AuthorizedRuntimeContext(
        user_id=uuid4(),
        role=UserRole.MEMBER,
        authorization_version=1,
        conversation_id=uuid4(),
        run_id=uuid4(),
        reservation_id=uuid4(),
        reconnect=False,
        route_family=Phase6RouteFamily.COMPOSITE,
        deadline_at=now + timedelta(seconds=50),
        recursion_limit=24,
        correction_ceiling=1,
        subquestion_ceiling=3,
        model_call_ceiling=9,
        tool_ceiling=5,
        discovery_ceiling=1,
        manifest_ceiling=3,
        side_effect_ceiling=1,
        reserved_amount_usd=Decimal("3.60"),
        remaining_usd=Decimal("3.60"),
        remaining_prompt_tokens=72000,
        remaining_completion_tokens=18000,
        optimistic_version=1,
        heartbeat_at=now,
        payload_hash="b" * 64,
        status="pending",
    )


def _stream_progress(query: str) -> tuple[list[str], list[str]]:
    """Stream one admitted run and collect start stages plus update nodes.

    Args:
        query: Original user text.

    Returns:
        ``(start_stages, update_nodes)`` in stream order.
    """

    compiled = build_query_graph(QueryGraphDeps()).compile()
    state = pending_query_state(_runtime().model_dump(mode="json"), user_query=query)
    starts: list[str] = []
    updates: list[str] = []
    for raw in compiled.stream(
        state,
        stream_mode=["updates", "custom"],
        version="v2",
    ):
        part = parse_stream_part(raw)
        if part is None:
            continue
        custom = custom_mapping_from_part(part)
        if custom is not None:
            assert set(custom) == {"kind", "stage"}
            assert custom["kind"] == "node_start"
            starts.append(str(custom["stage"]))
            continue
        mapping = updates_mapping_from_part(part)
        if mapping is not None:
            updates.extend(mapping)
    return starts, updates


def test_production_progress_stages_match_graph_keys() -> None:
    """Wrapper allow-list is the exact production stage set."""

    assert PRODUCTION_PROGRESS_STAGES == production_stage_names()


def test_start_precedes_the_same_node_update() -> None:
    """Each emitted start appears before that node's updates part."""

    starts, updates = _stream_progress("Hello")
    assert starts
    assert "general_scope" in starts
    assert "general_scope" in updates
    for stage in starts:
        if stage in updates:
            assert starts.index(stage) <= updates.index(stage)


def test_skipped_route_nodes_emit_zero_starts() -> None:
    """Company-only stages stay silent on a general greeting."""

    starts, updates = _stream_progress("Hello")
    forbidden = {
        "company_scope",
        "apply_correction",
        "fuse_evidence",
        "compose_tables",
        "disclose_optional_tools",
        "generate_answer",
    }
    assert forbidden.isdisjoint(starts)
    assert forbidden.isdisjoint(updates)
    assert "general_scope" in starts


def test_closed_state_noop_emits_zero_starts(monkeypatch: pytest.MonkeyPatch) -> None:
    """Closed-state pass-through must not write a start event."""

    written: list[object] = []
    monkeypatch.setattr(
        "smart_rag_agents.query.streaming.progress.get_stream_writer",
        lambda: written.append,
    )

    def passthrough(state: dict[str, object]) -> dict[str, object]:
        """Return state unchanged.

        Args:
            state: Closed graph state.

        Returns:
            The same mapping.
        """

        return state

    wrapped = wrap_progress_node("fuse_evidence", passthrough)
    closed = pending_query_state(user_query="Hello")
    closed["status"] = "admission_rejected"
    assert wrapped(closed)["status"] == "admission_rejected"
    assert written == []


def test_wrapper_rejects_unknown_stage_and_preserves_exceptions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unknown stages fail closed; node exceptions are not swallowed."""

    monkeypatch.setattr(
        "smart_rag_agents.query.streaming.progress.get_stream_writer",
        lambda: (lambda _payload: None),
    )
    with pytest.raises(ValueError, match="progress_stage_unknown"):
        wrap_progress_node("admission", lambda state: state)

    def boom(state: dict[str, object]) -> dict[str, object]:
        """Raise to prove the wrapper does not catch.

        Args:
            state: Unused.

        Returns:
            Never returns.

        Raises:
            RuntimeError: Always.
        """

        del state
        raise RuntimeError("node_failed")

    wrapped = wrap_progress_node("verify_answer", boom)
    with pytest.raises(RuntimeError, match="node_failed"):
        wrapped(pending_query_state(user_query="Hello"))
