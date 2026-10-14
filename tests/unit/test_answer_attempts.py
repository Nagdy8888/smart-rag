"""Counted answer retries stay inside the deadline and the call ceiling."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import cast
from uuid import uuid4

import pytest
from smart_rag_agents.query.nodes.answer_attempts import run_answer_attempts
from smart_rag_agents.query.state import QueryGraphState
from smart_rag_core.query_admission.exceptions import TimeoutAfterSendError
from smart_rag_core.query_answer.exceptions import AnswerError


def _context(seconds: float) -> SimpleNamespace:
    """Build a runtime whose deadline is ``seconds`` from now."""

    return SimpleNamespace(deadline_at=datetime.now(UTC) + timedelta(seconds=seconds))


def _run(
    monkeypatch: pytest.MonkeyPatch,
    *,
    send: object,
    seconds: float,
    remaining: int,
) -> tuple[list[str], object]:
    """Run attempts with a usage-recording stand-in for the counted call.

    Args:
        monkeypatch: Pytest patcher.
        send: Provider callable.
        seconds: Run time left.
        remaining: Model calls left.

    Returns:
        Usage attempt ids written, and the helper result or raised error.
    """

    usage: list[str] = []

    def _counted(_connection: object, **kwargs: object) -> tuple[object, object, str]:
        """Call ``send`` and record a usage row when the request was lost.

        Args:
            _connection: Unused connection.
            kwargs: Counted-call arguments.

        Returns:
            A successful triple when ``send`` returns.

        Raises:
            TimeoutAfterSendError: After recording usage for a lost response.
            AnswerError: Provider failures from ``send``.
        """

        attempt_id = str(kwargs["provider_attempt_id"])
        try:
            sent = kwargs["send"]
            if not callable(sent):
                raise AssertionError("send must be callable")
            payload: object = sent()
        except TimeoutAfterSendError:
            usage.append(attempt_id)
            raise
        return (payload, SimpleNamespace(optimistic_version=2), attempt_id)

    monkeypatch.setattr(
        "smart_rag_agents.query.nodes.answer_attempts.execute_counted_model_call",
        _counted,
    )
    state: dict[str, object] = {}
    try:
        result: object = cast(
            object,
            run_answer_attempts(
                cast(QueryGraphState, state),
                connection=object(),
                caller=object(),
                run_id=uuid4(),
                reservation_id=uuid4(),
                expected_version=1,
                model_id="gpt-4o-mini",
                send=send,  # type: ignore[arg-type]
                usage_from_result=lambda payload: (1, 1, None),
                context=_context(seconds),  # type: ignore[arg-type]
                remaining_model_calls=remaining,
            ),
        )
    except (TimeoutAfterSendError, AnswerError) as exc:
        return usage, exc
    return usage, result


def test_stall_then_success_writes_the_lost_attempt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A lost response is billed, then a second attempt can succeed."""

    calls = {"n": 0}

    def send() -> tuple[str, int, int]:
        """Fail once, then return a payload."""

        calls["n"] += 1
        if calls["n"] == 1:
            raise TimeoutAfterSendError("timeout_after_send")
        return ("ok", 2, 3)

    usage, result = _run(monkeypatch, send=send, seconds=30, remaining=3)
    assert len(usage) == 1
    assert calls["n"] == 2
    assert isinstance(result, tuple)


def test_two_stalls_stop_at_two(monkeypatch: pytest.MonkeyPatch) -> None:
    """A second lost response is not followed by a third send."""

    calls = {"n": 0}

    def send() -> tuple[str, int, int]:
        """Always lose the response."""

        calls["n"] += 1
        raise TimeoutAfterSendError("timeout_after_send")

    usage, result = _run(monkeypatch, send=send, seconds=30, remaining=3)
    assert calls["n"] == 2
    assert len(usage) == 2
    assert isinstance(result, TimeoutAfterSendError)


def test_short_deadline_does_not_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    """Less than eight seconds left keeps the single stalled attempt."""

    calls = {"n": 0}

    def send() -> tuple[str, int, int]:
        """Lose the only attempt."""

        calls["n"] += 1
        raise TimeoutAfterSendError("timeout_after_send")

    _usage, result = _run(monkeypatch, send=send, seconds=3, remaining=3)
    assert calls["n"] == 1
    assert isinstance(result, TimeoutAfterSendError)


def test_budget_denied_is_not_retried(monkeypatch: pytest.MonkeyPatch) -> None:
    """A 429 reason stops after the first attempt."""

    calls = {"n": 0}

    def send() -> tuple[str, int, int]:
        """Raise the provider budget reason."""

        calls["n"] += 1
        raise AnswerError("answer_budget_denied")

    _usage, result = _run(monkeypatch, send=send, seconds=30, remaining=3)
    assert calls["n"] == 1
    assert isinstance(result, AnswerError)
    assert result.reason == "answer_budget_denied"


def test_full_ceiling_does_not_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    """No remaining model call means the stalled attempt is the last one."""

    calls = {"n": 0}

    def send() -> tuple[str, int, int]:
        """Lose the only reserved attempt."""

        calls["n"] += 1
        raise TimeoutAfterSendError("timeout_after_send")

    _usage, result = _run(monkeypatch, send=send, seconds=30, remaining=0)
    assert calls["n"] == 1
    assert isinstance(result, TimeoutAfterSendError)
