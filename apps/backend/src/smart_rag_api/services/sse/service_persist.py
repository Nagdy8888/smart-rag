"""SSE store append, replay, settlement, and cooperative cancel."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncIterator
from uuid import UUID

import psycopg
from smart_rag_core.query_admission.context import AuthorizedRuntimeContext
from smart_rag_core.query_admission.exceptions import QueryAdmissionError
from smart_rag_core.query_admission.service import (
    load_query_run_runtime,
    true_up_query_reservation,
)
from smart_rag_core.security.identity import CallerContext
from smart_rag_core.sse.catalog import TERMINAL_SSE_EVENT_TYPES
from smart_rag_core.sse.framing import format_sse_event
from smart_rag_core.sse.store import PersistedRunEvent, RunEventStore, sqlstate_of

from smart_rag_api.services.sse.constants import (
    CANCEL_GRACE_SECONDS,
    NON_STARTABLE_STATUSES,
)
from smart_rag_api.services.sse.registry import LiveQueryRun

LOGGER = logging.getLogger(__name__)


class SsePersistMixin:
    """Mixin: durable event append, resume replay, and reservation true-up."""

    _store: RunEventStore
    _postgres_url: str | None
    _settled_run_ids: set[UUID]
    _sse_schema_version: str

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
        if record.status in NON_STARTABLE_STATUSES:
            return
        self._ensure_schema(caller, run_id)
        if not self._has_terminal(caller, run_id):
            self._append(caller, run_id, "error", {"code": "worker_unavailable"})

    def _log_append_failure(
        self,
        *,
        run_id: UUID,
        event_type: str,
        exc: BaseException,
        elapsed_seconds: float,
    ) -> None:
        """Log one sanitized append failure without secrets or payloads.

        Args:
            run_id: Run whose event failed to persist.
            event_type: Allow-listed type that was attempted.
            exc: Admission or driver error. Message text is not logged.
            elapsed_seconds: Wall time spent in the store call.

        Side Effects:
            Writes one structured info record. Never logs DSNs, JWTs,
            payload bodies, or exception messages.
        """

        reason = getattr(exc, "reason", None)
        if not isinstance(reason, str) or not reason:
            reason = type(exc).__name__
        LOGGER.info(
            "sse append failed",
            extra={
                "event": "sse.append_failed",
                "run_id": str(run_id),
                "sse_event_type": event_type,
                "reason": reason[:64],
                "sqlstate": sqlstate_of(exc),
                "elapsed_seconds": round(elapsed_seconds, 3),
            },
        )

    async def _append_async(
        self,
        caller: CallerContext,
        run_id: UUID,
        event_type: str,
        payload: dict[str, object],
    ) -> PersistedRunEvent | None:
        """Persist one event off the asyncio loop.

        Heartbeat and executor orchestration must use this helper so a
        synchronous run-row lock wait cannot freeze ``astream`` or SSE
        polling. Callers still await each append before the next event so
        sequence order and exactly-one terminal stay unchanged.

        Args:
            caller: Owner.
            run_id: Run id.
            event_type: Allow-listed type.
            payload: Candidate payload.

        Returns:
            Persisted row, or None when append is rejected after sanitizing.
        """

        return await asyncio.to_thread(
            self._append, caller, run_id, event_type, payload
        )

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
            Heartbeat lock or admission failures degrade to None. Status and
            terminal admission failures keep that same None return so the
            existing executor failure path can persist a sanitized error.
        """

        if event_type == "heartbeat" and self._has_terminal(caller, run_id):
            return None
        started = time.monotonic()
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
            except (QueryAdmissionError, ValueError) as exc:
                self._log_append_failure(
                    run_id=run_id,
                    event_type="error",
                    exc=exc,
                    elapsed_seconds=time.monotonic() - started,
                )
                return None
        except QueryAdmissionError as exc:
            self._log_append_failure(
                run_id=run_id,
                event_type=event_type,
                exc=exc,
                elapsed_seconds=time.monotonic() - started,
            )
            return None
        if persisted.event_type in TERMINAL_SSE_EVENT_TYPES:
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
