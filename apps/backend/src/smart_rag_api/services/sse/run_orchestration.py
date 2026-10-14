"""Start-once executor and heartbeat task helpers."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING
from uuid import UUID

from smart_rag_core.query_admission.context import AuthorizedRuntimeContext
from smart_rag_core.query_admission.exceptions import QueryAdmissionError
from smart_rag_core.query_admission.service import QueryRunRecord
from smart_rag_core.security.identity import CallerContext
from smart_rag_core.sse.store import PersistedRunEvent, RunEventStore

from smart_rag_api.services.sse.executors import QueryRunExecutor
from smart_rag_api.services.sse.registry import LiveQueryRun, QueryRunRegistry
from smart_rag_api.services.sse.run_executor import RunExecutorMixin
from smart_rag_api.services.sse.run_heartbeat import RunHeartbeatMixin

LOGGER = logging.getLogger(__name__)


class RunOrchestrationMixin(RunExecutorMixin, RunHeartbeatMixin):
    """Mixin: start the graph once and persist executor plus heartbeat drafts."""

    _store: RunEventStore
    _registry: QueryRunRegistry
    _executor: QueryRunExecutor
    _postgres_url: str | None
    _heartbeat_interval_seconds: float

    if TYPE_CHECKING:

        def _ensure_schema(self, caller: CallerContext, run_id: UUID) -> None:
            """Persist the first schema event. Provided by RunSettlementMixin."""

        def _load_durable_start(
            self, caller: CallerContext, run_id: UUID
        ) -> tuple[str, AuthorizedRuntimeContext] | None:
            """Load durable start input. Provided by RunSettlementMixin."""

        def _emit_worker_unavailable(self, caller: CallerContext, run_id: UUID) -> None:
            """Persist worker_unavailable. Provided by RunSettlementMixin."""

        def _cancel_tasks(self, live: LiveQueryRun) -> None:
            """Cancel live tasks. Provided by ReplayCancelMixin."""

        def _has_terminal(self, caller: CallerContext, run_id: UUID) -> bool:
            """Return whether a terminal event exists. Provided by ReplayCancelMixin."""

            ...

        async def _append_async(
            self,
            caller: CallerContext,
            run_id: UUID,
            event_type: str,
            payload: dict[str, object],
        ) -> PersistedRunEvent | None:
            """Persist one catalog event off the loop. Provided by EventAppendMixin."""

            ...

    async def start_admitted(
        self,
        caller: CallerContext,
        context: AuthorizedRuntimeContext,
    ) -> None:
        """Start the graph at admission, before a client attaches.

        ``remember_admitted`` has already stored the message. A later attach
        only replays events because ``_start_once`` is idempotent.

        Args:
            caller: Owner.
            context: Fresh admission context.
        """

        record = QueryRunRecord(
            run_id=context.run_id,
            conversation_id=context.conversation_id,
            creator_user_id=context.user_id,
            status=context.status,
            reservation_id=context.reservation_id,
            created_at=None,
        )
        live = self._registry.get_or_create(context.run_id)
        await self._start_once(caller, record, live, context)

    async def _start_once(
        self,
        caller: CallerContext,
        record: QueryRunRecord,
        live: LiveQueryRun,
        context: AuthorizedRuntimeContext | None,
    ) -> None:
        """Start the executor at most once in this process.

        ``live.started`` is set before the first ``await`` so two attaches
        racing on the same run cannot both start it. Store and durable-input
        calls run on worker threads. When a cancel arrives during those
        calls, the executor is not started (the cancel request already
        persisted ``cancelled``). Durable heartbeats are owned only by
        ``_run_heartbeat``.

        Args:
            caller: Owner.
            record: Current run row.
            live: Process handle.
            context: Fresh admit context when the POST is still in-flight.
        """

        if live.started:
            return
        live.started = True
        await asyncio.to_thread(self._ensure_schema, caller, record.run_id)
        live.notify_appended()
        try:
            await asyncio.to_thread(
                self._store.mark_running, caller, run_id=record.run_id
            )
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
            loaded = await asyncio.to_thread(
                self._load_durable_start, caller, record.run_id
            )
            if loaded is not None:
                loaded_message, loaded_runtime = loaded
                if not message:
                    message = loaded_message
                if runtime is None:
                    runtime = loaded_runtime
        if live.cancel_event.is_set():
            live.terminal = True
            live.notify_appended()
            return
        live.executor_task = asyncio.create_task(
            self._run_executor(caller, record, live, message, runtime)
        )
        live.heartbeat_task = asyncio.create_task(
            self._run_heartbeat(caller, record.run_id, live)
        )
