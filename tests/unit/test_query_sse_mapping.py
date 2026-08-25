"""Verified-final SSE mapping: hold draft text until verify_answer."""

from __future__ import annotations

import asyncio
from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from smart_rag_agents.query.graph import compile_query_graph
from smart_rag_agents.query.state import pending_query_state
from smart_rag_api.services.query_sse_mapping import (
    GENERATE_ANSWER_NODE,
    TOKEN_DELTA_LIMIT,
    VERIFY_ANSWER_NODE,
    QuerySseMapper,
    assert_catalog_event,
    chunk_answer_text,
)
from smart_rag_core.query_answer.models import AnswerPayload


def _payload(text: str, *, status: str = "complete") -> dict[str, object]:
    """Build a dumpable answer mapping.

    Args:
        text: Answer prose.
        status: Payload status.

    Returns:
        JSON-ready mapping.
    """

    return AnswerPayload(answer_text=text, status=status).model_dump(mode="json")


def test_chunk_answer_text_respects_catalog_bound() -> None:
    """Chunks stay within the 4096-character catalog limit."""

    long_text = "a" * (TOKEN_DELTA_LIMIT + 10)
    chunks = chunk_answer_text(long_text)
    assert chunks
    assert all(len(item) <= TOKEN_DELTA_LIMIT for item in chunks)
    assert "".join(chunks) == long_text
    assert chunk_answer_text("   ") == ()


def test_mapper_holds_draft_until_verify_then_emits_token_delta() -> None:
    """generate_answer text is withheld; verify_answer emits token_delta."""

    mapper = QuerySseMapper()
    draft_events = mapper.consume_chunk(
        {
            GENERATE_ANSWER_NODE: {
                "status": "drafted",
                "answer": _payload("SECRET_DRAFT_TEXT"),
            }
        }
    )
    types = [item[0] for item in draft_events]
    assert "token_delta" not in types
    assert "completed" not in types
    bodies = str(draft_events)
    assert "SECRET_DRAFT_TEXT" not in bodies
    for event_type, payload in draft_events:
        assert_catalog_event(event_type, payload)

    final_events = mapper.consume_chunk(
        {
            VERIFY_ANSWER_NODE: {
                "status": "verified",
                "answer": _payload("PUBLIC_FINAL_ANSWER"),
            }
        }
    )
    for event_type, payload in final_events:
        assert_catalog_event(event_type, payload)
    deltas = [
        payload["delta"]
        for event_type, payload in final_events
        if event_type == "token_delta"
    ]
    assert deltas == ["PUBLIC_FINAL_ANSWER"]
    assert final_events[-1][0] == "completed"
    assert mapper.verified_text == "PUBLIC_FINAL_ANSWER"


def test_mapper_empty_verified_answer_is_error_not_completed() -> None:
    """A successful graph with blank answer_text cannot emit completed."""

    mapper = QuerySseMapper()
    mapper.consume_chunk(
        {GENERATE_ANSWER_NODE: {"status": "drafted", "answer": _payload("held")}}
    )
    events = mapper.consume_chunk(
        {VERIFY_ANSWER_NODE: {"status": "verified", "answer": _payload("   ")}}
    )
    assert events[-1] == ("error", {"code": "empty_answer"})
    assert "completed" not in {item[0] for item in events}


def test_mapper_unverified_draft_at_finish_is_error() -> None:
    """Stream end without verify_answer is an error, not completed."""

    mapper = QuerySseMapper()
    mapper.consume_chunk(
        {GENERATE_ANSWER_NODE: {"status": "drafted", "answer": _payload("held")}}
    )
    events = mapper.finish()
    assert events == [("error", {"code": "unverified_answer"})]


def test_compiled_graph_updates_are_node_keyed() -> None:
    """Real compile_query_graph astream updates are keyed by node name."""

    compiled = compile_query_graph()

    async def _drain() -> list[object]:
        """Collect the first graph update chunks.

        Returns:
            Node-keyed update mappings.
        """

        chunks: list[object] = []
        async for chunk in compiled.astream(
            pending_query_state(),
            stream_mode="updates",
        ):
            chunks.append(chunk)
            if len(chunks) >= 4:
                break
        return chunks

    chunks = asyncio.run(_drain())
    assert chunks
    for chunk in chunks:
        assert isinstance(chunk, dict)
        assert chunk
        assert all(isinstance(key, str) for key in chunk)
        dumped = str(chunk)
        assert (
            "answer_text" not in dumped
            or "generate_answer" in chunk
            or "verify_answer" in chunk
        )


def test_mini_compiled_graph_does_not_emit_draft_before_verify() -> None:
    """A compiled generate_answer/verify_answer graph holds draft prose."""

    class _State(TypedDict):
        """Minimal compiled-graph state for draft-hold proof."""

        answer: dict[str, object]
        status: str

    def generate_answer(state: _State) -> _State:
        """Return an unverified draft.

        Args:
            state: Graph state.

        Returns:
            Draft node update.
        """

        del state
        return {
            "status": "drafted",
            "answer": _payload("MINI_DRAFT_SECRET"),
        }

    def verify_answer(state: _State) -> _State:
        """Return verified prose.

        Args:
            state: Graph state.

        Returns:
            Verified node update.
        """

        del state
        return {
            "status": "verified",
            "answer": _payload("MINI_PUBLIC_FINAL"),
        }

    builder = StateGraph(_State)
    builder.add_node("generate_answer", generate_answer)
    builder.add_node("verify_answer", verify_answer)
    builder.add_edge(START, "generate_answer")
    builder.add_edge("generate_answer", "verify_answer")
    builder.add_edge("verify_answer", END)
    compiled = builder.compile()
    mapper = QuerySseMapper()
    seen_types: list[str] = []

    async def _run() -> None:
        """Stream mini-graph updates into the SSE mapper."""

        async for chunk in compiled.astream(
            {"status": "pending", "answer": {}},
            stream_mode="updates",
        ):
            events = mapper.consume_chunk(chunk)
            seen_types.extend(event_type for event_type, _payload in events)
            joined = str(events)
            if "verify_answer" not in chunk:
                assert "MINI_DRAFT_SECRET" not in joined
                assert "MINI_PUBLIC_FINAL" not in joined
                assert "token_delta" not in {event_type for event_type, _ in events}

    asyncio.run(_run())
    events = mapper.finish() if not mapper.terminal_emitted else []
    seen_types.extend(event_type for event_type, _payload in events)
    assert "token_delta" in seen_types
    assert seen_types.count("completed") == 1
    assert mapper.verified_text == "MINI_PUBLIC_FINAL"
