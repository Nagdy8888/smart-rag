"""Unit tests for redacted query-run SSE LangSmith parent spans."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable, Mapping
from contextlib import AbstractContextManager
from typing import cast
from uuid import uuid4

import langsmith
import pytest
from smart_rag_core.observability.langsmith_tracing import (
    payload_contains_forbidden_text,
)
from smart_rag_core.observability.query_run_trace import (
    QUERY_RUN_SSE_SPAN,
    hashed_user_id,
    invoke_traced_query_run_sse,
    redact_query_run_sse_inputs,
    redact_query_run_sse_outputs,
)
from smart_rag_core.settings import AgentSettings

from tests.unit.test_langsmith_tracing import RecordingLangSmithClient
from tests.unit.typed_attrs import module_attr

CANARY_PASSAGE = "SECRET_COMPANY_PASSAGE_DO_NOT_EXPORT"
CANARY_TOKEN = "sk-canarysecretFORBID123456"  # noqa: S105 - inert leak canary
CANARY_EMAIL = "canary.user@example.com"
CANARY_JWT = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.canarypayload.signature"


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


def _summary(
    *,
    reason: str,
    event_type: str | None,
    exhausted: bool,
) -> dict[str, object]:
    """Build a sanitized termination mapping plus leak canaries.

    Args:
        reason: Termination reason.
        event_type: Terminal SSE type.
        exhausted: Whether ``astream`` exhausted naturally.

    Returns:
        Mapping that would leak if outputs were copied raw.
    """

    return {
        "termination_reason": reason,
        "terminal_event_type": event_type,
        "stream_exhausted": exhausted,
        "query": CANARY_PASSAGE,
        "jwt": CANARY_JWT,
        "email": CANARY_EMAIL,
        "api_key": CANARY_TOKEN,
        "sources": [CANARY_PASSAGE],
    }


def test_sse_redactors_drop_query_jwt_and_sources() -> None:
    """Parent I/O redaction keeps hashes/routes and drops secrets."""

    user_id = uuid4()
    inputs = redact_query_run_sse_inputs(
        {
            "run_id": "run-1",
            "user_id_sha256": hashed_user_id(user_id),
            "requested_route": "hybrid",
            "query": CANARY_PASSAGE,
            "jwt": CANARY_JWT,
            "email": CANARY_EMAIL,
            "api_key": CANARY_TOKEN,
            "model_versions": {"answer": "gpt-test"},
        }
    )
    assert inputs["run_id"] == "run-1"
    assert inputs["requested_route"] == "hybrid"
    rendered_inputs = json.dumps(inputs)
    assert CANARY_PASSAGE not in rendered_inputs
    assert CANARY_JWT not in rendered_inputs
    assert CANARY_TOKEN not in rendered_inputs
    assert CANARY_EMAIL not in rendered_inputs
    outputs = redact_query_run_sse_outputs(
        _summary(reason="completed", event_type="completed", exhausted=True)
    )
    assert outputs["termination_reason"] == "completed"
    assert outputs["terminal_event_type"] == "completed"
    assert outputs["stream_exhausted"] is True
    rendered_outputs = json.dumps(outputs)
    assert CANARY_PASSAGE not in rendered_outputs
    assert CANARY_JWT not in rendered_outputs
    assert CANARY_TOKEN not in rendered_outputs


def test_completed_sse_parent_omits_canaries() -> None:
    """Enabled tracing records ``query.run.sse`` without query or secrets."""

    recorder = RecordingLangSmithClient()
    settings = AgentSettings()
    run_id = uuid4()
    user_id = uuid4()
    captured: dict[str, str] = {}

    async def _thunk() -> Mapping[str, object]:
        """Return a completed summary that would leak if copied raw.

        Returns:
            Completed termination mapping plus canaries.
        """

        captured["ran"] = "1"
        return _summary(reason="completed", event_type="completed", exhausted=True)

    async def _run() -> Mapping[str, object]:
        """Invoke the parent span inside a recording client.

        Returns:
            Thunk result.
        """

        with _tracing_context(enabled=True, client=recorder):
            return await invoke_traced_query_run_sse(
                _thunk,
                settings=settings,
                run_id=run_id,
                user_id=user_id,
                requested_route="hybrid",
                effective_route="hybrid",
                model_versions={"answer": "gpt-test"},
                prompt_versions={"answer": "v1"},
            )

    result = asyncio.run(_run())
    assert captured["ran"] == "1"
    assert result["termination_reason"] == "completed"
    names = [item["name"] for item in recorder.created]
    assert QUERY_RUN_SSE_SPAN in names
    serialized = json.dumps(recorder.created + recorder.updated, default=str)
    assert CANARY_PASSAGE not in serialized
    assert CANARY_TOKEN not in serialized
    assert CANARY_EMAIL not in serialized
    assert CANARY_JWT not in serialized
    assert str(user_id) not in serialized
    assert not payload_contains_forbidden_text(
        recorder.created, CANARY_PASSAGE, CANARY_TOKEN, CANARY_EMAIL, CANARY_JWT
    )


def test_cancelled_sse_parent_keeps_cancelled_reason() -> None:
    """Cancelled summaries stay cancelled on the parent span."""

    recorder = RecordingLangSmithClient()
    settings = AgentSettings()

    async def _thunk() -> Mapping[str, object]:
        """Return a cancelled termination summary.

        Returns:
            Cancelled mapping plus canaries.
        """

        return _summary(reason="cancelled", event_type="cancelled", exhausted=False)

    async def _run() -> Mapping[str, object]:
        """Invoke the cancelled parent span.

        Returns:
            Thunk result.
        """

        with _tracing_context(enabled=True, client=recorder):
            return await invoke_traced_query_run_sse(
                _thunk,
                settings=settings,
                run_id=uuid4(),
                user_id=uuid4(),
                requested_route="hybrid",
            )

    result = asyncio.run(_run())
    assert result["termination_reason"] == "cancelled"
    assert result["stream_exhausted"] is False
    outputs = redact_query_run_sse_outputs(result)
    assert outputs["termination_reason"] == "cancelled"
    assert outputs["stream_exhausted"] is False
    serialized = json.dumps(recorder.created + recorder.updated, default=str)
    assert CANARY_PASSAGE not in serialized


def test_real_error_is_not_converted_to_success() -> None:
    """A genuine consumer exception stays an error, not a completed span."""

    recorder = RecordingLangSmithClient()
    settings = AgentSettings()

    async def _thunk() -> Mapping[str, object]:
        """Raise a real graph failure.

        Returns:
            Never returns.

        Raises:
            RuntimeError: Simulated graph failure.
        """

        raise RuntimeError("graph_failed")

    async def _run() -> None:
        """Invoke the parent span and expect the error.

        Raises:
            RuntimeError: Propagated from the thunk.
        """

        with _tracing_context(enabled=True, client=recorder):
            await invoke_traced_query_run_sse(
                _thunk,
                settings=settings,
                run_id=uuid4(),
                user_id=uuid4(),
                requested_route="hybrid",
            )

    with pytest.raises(RuntimeError, match="graph_failed"):
        asyncio.run(_run())
    outputs = redact_query_run_sse_outputs(
        _summary(reason="error", event_type="error", exhausted=False)
    )
    assert outputs["termination_reason"] == "error"
    assert outputs.get("termination_reason") != "completed"


def test_tracing_disabled_skips_parent_span() -> None:
    """When tracing is off, the thunk still runs and no parent is opened."""

    settings = AgentSettings()
    captured: dict[str, str] = {}

    async def _thunk() -> Mapping[str, object]:
        """Return a completed summary without opening a client.

        Returns:
            Completed termination mapping.
        """

        captured["ran"] = "1"
        return {
            "termination_reason": "completed",
            "terminal_event_type": "completed",
            "stream_exhausted": True,
        }

    result = asyncio.run(
        invoke_traced_query_run_sse(
            _thunk,
            settings=settings,
            run_id=uuid4(),
            user_id=uuid4(),
            requested_route="hybrid",
        )
    )
    assert captured["ran"] == "1"
    assert result["termination_reason"] == "completed"
    assert settings.langsmith_tracing is False
