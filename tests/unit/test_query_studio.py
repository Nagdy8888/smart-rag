"""Unit tests for the local LangGraph Studio query adapter."""

from __future__ import annotations

from uuid import uuid4

from smart_rag_agents.query.state import pending_query_state
from smart_rag_agents.query.studio import (
    query_text_from_studio_input,
    seed_studio_runtime,
    studio_authorized_runtime,
)
from smart_rag_core.query_profile.phase6_map import Phase6RouteFamily


def test_query_text_prefers_user_query_over_messages() -> None:
    """Explicit ``user_query`` wins over Studio chat messages."""

    assert (
        query_text_from_studio_input(
            {
                "user_query": " invoice status ",
                "messages": [{"role": "human", "content": "ignored"}],
            }
        )
        == "invoice status"
    )


def test_query_text_reads_last_human_message() -> None:
    """Studio chat input can populate the query when ``user_query`` is absent."""

    assert (
        query_text_from_studio_input(
            {
                "messages": [
                    {"role": "human", "content": "first"},
                    {"role": "ai", "content": "ack"},
                    {"type": "human", "content": [{"text": "second"}]},
                ]
            }
        )
        == "second"
    )


def test_studio_runtime_uses_envelope_ceilings_and_local_status() -> None:
    """Synthetic context copies Hybrid ceilings and is labeled studio_local."""

    context = studio_authorized_runtime(
        query="status?",
        family=Phase6RouteFamily.HYBRID,
        thread_id="thread-a",
    )
    assert context.status == "studio_local"
    assert context.route_family is Phase6RouteFamily.HYBRID
    assert context.model_call_ceiling == 7
    assert context.recursion_limit == 24
    assert len(context.payload_hash) == 64
    again = studio_authorized_runtime(
        query="status?",
        family=Phase6RouteFamily.HYBRID,
        thread_id="thread-a",
    )
    assert again.conversation_id == context.conversation_id
    assert again.user_id == context.user_id
    assert again.run_id != context.run_id


def test_seed_studio_runtime_rejects_unknown_family_without_context() -> None:
    """Unknown Studio families fail closed and do not mint authorized_runtime."""

    seeded = seed_studio_runtime(
        {**pending_query_state(user_query="hello"), "route_family": "not-a-family"},
        {"configurable": {"thread_id": str(uuid4())}},
    )
    assert seeded["status"] == "admission_rejected"
    assert seeded["authorized_runtime"] is None
    assert "allow-listed" in seeded["detail"]
