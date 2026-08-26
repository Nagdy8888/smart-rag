"""LangGraph executor termination, usage, and persist helpers."""

from __future__ import annotations

import asyncio
import inspect
import logging
from collections.abc import AsyncIterator
from typing import Protocol

import psycopg
from smart_rag_core.query_admission.context import AuthorizedRuntimeContext
from smart_rag_core.query_admission.exceptions import QueryAdmissionError

from smart_rag_api.services.query_sse_mapping import QuerySseMapper


class _CompactMemoryStore(Protocol):
    """Memory-store methods used after a successful terminal."""

    def put_compact(
        self,
        namespace: tuple[str, str, str],
        key: str,
        payload: dict[str, object],
    ) -> object:
        """Write one compacted store item.

        Args:
            namespace: Store namespace tuple.
            key: Item key.
            payload: Compact JSON mapping.

        Returns:
            Store write result.
        """

        ...


LOGGER = logging.getLogger(__name__)


class LangGraphExecutorSupport:
    """Mixin: termination summary, stream close, and post-terminal writes."""

    termination_summary: dict[str, object]
    _store: _CompactMemoryStore | None

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

        Side Effects:
            Updates ``termination_summary`` usage fields. Does not log text.
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

    def _commit_successful_terminal(
        self,
        context: AuthorizedRuntimeContext,
        mapper: QuerySseMapper,
        settings: object,
        *,
        remaining_model_calls: int,
        terminal_status: str,
    ) -> None:
        """Write summary and assistant text after a non-error terminal.

        The caller must already have yielded ``completed`` or ``partial``.
        Persist failures stay off the SSE log so they cannot overwrite that
        terminal with ``error``.

        Args:
            context: Authorized run context.
            mapper: Mapper that emitted the verified terminal.
            settings: Backend settings loaded once for this execute().
            remaining_model_calls: Remaining counted calls after the graph.
            terminal_status: Last node status.

        Side Effects:
            May consume ``usage_kind=summary`` and insert one assistant
            ``app.messages`` row. Logs ``error_type`` only when a write
            fails.
        """

        try:
            self._maybe_summarize(
                context,
                settings,
                remaining_model_calls=remaining_model_calls,
                terminal_status=terminal_status,
            )
        except Exception as exc:
            LOGGER.info(
                "query summary skipped",
                extra={
                    "event": "query.sse.summary_failed",
                    "error_type": type(exc).__name__,
                    "run_id": str(context.run_id),
                },
            )
        try:
            self._persist_assistant_answer(context, mapper, settings)
        except Exception as exc:
            LOGGER.info(
                "assistant message persist skipped",
                extra={
                    "event": "query.sse.assistant_persist_failed",
                    "error_type": type(exc).__name__,
                    "run_id": str(context.run_id),
                },
            )

    def _maybe_summarize(
        self,
        context: AuthorizedRuntimeContext,
        settings: object,
        *,
        remaining_model_calls: int,
        terminal_status: str,
    ) -> None:
        """Write a budgeted compact summary when the envelope can afford it.

        Args:
            context: Authorized run context.
            settings: Backend settings loaded once for this execute().
            remaining_model_calls: Remaining counted calls after the graph.
            terminal_status: Last node status. Summaries are skipped on
                admission/routing rejection.

        Side Effects:
            May consume ``usage_kind=summary`` and write one store item.
            Records ``summary_deferred`` by skipping the write when the
            envelope cannot cover the cap.
        """

        if terminal_status in {"admission_rejected", "routing_rejected"}:
            return
        if self._store is None:
            return
        from smart_rag_core.memory.summary import maybe_generate_conversation_summary
        from smart_rag_core.query_routing.preparation import caller_from_runtime

        db_url = getattr(settings, "supabase_db_url", None)
        postgres_url = db_url.get_secret_value() if db_url is not None else None
        if postgres_url is None:
            return
        store = self._store

        def _put(
            namespace: tuple[str, str, str],
            key: str,
            payload: dict[str, object],
        ) -> None:
            """Write one compacted store item.

            Args:
                namespace: Store namespace tuple.
                key: Item key.
                payload: JSON-compatible value.
            """

            store.put_compact(namespace, key, payload)

        with psycopg.connect(postgres_url) as connection:
            connection.execute("SET ROLE app_api")
            maybe_generate_conversation_summary(
                connection,
                caller=caller_from_runtime(context),
                run_id=context.run_id,
                reservation_id=context.reservation_id,
                expected_version=context.optimistic_version,
                remaining_model_calls=remaining_model_calls,
                remaining_usd=context.remaining_usd,
                conversation_id=context.conversation_id,
                user_id=str(context.user_id),
                memory_records=(),
                store_put=_put,
            )
            connection.commit()

    def _persist_assistant_answer(
        self,
        context: AuthorizedRuntimeContext,
        mapper: QuerySseMapper,
        settings: object,
    ) -> None:
        """Persist verified assistant prose when a DSN and text exist.

        Args:
            context: Authorized run context.
            mapper: Mapper that emitted the verified terminal.
            settings: Backend settings loaded once for this execute().

        Side Effects:
            Inserts one assistant ``app.messages`` row. Skips when the DSN
            or verified text is missing. Never logs message content.
        """

        answer_text = mapper.verified_text
        if not answer_text:
            return
        from smart_rag_core.query_admission.messages import append_query_message
        from smart_rag_core.query_routing.preparation import caller_from_runtime

        db_url = getattr(settings, "supabase_db_url", None)
        postgres_url = db_url.get_secret_value() if db_url is not None else None
        if postgres_url is None:
            return
        try:
            with psycopg.connect(postgres_url) as connection:
                connection.execute("SET ROLE app_api")
                append_query_message(
                    connection,
                    caller=caller_from_runtime(context),
                    conversation_id=context.conversation_id,
                    run_id=context.run_id,
                    role="assistant",
                    content=answer_text,
                )
                connection.commit()
        except (QueryAdmissionError, psycopg.Error):
            LOGGER.info(
                "assistant message persist skipped",
                extra={
                    "event": "query.sse.assistant_persist_failed",
                    "run_id": str(context.run_id),
                },
            )
