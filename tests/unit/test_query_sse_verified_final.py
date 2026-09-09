"""Verified-final SSE executor mapping and empty-answer terminals."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from smart_rag_api.services.sse_stream import LangGraphQueryRunExecutor
from smart_rag_core.observability.langsmith_tracing import estimate_traced_chat_cost_usd
from smart_rag_core.query_admission.exceptions import QueryAdmissionError
from smart_rag_core.query_answer.models import AnswerPayload

from tests.support.query_sse import (
    FakeCompiled,
    patch_recording_executor,
    runtime,
)


def test_production_executor_emits_verified_delta_then_one_terminal(
    monkeypatch: Any,
) -> None:
    """LangGraph executor maps updates into schema-safe verified SSE."""

    draft = AnswerPayload(answer_text="DRAFT_HIDDEN", status="complete")
    final = AnswerPayload(answer_text="VISIBLE_FINAL", status="complete")
    compiled = FakeCompiled(
        (
            {
                "generate_answer": {
                    "status": "drafted",
                    "answer": draft.model_dump(mode="json"),
                }
            },
            {
                "verify_answer": {
                    "status": "verified",
                    "answer": final.model_dump(mode="json"),
                    "prompt_tokens": 80,
                    "completion_tokens": 20,
                }
            },
        )
    )
    executor = LangGraphQueryRunExecutor()
    commits, _settlements = patch_recording_executor(monkeypatch, executor, compiled)

    async def _collect() -> list[tuple[str, dict[str, object]]]:
        """Drain production executor events.

        Returns:
            SSE event name and payload pairs.
        """

        events: list[tuple[str, dict[str, object]]] = []
        cancel = asyncio.Event()
        async for event in executor.execute(
            context=runtime(),
            message="hello",
            cancel_event=cancel,
        ):
            events.append(event)
        return events

    events = asyncio.run(_collect())
    types = [item[0] for item in events]
    assert "schema" not in types
    assert types.count("completed") == 1
    assert types[-1] == "completed"
    deltas = [
        payload.get("delta")
        for event_type, payload in events
        if event_type == "token_delta"
    ]
    assert deltas == ["VISIBLE_FINAL"]
    assert "DRAFT_HIDDEN" not in str(events)
    assert any(event_type == "status" for event_type in types)
    assert any(event_type == "usage" for event_type in types)
    assert commits.count("commit") == 3
    assert executor.termination_summary["input_tokens"] == 80
    assert executor.termination_summary["output_tokens"] == 20
    assert executor.termination_summary["estimated_cost_usd"] == pytest.approx(
        float(estimate_traced_chat_cost_usd(input_tokens=80, output_tokens=20))
    )


def test_production_executor_empty_answer_cannot_complete(monkeypatch: Any) -> None:
    """Verified empty prose becomes error, never completed."""

    compiled = FakeCompiled(
        (
            {
                "generate_answer": {
                    "status": "drafted",
                    "answer": AnswerPayload(
                        answer_text="x", status="complete"
                    ).model_dump(mode="json"),
                }
            },
            {
                "verify_answer": {
                    "status": "verified",
                    "answer": AnswerPayload(
                        answer_text="  ", status="complete"
                    ).model_dump(mode="json"),
                }
            },
        )
    )
    executor = LangGraphQueryRunExecutor()
    patch_recording_executor(monkeypatch, executor, compiled)

    async def _collect() -> list[tuple[str, dict[str, object]]]:
        """Drain empty-answer executor events.

        Returns:
            SSE event name and payload pairs.
        """

        events: list[tuple[str, dict[str, object]]] = []
        async for event in executor.execute(
            context=runtime(),
            message="hello",
            cancel_event=asyncio.Event(),
        ):
            events.append(event)
        return events

    events = asyncio.run(_collect())
    types = [item[0] for item in events]
    assert "completed" not in types
    assert types[-1] == "error"
    assert events[-1][1].get("code") == "empty_answer"


def test_production_executor_keeps_partial_when_summary_fails(
    monkeypatch: Any,
) -> None:
    """Post-terminal summary failure must not replace partial with error."""

    final = AnswerPayload(answer_text="Hello there.", status="partial")
    compiled = FakeCompiled(
        (
            {
                "generate_answer": {
                    "status": "answered",
                    "answer": final.model_dump(mode="json"),
                }
            },
            {
                "verify_answer": {
                    "status": "verified_partial",
                    "answer": final.model_dump(mode="json"),
                }
            },
        )
    )
    executor = LangGraphQueryRunExecutor()
    patch_recording_executor(monkeypatch, executor, compiled)

    def _boom(*args: object, **kwargs: object) -> None:
        """Raise the hosted summary failure observed on greeting runs.

        Args:
            *args: Ignored.
            **kwargs: Ignored.

        Raises:
            QueryAdmissionError: Always.
        """

        del args, kwargs
        raise QueryAdmissionError("message_persist_failed")

    monkeypatch.setattr(executor, "_maybe_summarize", _boom)

    async def _collect() -> list[tuple[str, dict[str, object]]]:
        """Drain summary-failure executor events.

        Returns:
            SSE event name and payload pairs.
        """

        events: list[tuple[str, dict[str, object]]] = []
        async for event in executor.execute(
            context=runtime(),
            message="hi",
            cancel_event=asyncio.Event(),
        ):
            events.append(event)
        return events

    events = asyncio.run(_collect())
    types = [item[0] for item in events]
    assert types.count("partial") == 1
    assert types[-1] == "partial"
    assert "error" not in types
    assert any(
        event_type == "token_delta" and payload.get("delta") == "Hello there."
        for event_type, payload in events
    )


def test_executor_persists_verified_text_when_later_sse_event_fails(
    monkeypatch: Any,
) -> None:
    """Token deltas already shown stay in the transcript if catalog assert fails."""

    final = AnswerPayload(answer_text="KEEP_LIVE_ANSWER", status="complete")
    compiled = FakeCompiled(
        (
            {
                "verify_answer": {
                    "status": "verified",
                    "answer": final.model_dump(mode="json"),
                    "prompt_tokens": 4,
                    "completion_tokens": 2,
                }
            },
        )
    )
    executor = LangGraphQueryRunExecutor()
    _commits, settlements = patch_recording_executor(monkeypatch, executor, compiled)

    def _reject_usage(event_type: str, _payload: dict[str, object]) -> None:
        """Fail closed only on the usage event after token_delta.

        Args:
            event_type: Catalog event name.
            _payload: Draft payload.

        Raises:
            ValueError: When the event is ``usage``.
        """

        if event_type == "usage":
            raise ValueError("sse_payload_field_not_allowlisted")

    monkeypatch.setattr(
        "smart_rag_api.services.query_sse_mapping.assert_catalog_event",
        _reject_usage,
    )

    async def _drain() -> None:
        """Drain until the catalog assertion aborts the stream."""

        async for _event in executor.execute(
            context=runtime(),
            message="hello",
            cancel_event=asyncio.Event(),
        ):
            pass

    with pytest.raises(ValueError, match="sse_payload_field_not_allowlisted"):
        asyncio.run(_drain())
    assert settlements == ["persist"]


def test_executor_emits_partial_when_deadline_elapses_while_opening_stream(
    monkeypatch: Any,
) -> None:
    """Opening astream after admit must not continue nodes past the envelope."""

    from datetime import timedelta
    from types import SimpleNamespace

    compiled = FakeCompiled(
        (
            {
                "company_scope": {
                    "status": "branches_executed",
                }
            },
        )
    )
    executor = LangGraphQueryRunExecutor()
    patch_recording_executor(monkeypatch, executor, compiled)
    ctx = runtime()
    ticks = {"n": 0}

    def _now(*, tz: object = None) -> object:
        """Return a pre-deadline clock once, then a post-deadline clock.

        Args:
            tz: Ignored timezone (UTC is used).

        Returns:
            Aware datetime.
        """

        del tz
        ticks["n"] += 1
        if ticks["n"] == 1:
            return ctx.deadline_at - timedelta(seconds=10)
        return ctx.deadline_at + timedelta(seconds=1)

    monkeypatch.setattr(
        "smart_rag_api.services.sse.langgraph_executor.datetime",
        SimpleNamespace(now=_now),
    )

    async def _collect() -> list[tuple[str, dict[str, object]]]:
        """Drain deadline-after-open events.

        Returns:
            SSE event name and payload pairs.
        """

        events: list[tuple[str, dict[str, object]]] = []
        async for event in executor.execute(
            context=ctx,
            message="what is Our First Agent System?",
            cancel_event=asyncio.Event(),
        ):
            events.append(event)
        return events

    events = asyncio.run(_collect())
    types = [item[0] for item in events]
    assert types == ["deadline", "partial"]
    assert events[1][1] == {"reason": "deadline_exhausted"}
    assert "company_scope" not in str(events)
