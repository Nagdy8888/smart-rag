"""Persist-then-flush SSE attach orchestration."""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator
from uuid import UUID

from smart_rag_core.query_admission.context import AuthorizedRuntimeContext
from smart_rag_core.query_admission.exceptions import QueryAdmissionError
from smart_rag_core.security.identity import CallerContext
from smart_rag_core.security.profile_snapshot import (
    is_session_revoked,
    load_profile_snapshot,
)
from smart_rag_core.sse.catalog import HEARTBEAT_INTERVAL_SECONDS
from smart_rag_core.sse.store import RunEventStore

from smart_rag_api.services.sse.constants import (
    ATTACH_IDLE_POLL_SECONDS,
    NON_STARTABLE_STATUSES,
    POLL_SECONDS,
)
from smart_rag_api.services.sse.executors import QueryRunExecutor
from smart_rag_api.services.sse.registry import QueryRunRegistry
from smart_rag_api.services.sse.run_access import RunAccessMixin
from smart_rag_api.services.sse.run_orchestration import RunOrchestrationMixin
from smart_rag_api.services.sse.service_persist import SsePersistMixin


class SseStreamService(RunAccessMixin, RunOrchestrationMixin, SsePersistMixin):
    """Persist-then-flush SSE attach for POST fetch and GET resume."""

    def __init__(
        self,
        *,
        store: RunEventStore,
        registry: QueryRunRegistry,
        executor: QueryRunExecutor,
        sse_schema_version: str,
        heartbeat_interval_seconds: float = HEARTBEAT_INTERVAL_SECONDS,
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
        self._identity_checked_at: float | None = None
        self._identity_checked_caller: CallerContext | None = None

    def _assert_stream_identity(self, caller: CallerContext) -> None:
        """Fail closed before delivery if the original bearer lost authority."""
        if caller.token_expires_at is None:
            # Only explicitly injected test identities lack verified JWT dates.
            return
        if time.time() >= caller.token_expires_at:
            raise QueryAdmissionError("session_expired")
        now = time.monotonic()
        if (
            self._identity_checked_at is not None
            and self._identity_checked_caller == caller
            and now - self._identity_checked_at < 1.0
        ):
            return
        if self._postgres_url is None:
            raise QueryAdmissionError("identity_store_unavailable")
        snapshot = load_profile_snapshot(self._postgres_url, user_id=caller.user_id)
        if (
            snapshot is None
            or snapshot.disabled
            or snapshot.role != caller.role
            or snapshot.authorization_version != caller.authorization_version
            or is_session_revoked(
                self._postgres_url,
                session_id=caller.session_id,
                issued_at=caller.token_issued_at,
                session_revoked_at=snapshot.session_revoked_at,
            )
        ):
            raise QueryAdmissionError("session_revoked")
        if time.time() >= caller.token_expires_at:
            raise QueryAdmissionError("session_expired")
        self._identity_checked_at = time.monotonic()
        self._identity_checked_caller = caller

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
            SSE frames. Persistence happens before each yield. Store reads
            run on worker threads; a live run wakes this loop on each append.

        Raises:
            QueryAdmissionError: Missing, foreign, or tombstoned run.
        """

        await asyncio.to_thread(self.assert_readable, caller, run_id=run_id)
        cursor = after
        async for frame, sequence, terminal in self._replay(caller, run_id, cursor):
            cursor = sequence
            yield frame
            if terminal:
                return

        record = await asyncio.to_thread(self.assert_readable, caller, run_id=run_id)
        live = self._registry.get(run_id)
        if live is None and record.status in NON_STARTABLE_STATUSES:
            async for frame, sequence, terminal in self._replay(caller, run_id, cursor):
                cursor = sequence
                yield frame
                if terminal:
                    return
            return

        if live is None and record.status == "pending":
            if context is None and not self._registry.has_input(run_id):
                loaded = await asyncio.to_thread(
                    self._load_durable_start, caller, run_id
                )
                if loaded is None:
                    await asyncio.to_thread(
                        self._emit_worker_unavailable, caller, run_id
                    )
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
            await self._start_once(caller, record, live, context)

        if live is not None and not live.started and record.status == "pending":
            await self._start_once(caller, record, live, context)

        while True:
            handle = self._registry.get(run_id)
            seen = handle.append_generation if handle is not None else 0
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
                await asyncio.sleep(POLL_SECONDS)
                continue
            await handle.wait_appended(seen, ATTACH_IDLE_POLL_SECONDS)
