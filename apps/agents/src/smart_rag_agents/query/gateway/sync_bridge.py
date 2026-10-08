"""Run one async gateway call from the synchronous query graph."""

from __future__ import annotations

import asyncio
import contextvars
import threading
import time
from collections.abc import Callable
from datetime import UTC, datetime

from smart_rag_core.gateways.model_types import ModelInputBoundError
from smart_rag_core.gateways.openai_answer import OpenAIAnswerError
from smart_rag_core.query_admission.context import AuthorizedRuntimeContext
from smart_rag_core.query_admission.exceptions import TimeoutAfterSendError
from smart_rag_core.query_answer.exceptions import AnswerError


def gateway_timeout_seconds(
    context: AuthorizedRuntimeContext | None,
) -> float:
    """Bound one answer or verifier call to remaining run deadline seconds.

    Args:
        context: Admitted run context, or None in isolated unit tests.

    Returns:
        Timeout seconds clipped to ``0.1``-``45``.
    """

    if context is None:
        return 20.0
    remaining = (context.deadline_at - datetime.now(UTC)).total_seconds()
    return max(0.1, min(45.0, remaining))


def attempt_timeout_seconds(
    context: AuthorizedRuntimeContext | None,
    cap_seconds: float,
) -> float:
    """Bound one attempt to the cap or the time still left, whichever is smaller.

    Args:
        context: Admitted run context, or None in isolated unit tests.
        cap_seconds: Per-attempt ceiling in seconds.

    Returns:
        Timeout seconds clipped to at least ``0.1``.
    """

    if context is None:
        return max(0.1, cap_seconds)
    remaining = (context.deadline_at - datetime.now(UTC)).total_seconds()
    return max(0.1, min(cap_seconds, remaining))


def run_coro(
    factory: Callable[[], object],
    *,
    cancel_check: Callable[[], bool] | None = None,
    timeout_seconds: float = 45.0,
) -> object:
    """Run one async gateway call from the sync query graph.

    Never nests ``asyncio.run`` on the live SSE event loop. When a loop is
    already running, the awaitable is created and completed on a dedicated
    thread with its own loop.

    Args:
        factory: Zero-arg callable that returns an awaitable or a value.
        cancel_check: Cooperative cancellation probe.
        timeout_seconds: Join deadline for the dedicated-thread path.

    Returns:
        Gateway result.

    Raises:
        AnswerError: On cancel or timeout while a loop is already running.
    """

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        produced = factory()
        if asyncio.iscoroutine(produced):

            async def _await_with_timeout() -> object:
                """Await the worker coroutine within the configured deadline.

                Returns:
                    Gateway result produced before the timeout.

                Raises:
                    TimeoutError: When the gateway exceeds the bounded wait.
                """

                return await asyncio.wait_for(
                    produced,
                    timeout=max(0.1, timeout_seconds),
                )

            try:
                return asyncio.run(_await_with_timeout())
            except AnswerError:
                raise
            except ModelInputBoundError as exc:
                raise AnswerError("input_bound_exceeded") from exc
            except TimeoutError as exc:
                raise TimeoutAfterSendError("timeout_after_send") from exc
            except OpenAIAnswerError as exc:
                raise AnswerError(exc.reason) from exc
            except Exception as exc:
                raise AnswerError("gateway_failed") from exc
        return produced

    if cancel_check is not None and cancel_check():
        raise AnswerError("cancelled")

    box: dict[str, object] = {}
    errors: dict[str, BaseException] = {}
    copied = contextvars.copy_context()

    def _worker() -> None:
        """Create and complete the awaitable on this thread's event loop."""

        def _inner() -> None:
            """Run the gateway factory inside the copied tracing context."""

            try:
                produced = factory()
                if asyncio.iscoroutine(produced):
                    box["value"] = asyncio.run(produced)
                else:
                    box["value"] = produced
            except BaseException as exc:
                errors["exc"] = exc

        copied.run(_inner)

    thread = threading.Thread(target=_worker, name="query-gateway-loop", daemon=True)
    thread.start()
    deadline = time.monotonic() + max(0.1, timeout_seconds)
    while thread.is_alive():
        if cancel_check is not None and cancel_check():
            raise AnswerError("cancelled")
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutAfterSendError("timeout_after_send")
        thread.join(timeout=min(0.05, remaining))
    if "exc" in errors:
        raised = errors["exc"]
        if isinstance(raised, AnswerError | TimeoutAfterSendError | OpenAIAnswerError):
            if isinstance(raised, OpenAIAnswerError):
                raise AnswerError(raised.reason) from raised
            raise raised
        if isinstance(raised, ModelInputBoundError):
            raise AnswerError("input_bound_exceeded") from raised
        raise AnswerError("gateway_failed") from raised
    return box.get("value")
