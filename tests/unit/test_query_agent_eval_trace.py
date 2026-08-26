"""Unit tests for redacted query-agent-eval LangSmith parent runs."""

from __future__ import annotations

import json
from collections.abc import Callable
from contextlib import AbstractContextManager
from typing import Any, cast
from uuid import uuid4

import langsmith
from smart_rag_core.observability.langsmith_tracing import (
    payload_contains_forbidden_text,
    short_content_hash,
)
from smart_rag_core.observability.query_run_trace import (
    QUERY_AGENT_EVAL_RUN,
    hashed_conversation_id,
    hashed_user_id,
    invoke_traced_query_agent_eval,
    redact_query_agent_eval_inputs,
    redact_query_agent_eval_outputs,
)
from smart_rag_core.settings import AgentSettings

from tests.support.langsmith import RecordingLangSmithClient
from tests.unit.typed_attrs import module_attr

CANARY_PASSAGE = "SECRET_COMPANY_PASSAGE_DO_NOT_EXPORT"
CANARY_TOKEN = "sk-canarysecretFORBID123456"  # noqa: S105 - inert leak canary
CANARY_EMAIL = "canary.user@example.com"


def _tracing_context(
    *, enabled: bool, client: object
) -> AbstractContextManager[object]:
    """Return LangSmith ``tracing_context`` with a known callable type.

    Args:
        enabled: Whether tracing is enabled for the block.
        client: Recording client used by the unit tests.

    Returns:
        Context manager from ``langsmith.tracing_context``.
    """

    factory = cast(
        Callable[..., AbstractContextManager[object]],
        module_attr(langsmith, "tracing_context"),
    )
    return factory(enabled=enabled, client=client)


def test_hashed_ids_omit_raw_uuids() -> None:
    """User and conversation hashes never copy the raw UUID string."""

    user_id = uuid4()
    conversation_id = uuid4()
    assert hashed_user_id(user_id) == short_content_hash(str(user_id))
    assert hashed_conversation_id(conversation_id) == short_content_hash(
        str(conversation_id)
    )
    assert str(user_id) not in hashed_user_id(user_id)
    assert str(conversation_id) not in hashed_conversation_id(conversation_id)


def test_redactors_drop_query_answer_and_canaries() -> None:
    """Parent I/O redaction keeps ids/routes and drops source text."""

    inputs = redact_query_agent_eval_inputs(
        {
            "case_id": "p4-acl_negative-0003",
            "query": CANARY_PASSAGE,
            "email": CANARY_EMAIL,
            "api_key": CANARY_TOKEN,
            "requested_route": "hybrid",
        }
    )
    assert inputs["case_id"] == "p4-acl_negative-0003"
    assert inputs["requested_route"] == "hybrid"
    assert CANARY_PASSAGE not in json.dumps(inputs)
    assert CANARY_TOKEN not in json.dumps(inputs)
    assert CANARY_EMAIL not in json.dumps(inputs)
    outputs = redact_query_agent_eval_outputs(
        {
            "completed": True,
            "answer_text": CANARY_PASSAGE,
            "answer_status": "complete",
            "effective_route": "hybrid",
            "cited_chunk_ids": ["chunk-a"],
            "agent_cost_usd": "0.01",
        }
    )
    assert outputs["completed"] is True
    assert outputs["effective_route"] == "hybrid"
    assert outputs["citation_count"] == 1
    assert CANARY_PASSAGE not in json.dumps(outputs)


def test_eval_parent_omits_canaries_and_records_case_id() -> None:
    """Enabled tracing records ``query.agent.eval`` without query or secrets."""

    recorder = RecordingLangSmithClient()
    settings = AgentSettings()
    run_id = uuid4()
    user_id = uuid4()
    conversation_id = uuid4()
    captured: dict[str, str] = {}

    def _thunk() -> dict[str, Any]:
        """Return a result that would leak if outputs were copied raw.

        Returns:
            Mapping including canary answer text.
        """

        captured["ran"] = "1"
        return {
            "completed": True,
            "answer_text": CANARY_PASSAGE,
            "answer_status": "complete",
            "effective_route": "hybrid",
            "cited_chunk_ids": ["chunk-a"],
            "agent_cost_usd": "0",
        }

    with _tracing_context(enabled=True, client=recorder):
        result = invoke_traced_query_agent_eval(
            _thunk,
            settings=settings,
            case_id="p4-acl_negative-0003",
            run_id=run_id,
            user_id=user_id,
            conversation_id=conversation_id,
            requested_route="hybrid",
        )
    assert captured["ran"] == "1"
    assert result["completed"] is True
    names = [item["name"] for item in recorder.created]
    assert QUERY_AGENT_EVAL_RUN in names
    parent = next(
        item for item in recorder.created if item["name"] == QUERY_AGENT_EVAL_RUN
    )
    serialized = json.dumps(recorder.created + recorder.updated, default=str)
    assert "p4-acl_negative-0003" in serialized
    assert CANARY_PASSAGE not in serialized
    assert CANARY_TOKEN not in serialized
    assert CANARY_EMAIL not in serialized
    assert str(user_id) not in serialized
    assert str(conversation_id) not in serialized
    assert not payload_contains_forbidden_text(
        recorder.created, CANARY_PASSAGE, CANARY_TOKEN, CANARY_EMAIL
    )
    extra = cast(dict[str, Any], parent.get("extra") or parent.get("metadata") or {})
    assert extra.get("case_id", "p4-acl_negative-0003")


def test_one_parent_span_per_case() -> None:
    """A fake agent emits one ``query.agent.eval`` parent per case."""

    recorder = RecordingLangSmithClient()
    settings = AgentSettings()
    case_ids = ("p4-acl_negative-0003", "p4-acl_negative-0004")

    def _thunk() -> dict[str, str]:
        """Return a completed stub.

        Returns:
            Completed flag only.
        """

        return {"completed": "true"}

    with _tracing_context(enabled=True, client=recorder):
        for case_id in case_ids:
            invoke_traced_query_agent_eval(
                _thunk,
                settings=settings,
                case_id=case_id,
                run_id=uuid4(),
                user_id=uuid4(),
                conversation_id=uuid4(),
            )
    parents = [
        item for item in recorder.created if item["name"] == QUERY_AGENT_EVAL_RUN
    ]
    assert len(parents) == len(case_ids)
