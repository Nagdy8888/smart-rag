"""Worker lifecycle: poll, claim, heartbeat, invoke ingestion probe graph."""

from __future__ import annotations

import logging
import socket
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor
from decimal import Decimal
from uuid import UUID

import psycopg
from smart_rag_agents.ingestion.graph import IngestionProbeState, build_probe_ingestion_graph
from smart_rag_core.jobs.exceptions import JobLeaseError, JobRepositoryError
from smart_rag_core.jobs.ingestion_repository import IngestionJobRepository
from smart_rag_core.schema.enums import JobErrorCategory
from smart_rag_core.schema.tables import IngestionJobRecord
from smart_rag_core.settings.worker import WorkerSettings

LOGGER = logging.getLogger(__name__)


class WorkerLifecycle:
    """Polls ingestion jobs and executes the Phase 3 probe graph only."""

    def __init__(self, settings: WorkerSettings) -> None:
        """Capture immutable worker settings for one process lifetime."""

        self._settings = settings
        self._stop_event = threading.Event()
        self._graph = build_probe_ingestion_graph()

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
                if len(in_flight) >= self._settings.worker_concurrency:
                    time.sleep(1)
                    continue
                job = self._claim_one()
                if job is None:
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
        """Signal the poll loop to exit."""

        self._stop_event.set()

    def _require_postgres_url(self) -> str:
        postgres_url = self._settings.supabase_db_url
        if postgres_url is None:
            raise JobRepositoryError("supabase_db_url_unconfigured")
        return postgres_url.get_secret_value()

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
            graph_input = _graph_input_from_job(job)
            result = self._graph.invoke(  # pyright: ignore[reportUnknownMemberType]
                graph_input,
                config={
                    "configurable": {
                        "postgres_url": postgres_url,
                        "lease_owner": self._lease_owner(),
                        "job_lease_seconds": self._settings.job_lease_seconds,
                    }
                },
            )
            with psycopg.connect(postgres_url) as connection:
                connection.execute("SET ROLE app_worker")
                repository = IngestionJobRepository(
                    connection,
                    lease_owner=self._lease_owner(),
                    lease_seconds=self._settings.job_lease_seconds,
                )
                if result.get("status") == "probe_validated":
                    completed = repository.complete(job.id, lease_token)
                    self._true_up_budget(connection, completed)
                else:
                    repository.fail(
                        job.id,
                        lease_token,
                        error_category=JobErrorCategory.VALIDATION,
                        last_error=str(result.get("detail", "probe_failed")),
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


def _graph_input_from_job(job: IngestionJobRecord) -> IngestionProbeState:
    """Build graph input containing IDs/tokens and durable Storage refs only."""

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
