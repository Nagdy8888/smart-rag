"""Admitted-run ownership, readability, and cancel notification."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from smart_rag_core.query_admission.context import AuthorizedRuntimeContext
from smart_rag_core.query_admission.exceptions import QueryAdmissionError
from smart_rag_core.query_admission.service import QueryRunRecord
from smart_rag_core.security.identity import CallerContext
from smart_rag_core.sse.store import PersistedRunEvent, RunEventStore

from smart_rag_api.services.sse.registry import LiveQueryRun, QueryRunRegistry


class RunAccessMixin:
    """Mixin: register admitted runs, authorize resume, and signal cancel."""

    _store: RunEventStore
    _registry: QueryRunRegistry

    if TYPE_CHECKING:

        def _has_terminal(self, caller: CallerContext, run_id: UUID) -> bool:
            """Return whether a terminal event exists. Provided by ReplayCancelMixin."""

            ...

        def _append(
            self,
            caller: CallerContext,
            run_id: UUID,
            event_type: str,
            payload: dict[str, object],
        ) -> PersistedRunEvent | None:
            """Persist one catalog event. Provided by EventAppendMixin."""

            ...

        async def _cooperative_cancel(self, live: LiveQueryRun) -> None:
            """Finish a live executor after cancel. Provided by ReplayCancelMixin."""

            ...

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
