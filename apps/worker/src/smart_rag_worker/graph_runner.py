"""LightRAG graph-writer worker loop.

Imports ``GraphIndexer`` / ``LightRagGraphIndexer`` from core retrieval, never
``lightrag``. Writer concurrency is one process-wide via durable lease plus
session advisory lock.
"""

from __future__ import annotations

import asyncio
import logging
import socket
import threading
from typing import Any
from uuid import UUID

import psycopg
from smart_rag_core.jobs.exceptions import GraphWriterLostError, JobLeaseError
from smart_rag_core.jobs.graph_index_service import GraphIndexService
from smart_rag_core.jobs.graph_writer import (
    GraphWriterGuard,
    heartbeat_graph_writer_lease,
)
from smart_rag_core.jobs.lightrag_repository import LightragIndexJobRepository
from smart_rag_core.retrieval.graph import DEFAULT_GRAPH_WORKSPACE, GraphIndexer
from smart_rag_core.retrieval.lightrag_adapter import LightRagRuntimeAdapter
from smart_rag_core.retrieval.lightrag_indexer import LightRagGraphIndexer
from smart_rag_core.schema.enums import JobErrorCategory
from smart_rag_core.settings.worker import WorkerSettings

LOGGER = logging.getLogger(__name__)


class GraphWorkerLoop:
    """Poll and process LightRAG jobs with lease, lock, and heartbeat."""

    def __init__(
        self,
        settings: WorkerSettings,
        *,
        adapter: LightRagRuntimeAdapter | None,
    ) -> None:
        """Capture worker settings and the optional attached adapter.

        Args:
            settings: Validated worker settings.
            adapter: Runtime adapter bound in ``WorkerLifecycle``, or ``None``
                when ``LIGHTRAG_DB_URL`` is unset.
        """

        self._settings = settings
        self._adapter = adapter
        self._indexer: GraphIndexer | None = (
            LightRagGraphIndexer(adapter) if adapter is not None else None
        )

    def process_once(self) -> bool:
        """Claim and process one graph job when the adapter is attached.

        Returns:
            True when a job was claimed (including fail/quarantine paths).
            False when there is no adapter or no eligible job.

        Side Effects:
            Commits claim, occupies the writer lease, holds a session
            advisory lock during mutation, then completes or fails the job.
        """

        if self._adapter is None or self._indexer is None:
            return False
        postgres_url = self._postgres_url()
        with psycopg.connect(postgres_url) as claimed:
            claimed.execute("SET ROLE app_worker")
            repository = LightragIndexJobRepository(
                claimed,
                lease_owner=self._lease_owner(),
                lease_seconds=self._settings.job_lease_seconds,
            )
            job = repository.claim()
            if job is None:
                claimed.rollback()
                return False
            claimed.commit()

        job_id = UUID(str(job["id"]))
        lease_token = str(job["lease_token"])
        writer_token: str | None = None
        lock_connection: psycopg.Connection | None = None
        guard: GraphWriterGuard | None = None
        stop_heartbeat = threading.Event()
        heartbeat_thread: threading.Thread | None = None
        try:
            with psycopg.connect(postgres_url) as occupy_conn:
                occupy_conn.execute("SET ROLE app_worker")
                guard = GraphWriterGuard(
                    occupy_conn,
                    lease_owner=self._lease_owner(),
                    lease_seconds=self._settings.job_lease_seconds,
                    workspace_key=DEFAULT_GRAPH_WORKSPACE,
                )
                try:
                    writer_token = guard.occupy(
                        job_id=job_id,
                        job_lease_token=lease_token,
                    )
                    occupy_conn.commit()
                except GraphWriterLostError as exc:
                    occupy_conn.rollback()
                    if exc.reason == "writer_lease_occupied":
                        self._fail_job(
                            postgres_url,
                            job_id,
                            lease_token,
                            error_category=JobErrorCategory.TRANSIENT,
                            last_error="writer_lease_occupied",
                        )
                        return True
                    raise

            lock_connection = psycopg.connect(postgres_url)
            lock_connection.autocommit = True
            if guard is None:
                raise GraphWriterLostError("writer_lease_not_occupied")
            try:
                guard.acquire_session_lock(lock_connection)
            except GraphWriterLostError as exc:
                if exc.reason == "advisory_lock_busy":
                    self._fail_job(
                        postgres_url,
                        job_id,
                        lease_token,
                        error_category=JobErrorCategory.TRANSIENT,
                        last_error="advisory_lock_busy",
                    )
                    return True
                raise

            def heartbeat_loop() -> None:
                while not stop_heartbeat.wait(
                    timeout=self._settings.job_heartbeat_interval_seconds
                ):
                    try:
                        with psycopg.connect(postgres_url) as connection:
                            connection.execute("SET ROLE app_worker")
                            repository = LightragIndexJobRepository(
                                connection,
                                lease_owner=self._lease_owner(),
                                lease_seconds=self._settings.job_lease_seconds,
                            )
                            repository.heartbeat(job_id, lease_token)
                            if writer_token is not None:
                                heartbeat_graph_writer_lease(
                                    connection,
                                    lease_owner=self._lease_owner(),
                                    writer_token=writer_token,
                                    lease_seconds=self._settings.job_lease_seconds,
                                )
                            connection.commit()
                    except (JobLeaseError, GraphWriterLostError):
                        return

            heartbeat_thread = threading.Thread(
                target=heartbeat_loop,
                name=f"graph-heartbeat-{job_id}",
                daemon=True,
            )
            heartbeat_thread.start()

            indexer = self._indexer
            adapter = self._adapter
            if not isinstance(indexer, LightRagGraphIndexer):
                raise RuntimeError("graph_indexer_missing")

            def _pre_provider() -> None:
                with psycopg.connect(postgres_url) as verify_conn:
                    verify_conn.execute("SET ROLE app_worker")
                    verify_guard = GraphWriterGuard(
                        verify_conn,
                        lease_owner=self._lease_owner(),
                        lease_seconds=self._settings.job_lease_seconds,
                        workspace_key=DEFAULT_GRAPH_WORKSPACE,
                    )
                    verify_guard.bind_occupied(
                        writer_token=writer_token or "",
                        lock_connection=lock_connection,
                    )
                    verify_guard.verify_lock_and_lease(
                        job_id=job_id,
                        job_lease_token=lease_token,
                    )
                    verify_conn.commit()

            adapter.callbacks.pre_provider_hook = _pre_provider
            with psycopg.connect(postgres_url) as work_conn:
                work_conn.execute("SET ROLE app_worker")
                work_guard = GraphWriterGuard(
                    work_conn,
                    lease_owner=self._lease_owner(),
                    lease_seconds=self._settings.job_lease_seconds,
                    workspace_key=DEFAULT_GRAPH_WORKSPACE,
                )
                work_guard.bind_occupied(
                    writer_token=writer_token or "",
                    lock_connection=lock_connection,
                )
                service = GraphIndexService(
                    work_conn,
                    indexer=indexer,
                    writer=work_guard,
                    repository=LightragIndexJobRepository(
                        work_conn,
                        lease_owner=self._lease_owner(),
                        lease_seconds=self._settings.job_lease_seconds,
                    ),
                )
                outcome = asyncio.run(
                    service.process_claimed_job(
                        job,
                        job_lease_token=lease_token,
                    )
                )
            self._finish_job(
                postgres_url,
                job_id,
                lease_token,
                outcome_kind=outcome.kind,
                error_category=outcome.error_category,
                last_error=outcome.last_error,
                result={
                    "vendor_status": outcome.vendor_status,
                    "workspace_state": outcome.workspace_state,
                    "maps_verified": False,
                    "reservation_kind": outcome.reservation_kind,
                },
            )
            return True
        except (GraphWriterLostError, JobLeaseError, psycopg.Error) as exc:
            LOGGER.exception("graph job %s failed: %s", job_id, exc)
            try:
                with psycopg.connect(postgres_url) as connection:
                    connection.execute("SET ROLE app_worker")
                    qguard = GraphWriterGuard(
                        connection,
                        lease_owner=self._lease_owner(),
                        lease_seconds=self._settings.job_lease_seconds,
                    )
                    qguard.quarantine(
                        reason=str(exc)[:512],
                        source_job_id=job_id,
                    )
                    connection.commit()
            except psycopg.Error:
                LOGGER.exception("unable to quarantine after graph job %s", job_id)
            self._fail_job(
                postgres_url,
                job_id,
                lease_token,
                error_category=JobErrorCategory.TRANSIENT,
                last_error=str(exc)[:4000],
            )
            return True
        finally:
            if self._adapter is not None:
                self._adapter.callbacks.pre_provider_hook = None
            stop_heartbeat.set()
            if heartbeat_thread is not None:
                heartbeat_thread.join(timeout=5)
            if guard is not None:
                try:
                    guard.release_session_lock()
                except psycopg.Error:
                    LOGGER.exception("graph advisory unlock failed for %s", job_id)
            if lock_connection is not None and not lock_connection.closed:
                lock_connection.close()
            if writer_token is not None:
                try:
                    with psycopg.connect(postgres_url) as connection:
                        connection.execute("SET ROLE app_worker")
                        releaser = GraphWriterGuard(
                            connection,
                            lease_owner=self._lease_owner(),
                            lease_seconds=self._settings.job_lease_seconds,
                        )
                        releaser.bind_occupied(
                            writer_token=writer_token,
                            lock_connection=None,
                        )
                        releaser.release()
                        connection.commit()
                except psycopg.Error:
                    LOGGER.exception("graph writer release failed for %s", job_id)

    def _finish_job(
        self,
        postgres_url: str,
        job_id: UUID,
        lease_token: str,
        *,
        outcome_kind: str,
        error_category: JobErrorCategory | None,
        last_error: str,
        result: dict[str, Any],
    ) -> None:
        with psycopg.connect(postgres_url) as connection:
            connection.execute("SET ROLE app_worker")
            repository = LightragIndexJobRepository(
                connection,
                lease_owner=self._lease_owner(),
                lease_seconds=self._settings.job_lease_seconds,
            )
            if outcome_kind == "completed":
                repository.complete(job_id, lease_token, result=result)
            else:
                repository.fail(
                    job_id,
                    lease_token,
                    error_category=error_category or JobErrorCategory.TRANSIENT,
                    last_error=last_error or outcome_kind,
                )
            connection.commit()

    def _fail_job(
        self,
        postgres_url: str,
        job_id: UUID,
        lease_token: str,
        *,
        error_category: JobErrorCategory,
        last_error: str,
    ) -> None:
        try:
            with psycopg.connect(postgres_url) as connection:
                connection.execute("SET ROLE app_worker")
                repository = LightragIndexJobRepository(
                    connection,
                    lease_owner=self._lease_owner(),
                    lease_seconds=self._settings.job_lease_seconds,
                )
                repository.fail(
                    job_id,
                    lease_token,
                    error_category=error_category,
                    last_error=last_error,
                )
                connection.commit()
        except (JobLeaseError, psycopg.Error):
            LOGGER.exception("unable to persist graph failure for job %s", job_id)

    def _postgres_url(self) -> str:
        if self._settings.supabase_db_url is None:
            raise JobLeaseError("supabase_db_url_unconfigured")
        return self._settings.supabase_db_url.get_secret_value()

    def _lease_owner(self) -> str:
        hostname = socket.gethostname()
        return f"{self._settings.worker_instance_id}@{hostname}"
