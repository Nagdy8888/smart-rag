"""Process-local SSE attach, heartbeat, cancel, and executor registry."""

from __future__ import annotations

import asyncio
import inspect
import logging
from collections.abc import AsyncIterator, Callable, Mapping
from datetime import UTC, datetime
from typing import Any, Protocol, cast
from uuid import UUID

import psycopg
from fastapi.responses import StreamingResponse

# isort: off
# hybrid_run must finish before query_admission package init (ceilings cycle).
import smart_rag_core.retrieval.hybrid_run as _hybrid_run_cycle_guard  # noqa: F401
from smart_rag_core.query_admission.context import AuthorizedRuntimeContext
from smart_rag_core.query_admission.exceptions import QueryAdmissionError
from smart_rag_core.query_admission.service import (
    QueryRunRecord,
    load_query_run_runtime,
    true_up_query_reservation,
)

# isort: on
from smart_rag_core.security.identity import CallerContext
from smart_rag_core.sse.catalog import (
    HEARTBEAT_INTERVAL_SECONDS,
    TERMINAL_SSE_EVENT_TYPES,
)
from smart_rag_core.sse.framing import format_sse_event
from smart_rag_core.sse.sanitize import sanitize_error_payload
from smart_rag_core.sse.store import PersistedRunEvent, RunEventStore

from smart_rag_api.services.query_sse_mapping import (
    QuerySseMapper,
    assert_catalog_event,
)

LOGGER = logging.getLogger(__name__)
CANCEL_GRACE_SECONDS = 0.25
"""Cooperative executor cleanup window after an explicit cancel."""

SSE_RESPONSE_HEADERS: dict[str, str] = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}

_POLL_SECONDS = 0.05
_NON_STARTABLE_STATUSES = frozenset(
    {"running", "completed", "cancelled", "partial", "failed"}
)
_STREAM_MODE_NAMES = frozenset({"updates", "values", "messages", "debug"})


def _coerce_stream_token_count(value: object) -> int | None:
    """Return a non-negative token count from a node or SSE field.

    Args:
        value: Graph or catalog token field.

    Returns:
        Integer count, or None when the value is missing or invalid.
    """

    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value >= 0 else None
    if isinstance(value, float) and value.is_integer() and value >= 0:
        return int(value)
    return None


def _updates_mapping_from_chunk(raw_chunk: object) -> dict[str, object] | None:
    """Unwrap one LangGraph ``astream`` updates payload.

    Args:
        raw_chunk: Dict ``{node: update}`` or ``(stream_mode, payload)``.

    Returns:
        Node-keyed mapping, or None when the chunk is not updates data.
    """

    chunk: object = raw_chunk
    if isinstance(chunk, tuple) and len(chunk) == 2:
        mode, data = chunk
        if isinstance(mode, str) and mode in _STREAM_MODE_NAMES:
            chunk = data
    if not isinstance(chunk, dict):
        return None
    return {str(key): value for key, value in cast(dict[object, object], chunk).items()}


def _token_counts_from_update(
    typed_update: Mapping[str, object],
) -> tuple[int | None, int | None]:
    """Read prompt and completion totals from one node update.

    Args:
        typed_update: Node return mapping.

    Returns:
        ``(prompt_tokens, completion_tokens)`` with None for missing sides.
    """

    prompt = _coerce_stream_token_count(typed_update.get("prompt_tokens"))
    if prompt is None:
        prompt = _coerce_stream_token_count(typed_update.get("input_tokens"))
    completion = _coerce_stream_token_count(typed_update.get("completion_tokens"))
    if completion is None:
        completion = _coerce_stream_token_count(typed_update.get("output_tokens"))
    return prompt, completion


class QueryRunExecutor(Protocol):
    """Produces application SSE drafts. Heartbeat and schema are service-owned."""

    def execute(
        self,
        *,
        context: AuthorizedRuntimeContext,
        message: str,
        cancel_event: asyncio.Event,
    ) -> AsyncIterator[tuple[str, dict[str, object]]]:
        """Yield ``(event_type, payload)`` until complete, cancelled, or failed.

        Args:
            context: Authorized runtime from admission.
            message: Untrusted user text for graph input.
            cancel_event: Set when POST ``/runs/{id}/cancel`` fires.

        Returns:
            Async iterator of allow-listed event type and extra=forbid payload.
        """

        raise NotImplementedError


class FixtureQueryRunExecutor:
    """Test executor: status, optional hold, optional completed. No OpenAI."""

    def __init__(
        self,
        *,
        hold_seconds: float | None = None,
        emit_completed: bool = True,
        extra_events: tuple[tuple[str, dict[str, object]], ...] = (),
    ) -> None:
        """Configure fixture behavior.

        Args:
            hold_seconds: Wait for cancel or timeout before completing.
            emit_completed: Yield a ``completed`` terminal when the hold ends.
            extra_events: Additional drafts after the initial status event.
        """

        self.hold_seconds = hold_seconds
        self.emit_completed = emit_completed
        self.extra_events = extra_events
        self.start_count = 0

    async def execute(
        self,
        *,
        context: AuthorizedRuntimeContext,
        message: str,
        cancel_event: asyncio.Event,
    ) -> AsyncIterator[tuple[str, dict[str, object]]]:
        """Emit status, optional extras, then hold or complete.

        Args:
            context: Authorized context. Unused besides proving injection.
            message: Unused untrusted text.
            cancel_event: Stops a hold early without emitting completed.

        Yields:
            Fixture events. Never includes passage text.
        """

        del context, message
        self.start_count += 1
        yield ("status", {"stage": "admitted", "status": "running"})
        for event_type, payload in self.extra_events:
            yield (event_type, payload)
        if self.hold_seconds is not None:
            try:
                await asyncio.wait_for(cancel_event.wait(), timeout=self.hold_seconds)
            except TimeoutError:
                pass
            if cancel_event.is_set():
                return
        if self.emit_completed:
            yield ("completed", {})


class LangGraphQueryRunExecutor:
    """Production executor: compiled query graph with optional checkpoints."""

    def __init__(self) -> None:
        """Create an executor that opens checkpointer/store lazily.

        Side Effects:
            None at construction. First ``execute`` may open a Postgres pool
            and construct process Hybrid/gateway bindings.
            ``PostgresSaver.setup()``, ``AsyncPostgresSaver.setup()``, and
            ``PostgresStore.setup()`` are never called.
        """

        self._holder = None
        self._async_holder = None
        self._store = None
        self._bindings = None
        self.termination_summary: dict[str, object] = {
            "termination_reason": "unknown",
            "terminal_event_type": None,
            "stream_exhausted": False,
        }

    def _process_bindings(self, settings: object):
        """Return process-reusable Hybrid/gateway bindings.

        Args:
            settings: Backend settings used when lifespan state is absent.

        Returns:
            ``QueryGraphProcessBindings`` with non-null Hybrid and gateway.

        Raises:
            QueryGraphRuntimeError: When required adapters cannot be built.

        Side Effects:
            Caches process Hybrid/gateway bindings on this executor.
        """

        from smart_rag_api.services.query_graph_runtime import (
            build_query_process_bindings,
        )

        if self._bindings is not None:
            return self._bindings
        self._bindings = build_query_process_bindings(settings=settings)
        return self._bindings

    def _bind_memory_store(self, settings: object):
        """Open the compact memory store and checkpointer once per process.

        Args:
            settings: Backend settings with the checkpoint DSN.

        Returns:
            ``(store_get, store_put)`` callables, or ``(None, None)``.

        Side Effects:
            Opens a memory store on first use. The async checkpointer is
            opened separately.
        """

        resolved = getattr(settings, "resolved_checkpoint_dsn", None)
        dsn = resolved() if callable(resolved) else None
        if not isinstance(dsn, str) or not dsn:
            return None, None
        if self._store is None:
            from smart_rag_agents.query.store import open_query_memory_store

            self._store = open_query_memory_store(dsn)
        memory_store = self._store
        if memory_store is None:
            return None, None

        def _bind_put(
            namespace: tuple[str, str, str],
            key: str,
            payload: dict[str, object],
        ) -> None:
            """Write one compact store item.

            Args:
                namespace: Store namespace tuple.
                key: Item key.
                payload: Compact JSON mapping.
            """

            memory_store.put_compact(namespace, key, payload)

        return memory_store.get_compact, _bind_put

    async def _ensure_async_checkpointer(self, settings: object):
        """Open the compact async query checkpointer once per process.

        Args:
            settings: Backend settings with the checkpoint DSN.

        Returns:
            ``CompactAsyncPostgresSaver`` or ``None`` when no DSN is
            configured.

        Side Effects:
            Opens an async checkpointer pool on first use. Never calls
            ``setup()``.
        """

        if self._async_holder is not None:
            return self._async_holder.saver
        resolved = getattr(settings, "resolved_checkpoint_dsn", None)
        dsn = resolved() if callable(resolved) else None
        if not isinstance(dsn, str) or not dsn:
            return None
        from smart_rag_agents.query.checkpointer import open_query_async_checkpointer

        self._async_holder = await open_query_async_checkpointer(dsn)
        return self._async_holder.saver

    async def execute(
        self,
        *,
        context: AuthorizedRuntimeContext,
        message: str,
        cancel_event: asyncio.Event,
    ) -> AsyncIterator[tuple[str, dict[str, object]]]:
        """Stream node completions as ``status`` events, then a terminal.

        Args:
            context: Server-derived ceilings and deadline.
            message: Untrusted user query.
            cancel_event: Stops iteration without restarting paid work later.

        Yields:
            Status events and at most one terminal. Retrieved source text is
            never copied into payloads. Summary or assistant persist after
            ``completed``/``partial`` cannot replace that terminal.

        Raises:
            asyncio.CancelledError: When the wrapping task is cancelled.
            ExternalFlowBlockedError: When tracing would export real company
                content without a verified subprocessor matrix.
        """

        from smart_rag_core.observability.governance_gate import (
            assert_langsmith_export_permitted,
        )
        from smart_rag_core.security.external_processing import ContentClass
        from smart_rag_core.settings import load_backend_settings

        settings = load_backend_settings()
        assert_langsmith_export_permitted(
            tracing_enabled=settings.langsmith_tracing,
            content_class=(
                ContentClass.SYNTHETIC
                if (
                    settings.mock_model_mode
                    or settings.allows_unsigned_local_live_providers()
                )
                else ContentClass.REAL_COMPANY
            ),
            provider_settings_verified=settings.subprocessor_matrix_verified,
            local_unsigned_waiver=settings.allows_unsigned_local_live_providers(),
        )
        self._set_termination(
            reason="unknown",
            terminal_event_type=None,
            stream_exhausted=False,
        )

        if datetime.now(tz=UTC) >= context.deadline_at:
            self._set_termination(reason="deadline", terminal_event_type="partial")
            yield ("deadline", {"route_family": context.route_family.value})
            yield ("partial", {"reason": "deadline_exhausted"})
            return

        from smart_rag_agents.query.graph import (
            compile_query_graph,
            pending_query_state,
        )

        from smart_rag_api.services.query_graph_runtime import (
            QueryGraphRuntimeError,
            build_query_graph_deps,
            open_run_app_api_connection,
        )

        connection = None
        connection_closed = False
        stream_iter: AsyncIterator[object] | None = None
        stream_exhausted = False
        stream_aclose_called = False
        terminal_yielded = False
        successful_terminal_committed = False
        last_remaining_calls = context.model_call_ceiling
        last_status = "running"
        last_prompt_tokens: int | None = None
        last_completion_tokens: int | None = None

        def _close_connection() -> None:
            """Close the app_api connection exactly once.

            Side Effects:
                Closes ``connection`` when it is still open.
            """

            nonlocal connection_closed
            if connection is None or connection_closed:
                return
            connection_closed = True
            connection.close()

        try:
            bindings = self._process_bindings(settings)
            connection = open_run_app_api_connection(bindings.supabase_dsn)
            store_binding = self._bind_memory_store(settings)
            if inspect.isawaitable(store_binding):
                store_get, store_put = await store_binding
            else:
                store_get, store_put = store_binding
            deps = build_query_graph_deps(
                bindings=bindings,
                connection=connection,
                cancel_check=cancel_event.is_set,
                store_get=store_get,
                store_put=store_put,
            )
            checkpointer = await self._ensure_async_checkpointer(settings)
            compiled = compile_query_graph(deps, checkpointer=checkpointer)
            state = pending_query_state(
                authorized_runtime=context.model_dump(mode="json"),
                user_query=message,
            )
            config: dict[str, object] = {
                "recursion_limit": context.recursion_limit,
                "configurable": {"thread_id": str(context.conversation_id)},
            }
            stream_method: Callable[..., AsyncIterator[object]] = compiled.astream  # type: ignore[reportUnknownMemberType]
            stream_iter = stream_method(state, cast(Any, config), stream_mode="updates")
            mapper = QuerySseMapper()
            LOGGER.info(
                "query sse stream started",
                extra={
                    "event": "query.sse.started",
                    "run_id": str(context.run_id),
                },
            )
            async for raw_chunk in stream_iter:
                # A completed node may have consumed a reservation and written
                # usage on this connection. Commit before the separate event
                # store appends its status, otherwise both writers deadlock on
                # the same run/reservation transaction.
                connection.commit()
                if cancel_event.is_set():
                    self._set_termination(
                        reason="cancelled",
                        terminal_event_type="cancelled",
                        stream_exhausted=False,
                    )
                    break
                typed_chunk = _updates_mapping_from_chunk(raw_chunk)
                if typed_chunk is not None:
                    for node_update in typed_chunk.values():
                        if isinstance(node_update, dict):
                            typed_update = {
                                str(key): value
                                for key, value in cast(
                                    dict[object, object], node_update
                                ).items()
                            }
                            remaining = typed_update.get("remaining_model_calls")
                            if isinstance(remaining, int):
                                last_remaining_calls = remaining
                            raw_status = typed_update.get("status")
                            if isinstance(raw_status, str) and raw_status:
                                last_status = raw_status[:64]
                            prompt_tokens, completion_tokens = (
                                _token_counts_from_update(typed_update)
                            )
                            if prompt_tokens is not None:
                                last_prompt_tokens = prompt_tokens
                            if completion_tokens is not None:
                                last_completion_tokens = completion_tokens
                for event_type, payload in mapper.consume_chunk(
                    typed_chunk if typed_chunk is not None else cast(object, raw_chunk)
                ):
                    assert_catalog_event(event_type, payload)
                    if event_type == "usage":
                        event_prompt, event_completion = _token_counts_from_update(
                            payload
                        )
                        if event_prompt is not None:
                            last_prompt_tokens = event_prompt
                        if event_completion is not None:
                            last_completion_tokens = event_completion
                    yield (event_type, payload)
                    if event_type in {"completed", "partial", "error", "cancelled"}:
                        if not terminal_yielded:
                            terminal_yielded = True
                            reason = (
                                "error"
                                if event_type == "error"
                                else (
                                    "cancelled"
                                    if event_type == "cancelled"
                                    else event_type
                                )
                            )
                            self._set_termination(
                                reason=reason,
                                terminal_event_type=event_type,
                            )
                        if (
                            event_type in {"completed", "partial"}
                            and not successful_terminal_committed
                        ):
                            successful_terminal_committed = True
                            self._commit_successful_terminal(
                                context,
                                mapper,
                                remaining_model_calls=last_remaining_calls,
                                terminal_status=last_status,
                            )
            else:
                stream_exhausted = True
                self._set_termination(
                    reason=str(self.termination_summary.get("termination_reason")),
                    terminal_event_type=(
                        str(self.termination_summary["terminal_event_type"])
                        if isinstance(
                            self.termination_summary.get("terminal_event_type"),
                            str,
                        )
                        else None
                    ),
                    stream_exhausted=True,
                )
            if stream_exhausted and not cancel_event.is_set():
                for event_type, payload in mapper.finish():
                    assert_catalog_event(event_type, payload)
                    yield (event_type, payload)
                    if event_type in {"completed", "partial", "error", "cancelled"}:
                        terminal_yielded = True
                        self._set_termination(
                            reason=("error" if event_type == "error" else event_type),
                            terminal_event_type=event_type,
                            stream_exhausted=True,
                        )
                    if (
                        event_type in {"completed", "partial"}
                        and not successful_terminal_committed
                    ):
                        successful_terminal_committed = True
                        self._commit_successful_terminal(
                            context,
                            mapper,
                            remaining_model_calls=last_remaining_calls,
                            terminal_status=last_status,
                        )
        except QueryGraphRuntimeError as exc:
            self._set_termination(reason="error", terminal_event_type="error")
            yield ("error", {"code": exc.reason})
        except asyncio.CancelledError:
            self._set_termination(
                reason="interrupted",
                terminal_event_type=str(
                    self.termination_summary.get("terminal_event_type")
                )
                if self.termination_summary.get("terminal_event_type")
                else "cancelled",
                stream_exhausted=stream_exhausted,
            )
            raise
        except GeneratorExit:
            self._set_termination(
                reason="interrupted",
                stream_exhausted=stream_exhausted,
            )
            raise
        except Exception:
            self._set_termination(reason="error", terminal_event_type="error")
            raise
        finally:
            self._record_stream_usage(
                input_tokens=last_prompt_tokens,
                output_tokens=last_completion_tokens,
            )
            _close_connection()
            if (
                stream_iter is not None
                and not stream_exhausted
                and not stream_aclose_called
            ):
                stream_aclose_called = True
                await self._aclose_stream(stream_iter)

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
            self._persist_assistant_answer(context, mapper)
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
        *,
        remaining_model_calls: int,
        terminal_status: str,
    ) -> None:
        """Write a budgeted compact summary when the envelope can afford it.

        Args:
            context: Authorized run context.
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
        from smart_rag_core.settings import load_backend_settings

        settings = load_backend_settings()
        postgres_url = (
            settings.supabase_db_url.get_secret_value()
            if settings.supabase_db_url is not None
            else None
        )
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
    ) -> None:
        """Persist verified assistant prose when a DSN and text exist.

        Args:
            context: Authorized run context.
            mapper: Mapper that emitted the verified terminal.

        Side Effects:
            Inserts one assistant ``app.messages`` row. Skips when the DSN
            or verified text is missing. Never logs message content.
        """

        answer_text = mapper.verified_text
        if not answer_text:
            return
        from smart_rag_core.query_admission.messages import append_query_message
        from smart_rag_core.query_routing.preparation import caller_from_runtime
        from smart_rag_core.settings import load_backend_settings

        settings = load_backend_settings()
        postgres_url = (
            settings.supabase_db_url.get_secret_value()
            if settings.supabase_db_url is not None
            else None
        )
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


def raw_status_is_partial(update: dict[str, object]) -> bool:
    """Return whether a node update is a deadline/partial terminal.

    Args:
        update: Node state mapping.

    Returns:
        True when status is ``verified_partial`` or ``insufficient_evidence``.
    """

    raw_status = update.get("status")
    return raw_status in {"verified_partial", "insufficient_evidence"}


class LiveQueryRun:
    """In-process handle for one run's executor and heartbeat."""

    def __init__(self) -> None:
        """Create an idle handle."""

        self.cancel_event = asyncio.Event()
        self.started = False
        self.terminal = False
        self.executor_task: asyncio.Task[None] | None = None
        self.heartbeat_task: asyncio.Task[None] | None = None


class QueryRunRegistry:
    """Process-local live runs and pending graph inputs keyed by ``run_id``."""

    def __init__(self) -> None:
        """Create an empty registry."""

        self._live: dict[UUID, LiveQueryRun] = {}
        self._inputs: dict[UUID, str] = {}
        self._contexts: dict[UUID, AuthorizedRuntimeContext] = {}

    def remember_input(
        self,
        run_id: UUID,
        message: str,
        context: AuthorizedRuntimeContext | None = None,
    ) -> None:
        """Store the user message and admit context for a later first attach.

        Args:
            run_id: Admitted run.
            message: Untrusted user text.
            context: Authorized runtime used to start the graph once.
        """

        self._inputs[run_id] = message
        if context is not None:
            self._contexts[run_id] = context

    def take_input(self, run_id: UUID) -> str:
        """Return the remembered message or empty string.

        Args:
            run_id: Run id.

        Returns:
            Stored message. Empty when this process never saw the POST body.
        """

        return self._inputs.get(run_id, "")

    def take_context(self, run_id: UUID) -> AuthorizedRuntimeContext | None:
        """Return the remembered admit context when this process saw the POST.

        Args:
            run_id: Run id.

        Returns:
            Stored context, or None after a process restart.
        """

        return self._contexts.get(run_id)

    def has_input(self, run_id: UUID) -> bool:
        """Return whether this process still has the POST body.

        Args:
            run_id: Run id.

        Returns:
            True when ``remember_input`` ran in this process.
        """

        return run_id in self._inputs

    def get(self, run_id: UUID) -> LiveQueryRun | None:
        """Return the live handle when this process owns the executor.

        Args:
            run_id: Run id.

        Returns:
            Live handle or None.
        """

        return self._live.get(run_id)

    def get_or_create(self, run_id: UUID) -> LiveQueryRun:
        """Return the existing handle or create an idle one.

        Args:
            run_id: Run id.

        Returns:
            Live handle.
        """

        handle = self._live.get(run_id)
        if handle is None:
            handle = LiveQueryRun()
            self._live[run_id] = handle
        return handle

    def drop(self, run_id: UUID) -> None:
        """Forget a finished live handle. Inputs stay for no-op reconnects.

        Args:
            run_id: Run id.
        """

        self._live.pop(run_id, None)

    def request_cancel(self, run_id: UUID) -> None:
        """Signal the live executor to stop. No-op when this process has none.

        Args:
            run_id: Run id.
        """

        handle = self._live.get(run_id)
        if handle is not None:
            handle.cancel_event.set()


class SseStreamService:
    """Persist-then-flush SSE attach for POST fetch and GET resume."""

    def __init__(
        self,
        *,
        store: RunEventStore,
        registry: QueryRunRegistry,
        executor: QueryRunExecutor,
        sse_schema_version: str,
        heartbeat_interval_seconds: int = HEARTBEAT_INTERVAL_SECONDS,
        postgres_url: str | None = None,
    ) -> None:
        """Bind store, registry, and executor.

        Args:
            store: Memory or Postgres event store used by this service.
            registry: Process-local live-run table.
            executor: LangGraph production executor or a test fixture.
            sse_schema_version: Value for the first ``schema`` event.
            heartbeat_interval_seconds: Production default is 15.
            postgres_url: Optional ``app_api`` DSN for durable resume and
                reservation settlement. Unit tests omit this so missing
                process input stays ``worker_unavailable``.
        """

        self._store = store
        self._registry = registry
        self._executor = executor
        self._sse_schema_version = sse_schema_version
        self._heartbeat_interval_seconds = heartbeat_interval_seconds
        self._postgres_url = postgres_url
        self._settled_run_ids: set[UUID] = set()

    def remember_admitted(
        self,
        caller: CallerContext,
        context: AuthorizedRuntimeContext,
        *,
        message: str,
    ) -> None:
        """Register ownership and the POST body after a successful admit.

        Args:
            caller: Owner.
            context: Admission result.
            message: Untrusted user text for a later first graph start.
        """

        record = QueryRunRecord(
            run_id=context.run_id,
            conversation_id=context.conversation_id,
            creator_user_id=context.user_id,
            status=context.status,
            reservation_id=context.reservation_id,
            created_at=None,
        )
        self._store.register_run(caller=caller, record=record)
        self._registry.remember_input(context.run_id, message, context)

    def assert_readable(self, caller: CallerContext, *, run_id: UUID) -> QueryRunRecord:
        """Authorize resume before headers are sent.

        Args:
            caller: Owner.
            run_id: Run id.

        Returns:
            Authorized run record.

        Raises:
            QueryAdmissionError: Missing, foreign, or tombstoned conversation.
        """

        return self._store.get_authorized_run(caller, run_id=run_id)

    def notify_cancel(self, caller: CallerContext, *, run_id: UUID) -> None:
        """Stop the live generator and persist ``cancelled`` if needed.

        Missing store rows are ignored so packet 5 fake cancel services still
        work. Live executors are signalled first.

        Args:
            caller: Owner.
            run_id: Run to cancel.
        """

        handle = self._registry.get(run_id)
        self._registry.request_cancel(run_id)
        try:
            self._store.get_authorized_run(caller, run_id=run_id)
        except QueryAdmissionError:
            return
        if not self._has_terminal(caller, run_id):
            self._append(caller, run_id, "cancelled", {})
        if handle is None:
            return
        heartbeat = handle.heartbeat_task
        if heartbeat is not None and not heartbeat.done():
            heartbeat.cancel()
        executor = handle.executor_task
        if executor is None or executor.done():
            handle.terminal = True
            return
        loop = executor.get_loop()
        loop.call_soon_threadsafe(
            lambda: loop.create_task(self._cooperative_cancel(handle))
        )

    async def iter_frames(
        self,
        caller: CallerContext,
        *,
        run_id: UUID,
        after: int,
        context: AuthorizedRuntimeContext | None = None,
    ) -> AsyncIterator[str]:
        """Replay persisted events, attach once, and yield framed SSE.

        Reconnect never starts a second graph when status is already
        running/completed/cancelled/partial/failed or this process has a live
        executor.

        Args:
            caller: Owner.
            run_id: Run id.
            after: Exclusive sequence cursor.
            context: Fresh admit context used to start the graph.

        Yields:
            SSE frames. Persistence happens before each yield.

        Raises:
            QueryAdmissionError: Missing, foreign, or tombstoned run.
        """

        self.assert_readable(caller, run_id=run_id)
        cursor = after
        async for frame, sequence, terminal in self._replay(caller, run_id, cursor):
            cursor = sequence
            yield frame
            if terminal:
                return

        record = self.assert_readable(caller, run_id=run_id)
        live = self._registry.get(run_id)
        if live is None and record.status in _NON_STARTABLE_STATUSES:
            async for frame, sequence, terminal in self._replay(caller, run_id, cursor):
                cursor = sequence
                yield frame
                if terminal:
                    return
            return

        if live is None and record.status == "pending":
            if context is None and not self._registry.has_input(run_id):
                loaded = self._load_durable_start(caller, run_id)
                if loaded is None:
                    self._emit_worker_unavailable(caller, run_id)
                    async for frame, sequence, terminal in self._replay(
                        caller, run_id, cursor
                    ):
                        cursor = sequence
                        yield frame
                        if terminal:
                            return
                    return
                message, runtime = loaded
                self._registry.remember_input(run_id, message, runtime)
                context = runtime
            live = self._registry.get_or_create(run_id)
            self._start_once(caller, record, live, context)

        if live is not None and not live.started and record.status == "pending":
            self._start_once(caller, record, live, context)

        loop = asyncio.get_running_loop()
        last_heartbeat_at = loop.time()
        while True:
            emitted = False
            async for frame, sequence, terminal in self._replay(caller, run_id, cursor):
                cursor = sequence
                emitted = True
                yield frame
                if terminal:
                    self._registry.drop(run_id)
                    return
            handle = self._registry.get(run_id)
            if handle is None or handle.terminal:
                async for frame, sequence, terminal in self._replay(
                    caller, run_id, cursor
                ):
                    cursor = sequence
                    yield frame
                    if terminal:
                        self._registry.drop(run_id)
                        return
                if not emitted:
                    return
            now = loop.time()
            if (
                handle is not None
                and not handle.terminal
                and not handle.cancel_event.is_set()
                and now - last_heartbeat_at >= self._heartbeat_interval_seconds
            ):
                self._append(caller, run_id, "heartbeat", {})
                last_heartbeat_at = now
            await asyncio.sleep(_POLL_SECONDS)

    def _start_once(
        self,
        caller: CallerContext,
        record: QueryRunRecord,
        live: LiveQueryRun,
        context: AuthorizedRuntimeContext | None,
    ) -> None:
        """Start the executor at most once in this process.

        Heartbeats are persisted by the attach loop while a stream is open.

        Args:
            caller: Owner.
            record: Current run row.
            live: Process handle.
            context: Fresh admit context when the POST is still in-flight.
        """

        if live.started:
            return
        live.started = True
        self._ensure_schema(caller, record.run_id)
        try:
            self._store.mark_running(caller, run_id=record.run_id)
        except QueryAdmissionError:
            LOGGER.info(
                "query run not marked running",
                extra={
                    "event": "sse.mark_running_skipped",
                    "run_id": str(record.run_id),
                },
            )
        message = self._registry.take_input(record.run_id)
        runtime = context or self._registry.take_context(record.run_id)
        if (not message or runtime is None) and self._postgres_url:
            loaded = self._load_durable_start(caller, record.run_id)
            if loaded is not None:
                loaded_message, loaded_runtime = loaded
                if not message:
                    message = loaded_message
                if runtime is None:
                    runtime = loaded_runtime
        live.executor_task = asyncio.create_task(
            self._run_executor(caller, record, live, message, runtime)
        )
        live.heartbeat_task = asyncio.create_task(
            self._run_heartbeat(caller, record.run_id, live)
        )

    async def _run_executor(
        self,
        caller: CallerContext,
        record: QueryRunRecord,
        live: LiveQueryRun,
        message: str,
        context: AuthorizedRuntimeContext | None,
    ) -> None:
        """Run the executor once and persist its drafts.

        Args:
            caller: Owner.
            record: Run row.
            live: Process handle.
            message: User text.
            context: Optional admit context; reconstructed from the record
                when missing (GET-after-202 on the same process).
        """

        runtime = context or self._registry.take_context(record.run_id)
        if (runtime is None or not message) and self._postgres_url:
            loaded = self._load_durable_start(caller, record.run_id)
            if loaded is not None:
                loaded_message, loaded_runtime = loaded
                if not message:
                    message = loaded_message
                if runtime is None:
                    runtime = loaded_runtime
        if runtime is None:
            self._emit_worker_unavailable(caller, record.run_id)
            live.terminal = True
            self._cancel_tasks(live)
            return
        try:
            from smart_rag_core.observability.query_run_trace import (
                invoke_traced_query_run_sse,
            )
            from smart_rag_core.settings import (
                SettingsValidationError,
                load_backend_settings,
            )

            try:
                settings = load_backend_settings()
            except (SettingsValidationError, ValueError):
                settings = None

            async def _consume() -> dict[str, object]:
                """Drain the executor and persist drafts.

                Returns:
                    Termination summary plus assistant text and usage when
                    the stream emitted those catalog events.
                """

                assistant_parts: list[str] = []
                prompt_tokens: int | None = None
                completion_tokens: int | None = None
                async for event_type, payload in self._executor.execute(
                    context=runtime,
                    message=message,
                    cancel_event=live.cancel_event,
                ):
                    self._append(caller, record.run_id, event_type, payload)
                    if event_type == "token_delta":
                        delta = payload.get("delta")
                        if isinstance(delta, str) and delta:
                            assistant_parts.append(delta)
                    elif event_type == "usage":
                        event_prompt, event_completion = _token_counts_from_update(
                            payload
                        )
                        if event_prompt is not None:
                            prompt_tokens = event_prompt
                        if event_completion is not None:
                            completion_tokens = event_completion
                if not self._has_terminal(caller, record.run_id):
                    if live.cancel_event.is_set():
                        self._append(caller, record.run_id, "cancelled", {})
                    else:
                        self._append(
                            caller,
                            record.run_id,
                            "error",
                            {"code": "run_failed"},
                        )
                summary = getattr(self._executor, "termination_summary", None)
                payload: dict[str, object]
                if isinstance(summary, dict):
                    typed_summary = cast(dict[object, object], summary)
                    payload = {str(key): value for key, value in typed_summary.items()}
                else:
                    payload = {
                        "termination_reason": (
                            "cancelled" if live.cancel_event.is_set() else "unknown"
                        ),
                        "terminal_event_type": None,
                        "stream_exhausted": False,
                    }
                if assistant_parts:
                    payload["assistant_message"] = "".join(assistant_parts)
                if prompt_tokens is None:
                    prompt_tokens = _coerce_stream_token_count(
                        payload.get("input_tokens")
                    )
                if prompt_tokens is None:
                    prompt_tokens = _coerce_stream_token_count(
                        payload.get("prompt_tokens")
                    )
                if completion_tokens is None:
                    completion_tokens = _coerce_stream_token_count(
                        payload.get("output_tokens")
                    )
                if completion_tokens is None:
                    completion_tokens = _coerce_stream_token_count(
                        payload.get("completion_tokens")
                    )
                if prompt_tokens is not None:
                    payload["input_tokens"] = prompt_tokens
                if completion_tokens is not None:
                    payload["output_tokens"] = completion_tokens
                input_count = _coerce_stream_token_count(payload.get("input_tokens"))
                output_count = _coerce_stream_token_count(payload.get("output_tokens"))
                if input_count is not None or output_count is not None:
                    from smart_rag_core.observability.langsmith_tracing import (
                        estimate_traced_chat_cost_usd,
                    )

                    input_total = 0 if input_count is None else input_count
                    output_total = 0 if output_count is None else output_count
                    payload["input_tokens"] = input_total
                    payload["output_tokens"] = output_total
                    payload["total_tokens"] = input_total + output_total
                    payload["estimated_cost_usd"] = float(
                        estimate_traced_chat_cost_usd(
                            input_tokens=input_total,
                            output_tokens=output_total,
                        )
                    )
                return payload

            if settings is None:
                await _consume()
            else:
                await invoke_traced_query_run_sse(
                    _consume,
                    settings=settings,
                    run_id=record.run_id,
                    user_id=runtime.user_id,
                    user_message=message,
                    requested_route=runtime.route_family.value,
                    effective_route=runtime.route_family.value,
                )
        except asyncio.CancelledError:
            if not self._has_terminal(caller, record.run_id):
                self._append(caller, record.run_id, "cancelled", {})
            raise
        except Exception as exc:
            LOGGER.info(
                "query executor failed",
                extra={
                    "event": "sse.executor_failed",
                    "error_type": type(exc).__name__,
                },
            )
            if not self._has_terminal(caller, record.run_id):
                self._append(
                    caller,
                    record.run_id,
                    "error",
                    sanitize_error_payload(exc),
                )
        finally:
            live.terminal = True
            heartbeat = live.heartbeat_task
            if heartbeat is not None and not heartbeat.done():
                heartbeat.cancel()

    async def _run_heartbeat(
        self, caller: CallerContext, run_id: UUID, live: LiveQueryRun
    ) -> None:
        """Persist a heartbeat every interval until the run is terminal.

        Args:
            caller: Owner.
            run_id: Run id.
            live: Process handle.
        """

        try:
            while not live.terminal and not live.cancel_event.is_set():
                await asyncio.sleep(self._heartbeat_interval_seconds)
                if live.terminal or live.cancel_event.is_set():
                    break
                if self._has_terminal(caller, run_id):
                    break
                self._append(caller, run_id, "heartbeat", {})
        except asyncio.CancelledError:
            return

    def _ensure_schema(self, caller: CallerContext, run_id: UUID) -> None:
        """Persist ``schema`` as sequence 1 when the log is empty.

        Args:
            caller: Owner.
            run_id: Run id.
        """

        existing = self._store.list_after(caller, run_id=run_id, after=0)
        if existing:
            return
        self._append(
            caller,
            run_id,
            "schema",
            {"sse_schema_version": self._sse_schema_version},
        )

    def _load_durable_start(
        self, caller: CallerContext, run_id: UUID
    ) -> tuple[str, AuthorizedRuntimeContext] | None:
        """Rebuild user text and runtime from durable records.

        Args:
            caller: Owner.
            run_id: Admitted run.

        Returns:
            Persisted message and runtime, or None when the DSN is unset
            or durable input cannot be loaded. Missing input must remain
            ``worker_unavailable`` for process-local tests.
        """

        if not self._postgres_url:
            return None
        try:
            with psycopg.connect(self._postgres_url) as connection:
                connection.execute("SET ROLE app_api")
                runtime, message = load_query_run_runtime(
                    connection, caller=caller, run_id=run_id
                )
        except (QueryAdmissionError, psycopg.Error):
            return None
        if not message:
            return None
        return message, runtime

    def _settle_reservation(self, caller: CallerContext, run_id: UUID) -> None:
        """True-up the run reservation once on a terminal event.

        Args:
            caller: Owner.
            run_id: Run whose reservation should settle.

        Side Effects:
            Calls ``true_up_query_reservation`` at most once per run in
            this process. No-ops without a DSN or reservation id.
        """

        if not self._postgres_url or run_id in self._settled_run_ids:
            return
        try:
            record = self._store.get_authorized_run(caller, run_id=run_id)
        except QueryAdmissionError:
            return
        reservation_id = record.reservation_id
        if reservation_id is None:
            self._settled_run_ids.add(run_id)
            return
        try:
            with psycopg.connect(self._postgres_url) as connection:
                connection.execute("SET ROLE app_api")
                true_up_query_reservation(
                    connection, caller=caller, reservation_id=reservation_id
                )
                connection.commit()
            self._settled_run_ids.add(run_id)
        except (QueryAdmissionError, psycopg.Error):
            LOGGER.info(
                "reservation true-up skipped",
                extra={
                    "event": "sse.reservation_true_up_failed",
                    "run_id": str(run_id),
                },
            )

    def _emit_worker_unavailable(self, caller: CallerContext, run_id: UUID) -> None:
        """Persist schema then a sanitized terminal when this process cannot run.

        Allowed only for true orphans: ``pending`` with no startable input on
        this process. Never persist ``worker_unavailable`` while status is
        ``running`` (another replica may still complete the run).

        Args:
            caller: Owner.
            run_id: Run id.
        """

        try:
            record = self._store.get_authorized_run(caller, run_id=run_id)
        except QueryAdmissionError:
            return
        if record.status in _NON_STARTABLE_STATUSES:
            return
        self._ensure_schema(caller, run_id)
        if not self._has_terminal(caller, run_id):
            self._append(caller, run_id, "error", {"code": "worker_unavailable"})

    def _append(
        self,
        caller: CallerContext,
        run_id: UUID,
        event_type: str,
        payload: dict[str, object],
    ) -> PersistedRunEvent | None:
        """Persist one event. Invalid drafts become a sanitized error.

        Args:
            caller: Owner.
            run_id: Run id.
            event_type: Allow-listed type.
            payload: Candidate payload.

        Returns:
            Persisted row, or None when append is rejected after sanitizing.
        """

        if event_type == "heartbeat" and self._has_terminal(caller, run_id):
            return None
        try:
            persisted = self._store.append(
                caller,
                run_id=run_id,
                event_type=event_type,
                payload=payload,
            )
        except ValueError:
            LOGGER.info(
                "rejected sse payload",
                extra={"event": "sse.payload_rejected", "sse_event_type": event_type},
            )
            if event_type == "error":
                return None
            try:
                persisted = self._store.append(
                    caller,
                    run_id=run_id,
                    event_type="error",
                    payload={"code": "run_failed"},
                )
            except (QueryAdmissionError, ValueError):
                return None
        except QueryAdmissionError:
            return None
        if persisted is not None and persisted.event_type in TERMINAL_SSE_EVENT_TYPES:
            self._settle_reservation(caller, run_id)
        return persisted

    def _has_terminal(self, caller: CallerContext, run_id: UUID) -> bool:
        """Return whether a terminal event is already persisted.

        Args:
            caller: Owner.
            run_id: Run id.

        Returns:
            True when a terminal event exists.
        """

        events = self._store.list_after(caller, run_id=run_id, after=0)
        return any(item.event_type in TERMINAL_SSE_EVENT_TYPES for item in events)

    async def _replay(
        self, caller: CallerContext, run_id: UUID, after: int
    ) -> AsyncIterator[tuple[str, int, bool]]:
        """Yield framed events after ``after``.

        Args:
            caller: Owner.
            run_id: Run id.
            after: Exclusive cursor.

        Yields:
            Frame text, new cursor, and whether the event is terminal.
        """

        for event in self._store.list_after(caller, run_id=run_id, after=after):
            frame = format_sse_event(
                sequence=event.sequence,
                event_type=event.event_type,
                payload=event.payload,
            )
            terminal = event.event_type in TERMINAL_SSE_EVENT_TYPES
            yield frame, event.sequence, terminal

    async def _cooperative_cancel(self, live: LiveQueryRun) -> None:
        """Give the executor a short cleanup window, then hard-cancel.

        Args:
            live: Process handle whose cancel event is already set.

        Side Effects:
            Cancels ``executor_task`` only when it is still running after
            ``CANCEL_GRACE_SECONDS``. Marks the handle terminal.
        """

        executor = live.executor_task
        if executor is None or executor.done():
            live.terminal = True
            return
        try:
            await asyncio.wait_for(
                asyncio.shield(executor), timeout=CANCEL_GRACE_SECONDS
            )
        except TimeoutError:
            if not executor.done():
                executor.cancel()
                try:
                    await executor
                except asyncio.CancelledError:
                    pass
        except asyncio.CancelledError:
            if not executor.done():
                try:
                    await executor
                except asyncio.CancelledError:
                    pass
        live.terminal = True

    def _cancel_tasks(self, live: LiveQueryRun) -> None:
        """Cancel heartbeat and executor tasks for a finished run.

        Args:
            live: Process handle.
        """

        for task in (live.heartbeat_task, live.executor_task):
            if task is not None and not task.done():
                task.cancel()


def wants_event_stream(accept: str | None) -> bool:
    """Return whether ``Accept`` asks for SSE.

    Args:
        accept: Accept header.

    Returns:
        True when ``text/event-stream`` is present.
    """

    if accept is None:
        return False
    return "text/event-stream" in accept.lower()


def resume_after_sequence(after: int, last_event_id: str | None) -> int:
    """Combine ``after`` with SSE ``Last-Event-ID``.

    Args:
        after: Query parameter. ``0`` means from the start unless Last-Event-ID
            is higher.
        last_event_id: Optional SSE reconnect header.

    Returns:
        Exclusive cursor. Invalid Last-Event-ID values are ignored.
    """

    header_value = 0
    if last_event_id is not None and last_event_id.strip().isdigit():
        header_value = int(last_event_id.strip())
    return max(after, header_value)


def sse_streaming_response(frames: AsyncIterator[str]) -> StreamingResponse:
    """Build a ``text/event-stream`` response with no-buffering headers.

    Args:
        frames: Persist-then-flush iterator.

    Returns:
        StreamingResponse whose headers win over middleware ``setdefault``.
    """

    return StreamingResponse(
        frames,
        media_type="text/event-stream",
        headers=SSE_RESPONSE_HEADERS,
    )


def default_executor_factory() -> QueryRunExecutor:
    """Return the production LangGraph executor.

    Returns:
        LangGraph-backed executor. Import-safe until ``execute`` runs.
    """

    return LangGraphQueryRunExecutor()
