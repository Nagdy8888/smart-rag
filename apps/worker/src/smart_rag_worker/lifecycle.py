"""Worker lifecycle: poll, claim, heartbeat, invoke ingestion graphs."""

from __future__ import annotations

import asyncio
import logging
import socket
import threading
import time
from collections.abc import Callable, Mapping
from concurrent.futures import Future, ThreadPoolExecutor
from decimal import Decimal
from typing import Any, cast
from uuid import UUID

import psycopg
from smart_rag_agents.ingestion.checkpointer import (
    IngestionCheckpointer,
    open_ingestion_checkpointer,
)
from smart_rag_agents.ingestion.crawl_graph import (
    IngestionCrawlState,
    build_crawl_ingestion_graph,
)
from smart_rag_agents.ingestion.graph import (
    IngestionProbeState,
    build_probe_ingestion_graph,
)
from smart_rag_agents.ingestion.index_graph import (
    IngestionIndexState,
    build_index_ingestion_graph,
)
from smart_rag_agents.ingestion.scan_graph import (
    IngestionScanState,
    build_scan_promote_ingestion_graph,
)
from smart_rag_core.ingestion.parser.sandbox.launcher import (
    docker_sandbox_available,
    inprocess_parser_permitted,
)
from smart_rag_core.jobs.exceptions import JobLeaseError, JobRepositoryError
from smart_rag_core.jobs.ingestion_repository import IngestionJobRepository
from smart_rag_core.observability.ingest_progress import log_ingest_progress
from smart_rag_core.observability.ingest_trace import (
    ingest_run_name_for_job_kind,
    invoke_traced_ingestion,
)
from smart_rag_core.retrieval.lightrag_adapter import (
    LightRagRuntimeAdapter,
    bind_process_runtime_adapter,
)
from smart_rag_core.schema.enums import JobErrorCategory
from smart_rag_core.schema.tables import IngestionJobRecord
from smart_rag_core.settings.base import Environment
from smart_rag_core.settings.worker import WorkerSettings

from smart_rag_worker.bm25_runner import Bm25WorkerLoop
from smart_rag_worker.graph_runner import GraphWorkerLoop
from smart_rag_worker.privileged_storage import load_worker_privileged_storage_secret

LOGGER = logging.getLogger(__name__)


def patch_checkpoint_lease_token(
    graph: Any,
    config: dict[str, object],
    lease_token: str,
) -> None:
    """Overwrite checkpointed ``lease_token`` with the currently claimed token.

    Args:
        graph: Compiled graph exposing ``update_state``.
        config: Runnable config including ``thread_id``.
        lease_token: Token from the latest job claim.

    Side Effects:
        Writes a new checkpoint when ``lease_token`` is non-empty. Resume via
        ``invoke(None)`` otherwise keeps the failed attempt's token, and
        canonical ledger writes fail with ``invalid_or_expired_lease``.
    """

    if not lease_token:
        return
    graph.update_state(config, {"lease_token": lease_token})  # pyright: ignore[reportUnknownMemberType]


class WorkerLifecycle:
    """Polls ingestion jobs and executes probe or scan/promote graphs."""

    def __init__(self, settings: WorkerSettings) -> None:
        """Capture immutable worker settings and compile durable graphs.

        Args:
            settings: Validated worker settings for this process.

        Side Effects:
            Opens a Postgres checkpointer pool when a database URL is
            configured. Runtime never calls ``PostgresSaver.setup()``.
            When ``LIGHTRAG_DB_URL`` is set, opens one long-lived asyncio
            loop, attaches the runtime LightRAG adapter on that loop, and
            reuses it for graph jobs. Never ``asyncio.run`` after attach,
            because that closes the asyncpg pool.
        """

        assert_worker_parser_sandbox(settings)
        self._settings = settings
        self._stop_event = threading.Event()
        self._checkpointer: IngestionCheckpointer | None = None
        self._lightrag_adapter: LightRagRuntimeAdapter | None = None
        saver = None
        checkpoint_dsn = settings.resolved_checkpoint_dsn()
        if checkpoint_dsn is not None:
            self._checkpointer = open_ingestion_checkpointer(
                checkpoint_dsn,
                max_size=max(8, settings.worker_concurrency * 4),
            )
            saver = self._checkpointer.saver
        self._lightrag_loop: asyncio.AbstractEventLoop | None = None
        try:
            if settings.lightrag_db_url is not None:
                self._lightrag_loop = asyncio.new_event_loop()
                asyncio.set_event_loop(self._lightrag_loop)
                self._lightrag_adapter = self._lightrag_loop.run_until_complete(
                    bind_process_runtime_adapter(
                        dsn=settings.lightrag_db_url,
                        settings=settings,
                    )
                )
            self._probe_graph = build_probe_ingestion_graph(checkpointer=saver)
            self._scan_graph = build_scan_promote_ingestion_graph(checkpointer=saver)
            self._crawl_graph = build_crawl_ingestion_graph(checkpointer=saver)
            self._index_graph = build_index_ingestion_graph(checkpointer=saver)
            self._bm25_loop = Bm25WorkerLoop(settings)
            self._graph_loop = GraphWorkerLoop(
                settings,
                adapter=self._lightrag_adapter,
                async_loop=self._lightrag_loop,
            )
        except BaseException:
            self.stop()
            raise

    def run_forever(self) -> None:
        """Poll and process jobs until stopped."""

        if self._settings.supabase_db_url is None:
            LOGGER.warning(
                "SUPABASE_DB_URL is unset; worker idle without queue processing"
            )
            while not self._stop_event.is_set():
                time.sleep(self._settings.job_poll_interval_seconds)
            return
        with ThreadPoolExecutor(max_workers=self._settings.worker_concurrency) as pool:
            in_flight: set[Future[None]] = set()
            self._enqueue_query_maintenance()
            while not self._stop_event.is_set():
                still_running: set[Future[None]] = set()
                for future in in_flight:
                    if not future.done():
                        still_running.add(future)
                        continue
                    exc = future.exception()
                    if exc is not None:
                        LOGGER.exception(
                            "ingestion job future failed",
                            exc_info=exc,
                        )
                in_flight = still_running
                self._graph_loop.process_once()
                if len(in_flight) >= self._settings.worker_concurrency:
                    time.sleep(1)
                    continue
                job = self._claim_one()
                if job is None:
                    self._enqueue_query_maintenance()
                    self._bm25_loop.process_once()
                    if self._settings.worker_once:
                        break
                    time.sleep(self._settings.job_poll_interval_seconds)
                    continue
                in_flight.add(pool.submit(self._process_job, job))
                if self._settings.worker_once:
                    for future in in_flight:
                        future.result()
                    break

    def stop(self) -> None:
        """Signal the poll loop to exit and close session-mode pools.

        Side Effects:
            Closes the checkpointer pool and finalizes LightRAG storages when
            they were opened. Does not call schema-admin initialize.
        """

        self._stop_event.set()
        if self._lightrag_adapter is not None:
            loop = self._lightrag_loop
            if loop is None or loop.is_closed():
                asyncio.run(self._lightrag_adapter.finalize())
            else:
                asyncio.set_event_loop(loop)
                loop.run_until_complete(self._lightrag_adapter.finalize())
            self._lightrag_adapter = None
        if self._lightrag_loop is not None:
            if not self._lightrag_loop.is_closed():
                self._lightrag_loop.close()
            self._lightrag_loop = None
            asyncio.set_event_loop(None)
        if self._checkpointer is not None:
            self._checkpointer.close()
            self._checkpointer = None

    def _require_postgres_url(self) -> str:
        """Return the configured Postgres URL or fail closed.

        Returns:
            Connection URL for worker-role SQL.

        Raises:
            JobRepositoryError: When ``supabase_db_url`` is unset.
        """

        postgres_url = self._settings.supabase_db_url
        if postgres_url is None:
            raise JobRepositoryError("supabase_db_url_unconfigured")
        return postgres_url.get_secret_value()

    def _graph_config(self) -> dict[str, object]:
        """Build configurable graph settings from worker env.

        Returns:
            LangGraph ``configurable`` mapping. ``storage_admin_secret`` comes
            from the isolated worker Storage loader, never ``WorkerSettings``.

        Raises:
            JobRepositoryError: If ``SUPABASE_DB_URL`` is unset.

        Side Effects:
            Reads ``SUPABASE_STORAGE_ADMIN_SECRET`` through
            ``load_worker_privileged_storage_secret``.
        """

        storage_secret = load_worker_privileged_storage_secret()
        crawl_proxy = (
            str(self._settings.crawl_proxy_url)
            if self._settings.crawl_proxy_url is not None
            else None
        )
        return {
            "postgres_url": self._require_postgres_url(),
            "lease_owner": self._lease_owner(),
            "job_lease_seconds": self._settings.job_lease_seconds,
            "storage_url": self._settings.supabase_url,
            "storage_admin_secret": storage_secret,
            "clamav_host": self._settings.clamav_host,
            "clamav_port": self._settings.clamav_port,
            "crawl_proxy_url": crawl_proxy,
            "mock_model_mode": self._settings.mock_model_mode,
            "subprocessor_matrix_verified": (
                self._settings.subprocessor_matrix_verified
            ),
        }

    def _run_config(self, job: IngestionJobRecord) -> dict[str, object]:
        """Build LangGraph runnable config keyed by ingestion ``job_id``.

        Args:
            job: Claimed ingestion job. ``thread_id`` equals ``job.id`` so a
                crashed worker resumes the same checkpoint thread.
                ``job_lease_token`` is the live claim token, not a checkpointed
                value from a prior attempt.

        Returns:
            ``{"configurable": ...}`` mapping for ``graph.invoke`` / ``get_state``.
        """

        return {
            "configurable": {
                **self._graph_config(),
                "thread_id": str(job.id),
                "job_lease_token": job.lease_token or "",
            }
        }

    def _invoke_graph(
        self,
        graph: Any,
        initial_input: Mapping[str, object],
        config: dict[str, object],
        *,
        success_statuses: tuple[str, ...],
    ) -> dict[str, object]:
        """Invoke or resume one compiled graph using checkpoint thread id.

        Args:
            graph: Compiled ingestion graph.
            initial_input: Fresh-run state payload (IDs/hashes/Storage refs).
            config: Runnable config including ``thread_id``.
            success_statuses: Terminal success markers. If a prior run already
                reached one of these and ``next`` is empty, skip re-invoke so a
                crash after graph success but before ``complete()`` does not
                start a new superstep.

        Returns:
            Graph result mapping.

        Side Effects:
            Writes checkpoints when a PostgresSaver is bound. Ledgered node
            side effects remain idempotent under replay. Resume patches
            ``lease_token`` from the current claim so canonical ledger writes
            do not use a checkpointed token from a failed attempt.
        """

        if self._checkpointer is None:
            return _graph_result_mapping(
                graph.invoke(initial_input, config)  # pyright: ignore[reportUnknownMemberType]
            )
        snapshot = graph.get_state(config)  # pyright: ignore[reportUnknownMemberType]
        next_nodes = tuple(snapshot.next or ())
        values = _graph_result_mapping(snapshot.values)
        lease_token = str(initial_input.get("lease_token") or "")
        configurable = config.get("configurable")
        if isinstance(configurable, dict) and lease_token:
            configurable["job_lease_token"] = lease_token
        if next_nodes:
            patch_checkpoint_lease_token(graph, config, lease_token)
            return _graph_result_mapping(
                graph.invoke(None, config)  # pyright: ignore[reportUnknownMemberType]
            )
        if values.get("status") in success_statuses:
            return values
        return _graph_result_mapping(
            graph.invoke(initial_input, config)  # pyright: ignore[reportUnknownMemberType]
        )

    def _invoke_traced_graph(
        self,
        job: IngestionJobRecord,
        graph: Any,
        initial_input: Mapping[str, object],
        config: dict[str, object],
        *,
        success_statuses: tuple[str, ...],
    ) -> dict[str, object]:
        """Invoke one ingestion graph inside a redacted LangSmith parent run.

        Args:
            job: Claimed job providing ``job_id`` and hashed document/version
                ids.
            graph: Compiled ingestion graph.
            initial_input: Fresh-run state payload.
            config: Runnable config including ``thread_id``.
            success_statuses: Terminal success markers for resume.

        Returns:
            Graph result mapping.

        Side Effects:
            Binds ``job_id`` correlation, emits one ``[hybrid]`` claimed line,
            and opens ``ingestion.scan`` / ``ingestion.index`` (or crawl/probe)
            when tracing is on.
        """

        run_name = ingest_run_name_for_job_kind(job.job_kind) or "ingestion.probe"
        log_ingest_progress("hybrid", job.job_kind, job.id)
        return invoke_traced_ingestion(
            lambda: self._invoke_graph(
                graph,
                initial_input,
                config,
                success_statuses=success_statuses,
            ),
            settings=self._settings,
            job_id=job.id,
            run_name=run_name,
            document_id=job.document_id,
            version_id=job.version_id,
        )

    def _claim_one(self) -> IngestionJobRecord | None:
        """Claim the next eligible ingestion job, or return None.

        Returns:
            Leased job record, or ``None`` when the queue is empty.
        """

        postgres_url = self._require_postgres_url()
        with psycopg.connect(postgres_url) as connection:
            connection.execute("SET ROLE app_worker")
            repository = IngestionJobRepository(
                connection,
                lease_owner=self._lease_owner(),
                lease_seconds=self._settings.job_lease_seconds,
            )
            job = repository.claim()
            if job is None:
                connection.rollback()
                return None
            connection.commit()
            return job

    def _process_job(self, job: IngestionJobRecord) -> None:
        """Run one leased ingestion job and persist success or failure.

        Args:
            job: Claimed ingestion job with a lease token.

        Side Effects:
            Unexpected exceptions (including scan-event RLS failures) are
            logged and persisted through ``fail`` so the lease is not orphaned.
        """

        postgres_url = self._require_postgres_url()
        lease_token = job.lease_token
        if lease_token is None:
            LOGGER.error("claimed job %s missing lease token", job.id)
            return
        stop_heartbeat = threading.Event()
        lease_lost = threading.Event()

        heartbeat_thread = threading.Thread(
            target=heartbeat_until_stopped,
            kwargs={
                "stop": stop_heartbeat,
                "lease_lost": lease_lost,
                "interval_seconds": self._settings.job_heartbeat_interval_seconds,
                "beat": lambda: self._heartbeat_once(job.id, lease_token),
                "job_id": job.id,
            },
            name=f"heartbeat-{job.id}",
            daemon=True,
        )
        heartbeat_thread.start()
        try:
            config = self._run_config(job)
            configurable = cast(dict[str, object], config["configurable"])
            configurable["lease_lost"] = lease_lost
            if job.job_kind == "scan_promote":
                graph_input = _scan_graph_input_from_job(job)
                result = self._invoke_traced_graph(
                    job,
                    self._scan_graph,
                    graph_input,
                    config,
                    success_statuses=("promoted",),
                )
                success = result.get("status") == "promoted"
                detail = str(result.get("detail", "scan_promote_failed"))
            elif job.job_kind == "website_crawl":
                graph_input = _crawl_graph_input_from_job(job)
                result = self._invoke_traced_graph(
                    job,
                    self._crawl_graph,
                    graph_input,
                    config,
                    success_statuses=("crawl_completed",),
                )
                success = result.get("status") == "crawl_completed"
                detail = str(result.get("detail", "website_crawl_failed"))
            elif job.job_kind == "hybrid_index":
                graph_input = _index_graph_input_from_job(job)
                result = self._invoke_traced_graph(
                    job,
                    self._index_graph,
                    graph_input,
                    config,
                    success_statuses=("indexed",),
                )
                success = result.get("status") == "indexed"
                detail = str(result.get("detail", "hybrid_index_failed"))
            elif job.job_kind in {
                "query_memory_reaper",
                "langsmith_trace_deletion",
                "query_reservation_true_up",
            }:
                success, detail = self._process_query_maintenance(job)
            else:
                graph_input = _probe_graph_input_from_job(job)
                result = self._invoke_traced_graph(
                    job,
                    self._probe_graph,
                    graph_input,
                    config,
                    success_statuses=("probe_validated",),
                )
                success = result.get("status") == "probe_validated"
                detail = str(result.get("detail", "probe_failed"))

            with psycopg.connect(postgres_url) as connection:
                connection.execute("SET ROLE app_worker")
                repository = IngestionJobRepository(
                    connection,
                    lease_owner=self._lease_owner(),
                    lease_seconds=self._settings.job_lease_seconds,
                )
                if lease_lost.is_set():
                    LOGGER.warning("lease lost for job %s; refusing complete()", job.id)
                    _log_hybrid_job_outcome(job, reason_code="lease_lost")
                    try:
                        repository.fail(
                            job.id,
                            lease_token,
                            error_category=JobErrorCategory.TRANSIENT,
                            last_error="lease_lost",
                        )
                        connection.commit()
                    except JobLeaseError:
                        connection.rollback()
                        LOGGER.warning(
                            "lease-lost fail skipped for job %s; token no longer owns row",
                            job.id,
                        )
                elif success:
                    completed = repository.complete(job.id, lease_token)
                    _log_hybrid_job_outcome(job, reason_code=None)
                    if job.job_kind not in {
                        "query_memory_reaper",
                        "langsmith_trace_deletion",
                        "query_reservation_true_up",
                    }:
                        self._true_up_budget(connection, completed)
                else:
                    _log_hybrid_job_outcome(job, reason_code="job_failed")
                    repository.fail(
                        job.id,
                        lease_token,
                        error_category=JobErrorCategory.VALIDATION,
                        last_error=detail,
                    )
                connection.commit()
        except (JobLeaseError, JobRepositoryError, psycopg.Error) as exc:
            LOGGER.exception("job %s failed: %s", job.id, exc)
            _log_hybrid_job_outcome(job, reason_code="job_failed")
            self._fail_job(job.id, lease_token, str(exc))
        except Exception as exc:
            LOGGER.exception("job %s failed with unexpected error: %s", job.id, exc)
            _log_hybrid_job_outcome(job, reason_code="unexpected_error")
            self._fail_job(job.id, lease_token, str(exc))
        finally:
            stop_heartbeat.set()
            heartbeat_thread.join(timeout=5)

    def _enqueue_query_maintenance(self) -> None:
        """Enqueue daily reaper and LangSmith-deletion jobs without a budget.

        Side Effects:
            Inserts ``query_memory_reaper``, ``langsmith_trace_deletion``, and
            hourly ``query_reservation_true_up`` jobs when missing. Never
            reserves ingestion budget.
        """

        postgres_url = self._require_postgres_url()
        try:
            from smart_rag_core.memory.reaper import enqueue_query_maintenance_jobs
            from smart_rag_core.query_admission.service import (
                enqueue_query_reservation_true_up_job,
            )

            with psycopg.connect(postgres_url) as connection:
                connection.execute("SET ROLE app_worker")
                enqueue_query_maintenance_jobs(connection)
                enqueue_query_reservation_true_up_job(connection)
                connection.commit()
        except psycopg.Error:
            LOGGER.exception("unable to enqueue query maintenance jobs")

    def _process_query_maintenance(self, job: IngestionJobRecord) -> tuple[bool, str]:
        """Run the dedicated reaper or LangSmith deletion-request worker.

        Args:
            job: Claimed maintenance job.

        Returns:
            ``(success, detail)``. Never invokes budget true-up.

        Side Effects:
            May NULL completed idempotency keys, delete completed events, or
            record LangSmith deletion HTTP attempts.
        """

        postgres_url = self._require_postgres_url()
        with psycopg.connect(postgres_url) as connection:
            connection.execute("SET ROLE app_worker")
            if job.job_kind == "query_reservation_true_up":
                from smart_rag_core.query_admission.service import (
                    enqueue_query_reservation_true_up_job,
                    reconcile_expired_query_runs,
                )

                enqueue_query_reservation_true_up_job(connection)
                settled = reconcile_expired_query_runs(connection)
                connection.commit()
                return True, f"query_reservation_true_up:{settled}"
            if job.job_kind == "query_memory_reaper":
                from smart_rag_core.memory.reaper import (
                    enqueue_query_maintenance_jobs,
                    reap_query_run_retention,
                )

                enqueue_query_maintenance_jobs(connection)
                result = reap_query_run_retention(connection)
                connection.commit()
                if result.true_up_invoked:
                    return False, "reaper_invoked_true_up"
                return True, "query_memory_reaper_ok"
            from smart_rag_core.observability.langsmith_deletion import (
                HttpLangSmithDeletionTransport,
                process_langsmith_deletion_requests,
            )

            api_key = (
                self._settings.langsmith_api_key.get_secret_value()
                if self._settings.langsmith_api_key is not None
                else None
            )
            endpoint = (
                str(self._settings.langsmith_endpoint)
                if self._settings.langsmith_endpoint is not None
                else "https://api.smith.langchain.com"
            )
            transport = HttpLangSmithDeletionTransport(
                api_key=api_key,
                endpoint=endpoint,
            )
            process_langsmith_deletion_requests(connection, transport=transport)
            connection.commit()
            return True, "langsmith_trace_deletion_ok"

    def _fail_job(self, job_id: UUID, lease_token: str, message: str) -> None:
        """Best-effort persist a transient ingestion job failure.

        Args:
            job_id: Ingestion job identifier.
            lease_token: Active lease token.
            message: Operator-visible error detail, truncated to 4000 chars.
        """

        postgres_url = self._require_postgres_url()
        try:
            with psycopg.connect(postgres_url) as connection:
                connection.execute("SET ROLE app_worker")
                repository = IngestionJobRepository(
                    connection,
                    lease_owner=self._lease_owner(),
                    lease_seconds=self._settings.job_lease_seconds,
                )
                repository.fail(
                    job_id,
                    lease_token,
                    error_category=JobErrorCategory.TRANSIENT,
                    last_error=message[:4000],
                )
                connection.commit()
        except (psycopg.Error, JobLeaseError):
            LOGGER.exception("unable to persist failure for job %s", job_id)

    def _true_up_budget(
        self,
        connection: psycopg.Connection,
        job: IngestionJobRecord,
    ) -> None:
        """Commit the reserved ingestion budget after a successful job.

        Args:
            connection: Open worker-role connection.
            job: Completed job whose payload may include a reservation id.
        """

        reservation_raw = job.payload_ref.get("budget_reservation_id")
        if not isinstance(reservation_raw, str):
            return
        estimated_raw = job.payload_ref.get("estimated_cost_usd", "0")
        actual = Decimal(str(estimated_raw))
        repository = IngestionJobRepository(
            connection,
            lease_owner=self._lease_owner(),
            lease_seconds=self._settings.job_lease_seconds,
        )
        repository.admission.true_up_ingestion_reservation(
            UUID(reservation_raw),
            actual_cost_usd=actual,
        )

    def _lease_owner(self) -> str:
        """Return the stable lease owner id for this worker process.

        Returns:
            ``{instance_id}@{hostname}`` owner string.
        """

        hostname = socket.gethostname()
        return f"{self._settings.worker_instance_id}@{hostname}"

    def _heartbeat_once(self, job_id: UUID, lease_token: str) -> None:
        """Renew one ingestion lease on a dedicated connection.

        Args:
            job_id: Claimed job identifier.
            lease_token: Active lease token.

        Raises:
            JobLeaseError: When heartbeat is rejected.
        """

        postgres_url = self._require_postgres_url()
        with psycopg.connect(postgres_url) as connection:
            connection.execute("SET ROLE app_worker")
            repository = IngestionJobRepository(
                connection,
                lease_owner=self._lease_owner(),
                lease_seconds=self._settings.job_lease_seconds,
            )
            repository.heartbeat(job_id, lease_token)
            connection.commit()


def assert_worker_parser_sandbox(settings: WorkerSettings) -> None:
    """Fail worker start when the parser sandbox would share Storage Admin.

    Args:
        settings: Validated worker settings.

    Raises:
        JobRepositoryError: When Docker is required and missing, or when
            in-process parsing would run in the same process as
            ``SUPABASE_STORAGE_ADMIN_SECRET``.
    """

    storage_secret = load_worker_privileged_storage_secret()
    inprocess = bool(settings.allow_inprocess_parser) or inprocess_parser_permitted()
    if inprocess:
        if settings.app_env is not Environment.TEST:
            raise JobRepositoryError("inprocess_parser_requires_app_env_test")
        if storage_secret:
            raise JobRepositoryError(
                "inprocess_parser_forbidden_with_storage_admin_secret"
            )
        return
    if not docker_sandbox_available():
        raise JobRepositoryError("parser_sandbox_docker_required")


def _log_hybrid_job_outcome(
    job: IngestionJobRecord,
    *,
    reason_code: str | None,
) -> None:
    """Emit one ``[hybrid]`` completion or failure line without job detail text.

    Args:
        job: Claimed ingestion job.
        reason_code: ``None`` on success; a short token on failure.

    Side Effects:
        Logs one progress line. Maintenance jobs stay quiet.
    """

    if job.job_kind in {
        "query_memory_reaper",
        "langsmith_trace_deletion",
        "query_reservation_true_up",
    }:
        return
    if reason_code is None:
        log_ingest_progress("hybrid", f"{job.job_kind}_done", job.id)
        return
    category = (
        JobErrorCategory.TRANSIENT
        if reason_code in {"lease_lost", "job_failed", "unexpected_error"}
        else JobErrorCategory.VALIDATION
    )
    if reason_code == "job_failed":
        category = JobErrorCategory.VALIDATION
    log_ingest_progress(
        "hybrid",
        f"{job.job_kind}_failed",
        job.id,
        error_category=category,
        reason_code=reason_code,
    )


def heartbeat_until_stopped(
    *,
    stop: threading.Event,
    lease_lost: threading.Event,
    interval_seconds: float,
    beat: Callable[[], None],
    job_id: UUID,
) -> None:
    """Renew a job lease until stop or ``JobLeaseError``.

    Args:
        stop: Set by the worker when the job thread finishes.
        lease_lost: Set when heartbeat is rejected so graph invoke must not
            ``complete()``.
        interval_seconds: Sleep between heartbeats.
        beat: Zero-argument callable that raises ``JobLeaseError`` on loss.
        job_id: Job id for logs.

    Side Effects:
        Sets ``lease_lost`` and returns on ``JobLeaseError``. Does not stop
        the graph by itself; nodes observe the event / re-validate the lease.
    """

    while not stop.wait(timeout=interval_seconds):
        try:
            beat()
        except JobLeaseError:
            LOGGER.warning("heartbeat lost for job %s", job_id)
            lease_lost.set()
            return


def _graph_result_mapping(payload: object) -> dict[str, object]:
    """Copy a compiled-graph result or checkpoint values into a plain dict.

    Args:
        payload: ``invoke`` result or ``get_state().values``.

    Returns:
        String-keyed mapping. Empty when ``payload`` is not a ``dict``.
    """

    if not isinstance(payload, dict):
        return {}
    return cast(dict[str, object], payload)


def _probe_graph_input_from_job(job: IngestionJobRecord) -> IngestionProbeState:
    """Build probe graph input containing IDs/tokens and durable Storage refs only."""

    payload = job.payload_ref
    return {
        "job_id": str(job.id),
        "lease_token": job.lease_token or "",
        "document_id": str(job.document_id) if job.document_id else None,
        "version_id": str(job.version_id) if job.version_id else None,
        "operation_key": str(payload.get("operation_key", job.job_kind)),
        "storage_bucket": (
            str(payload["storage_bucket"])
            if isinstance(payload.get("storage_bucket"), str)
            else None
        ),
        "storage_path": (
            str(payload["storage_path"])
            if isinstance(payload.get("storage_path"), str)
            else None
        ),
        "status": "probe_pending",
        "ledger_written": False,
        "detail": "",
    }


def _scan_graph_input_from_job(job: IngestionJobRecord) -> IngestionScanState:
    """Build scan/promote graph input from durable job payload."""

    payload: dict[str, Any] = job.payload_ref
    content_class = str(payload.get("content_class", "real_company"))
    review_approved = bool(payload.get("review_approved", False))
    return {
        "job_id": str(job.id),
        "lease_token": job.lease_token or "",
        "document_id": str(job.document_id) if job.document_id else None,
        "version_id": str(job.version_id) if job.version_id else None,
        "operation_key": str(payload.get("operation_key", job.job_kind)),
        "storage_bucket": (
            str(payload["storage_bucket"])
            if isinstance(payload.get("storage_bucket"), str)
            else None
        ),
        "storage_path": (
            str(payload["storage_path"])
            if isinstance(payload.get("storage_path"), str)
            else None
        ),
        "content_hash": (
            str(payload["content_hash"])
            if isinstance(payload.get("content_hash"), str)
            else None
        ),
        "byte_size": (
            int(payload["byte_size"])
            if isinstance(payload.get("byte_size"), int)
            else None
        ),
        "media_type": (
            str(payload["media_type"])
            if isinstance(payload.get("media_type"), str)
            else None
        ),
        "destination_bucket": (
            str(payload["destination_bucket"])
            if isinstance(payload.get("destination_bucket"), str)
            else None
        ),
        "destination_path": (
            str(payload["destination_path"])
            if isinstance(payload.get("destination_path"), str)
            else None
        ),
        "reservation_id": (
            str(payload["reservation_id"])
            if isinstance(payload.get("reservation_id"), str)
            else None
        ),
        "declared_category": (
            str(payload["declared_category"])
            if isinstance(payload.get("declared_category"), str)
            else None
        ),
        "attestation_policy_version": (
            str(payload["attestation_policy_version"])
            if isinstance(payload.get("attestation_policy_version"), str)
            else None
        ),
        "uploader_user_id": (
            str(payload["uploader_user_id"])
            if isinstance(payload.get("uploader_user_id"), str)
            else None
        ),
        "review_approved": review_approved,
        "content_class": content_class,
        "crash_after": (
            str(payload["crash_after"])
            if isinstance(payload.get("crash_after"), str)
            else None
        ),
        "status": "scan_pending",
        "scan_result": None,
        "detail": "",
    }


def _crawl_graph_input_from_job(job: IngestionJobRecord) -> IngestionCrawlState:
    """Build crawl graph input from durable job payload."""

    payload = job.payload_ref
    return {
        "job_id": str(job.id),
        "lease_token": job.lease_token or "",
        "source_id": (
            str(payload["source_id"])
            if isinstance(payload.get("source_id"), str)
            else None
        ),
        "version_id": str(job.version_id) if job.version_id else None,
        "operation_key": str(payload.get("operation_key", job.job_kind)),
        "content_class": str(payload.get("content_class", "real_company")),
        "graph_eligible": bool(payload.get("graph_eligible", False)),
        "attestation_policy_version": (
            str(payload["attestation_policy_version"])
            if isinstance(payload.get("attestation_policy_version"), str)
            else None
        ),
        "status": "crawl_pending",
        "pages_fetched": 0,
        "crawl_run_id": None,
        "detail": "",
    }


def _index_graph_input_from_job(job: IngestionJobRecord) -> IngestionIndexState:
    """Build hybrid indexing graph input from durable job payload."""

    payload = job.payload_ref
    return {
        "job_id": str(job.id),
        "lease_token": job.lease_token or "",
        "document_id": str(job.document_id) if job.document_id else None,
        "version_id": str(job.version_id) if job.version_id else None,
        "operation_key": str(payload.get("operation_key", job.job_kind)),
        "storage_bucket": (
            str(payload["storage_bucket"])
            if isinstance(payload.get("storage_bucket"), str)
            else None
        ),
        "storage_path": (
            str(payload["storage_path"])
            if isinstance(payload.get("storage_path"), str)
            else None
        ),
        "content_hash": (
            str(payload["content_hash"])
            if isinstance(payload.get("content_hash"), str)
            else None
        ),
        "byte_size": (
            int(payload["byte_size"])
            if isinstance(payload.get("byte_size"), int)
            else None
        ),
        "media_type": (
            str(payload["media_type"])
            if isinstance(payload.get("media_type"), str)
            else None
        ),
        "filename": (
            str(payload["filename"])
            if isinstance(payload.get("filename"), str)
            else None
        ),
        "document_title": (
            str(payload["document_title"])
            if isinstance(payload.get("document_title"), str)
            else None
        ),
        "declared_category": (
            str(payload["declared_category"])
            if isinstance(payload.get("declared_category"), str)
            else None
        ),
        "attestation_policy_version": (
            str(payload["attestation_policy_version"])
            if isinstance(payload.get("attestation_policy_version"), str)
            else None
        ),
        "review_approved": bool(payload.get("review_approved", False)),
        "content_class": str(payload.get("content_class", "real_company")),
        "graph_eligible": bool(payload.get("graph_eligible", False)),
        "crawl_run_id": (
            str(payload["crawl_run_id"])
            if isinstance(payload.get("crawl_run_id"), str)
            else None
        ),
        "status": "index_pending",
        "chunk_set_hash": None,
        "bm25_job_id": None,
        "detail": "",
    }
