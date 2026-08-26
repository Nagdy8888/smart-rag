"""Query-run executors: fixture drafts and the compiled LangGraph adapter."""

from __future__ import annotations

import asyncio
import inspect
import logging
from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime
from typing import Any, Protocol, cast

from smart_rag_core.query_admission.context import AuthorizedRuntimeContext

from smart_rag_api.services.query_sse_mapping import (
    QuerySseMapper,
    assert_catalog_event,
)
from smart_rag_api.services.sse.chunks import (
    token_counts_from_update,
    updates_mapping_from_chunk,
)
from smart_rag_api.services.sse.executor_support import LangGraphExecutorSupport

LOGGER = logging.getLogger(__name__)


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


class LangGraphQueryRunExecutor(LangGraphExecutorSupport):
    """Production executor: compiled query graph with optional checkpoints."""

    def __init__(self) -> None:
        """Create an executor that opens checkpointer/store lazily.

        Side Effects:
            None at construction. First ``execute`` may open a Postgres pool
            and construct process Hybrid/gateway bindings.
            ``PostgresSaver.setup()``, ``AsyncPostgresSaver.setup()``, and
            ``PostgresStore.setup()`` are never called.
        """

        self._async_holder = None
        self._store = None
        self._bindings = None
        self._compiled = None
        self._compiled_checkpointer_id: int | None = None
        self.compile_count = 0
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

    def _compiled_query_graph(self, checkpointer: object) -> object:
        """Compile the static topology once per executor and checkpointer.

        Args:
            checkpointer: Process async saver, or ``None``.

        Returns:
            Compiled query graph. Per-run deps are not captured.
        """

        marker = id(checkpointer) if checkpointer is not None else None
        if self._compiled is not None and self._compiled_checkpointer_id == marker:
            return self._compiled
        from smart_rag_agents.query.graph import compile_query_graph

        self._compiled = compile_query_graph(checkpointer=checkpointer)
        self._compiled_checkpointer_id = marker
        self.compile_count += 1
        return self._compiled

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

        from smart_rag_agents.query.deps import QueryGraphContext
        from smart_rag_agents.query.graph import pending_query_state

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
            compiled = self._compiled_query_graph(checkpointer)
            state = pending_query_state(
                authorized_runtime=context.model_dump(mode="json"),
                user_query=message,
            )
            config: dict[str, object] = {
                "recursion_limit": context.recursion_limit,
                "configurable": {"thread_id": str(context.conversation_id)},
            }
            stream_method: Callable[..., AsyncIterator[object]] = compiled.astream  # type: ignore[reportUnknownMemberType]
            stream_iter = stream_method(
                state,
                cast(Any, config),
                stream_mode="updates",
                context=QueryGraphContext(deps=deps),
            )
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
                typed_chunk = updates_mapping_from_chunk(raw_chunk)
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
                            prompt_tokens, completion_tokens = token_counts_from_update(
                                typed_update
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
                        event_prompt, event_completion = token_counts_from_update(
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
                                settings,
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
                            settings,
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
