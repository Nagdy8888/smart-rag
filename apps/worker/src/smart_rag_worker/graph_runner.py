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
from collections.abc import Coroutine, Mapping
from typing import Any, TypeVar, cast
from uuid import UUID

import psycopg
from smart_rag_core.jobs.exceptions import GraphWriterLostError, JobLeaseError
from smart_rag_core.jobs.graph_index_service import GraphIndexService
from smart_rag_core.jobs.graph_mapping_hybrid import bind_mapping_support
from smart_rag_core.jobs.graph_writer import (
    GraphWriterGuard,
    heartbeat_graph_writer_lease,
)
from smart_rag_core.jobs.lightrag_repository import LightragIndexJobRepository
from smart_rag_core.jobs.limits import (
    DEFAULT_GRAPH_SOURCE_BATCH_DEADLINE_SECONDS,
    LOCAL_DEMO_MAX_MAPPING_ENTITIES,
    LOCAL_DEMO_MAX_MAPPING_RELATIONS,
    MAX_MAPPING_ENTITIES,
    MAX_MAPPING_RELATIONS,
)
from smart_rag_core.jobs.maintenance_pause import MaintenancePauseController
from smart_rag_core.observability.ingest_progress import log_ingest_progress
from smart_rag_core.observability.ingest_trace import (
    INGEST_RUN_GRAPH,
    invoke_traced_ingestion,
)
from smart_rag_core.retrieval.graph import DEFAULT_GRAPH_WORKSPACE, GraphIndexer
from smart_rag_core.retrieval.lightrag_adapter import LightRagRuntimeAdapter
from smart_rag_core.retrieval.lightrag_indexer import LightRagGraphIndexer
from smart_rag_core.schema.enums import JobErrorCategory
from smart_rag_core.settings.base import Environment
from smart_rag_core.settings.worker import WorkerSettings

LOGGER = logging.getLogger(__name__)

T = TypeVar("T")


def effective_graph_mapping_limits(
    settings: WorkerSettings,
    job: dict[str, Any],
) -> tuple[int, int]:
    """Return production limits or the approved local synthetic-demo limits.

    Args:
        settings: Validated worker settings.
        job: Claimed LightRAG job including its payload.

    Returns:
        Entity and relation limits. The larger fixed pair is returned only
        when ``APP_ENV=local`` and the payload explicitly records synthetic,
        reviewed demo content plus ``local_demo_mapping_override=true``.

    Security:
        Staging/production and unreviewed/non-synthetic jobs always retain the
        production 200/200 caps, even if a payload requests the override.
    """

    payload_raw = job.get("payload_ref")
    payload: Mapping[str, object]
    if isinstance(payload_raw, Mapping):
        payload = cast(Mapping[str, object], payload_raw)
    else:
        payload = {}
    local_demo = (
        settings.app_env is Environment.LOCAL
        and payload.get("local_demo_mapping_override") is True
        and payload.get("content_class") == "synthetic"
        and payload.get("review_approved") is True
    )
    if local_demo:
        return (
            LOCAL_DEMO_MAX_MAPPING_ENTITIES,
            LOCAL_DEMO_MAX_MAPPING_RELATIONS,
        )
    return MAX_MAPPING_ENTITIES, MAX_MAPPING_RELATIONS


def run_lightrag_coroutine(
    coro: Coroutine[Any, Any, T],
    *,
    loop: asyncio.AbstractEventLoop | None,
) -> T:
    """Await a LightRAG coroutine on the adapter's long-lived event loop.

    Args:
        coro: Adapter or index-service coroutine.
        loop: Loop that created the asyncpg pool at worker startup. ``None``
            uses ``asyncio.run`` only when the adapter was never attached.

    Returns:
        Coroutine result.

    Raises:
        BaseException: Propagates whatever the coroutine raises.

    Side Effects:
        ``asyncio.run`` closes its loop and destroys the LightRAG connection
        pool. Bind and ``process_claimed_job`` must therefore share ``loop``.
    """

    if loop is None:
        return asyncio.run(coro)
    asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)


class GraphWorkerLoop:
    """Poll and process LightRAG jobs with lease, lock, and heartbeat."""

    def __init__(
        self,
        settings: WorkerSettings,
        *,
        adapter: LightRagRuntimeAdapter | None,
        pause_controller: MaintenancePauseController | None = None,
        async_loop: asyncio.AbstractEventLoop | None = None,
    ) -> None:
        """Capture worker settings and the optional attached adapter.

        Args:
            settings: Validated worker settings.
            adapter: Runtime adapter bound in ``WorkerLifecycle``, or ``None``
                when ``LIGHTRAG_DB_URL`` is unset.
            pause_controller: User-load pause for LightRAG rebuilds. Defaults
                to unmeasured-allows so missing docker telemetry does not
                dead-letter rebuilds. Inject fixtures to prove 70%.
            async_loop: Event loop that opened the LightRAG asyncpg pool.
                Must be the same loop used for ``process_claimed_job``.
        """

        self._settings = settings
        self._adapter = adapter
        self._async_loop = async_loop
        self._pause_controller = (
            pause_controller or MaintenancePauseController.unmeasured_allows()
        )
        self._indexer: GraphIndexer | None = (
            LightRagGraphIndexer(
                adapter,
                deadline_seconds=DEFAULT_GRAPH_SOURCE_BATCH_DEADLINE_SECONDS,
            )
            if adapter is not None
            else None
        )

    def process_once(self) -> bool:
        """Claim and process one graph job when the adapter is attached.

        Returns:
            True when a job was claimed (including fail/quarantine paths).
            False when there is no adapter or no eligible job.

        Side Effects:
            Commits claim, occupies the writer lease, holds a session
            advisory lock during mutation, then completes or fails the job.
            Unhandled exceptions fail the job. Isolated candidate jobs do
            not quarantine the live workspace.
        """

        adapter = self._adapter
        indexer = self._indexer
        if adapter is None or indexer is None:
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
        version_id_raw = job.get("version_id")
        document_id_raw = job.get("document_id")
        payload_raw = job.get("payload_ref")
        payload: Mapping[str, object]
        if isinstance(payload_raw, Mapping):
            payload = cast(Mapping[str, object], payload_raw)
        else:
            payload = {}
        writer_token: str | None = None
        occupied_token = ""
        lock_connection: psycopg.Connection | None = None
        guard: GraphWriterGuard | None = None
        stop_heartbeat = threading.Event()
        heartbeat_thread: threading.Thread | None = None
        log_ingest_progress("graph", "lightrag_index", job_id)
        adapter.callbacks.ingest_job_id = str(job_id)
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
                    occupied_token = guard.occupy(
                        job_id=job_id,
                        job_lease_token=lease_token,
                    )
                    writer_token = occupied_token
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
                        log_ingest_progress(
                            "graph",
                            "lightrag_index_failed",
                            job_id,
                            error_category=JobErrorCategory.TRANSIENT,
                            reason_code="writer_lease_occupied",
                        )
                        return True
                    raise

            lock_connection = psycopg.connect(postgres_url)
            lock_connection.autocommit = True
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
                    log_ingest_progress(
                        "graph",
                        "lightrag_index_failed",
                        job_id,
                        error_category=JobErrorCategory.TRANSIENT,
                        reason_code="advisory_lock_busy",
                    )
                    return True
                raise

            def heartbeat_loop() -> None:
                """Renew LightRAG and graph-writer leases until stop is set."""

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
                            heartbeat_graph_writer_lease(
                                connection,
                                lease_owner=self._lease_owner(),
                                writer_token=occupied_token,
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

            if not isinstance(indexer, LightRagGraphIndexer):
                raise RuntimeError("graph_indexer_missing")

            def _pre_provider() -> None:
                """Re-check the occupied graph-writer lease before vendor calls."""

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
                mapping_max_entities, mapping_max_relations = (
                    effective_graph_mapping_limits(self._settings, job)
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
                    mapping_support=bind_mapping_support(work_conn, self._settings),
                    pause_controller=self._pause_controller,
                    mapping_max_entities=mapping_max_entities,
                    mapping_max_relations=mapping_max_relations,
                )
                outcome = invoke_traced_ingestion(
                    lambda: run_lightrag_coroutine(
                        service.process_claimed_job(
                            job,
                            job_lease_token=lease_token,
                        ),
                        loop=self._async_loop,
                    ),
                    settings=self._settings,
                    job_id=job_id,
                    run_name=INGEST_RUN_GRAPH,
                    document_id=str(document_id_raw) if document_id_raw else None,
                    version_id=str(version_id_raw) if version_id_raw else None,
                    content_class=(
                        str(payload.get("content_class"))
                        if isinstance(payload.get("content_class"), str)
                        else None
                    ),
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
                    "maps_verified": outcome.maps_verified,
                    "mapping_reason": outcome.mapping_reason,
                    "reservation_kind": outcome.reservation_kind,
                },
            )
            _log_graph_outcome(job_id, outcome.kind, outcome.error_category)
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
            log_ingest_progress(
                "graph",
                "lightrag_index_failed",
                job_id,
                error_category=JobErrorCategory.TRANSIENT,
                reason_code="job_failed",
            )
            return True
        except Exception as exc:
            reason = type(exc).__name__[:128]
            LOGGER.exception("graph job %s unhandled: %s", job_id, reason)
            payload_raw: object = job.get("payload_ref")
            isolate = False
            if isinstance(payload_raw, dict):
                isolate = (
                    cast(dict[str, object], payload_raw).get("isolate_candidate")
                    is True
                )
            if not isolate:
                try:
                    with psycopg.connect(postgres_url) as connection:
                        connection.execute("SET ROLE app_worker")
                        qguard = GraphWriterGuard(
                            connection,
                            lease_owner=self._lease_owner(),
                            lease_seconds=self._settings.job_lease_seconds,
                        )
                        qguard.quarantine(
                            reason=reason,
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
                last_error=reason,
            )
            log_ingest_progress(
                "graph",
                "lightrag_index_failed",
                job_id,
                error_category=JobErrorCategory.TRANSIENT,
                reason_code="unhandled_exception",
            )
            return True
        finally:
            adapter.callbacks.ingest_job_id = None
            adapter.callbacks.pre_provider_hook = None
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
        """Persist completion or classified failure for one LightRAG job.

        Args:
            postgres_url: Worker Postgres URL.
            job_id: LightRAG index job identifier.
            lease_token: Active lease token.
            outcome_kind: ``completed`` or a failure kind.
            error_category: Failure category when not completing.
            last_error: Operator-visible error detail.
            result: Completion payload stored on success.
        """

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
        """Best-effort persist a LightRAG job failure.

        Args:
            postgres_url: Worker Postgres URL.
            job_id: LightRAG index job identifier.
            lease_token: Active lease token.
            error_category: Classified failure category.
            last_error: Operator-visible error detail.
        """

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
        """Return the configured Supabase Postgres URL.

        Returns:
            Connection URL for worker-role SQL.

        Raises:
            JobLeaseError: When ``supabase_db_url`` is unset.
        """

        if self._settings.supabase_db_url is None:
            raise JobLeaseError("supabase_db_url_unconfigured")
        return self._settings.supabase_db_url.get_secret_value()

    def _lease_owner(self) -> str:
        """Return the stable lease owner id for this worker process.

        Returns:
            ``{instance_id}@{hostname}`` owner string.
        """

        hostname = socket.gethostname()
        return f"{self._settings.worker_instance_id}@{hostname}"


def _log_graph_outcome(
    job_id: UUID,
    outcome_kind: str,
    error_category: JobErrorCategory | None,
) -> None:
    """Emit one ``[graph]`` completion or failure line.

    Args:
        job_id: LightRAG job identifier.
        outcome_kind: Service outcome kind.
        error_category: Failure category when not completed.

    Side Effects:
        One progress log. ``completed`` maps to ``graph_ready``.
    """

    if outcome_kind == "completed":
        log_ingest_progress("graph", "graph_ready", job_id)
        return
    stage = (
        "graph_ineligible"
        if outcome_kind == "graph_ineligible"
        else "lightrag_index_failed"
    )
    reason = outcome_kind if outcome_kind.replace("_", "").isalnum() else "job_failed"
    log_ingest_progress(
        "graph",
        stage,
        job_id,
        error_category=error_category or JobErrorCategory.TRANSIENT,
        reason_code=reason,
    )
