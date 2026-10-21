"""Verified-final SSE mapping: hold draft text until verify_answer."""

from __future__ import annotations

import asyncio
from typing import Literal, TypedDict, cast

import pytest
from langgraph.graph import END, START, StateGraph
from smart_rag_agents.query.graph import compile_query_graph
from smart_rag_agents.query.state import pending_query_state
from smart_rag_api.services.query_sse_mapping import (
    ALLOWED_SSE_FIELDS,
    GENERAL_SCOPE_NODE,
    GENERATE_ANSWER_NODE,
    MIXED_SCOPE_NODE,
    TOKEN_DELTA_LIMIT,
    VERIFY_ANSWER_NODE,
    WEB_SCOPE_NODE,
    QuerySseMapper,
    assert_catalog_event,
    chunk_answer_text,
)
from smart_rag_api.services.sse.mapping.contracts import (
    CANONICAL_REFUSAL_TEXT,
    ORGANIZE_ANSWER_NODE,
)
from smart_rag_core.query_answer.models import AnswerPayload
from smart_rag_core.security.untrusted import isolate_untrusted_text
from smart_rag_core.sse.catalog import PAYLOAD_MODELS
from smart_rag_core.sse.sanitize import validate_sse_payload

from tests.support.typed_graph import untyped


def _release(
    mapper: QuerySseMapper, update: dict[str, object]
) -> list[tuple[str, dict[str, object]]]:
    """Hold the verified payload, then release it from the rewrite node.

    Args:
        mapper: Stream mapper under test.
        update: Verify-node update that the rewrite node echoes.

    Returns:
        Events emitted when the rewrite node completes.
    """

    held = mapper.consume_chunk({VERIFY_ANSWER_NODE: update})
    assert "token_delta" not in [item[0] for item in held]
    return mapper.consume_chunk({ORGANIZE_ANSWER_NODE: update})


def _payload(
    text: str, *, status: Literal["complete", "partial", "refused"] = "complete"
) -> dict[str, object]:
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
    assert chunk_answer_text("hello") == ("hello",)


def test_chunk_answer_text_fits_after_html_escape() -> None:
    """Quotes under the raw cap still split so each escaped delta validates."""

    quoted = '"' * 4000
    assert len(quoted) < TOKEN_DELTA_LIMIT
    assert len(isolate_untrusted_text(quoted)) > TOKEN_DELTA_LIMIT
    chunks = chunk_answer_text(quoted)
    assert len(chunks) > 1
    assert "".join(chunks) == quoted
    for piece in chunks:
        validate_sse_payload("token_delta", {"delta": piece})


def test_mapper_holds_draft_until_verify_then_emits_token_delta() -> None:
    """generate_answer text is withheld; the rewrite node emits token_delta."""

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

    final_events = _release(
        mapper,
        {
            "status": "verified",
            "answer": _payload("PUBLIC_FINAL_ANSWER"),
        },
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


def test_mapper_emits_one_answer_origin_before_token_delta() -> None:
    """Origin is emitted once before tokens when the payload has an origin."""

    from smart_rag_core.query_routing.knowledge_scope import KnowledgeScope

    mapper = QuerySseMapper()
    payload = AnswerPayload(
        answer_text="Paris is the capital of France.",
        status="complete",
        answer_origin=KnowledgeScope.GENERAL_KNOWLEDGE,
    ).model_dump(mode="json")
    events = _release(mapper, {"status": "verified", "answer": payload})
    types = [item[0] for item in events]
    assert types.count("answer_origin") == 1
    assert types.index("answer_origin") < types.index("token_delta")
    assert events[types.index("answer_origin")][1] == {"origin": "general_knowledge"}
    web_events = _release(
        QuerySseMapper(),
        {
            "status": "verified",
            "answer": AnswerPayload(
                answer_text="Public web draft.",
                status="complete",
                answer_origin=KnowledgeScope.WEB,
            ).model_dump(mode="json"),
        },
    )
    web_types = [item[0] for item in web_events]
    assert web_events[web_types.index("answer_origin")][1] == {"origin": "web"}
    assert "citation_preview" not in types
    historical = _release(
        QuerySseMapper(),
        {
            "status": "verified",
            "answer": _payload("Older compatible answer"),
        },
    )
    assert "answer_origin" not in [item[0] for item in historical]


def test_mapper_emits_usage_from_verify_totals() -> None:
    """Verified answers publish accumulated provider tokens before the terminal."""

    mapper = QuerySseMapper()
    events = _release(
        mapper,
        {
            "status": "verified",
            "answer": _payload("Counted answer."),
            "prompt_tokens": 12,
            "completion_tokens": 7,
        },
    )
    for event_type, payload in events:
        assert_catalog_event(event_type, payload)
    types = [item[0] for item in events]
    assert types.count("usage") == 1
    assert types.index("usage") < types.index("completed")
    assert events[types.index("usage")][1] == {
        "prompt_tokens": 12,
        "completion_tokens": 7,
    }


def test_mapper_emits_billed_cost_with_usage() -> None:
    """Verified answers may publish billed USD alongside provider tokens."""

    mapper = QuerySseMapper()
    events = _release(
        mapper,
        {
            "status": "verified",
            "answer": _payload("Counted answer."),
            "prompt_tokens": 923,
            "completion_tokens": 167,
            "cost_usd": 0.48,
        },
    )
    usage = next(item for item in events if item[0] == "usage")
    assert usage[1] == {
        "prompt_tokens": 923,
        "completion_tokens": 167,
        "cost_usd": 0.48,
    }
    for event_type, payload in events:
        assert_catalog_event(event_type, payload)


def test_mapper_maps_deadline_exhausted_reject_to_partial() -> None:
    """Retrieve-time deadline is catalog deadline then partial, not error."""

    mapper = QuerySseMapper()
    events = mapper.consume_chunk(
        {
            "company_scope": {
                "status": "routing_rejected",
                "detail": "deadline_exhausted",
            }
        }
    )
    for event_type, payload in events:
        assert_catalog_event(event_type, payload)
    types = [item[0] for item in events]
    assert "error" not in types
    assert types.count("deadline") == 1
    assert types.count("partial") == 1
    assert events[types.index("partial")][1] == {"reason": "deadline_exhausted"}
    assert mapper.terminal_emitted is True


def test_mapper_keeps_non_deadline_routing_reject_as_error() -> None:
    """Empty-query and other routing rejects stay error with the status code."""

    mapper = QuerySseMapper()
    events = mapper.consume_chunk(
        {"prepare_query": {"status": "routing_rejected", "detail": "empty_query"}}
    )
    for event_type, payload in events:
        assert_catalog_event(event_type, payload)
    types = [item[0] for item in events]
    assert ("error", {"code": "routing_rejected"}) in events
    assert "partial" not in types
    assert mapper.terminal_emitted is True


def test_mapper_allowlist_covers_catalog_payload_fields() -> None:
    """Mapper field allowlist stays identical to extra=forbid catalog models."""

    catalog_fields = {
        name for model in PAYLOAD_MODELS.values() for name in model.model_fields
    }
    assert ALLOWED_SSE_FIELDS == catalog_fields
    assert_catalog_event(
        "usage",
        {"prompt_tokens": 1, "completion_tokens": 1, "cost_usd": 0.01},
    )
    assert_catalog_event("coverage", {"coverage_score": 0.65})
    with pytest.raises(ValueError, match="sse_payload_field_not_allowlisted"):
        assert_catalog_event("usage", {"prompt_tokens": 1, "secret_field": "nope"})


def test_mapper_empty_verified_answer_is_error_not_completed() -> None:
    """A successful graph with blank answer_text cannot emit completed."""

    mapper = QuerySseMapper()
    mapper.consume_chunk(
        {GENERATE_ANSWER_NODE: {"status": "drafted", "answer": _payload("held")}}
    )
    events = _release(mapper, {"status": "verified", "answer": _payload("   ")})
    assert events[-1] == ("error", {"code": "empty_answer"})
    assert "completed" not in {item[0] for item in events}


def test_mapper_holds_general_and_mixed_scope_drafts() -> None:
    """Direct scope nodes hold draft text until verify_answer."""

    for node_name in (GENERAL_SCOPE_NODE, MIXED_SCOPE_NODE, WEB_SCOPE_NODE):
        mapper = QuerySseMapper()
        draft_events = mapper.consume_chunk(
            {
                node_name: {
                    "status": "answered",
                    "answer": _payload("SCOPE_DRAFT_SECRET"),
                }
            }
        )
        assert "token_delta" not in [item[0] for item in draft_events]
        assert "SCOPE_DRAFT_SECRET" not in str(draft_events)
        final_events = _release(
            mapper,
            {
                "status": "verified",
                "answer": _payload("SCOPE_PUBLIC_FINAL"),
            },
        )
        deltas = [
            payload["delta"]
            for event_type, payload in final_events
            if event_type == "token_delta"
        ]
        assert deltas == ["SCOPE_PUBLIC_FINAL"]
        assert final_events[-1][0] == "completed"


def test_mapper_strips_web_excerpts_and_holds_web_draft() -> None:
    """Web node updates never leak excerpts; token_delta waits for verify."""

    mapper = QuerySseMapper()
    events = mapper.consume_chunk(
        {
            WEB_SCOPE_NODE: {
                "status": "answered",
                "answer": _payload("SECRET_WEB_DRAFT"),
                "web_sources": [
                    {
                        "excerpt": "SECRET_EXCERPT_BODY",
                        "url": "https://example.com/news",
                    }
                ],
            }
        }
    )
    dumped = str(events)
    assert "token_delta" not in [item[0] for item in events]
    assert "SECRET_WEB_DRAFT" not in dumped
    assert "SECRET_EXCERPT_BODY" not in dumped
    assert "https://example.com/news" not in dumped
    for event_type, payload in events:
        assert_catalog_event(event_type, payload)


def test_mapper_web_scope_reject_is_terminal_without_token_delta() -> None:
    """Fail-closed Web still maps to catalog error, not a draft answer."""

    mapper = QuerySseMapper()
    events = mapper.consume_chunk(
        {
            WEB_SCOPE_NODE: {
                "status": "routing_rejected",
                "detail": "web_search_disabled",
            }
        }
    )
    assert ("error", {"code": "routing_rejected"}) in events
    assert "token_delta" not in [item[0] for item in events]
    assert mapper.terminal_emitted is True


def test_custom_web_progress_keys_omit_query_and_bodies() -> None:
    """``web_search`` / ``web_read`` custom events are keys only."""

    mapper = QuerySseMapper()
    started = mapper.consume_custom({"kind": "node_start", "stage": "web_search"})
    assert started == [
        ("status", {"stage": "web_search", "status": "running", "phase": "started"})
    ]
    dropped = mapper.consume_custom(
        {
            "kind": "node_start",
            "stage": "web_read",
            "excerpt": "SECRET_BODY",
            "query": "search the web for latest news",
        }
    )
    assert dropped == []
    read = mapper.consume_custom({"kind": "node_start", "stage": "web_read"})
    assert read == [
        ("status", {"stage": "web_read", "status": "running", "phase": "started"})
    ]


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
        async for chunk in untyped(compiled).astream(
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
        typed_chunk = cast(dict[str, object], chunk)
        assert typed_chunk
        assert all(isinstance(key, str) for key in typed_chunk)
        dumped = str(typed_chunk)
        assert (
            "answer_text" not in dumped
            or "generate_answer" in typed_chunk
            or "verify_answer" in typed_chunk
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

    builder = untyped(StateGraph(_State))
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


_TERMINALS = frozenset({"completed", "cancelled", "error", "partial"})


def _terminal_events(
    events: list[tuple[str, dict[str, object]]],
) -> list[tuple[str, dict[str, object]]]:
    """Return catalog terminal drafts only.

    Args:
        events: Mapper drafts.

    Returns:
        Terminal (type, payload) pairs in arrival order.
    """

    return [item for item in events if item[0] in _TERMINALS]


def test_mapper_maps_generate_insufficient_evidence_to_partial() -> None:
    """Generate-time refusal is tokens, limitation, and one partial."""

    mapper = QuerySseMapper()
    events = mapper.consume_chunk(
        {GENERATE_ANSWER_NODE: {"status": "insufficient_evidence"}}
    )
    for event_type, payload in events:
        assert_catalog_event(event_type, payload)
    types = [item[0] for item in events]
    assert "error" not in types
    assert types.count("partial") == 1
    assert types.count("limitation") == 1
    verify_events = [
        item[1]
        for item in events
        if item[0] == "status" and item[1].get("stage") == VERIFY_ANSWER_NODE
    ]
    assert verify_events == [
        {"stage": VERIFY_ANSWER_NODE, "status": "running", "phase": "started"},
        {
            "stage": VERIFY_ANSWER_NODE,
            "status": "insufficient_evidence",
            "phase": "completed",
        },
    ]
    assert types.index("token_delta") < types.index("limitation")
    assert types.index("limitation") < types.index("partial")
    assert events[types.index("limitation")][1] == {
        "code": "insufficient_evidence",
    }
    assert events[types.index("partial")][1] == {
        "reason": "insufficient_evidence",
    }
    deltas = [
        payload["delta"]
        for event_type, payload in events
        if event_type == "token_delta"
    ]
    assert "".join(str(item) for item in deltas) == CANONICAL_REFUSAL_TEXT
    assert mapper.terminal_emitted is True
    assert mapper.finish() == []
    assert _terminal_events(events) == [
        ("partial", {"reason": "insufficient_evidence"}),
    ]


def test_mapper_maps_fusion_insufficient_evidence_without_empty_answer() -> None:
    """Pre-answer insufficient_evidence is a graceful partial, not empty_answer."""

    mapper = QuerySseMapper()
    events = mapper.consume_chunk(
        {"fuse_evidence": {"status": "insufficient_evidence"}}
    )
    types = [item[0] for item in events]
    assert "error" not in types
    assert ("partial", {"reason": "insufficient_evidence"}) in events
    assert any(item[0] == "token_delta" for item in events)
    assert mapper.finish() == []


def test_mapper_maps_refused_verify_to_partial_not_error() -> None:
    """Verified refusal stays partial with a non-empty token."""

    mapper = QuerySseMapper()
    events = _release(
        mapper,
        {
            "status": "refused",
            "answer": _payload("  ", status="refused"),
        },
    )
    types = [item[0] for item in events]
    assert "error" not in types
    assert "empty_answer" not in str(events)
    assert types[-1] == "partial"
    assert events[-1][1] == {"reason": "refused"}
    assert ("limitation", {"code": "insufficient_evidence"}) in events
    assert _terminal_events(events) == [("partial", {"reason": "refused"})]


def test_mapper_verified_partial_is_not_a_deadline() -> None:
    """Ordinary verified_partial does not emit a deadline diagnostic."""

    mapper = QuerySseMapper()
    events = _release(
        mapper,
        {
            "status": "verified_partial",
            "answer": _payload("Kept partial.", status="partial"),
        },
    )
    types = [item[0] for item in events]
    assert "deadline" not in types
    assert types[-1] == "partial"
    assert events[-1][1] == {"reason": "verified_partial"}
    assert "error" not in types


def test_mapper_answer_deadline_reserve_emits_deadline_then_partial() -> None:
    """Answer-stage reserve exhaustion is deadline plus one partial."""

    mapper = QuerySseMapper()
    events = mapper.consume_chunk(
        {
            GENERATE_ANSWER_NODE: {
                "status": "verified_partial",
                "detail": "answer_deadline_reserve_exhausted",
                "answer": _payload("Time ran out.", status="partial"),
            }
        }
    )
    types = [item[0] for item in events]
    assert types.count("deadline") == 1
    assert types.count("partial") == 1
    assert types.index("token_delta") < types.index("deadline")
    assert types.index("deadline") < types.index("partial")
    assert events[types.index("partial")][1] == {"reason": "deadline_exhausted"}
    assert "error" not in types


def test_mapper_verify_update_is_idempotent() -> None:
    """A second verify chunk after a terminal is a no-op."""

    mapper = QuerySseMapper()
    first = _release(
        mapper,
        {
            "status": "verified",
            "answer": _payload("PUBLIC_FINAL_ANSWER"),
        },
    )
    second = mapper.consume_chunk(
        {
            VERIFY_ANSWER_NODE: {
                "status": "verified",
                "answer": _payload("SECOND_VERIFY_MUST_NOT_EMIT"),
            }
        }
    )
    assert first[-1][0] == "completed"
    assert second == []
    assert "SECOND_VERIFY_MUST_NOT_EMIT" not in str(second)
    assert mapper.finish() == []
    assert _terminal_events(first) == [("completed", {})]


def test_mapper_verifier_skipped_is_partial_not_deadline() -> None:
    """A skipped verifier releases the answer as partial with a limitation."""

    mapper = QuerySseMapper()
    events = _release(
        mapper,
        {
            "status": "verified_partial",
            "detail": "verifier_skipped:deadline_exhausted",
            "answer": _payload("Refund period is 30 days.", status="complete"),
            "verification": {
                "omitted_link_ids": [],
                "verifier_skipped_reason": "deadline_exhausted",
            },
        },
    )
    types = [item[0] for item in events]
    assert "deadline" not in types
    assert ("limitation", {"code": "verifier_skipped"}) in events
    assert types[-1] == "partial"
    assert events[-1][1] == {"reason": "verified_partial"}


def test_mapper_citation_leaf_unresolved_is_partial() -> None:
    """A skipped leaf emits a limitation and keeps the partial terminal."""

    mapper = QuerySseMapper()
    events = _release(
        mapper,
        {
            "status": "verified_partial",
            "detail": "citation_leaf_unresolved",
            "answer": _payload("Refund period is 30 days.", status="complete"),
            "verification": {
                "omitted_link_ids": [],
                "skipped_citation_count": 1,
            },
        },
    )
    assert ("limitation", {"code": "citation_leaf_unresolved"}) in events
    assert events[-1] == ("partial", {"reason": "verified_partial"})
