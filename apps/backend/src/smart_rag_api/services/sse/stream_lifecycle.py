"""Executor termination summary, usage accounting, and stream close."""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import AsyncIterator


class StreamLifecycleMixin:
    """Mixin: termination summary, token accounting, and unfinished stream close."""

    termination_summary: dict[str, object]

    def _set_termination(
        self,
        *,
        reason: str,
        terminal_event_type: str | None = None,
        stream_exhausted: bool | None = None,
    ) -> None:
        """Store a sanitized stream-termination summary.

        Args:
            reason: ``completed``, ``partial``, ``cancelled``, ``deadline``,
                ``error``, ``interrupted``, or ``unknown``.
            terminal_event_type: First SSE terminal type, if any.
            stream_exhausted: Override for natural ``astream`` exhaustion.
                ``None`` keeps the current value.
        """

        exhausted = self.termination_summary.get("stream_exhausted")
        kept = exhausted if stream_exhausted is None else stream_exhausted
        previous = self.termination_summary
        self.termination_summary = {
            "termination_reason": reason,
            "terminal_event_type": terminal_event_type,
            "stream_exhausted": kept,
        }
        for key in (
            "input_tokens",
            "output_tokens",
            "total_tokens",
            "estimated_cost_usd",
        ):
            value = previous.get(key)
            if value is not None:
                self.termination_summary[key] = value

    def _record_stream_usage(
        self,
        *,
        input_tokens: int | None,
        output_tokens: int | None,
    ) -> None:
        """Attach accumulated token counts and estimated USD to the summary.

        Args:
            input_tokens: Latest graph ``prompt_tokens`` total.
            output_tokens: Latest graph ``completion_tokens`` total.
        """

        if input_tokens is None and output_tokens is None:
            return
        input_count = 0 if input_tokens is None else input_tokens
        output_count = 0 if output_tokens is None else output_tokens
        from smart_rag_core.observability.langsmith_tracing import (
            estimate_traced_chat_cost_usd,
        )

        self.termination_summary["input_tokens"] = input_count
        self.termination_summary["output_tokens"] = output_count
        self.termination_summary["total_tokens"] = input_count + output_count
        self.termination_summary["estimated_cost_usd"] = float(
            estimate_traced_chat_cost_usd(
                input_tokens=input_count,
                output_tokens=output_count,
            )
        )

    async def _aclose_stream(self, stream_iter: AsyncIterator[object]) -> None:
        """Close an unfinished LangGraph stream without converting GeneratorExit.

        Args:
            stream_iter: ``astream`` iterator that did not exhaust naturally.

        Raises:
            GeneratorExit: Re-raised when the generator is being closed.
            asyncio.CancelledError: Re-raised after ``aclose`` finishes.
        """

        close = getattr(stream_iter, "aclose", None)
        if not callable(close):
            return

        async def _close() -> None:
            """Await ``aclose`` when it returns an awaitable."""

            closed = close()
            if inspect.isawaitable(closed):
                await closed

        close_task = asyncio.create_task(_close())
        try:
            await asyncio.shield(close_task)
        except asyncio.CancelledError:
            await close_task
            raise
        except GeneratorExit:
            raise
