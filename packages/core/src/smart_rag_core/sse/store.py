"""Run-event persistence protocol, in-memory store, and Postgres RPC wrappers."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from threading import Lock, RLock
from typing import NoReturn, Protocol
from uuid import UUID

import psycopg
from psycopg.types.json import Json

from smart_rag_core.query_admission.exceptions import QueryAdmissionError
from smart_rag_core.query_admission.service import QueryRunRecord
from smart_rag_core.security.identity import CallerContext
from smart_rag_core.sse.catalog import TERMINAL_SSE_EVENT_TYPES
from smart_rag_core.sse.sanitize import as_json_object, validate_sse_payload

_REASON_PREFIX = "query_admission:"


def _raise_store_error(exc: BaseException) -> NoReturn:
    """Map a Postgres error to ``QueryAdmissionError`` and raise.

    Args:
        exc: Driver or database error.

    Raises:
        QueryAdmissionError: Always.
    """

    message = str(exc)
    reason = "database_rejected"
    if _REASON_PREFIX in message:
        start = message.find(_REASON_PREFIX) + len(_REASON_PREFIX)
        tail = message[start:].split()[0].strip("\"'")
        reason = tail.split("\n")[0]
    raise QueryAdmissionError(reason) from exc


_TERMINAL_STATUS = {
    "completed": "completed",
    "cancelled": "cancelled",
    "error": "failed",
    "partial": "partial",
}


@dataclass(frozen=True, slots=True)
class PersistedRunEvent:
    """One durably sequenced run event.

    Attributes:
        run_id: Owning run.
        sequence: Monotonic run-local id.
        event_type: Allow-listed type.
        payload: Sanitized JSON object.
        created_at: Insert timestamp.
    """

    run_id: UUID
    sequence: int
    event_type: str
    payload: dict[str, object]
    created_at: datetime


class RunEventStore(Protocol):
    """Persist and replay run events. Implementations must sequence before yield."""

    def register_run(
        self,
        *,
        caller: CallerContext,
        record: QueryRunRecord,
        conversation_deleted: bool = False,
    ) -> None:
        """Remember run ownership for later attach.

        Args:
            caller: Owner used for access checks.
            record: Admitted run.
            conversation_deleted: Tombstone flag.
        """

        raise NotImplementedError

    def mark_conversation_deleted(self, *, conversation_id: UUID) -> None:
        """Tombstone a conversation so resume denies immediately.

        Args:
            conversation_id: Conversation to tombstone.
        """

        raise NotImplementedError

    def mark_running(self, caller: CallerContext, *, run_id: UUID) -> None:
        """Transition pending → running on first executor attach.

        Args:
            caller: Owner.
            run_id: Run to mark.
        """

        raise NotImplementedError

    def get_authorized_run(
        self, caller: CallerContext, *, run_id: UUID
    ) -> QueryRunRecord:
        """Return an owned run or raise ``not_found``.

        Args:
            caller: Caller.
            run_id: Run id.

        Returns:
            Run record.

        Raises:
            QueryAdmissionError: Missing, foreign, or tombstoned conversation.
        """

        raise NotImplementedError

    def append(
        self,
        caller: CallerContext,
        *,
        run_id: UUID,
        event_type: str,
        payload: dict[str, object],
    ) -> PersistedRunEvent:
        """Validate, allocate the next sequence, and persist before return.

        Args:
            caller: Owner.
            run_id: Run id.
            event_type: Allow-listed type.
            payload: Candidate payload.

        Returns:
            Persisted event with sequence.

        Raises:
            QueryAdmissionError: Authorization or tombstone failure.
            ValueError: Unknown type or invalid payload.
        """

        raise NotImplementedError

    def list_after(
        self, caller: CallerContext, *, run_id: UUID, after: int
    ) -> tuple[PersistedRunEvent, ...]:
        """Return events with sequence strictly greater than ``after``.

        Args:
            caller: Owner.
            run_id: Run id.
            after: Exclusive lower bound. ``0`` means from the start.

        Returns:
            Ordered events.

        Raises:
            QueryAdmissionError: Missing, foreign, or tombstoned.
        """

        raise NotImplementedError


def _empty_persisted_events() -> list[PersistedRunEvent]:
    """Return an empty event list for a new in-memory run.

    Returns:
        Empty list.
    """

    return []


@dataclass
class _MemoryRun:
    """In-memory run metadata for HTTP tests that inject this store."""

    record: QueryRunRecord
    conversation_deleted: bool = False
    events: list[PersistedRunEvent] = field(default_factory=_empty_persisted_events)


class MemoryRunEventStore:
    """Process-local store used by the same SSE service as Postgres tests."""

    def __init__(self) -> None:
        """Create an empty store."""

        self._runs: dict[UUID, _MemoryRun] = {}
        self._lock = Lock()

    def register_run(
        self,
        *,
        caller: CallerContext,
        record: QueryRunRecord,
        conversation_deleted: bool = False,
    ) -> None:
        """Remember one admitted run.

        Args:
            caller: Owner. Must match ``record.creator_user_id``.
            record: Admitted run.
            conversation_deleted: Tombstone flag.
        """

        del caller
        with self._lock:
            existing = self._runs.get(record.run_id)
            if existing is None:
                self._runs[record.run_id] = _MemoryRun(
                    record=record,
                    conversation_deleted=conversation_deleted,
                )
                return
            existing.record = record
            existing.conversation_deleted = conversation_deleted

    def mark_conversation_deleted(self, *, conversation_id: UUID) -> None:
        """Tombstone every run on the conversation.

        Args:
            conversation_id: Conversation id.
        """

        with self._lock:
            for item in self._runs.values():
                if item.record.conversation_id == conversation_id:
                    item.conversation_deleted = True

    def mark_running(self, caller: CallerContext, *, run_id: UUID) -> None:
        """Set status to running when still pending.

        Args:
            caller: Owner.
            run_id: Run id.
        """

        with self._lock:
            item = self._require(caller, run_id)
            if item.record.status == "pending":
                item.record = QueryRunRecord(
                    run_id=item.record.run_id,
                    conversation_id=item.record.conversation_id,
                    creator_user_id=item.record.creator_user_id,
                    status="running",
                    reservation_id=item.record.reservation_id,
                    created_at=item.record.created_at,
                )

    def get_authorized_run(
        self, caller: CallerContext, *, run_id: UUID
    ) -> QueryRunRecord:
        """Return an owned run.

        Args:
            caller: Caller.
            run_id: Run id.

        Returns:
            Run record.

        Raises:
            QueryAdmissionError: ``not_found`` for missing/foreign/tombstoned.
        """

        with self._lock:
            return self._require(caller, run_id).record

    def append(
        self,
        caller: CallerContext,
        *,
        run_id: UUID,
        event_type: str,
        payload: dict[str, object],
    ) -> PersistedRunEvent:
        """Append one validated event with the next sequence.

        Args:
            caller: Owner.
            run_id: Run id.
            event_type: Allow-listed type.
            payload: Candidate payload.

        Returns:
            Persisted event.

        Raises:
            QueryAdmissionError: Access failure.
            ValueError: Invalid type or payload.
        """

        validated = validate_sse_payload(event_type, payload)
        with self._lock:
            item = self._require(caller, run_id)
            if event_type in TERMINAL_SSE_EVENT_TYPES:
                existing_terminal = next(
                    (
                        event
                        for event in item.events
                        if event.event_type in TERMINAL_SSE_EVENT_TYPES
                    ),
                    None,
                )
                if existing_terminal is not None:
                    return existing_terminal
            sequence = (item.events[-1].sequence + 1) if item.events else 1
            persisted = PersistedRunEvent(
                run_id=run_id,
                sequence=sequence,
                event_type=event_type,
                payload=validated,
                created_at=datetime.now(tz=UTC),
            )
            item.events.append(persisted)
            if event_type in _TERMINAL_STATUS:
                item.record = QueryRunRecord(
                    run_id=item.record.run_id,
                    conversation_id=item.record.conversation_id,
                    creator_user_id=item.record.creator_user_id,
                    status=_TERMINAL_STATUS[event_type],
                    reservation_id=item.record.reservation_id,
                    created_at=item.record.created_at,
                )
            return persisted

    def list_after(
        self, caller: CallerContext, *, run_id: UUID, after: int
    ) -> tuple[PersistedRunEvent, ...]:
        """Replay events after ``after``.

        Args:
            caller: Owner.
            run_id: Run id.
            after: Exclusive lower bound.

        Returns:
            Ordered events.

        Raises:
            QueryAdmissionError: Access failure.
        """

        with self._lock:
            item = self._require(caller, run_id)
            return tuple(event for event in item.events if event.sequence > after)

    def _require(self, caller: CallerContext, run_id: UUID) -> _MemoryRun:
        """Return the owned in-memory run or raise ``not_found``.

        Args:
            caller: Caller.
            run_id: Run id.

        Returns:
            Memory row.

        Raises:
            QueryAdmissionError: Missing, foreign, or tombstoned.
        """

        item = self._runs.get(run_id)
        if item is None:
            raise QueryAdmissionError("not_found")
        if item.conversation_deleted:
            raise QueryAdmissionError("not_found")
        if str(item.record.creator_user_id) != caller.user_id:
            raise QueryAdmissionError("not_found")
        return item


class PostgresRunEventStore:
    """``app.append_run_event`` / ``app.list_run_events_after`` wrappers."""

    def __init__(self, postgres_url: str) -> None:
        """Store the app_api DSN.

        Args:
            postgres_url: Postgres URL. No connection is opened here.
        """

        self._postgres_url = postgres_url
        self._connection: psycopg.Connection | None = None
        self._connection_lock = RLock()

    @contextmanager
    def _transaction(self) -> Iterator[psycopg.Connection]:
        """Yield one serialized transaction on a reusable database session.

        Reusing the API session avoids a TLS and hosted-pooler handshake for
        every SSE frame. Automatic prepared statements remain disabled because
        the configured Supabase transaction pooler can switch server sessions.
        The lock prevents concurrent executor, heartbeat, and replay operations
        from sharing a Psycopg transaction.

        Yields:
            Open connection with ``app_api`` selected for this transaction.

        Raises:
            psycopg.Error: Connection, role, RPC, commit, or rollback failure.
        """

        with self._connection_lock:
            if self._connection is None or self._connection.closed:
                self._connection = psycopg.connect(
                    self._postgres_url,
                    prepare_threshold=None,
                )
            connection = self._connection
            try:
                connection.execute("SET ROLE app_api")
                yield connection
                connection.commit()
            except BaseException:
                connection.rollback()
                raise

    def close(self) -> None:
        """Close the reusable database session.

        Side Effects:
            Waits for an active store transaction, then closes its connection.
            Calling this method more than once is safe.
        """

        with self._connection_lock:
            if self._connection is not None:
                self._connection.close()
                self._connection = None

    def register_run(
        self,
        *,
        caller: CallerContext,
        record: QueryRunRecord,
        conversation_deleted: bool = False,
    ) -> None:
        """Postgres ownership is the ``app.runs`` row. No extra registration.

        Args:
            caller: Unused.
            record: Unused.
            conversation_deleted: Unused.
        """

        del caller, record, conversation_deleted

    def mark_conversation_deleted(self, *, conversation_id: UUID) -> None:
        """Tombstones are written on ``app.conversations``. Packet 7 owns delete.

        Args:
            conversation_id: Unused.
        """

        del conversation_id

    def mark_running(self, caller: CallerContext, *, run_id: UUID) -> None:
        """Call ``app.heartbeat_query_run`` so pending becomes running.

        Args:
            caller: Owner.
            run_id: Run id.

        Raises:
            QueryAdmissionError: When the RPC rejects the caller.
        """

        from smart_rag_core.query_admission.service import heartbeat_query_run

        with self._transaction() as connection:
            heartbeat_query_run(connection, caller=caller, run_id=run_id)

    def get_authorized_run(
        self, caller: CallerContext, *, run_id: UUID
    ) -> QueryRunRecord:
        """Fetch via ``app.get_query_run``.

        Args:
            caller: Owner.
            run_id: Run id.

        Returns:
            Run record.

        Raises:
            QueryAdmissionError: Missing/foreign/tombstoned.
        """

        from smart_rag_core.query_admission.service import get_query_run

        with self._transaction() as connection:
            return get_query_run(connection, caller=caller, run_id=run_id)

    def append(
        self,
        caller: CallerContext,
        *,
        run_id: UUID,
        event_type: str,
        payload: dict[str, object],
    ) -> PersistedRunEvent:
        """Persist through ``app.append_run_event``.

        Args:
            caller: Owner.
            run_id: Run id.
            event_type: Allow-listed type.
            payload: Candidate payload.

        Returns:
            Persisted event.

        Raises:
            QueryAdmissionError: RPC failure.
            ValueError: Invalid type or payload.
        """

        validated = validate_sse_payload(event_type, payload)
        try:
            with self._transaction() as connection:
                row = connection.execute(
                    """
                    SELECT run_id, sequence, event_type, payload, created_at
                    FROM app.append_run_event(
                        %s::uuid, %s::text, %s::bigint, %s::uuid, %s::text, %s::jsonb
                    )
                    """,
                    (
                        caller.user_id,
                        caller.rpc_role(),
                        caller.rpc_authorization_version(),
                        run_id,
                        event_type,
                        Json(validated),
                    ),
                ).fetchone()
        except psycopg.Error as exc:
            _raise_store_error(exc)
        if row is None:
            raise QueryAdmissionError("append_returned_no_row")
        return PersistedRunEvent(
            run_id=row[0],
            sequence=int(row[1]),
            event_type=str(row[2]),
            payload=as_json_object(row[3]),
            created_at=row[4],
        )

    def list_after(
        self, caller: CallerContext, *, run_id: UUID, after: int
    ) -> tuple[PersistedRunEvent, ...]:
        """Replay through ``app.list_run_events_after``.

        Args:
            caller: Owner.
            run_id: Run id.
            after: Exclusive lower bound.

        Returns:
            Ordered events.

        Raises:
            QueryAdmissionError: Access failure.
        """

        try:
            with self._transaction() as connection:
                rows = connection.execute(
                    """
                    SELECT run_id, sequence, event_type, payload, created_at
                    FROM app.list_run_events_after(
                        %s::uuid, %s::text, %s::bigint, %s::uuid, %s::bigint
                    )
                    """,
                    (
                        caller.user_id,
                        caller.rpc_role(),
                        caller.rpc_authorization_version(),
                        run_id,
                        after,
                    ),
                ).fetchall()
        except psycopg.Error as exc:
            _raise_store_error(exc)
        events: list[PersistedRunEvent] = []
        for row in rows:
            events.append(
                PersistedRunEvent(
                    run_id=row[0],
                    sequence=int(row[1]),
                    event_type=str(row[2]),
                    payload=as_json_object(row[3]),
                    created_at=row[4],
                )
            )
        return tuple(events)
