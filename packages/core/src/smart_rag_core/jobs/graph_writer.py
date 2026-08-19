"""Durable graph-writer lease and session advisory-lock helpers.

The vendor schema-migration lock is never treated as the application writer
lock. Callers must not hold a database transaction across model extraction.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from typing import Final
from uuid import UUID, uuid4

import psycopg
from psycopg.rows import dict_row

from smart_rag_core.jobs.exceptions import GraphWriterLostError, JobLeaseError
from smart_rag_core.jobs.limits import GRAPH_POINTER_ID
from smart_rag_core.retrieval.graph import (
    DEFAULT_GRAPH_WORKSPACE,
    graph_chunker_config_snapshot,
)
from smart_rag_core.schema.enums import GraphWorkspaceState

ADVISORY_LOCK_NAMESPACE: Final[str] = "smart-rag-graph-writer-v1"


def graph_advisory_lock_keys(workspace_key: str) -> tuple[int, int]:
    """Derive a stable session advisory-lock key pair from a workspace key.

    Keys are positive signed int4 values so ``pg_locks`` lookups stay simple.
    This is not the LightRAG vendor schema-migration lock.

    Args:
        workspace_key: Application workspace identifier such as
            ``company_default``.

    Returns:
        Two positive int4 advisory-lock keys.

    Raises:
        ValueError: If ``workspace_key`` is empty.
    """

    stripped = workspace_key.strip()
    if not stripped:
        raise ValueError("workspace_key_empty")
    digest = hashlib.sha256(f"{ADVISORY_LOCK_NAMESPACE}:{stripped}".encode()).digest()
    key_one = int.from_bytes(digest[0:4], "big") & 0x7FFFFFFF
    key_two = int.from_bytes(digest[4:8], "big") & 0x7FFFFFFF
    if key_one == 0 and key_two == 0:
        key_two = 1
    return key_one, key_two


def heartbeat_graph_writer_lease(
    connection: psycopg.Connection,
    *,
    lease_owner: str,
    writer_token: str,
    lease_seconds: int,
) -> None:
    """Renew the singleton writer lease on a short-lived connection.

    Args:
        connection: ``app_worker`` connection.
        lease_owner: Worker instance identifier.
        writer_token: Token from ``occupy``.
        lease_seconds: Lease duration.

    Raises:
        GraphWriterLostError: If the writer lease cannot be renewed.

    Side Effects:
        Updates ``app.graph_writer_lease``. Caller must commit.
    """

    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT app.heartbeat_graph_writer_lease(%s, %s, %s)
            """,
            (lease_owner, writer_token, lease_seconds),
        )
        row = cursor.fetchone()
    if row is None or row[0] is not True:
        raise GraphWriterLostError("writer_lease_lost")


class GraphWriterGuard:
    """Occupy the singleton writer lease and hold a session advisory lock.

    The lock connection must stay open for the mutation duration with
    autocommit enabled so no transaction spans extraction. Lease checks use
    short-lived application transactions on a separate connection.
    """

    def __init__(
        self,
        connection: psycopg.Connection,
        *,
        lease_owner: str,
        lease_seconds: int,
        workspace_key: str = DEFAULT_GRAPH_WORKSPACE,
    ) -> None:
        """Bind the application connection used for lease RPCs.

        Args:
            connection: ``app_worker`` connection. Callers commit short
                transactions; this object never leaves a transaction open
                across provider calls.
            lease_owner: Worker instance identifier shared with job leases.
            lease_seconds: Writer and job lease duration.
            workspace_key: Workspace used to derive the advisory-lock key.
        """

        self._connection = connection
        self._lease_owner = lease_owner
        self._lease_seconds = lease_seconds
        self._workspace_key = workspace_key
        self._writer_token: str | None = None
        self._lock_keys = graph_advisory_lock_keys(workspace_key)
        self._lock_connection: psycopg.Connection | None = None

    def bind_occupied(
        self,
        *,
        writer_token: str,
        lock_connection: psycopg.Connection | None,
    ) -> None:
        """Attach an already-occupied lease token and lock connection.

        Used by heartbeat and work connections that did not call ``occupy``.

        Args:
            writer_token: Token returned by ``occupy``.
            lock_connection: Dedicated autocommit lock connection, or ``None``.
        """

        self._writer_token = writer_token
        self._lock_connection = lock_connection

    @property
    def writer_token(self) -> str:
        """Return the occupied writer-lease token.

        Returns:
            Writer token issued by ``occupy``.

        Raises:
            GraphWriterLostError: If the writer lease was never occupied.
        """

        if self._writer_token is None:
            raise GraphWriterLostError("writer_lease_not_occupied")
        return self._writer_token

    @property
    def lock_keys(self) -> tuple[int, int]:
        """Return the session advisory-lock key pair."""

        return self._lock_keys

    @property
    def workspace_key(self) -> str:
        """Return the workspace key this guard serializes."""

        return self._workspace_key

    def occupy(self, *, job_id: UUID, job_lease_token: str) -> str:
        """Validate the job lease and occupy the singleton writer lease.

        Args:
            job_id: Claimed LightRAG job identifier.
            job_lease_token: Job lease token from the claim RPC.

        Returns:
            Writer-lease token.

        Raises:
            JobLeaseError: If the job lease is invalid.
            GraphWriterLostError: If another writer holds a valid lease.

        Side Effects:
            Updates ``app.graph_writer_lease`` in the same transaction as the
            job-lease check. Caller must commit.
        """

        if not self._validate_job_lease(job_id, job_lease_token):
            raise JobLeaseError("invalid_or_expired_lease")
        token = str(uuid4())
        with self._connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT app.occupy_graph_writer_lease(%s, %s, %s)
                """,
                (self._lease_owner, token, self._lease_seconds),
            )
            row = cursor.fetchone()
        if row is None or row[0] is not True:
            raise GraphWriterLostError("writer_lease_occupied")
        self._writer_token = token
        return token

    def heartbeat(self, *, job_id: UUID, job_lease_token: str) -> None:
        """Renew both the job lease and the writer lease.

        Args:
            job_id: Claimed LightRAG job identifier.
            job_lease_token: Job lease token.

        Raises:
            GraphWriterLostError: If either lease cannot be renewed.

        Side Effects:
            Updates job and writer lease expiry. Caller must commit.
        """

        if not self._heartbeat_job(job_id, job_lease_token):
            raise GraphWriterLostError("job_lease_lost")
        if self._writer_token is None:
            raise GraphWriterLostError("writer_lease_not_occupied")
        with self._connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT app.heartbeat_graph_writer_lease(%s, %s, %s)
                """,
                (self._lease_owner, self._writer_token, self._lease_seconds),
            )
            row = cursor.fetchone()
        if row is None or row[0] is not True:
            raise GraphWriterLostError("writer_lease_lost")

    def release(self) -> None:
        """Release the writer lease when this owner still holds it.

        Side Effects:
            Clears ``app.graph_writer_lease`` owner/token when tokens match.
            Caller must commit.
        """

        if self._writer_token is None:
            return
        with self._connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT app.release_graph_writer_lease(%s, %s)
                """,
                (self._lease_owner, self._writer_token),
            )
        self._writer_token = None

    def acquire_session_lock(self, lock_connection: psycopg.Connection) -> None:
        """Acquire a session-level advisory lock on a dedicated connection.

        Args:
            lock_connection: Autocommit ``app_worker`` connection held for the
                mutation duration. Must not be the job-claim transaction.

        Raises:
            GraphWriterLostError: If ``pg_try_advisory_lock`` returns false.

        Side Effects:
            Holds ``pg_advisory_lock`` until ``release_session_lock`` or
            disconnect. Does not open a wrapping transaction.
        """

        key_one, key_two = self._lock_keys
        lock_connection.execute("SET ROLE app_worker")
        with lock_connection.cursor() as cursor:
            cursor.execute(
                "SELECT pg_try_advisory_lock(%s, %s)",
                (key_one, key_two),
            )
            row = cursor.fetchone()
        if row is None or row[0] is not True:
            raise GraphWriterLostError("advisory_lock_busy")
        self._lock_connection = lock_connection

    def release_session_lock(self) -> None:
        """Release the session advisory lock when this session holds it.

        Side Effects:
            Calls ``pg_advisory_unlock``. Closing the lock connection also
            releases the lock.
        """

        lock_connection = self._lock_connection
        if lock_connection is None or lock_connection.closed:
            self._lock_connection = None
            return
        key_one, key_two = self._lock_keys
        with lock_connection.cursor() as cursor:
            cursor.execute(
                "SELECT pg_advisory_unlock(%s, %s)",
                (key_one, key_two),
            )
        self._lock_connection = None

    def session_holds_advisory_lock(self) -> bool:
        """Return whether this backend session still holds the writer lock.

        Postgres 17 stores a two-``int4`` ``pg_advisory_lock(key1, key2)`` as
        ``pg_locks.objsubid = 2``. Older catalogs used ``1``. Accept both so
        hosted Supabase does not report ``advisory_lock_lost`` immediately
        after a successful ``pg_try_advisory_lock``.

        Returns:
            True when ``pg_locks`` shows a granted session advisory lock for
            this backend PID and key pair.
        """

        lock_connection = self._lock_connection
        if lock_connection is None or lock_connection.closed:
            return False
        key_one, key_two = self._lock_keys
        with lock_connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT EXISTS (
                  SELECT 1
                  FROM pg_catalog.pg_locks
                  WHERE locktype = 'advisory'
                    AND granted
                    AND pid = pg_backend_pid()
                    AND objsubid IN (1, 2)
                    AND classid = %s::oid
                    AND objid = %s::oid
                )
                """,
                (key_one, key_two),
            )
            row = cursor.fetchone()
        return row is not None and row[0] is True

    def verify_lock_and_lease(self, *, job_id: UUID, job_lease_token: str) -> None:
        """Fail closed when the advisory lock or either durable lease is gone.

        Args:
            job_id: Claimed LightRAG job identifier.
            job_lease_token: Job lease token.

        Raises:
            GraphWriterLostError: On lock, job-lease, or writer-lease loss.

        Side Effects:
            Runs a short job/writer lease validation transaction. Does not
            keep that transaction open.
        """

        if not self.session_holds_advisory_lock():
            raise GraphWriterLostError("advisory_lock_lost")
        if self._writer_token is None:
            raise GraphWriterLostError("writer_lease_not_occupied")
        with self._connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT app.validate_active_lightrag_lease(%s, %s, %s)
                """,
                (job_id, self._lease_owner, job_lease_token),
            )
            job_ok = cursor.fetchone()
            cursor.execute(
                """
                SELECT app.validate_active_graph_writer_lease(%s, %s)
                """,
                (self._lease_owner, self._writer_token),
            )
            writer_ok = cursor.fetchone()
        if job_ok is None or job_ok[0] is not True:
            raise GraphWriterLostError("job_lease_lost")
        if writer_ok is None or writer_ok[0] is not True:
            raise GraphWriterLostError("writer_lease_lost")

    def quarantine(
        self,
        *,
        reason: str,
        source_job_id: UUID | None = None,
        enqueue_reconciliation: bool = True,
    ) -> UUID | None:
        """Persist ``quarantined`` and optionally enqueue reconciliation.

        Args:
            reason: Machine-readable quarantine reason stored on the snapshot.
            source_job_id: Optional job that triggered quarantine.
            enqueue_reconciliation: When true, insert a low-priority rebuild
                row with ``payload_ref.reconciliation``.

        Returns:
            Reconciliation job id when enqueued, otherwise ``None``.

        Side Effects:
            Updates workspace state. Caller must commit. Does not mutate
            vendor tables.
        """

        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT app.quarantine_graph_workspace(%s, %s)",
                (self._workspace_key, reason),
            )
            if not enqueue_reconciliation:
                return None
            cursor.execute(
                """
                SELECT app.enqueue_graph_reconciliation_job(%s, %s, %s)
                """,
                (self._workspace_key, source_job_id, reason),
            )
            row = cursor.fetchone()
        if row is None or row[0] is None:
            return None
        return UUID(str(row[0]))

    def transition_state(
        self,
        *,
        from_states: Sequence[GraphWorkspaceState],
        to_state: GraphWorkspaceState,
        snapshot: dict[str, object] | None = None,
    ) -> UUID:
        """Transition the workspace when the current state is allowed.

        Args:
            from_states: Permitted source states.
            to_state: Target application state.
            snapshot: Optional JSON merged into ``config_snapshot``.

        Returns:
            Workspace row id.

        Raises:
            GraphWriterLostError: If the current state refuses the transition.

        Side Effects:
            Updates ``app.graph_workspaces``. Caller must commit.
        """

        payload = dict(graph_chunker_config_snapshot())
        if snapshot:
            payload.update(snapshot)
        with self._connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT app.transition_graph_workspace_state(%s, %s::app.graph_workspace_state[], %s, %s::jsonb)
                """,
                (
                    self._workspace_key,
                    [state.value for state in from_states],
                    to_state.value,
                    json.dumps(payload),
                ),
            )
            row = cursor.fetchone()
        if row is None or row[0] is None:
            raise GraphWriterLostError("workspace_state_refused")
        return UUID(str(row[0]))

    def load_pointer_generation(self) -> int:
        """Return the singleton active-workspace generation.

        Returns:
            Positive generation, defaulting to ``1`` when the pointer is empty.
        """

        with self._connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT generation
                FROM app.graph_active_workspace_pointer
                WHERE id = %s::uuid
                """,
                (GRAPH_POINTER_ID,),
            )
            row = cursor.fetchone()
        if row is None or row[0] is None:
            return 1
        return int(row[0])

    def attach_default_pointer_if_null(self) -> None:
        """Point the singleton at ``company_default`` when unset.

        This is initial attach, not a Packet 7 generation-bumping switch.
        The workspace is not marked ``active``.

        Side Effects:
            May update ``app.graph_active_workspace_pointer.workspace_id``.
            Caller must commit.
        """

        with self._connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE app.graph_active_workspace_pointer AS pointer
                SET
                  workspace_id = ws.id,
                  updated_at = timezone('utc', now())
                FROM app.graph_workspaces AS ws
                WHERE pointer.id = %s::uuid
                  AND pointer.workspace_id IS NULL
                  AND ws.workspace_key = %s
                """,
                (GRAPH_POINTER_ID, self._workspace_key),
            )

    def ensure_building_rebuild_workspace(self) -> UUID:
        """Insert or return the isolated rebuild workspace. Pointer unchanged.

        Returns:
            Isolated workspace row id.

        Side Effects:
            Inserts ``{workspace_key}__rebuild`` in ``building`` when missing.
            Caller must commit. Does not switch the active pointer.
        """

        rebuild_key = f"{self._workspace_key}__rebuild"
        snapshot = graph_chunker_config_snapshot()
        with self._connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO app.graph_workspaces (
                  workspace_key,
                  state,
                  config_snapshot
                )
                VALUES (
                  %s,
                  'building'::app.graph_workspace_state,
                  %s::jsonb
                )
                ON CONFLICT (workspace_key) DO UPDATE
                  SET updated_at = timezone('utc', now())
                RETURNING id
                """,
                (rebuild_key, json.dumps(snapshot)),
            )
            row = cursor.fetchone()
        if row is None:
            raise GraphWriterLostError("rebuild_workspace_missing")
        return UUID(str(row[0]))

    def _validate_job_lease(self, job_id: UUID, job_lease_token: str) -> bool:
        """Return whether this owner still holds an active LightRAG job lease.

        Args:
            job_id: LightRAG index job identifier.
            job_lease_token: Opaque lease token presented by the worker.

        Returns:
            True when ``validate_active_lightrag_lease`` accepts the token.
        """

        with self._connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT app.validate_active_lightrag_lease(%s, %s, %s)
                """,
                (job_id, self._lease_owner, job_lease_token),
            )
            row = cursor.fetchone()
        return row is not None and row[0] is True

    def _heartbeat_job(self, job_id: UUID, job_lease_token: str) -> bool:
        """Extend the LightRAG job lease heartbeat for this owner.

        Args:
            job_id: LightRAG index job identifier.
            job_lease_token: Opaque lease token presented by the worker.

        Returns:
            True when the heartbeat RPC accepted the token.
        """

        with self._connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT app.heartbeat_lightrag_index_job(%s, %s, %s, %s)
                """,
                (
                    job_id,
                    self._lease_owner,
                    job_lease_token,
                    self._lease_seconds,
                ),
            )
            row = cursor.fetchone()
        return row is not None and row[0] is True


def load_workspace_row(
    connection: psycopg.Connection,
    *,
    workspace_key: str = DEFAULT_GRAPH_WORKSPACE,
) -> dict[str, object]:
    """Load one application workspace row.

    Args:
        connection: ``app_worker`` connection.
        workspace_key: Workspace identifier.

    Returns:
        Mapping of workspace columns.

    Raises:
        GraphWriterLostError: If the workspace row is missing.
    """

    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(
            """
            SELECT *
            FROM app.graph_workspaces
            WHERE workspace_key = %s
            """,
            (workspace_key,),
        )
        row = cursor.fetchone()
    if row is None:
        raise GraphWriterLostError("workspace_missing")
    return dict(row)


def allowed_index_from_states() -> tuple[GraphWorkspaceState, ...]:
    """Return states from which a normal index mutation may start.

    Returns:
        ``building``, ``active``, ``updating``, and ``filtered_dirty``.
    """

    return (
        GraphWorkspaceState.BUILDING,
        GraphWorkspaceState.ACTIVE,
        GraphWorkspaceState.UPDATING,
        GraphWorkspaceState.FILTERED_DIRTY,
    )
