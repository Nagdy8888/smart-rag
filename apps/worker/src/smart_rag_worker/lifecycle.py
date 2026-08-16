"""Worker lifecycle: poll, claim, heartbeat, invoke ingestion graphs."""

from __future__ import annotations

import asyncio
import logging
import socket
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor
from decimal import Decimal
from typing import Any
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
from smart_rag_core.jobs.exceptions import JobLeaseError, JobRepositoryError
from smart_rag_core.jobs.ingestion_repository import IngestionJobRepository
from smart_rag_core.retrieval.lightrag_adapter import (
    LightRagRuntimeAdapter,
    bind_process_runtime_adapter,
)
from smart_rag_core.schema.enums import JobErrorCategory
from smart_rag_core.schema.tables import IngestionJobRecord
from smart_rag_core.settings.worker import WorkerSettings

from smart_rag_worker.bm25_runner import Bm25WorkerLoop
from smart_rag_worker.graph_runner import GraphWorkerLoop
from smart_rag_worker.privileged_storage import load_worker_privileged_storage_secret

LOGGER = logging.getLogger(__name__)


class WorkerLifecycle:
    """Polls ingestion jobs and executes probe or scan/promote graphs."""

    def __init__(self, settings: WorkerSettings) -> None:
        """Capture immutable worker settings and compile durable graphs.

        Args:
            settings: Validated worker settings for this process.

        Side Effects:
            Opens a Postgres checkpointer pool when a database URL is
            configured. Runtime never calls ``PostgresSaver.setup()``.
            When ``LIGHTRAG_DB_URL`` is set, attaches the runtime LightRAG
            adapter without schema-admin ``initialize_storages``.
        """

        self._settings = settings
        self._stop_event = threading.Event()
        self._checkpointer: IngestionCheckpointer | None = None
        self._lightrag_adapter: LightRagRuntimeAdapter | None = None
        saver = None
        checkpoint_dsn = settings.resolved_checkpoint_dsn()
        if checkpoint_dsn is not None:
            self._checkpointer = open_ingestion_checkpointer(
                checkpoint_dsn,
                max_size=settings.worker_concurrency,
            )
            saver = self._checkpointer.saver
        if settings.lightrag_db_url is not None:
            self._lightrag_adapter = asyncio.run(
                bind_process_runtime_adapter(
                    dsn=settings.lightrag_db_url,
                    settings=settings,
                )
            )
        try:
            self._probe_graph = build_probe_ingestion_graph(checkpointer=saver)
            self._scan_graph = build_scan_promote_ingestion_graph(checkpointer=saver)
            self._crawl_graph = build_crawl_ingestion_graph(checkpointer=saver)
            self._index_graph = build_index_ingestion_graph(checkpointer=saver)
            self._bm25_loop = Bm25WorkerLoop(settings)
            self._graph_loop = GraphWorkerLoop(
                settings,
                adapter=self._lightrag_adapter,
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
            while not self._stop_event.is_set():
                in_flight = {future for future in in_flight if not future.done()}
                self._graph_loop.process_once()
                if len(in_flight) >= self._settings.worker_concurrency:
                    time.sleep(1)
                    continue
                job = self._claim_one()
                if job is None:
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
            asyncio.run(self._lightrag_adapter.finalize())
            self._lightrag_adapter = None
        if self._checkpointer is not None:
            self._checkpointer.close()
            self._checkpointer = None

    def _require_postgres_url(self) -> str:
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
        }

    def _run_config(self, job: IngestionJobRecord) -> dict[str, object]:
        """Build LangGraph runnable config keyed by ingestion ``job_id``.

        Args:
            job: Claimed ingestion job. ``thread_id`` equals ``job.id`` so a
                crashed worker resumes the same checkpoint thread.

        Returns:
            ``{"configurable": ...}`` mapping for ``graph.invoke`` / ``get_state``.
        """

        return {
            "configurable": {
                "thread_id": str(job.id),
                **self._graph_config(),
            }
        }

    def _invoke_graph(
        self,
        graph: Any,
        initial_input: dict[str, Any],
        config: dict[str, object],
        *,
        success_statuses: tuple[str, ...],
    ) -> dict[str, Any]:
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
            side effects remain idempotent under replay.
        """

        if self._checkpointer is None:
            result = graph.invoke(initial_input, config)  # pyright: ignore[reportUnknownMemberType]
            return dict(result)
        snapshot = graph.get_state(config)  # pyright: ignore[reportUnknownMemberType]
        next_nodes = tuple(snapshot.next or ())
        values = snapshot.values if isinstance(snapshot.values, dict) else {}
        if next_nodes:
            result = graph.invoke(None, config)  # pyright: ignore[reportUnknownMemberType]
        elif values.get("status") in success_statuses:
            result = values
        else:
            result = graph.invoke(initial_input, config)  # pyright: ignore[reportUnknownMemberType]
        return dict(result)

    def _claim_one(self) -> IngestionJobRecord | None:
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
        postgres_url = self._require_postgres_url()
        lease_token = job.lease_token
        if lease_token is None:
            LOGGER.error("claimed job %s missing lease token", job.id)
            return
        stop_heartbeat = threading.Event()

        def heartbeat_loop() -> None:
            while not stop_heartbeat.wait(
                timeout=self._settings.job_heartbeat_interval_seconds
            ):
                try:
                    with psycopg.connect(postgres_url) as connection:
                        connection.execute("SET ROLE app_worker")
                        repository = IngestionJobRepository(
                            connection,
                            lease_owner=self._lease_owner(),
                            lease_seconds=self._settings.job_lease_seconds,
                        )
                        repository.heartbeat(job.id, lease_token)
                        connection.commit()
                except JobLeaseError:
                    LOGGER.warning("heartbeat lost for job %s", job.id)
                    return

        heartbeat_thread = threading.Thread(
            target=heartbeat_loop,
            name=f"heartbeat-{job.id}",
            daemon=True,
        )
        heartbeat_thread.start()
        try:
            config = self._run_config(job)
            if job.job_kind == "scan_promote":
                graph_input = _scan_graph_input_from_job(job)
                result = self._invoke_graph(  # pyright: ignore[reportUnknownMemberType]
                    self._scan_graph,
                    graph_input,
                    config,
                    success_statuses=("promoted",),
                )
                success = result.get("status") == "promoted"
                detail = str(result.get("detail", "scan_promote_failed"))
            elif job.job_kind == "website_crawl":
                graph_input = _crawl_graph_input_from_job(job)
                result = self._invoke_graph(  # pyright: ignore[reportUnknownMemberType]
                    self._crawl_graph,
                    graph_input,
                    config,
                    success_statuses=("crawl_completed",),
                )
                success = result.get("status") == "crawl_completed"
                detail = str(result.get("detail", "website_crawl_failed"))
            elif job.job_kind == "hybrid_index":
                graph_input = _index_graph_input_from_job(job)
                result = self._invoke_graph(  # pyright: ignore[reportUnknownMemberType]
                    self._index_graph,
                    graph_input,
                    config,
                    success_statuses=("indexed",),
                )
                success = result.get("status") == "indexed"
                detail = str(result.get("detail", "hybrid_index_failed"))
            else:
                graph_input = _probe_graph_input_from_job(job)
                result = self._invoke_graph(  # pyright: ignore[reportUnknownMemberType]
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
                if success:
                    completed = repository.complete(job.id, lease_token)
                    self._true_up_budget(connection, completed)
                else:
                    repository.fail(
                        job.id,
                        lease_token,
                        error_category=JobErrorCategory.VALIDATION,
                        last_error=detail,
                    )
                connection.commit()
        except (JobLeaseError, JobRepositoryError, psycopg.Error) as exc:
            LOGGER.exception("job %s failed: %s", job.id, exc)
            self._fail_job(job.id, lease_token, str(exc))
        finally:
            stop_heartbeat.set()
            heartbeat_thread.join(timeout=5)

    def _fail_job(self, job_id: UUID, lease_token: str, message: str) -> None:
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
        except psycopg.Error:
            LOGGER.exception("unable to persist failure for job %s", job_id)

    def _true_up_budget(
        self,
        connection: psycopg.Connection,
        job: IngestionJobRecord,
    ) -> None:
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
        hostname = socket.gethostname()
        return f"{self._settings.worker_instance_id}@{hostname}"


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
        "content_class": str(payload.get("content_class", "synthetic")),
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
        "content_class": str(payload.get("content_class", "synthetic")),
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
