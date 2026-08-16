"""BM25 projection worker loop."""

from __future__ import annotations

import logging
import threading
from uuid import UUID

import psycopg
from smart_rag_core.ingestion.bm25_projection import Bm25ProjectionService
from smart_rag_core.ingestion.bm25_reconcile import Bm25ReconcileDecision
from smart_rag_core.jobs.bm25_repository import Bm25IndexJobRepository
from smart_rag_core.jobs.exceptions import JobLeaseError, JobRepositoryError
from smart_rag_core.schema.enums import JobErrorCategory
from smart_rag_core.settings.worker import WorkerSettings

LOGGER = logging.getLogger(__name__)


class Bm25WorkerLoop:
    """Poll and process BM25 projection jobs with lease semantics."""

    def __init__(self, settings: WorkerSettings) -> None:
        """Capture worker settings for BM25 polling."""

        self._settings = settings

    def process_once(self) -> bool:
        """Claim one pending job or reconcile one stuck processing job.

        Returns:
            True when a job was claimed (including fail paths). False when
            ParadeDB is unconfigured or the queues are idle.
        """

        if self._parade_url() is None:
            return False
        if self._reconcile_once():
            return True
        return self._process_claimed_once()

    def _reconcile_once(self) -> bool:
        """Lease one unowned processing job and complete only after verify.

        Returns:
            True when a stuck job was claimed.

        Side Effects:
            Completes the outbox only when ParadeDB verify still holds. Verify
            failure uses existing fail/retry/dead-letter semantics and never
            calls Hybrid Ready finalize.
        """

        postgres_url = self._postgres_url()
        parade_url = self._parade_url()
        if parade_url is None:
            return False
        with psycopg.connect(postgres_url) as supabase:
            supabase.execute("SET ROLE app_worker")
            repository = self._repository(supabase)
            job = repository.claim_reconcile()
            if job is None:
                supabase.rollback()
                return False
            supabase.commit()

        job_id = UUID(str(job["id"]))
        lease_token = str(job["lease_token"])
        version_id = UUID(str(job["version_id"]))
        operation = str(job["operation"])
        decision = Bm25ReconcileDecision(action="fail", reason="reconcile_not_run")
        try:
            with (
                psycopg.connect(postgres_url) as supabase,
                psycopg.connect(parade_url) as parade,
            ):
                supabase.execute("SET ROLE app_worker")
                parade.execute("SET ROLE paradedb_writer")
                service = Bm25ProjectionService(supabase, parade)
                if operation == "delete":
                    decision = service.reconcile_delete_job(version_id=version_id)
                else:
                    decision = service.reconcile_upsert_job(
                        version_id=version_id,
                        job_id=job_id,
                    )
                if decision.action == "complete":
                    supabase.commit()
                else:
                    supabase.rollback()

            with psycopg.connect(postgres_url) as connection:
                connection.execute("SET ROLE app_worker")
                repository = self._repository(connection)
                if decision.action == "complete":
                    repository.complete(job_id, lease_token)
                elif decision.action == "fail":
                    repository.fail(
                        job_id,
                        lease_token,
                        error_category=JobErrorCategory.TRANSIENT,
                        last_error=decision.reason,
                    )
                connection.commit()
            return True
        except (JobLeaseError, JobRepositoryError, psycopg.Error) as exc:
            LOGGER.exception("bm25 reconcile %s failed: %s", job_id, exc)
            self._fail_best_effort(
                postgres_url,
                job_id,
                lease_token,
                last_error="bm25_reconcile_exception",
            )
            return True

    def _process_claimed_once(self) -> bool:
        """Claim and process one pending or expired-lease BM25 job."""

        postgres_url = self._postgres_url()
        parade_url = self._parade_url()
        if parade_url is None:
            return False
        with psycopg.connect(postgres_url) as supabase:
            supabase.execute("SET ROLE app_worker")
            repository = self._repository(supabase)
            job = repository.claim()
            if job is None:
                supabase.rollback()
                return False
            supabase.commit()

        job_id = UUID(str(job["id"]))
        lease_token = str(job["lease_token"])
        version_id = UUID(str(job["version_id"]))
        operation = str(job["operation"])

        stop_heartbeat = threading.Event()

        def heartbeat_loop() -> None:
            """Renew the BM25 job lease until the worker signals stop."""

            while not stop_heartbeat.wait(
                timeout=self._settings.job_heartbeat_interval_seconds
            ):
                try:
                    with psycopg.connect(postgres_url) as connection:
                        connection.execute("SET ROLE app_worker")
                        repository = self._repository(connection)
                        repository.heartbeat(job_id, lease_token)
                        connection.commit()
                except JobLeaseError:
                    return

        heartbeat_thread = threading.Thread(
            target=heartbeat_loop,
            name=f"bm25-heartbeat-{job_id}",
            daemon=True,
        )
        heartbeat_thread.start()
        try:
            with (
                psycopg.connect(postgres_url) as supabase,
                psycopg.connect(parade_url) as parade,
            ):
                supabase.execute("SET ROLE app_worker")
                parade.execute("SET ROLE paradedb_writer")
                service = Bm25ProjectionService(supabase, parade)
                if operation == "delete":
                    success = service.process_delete_job(version_id=version_id)
                else:
                    success = service.process_upsert_job(
                        version_id=version_id,
                        job_id=job_id,
                    )
                if success:
                    supabase.commit()
                    parade.commit()
                else:
                    supabase.rollback()
                    parade.rollback()

            with psycopg.connect(postgres_url) as connection:
                connection.execute("SET ROLE app_worker")
                repository = self._repository(connection)
                if success:
                    repository.complete(job_id, lease_token)
                else:
                    repository.fail(
                        job_id,
                        lease_token,
                        error_category=JobErrorCategory.TRANSIENT,
                        last_error="bm25_projection_verification_failed",
                    )
                connection.commit()
            return True
        except (JobLeaseError, JobRepositoryError, psycopg.Error) as exc:
            LOGGER.exception("bm25 job %s failed: %s", job_id, exc)
            return True
        finally:
            stop_heartbeat.set()
            heartbeat_thread.join(timeout=5)

    def _fail_best_effort(
        self,
        postgres_url: str,
        job_id: UUID,
        lease_token: str,
        *,
        last_error: str,
    ) -> None:
        """Fail a leased job after an unexpected reconcile exception.

        Args:
            postgres_url: Worker database URL.
            job_id: Claimed outbox id.
            lease_token: Claimed lease token.
            last_error: Sanitized error recorded on the job.

        Side Effects:
            May schedule retry or dead-letter. Swallows lease loss.
        """

        try:
            with psycopg.connect(postgres_url) as connection:
                connection.execute("SET ROLE app_worker")
                repository = self._repository(connection)
                repository.fail(
                    job_id,
                    lease_token,
                    error_category=JobErrorCategory.TRANSIENT,
                    last_error=last_error,
                )
                connection.commit()
        except (JobLeaseError, JobRepositoryError, psycopg.Error):
            LOGGER.exception("bm25 reconcile fail path lost lease for %s", job_id)

    def _repository(self, connection: psycopg.Connection) -> Bm25IndexJobRepository:
        """Build a repository bound to one worker connection."""

        return Bm25IndexJobRepository(
            connection,
            lease_owner=self._lease_owner(),
            lease_seconds=self._settings.job_lease_seconds,
        )

    def _postgres_url(self) -> str:
        """Return the configured Supabase Postgres URL.

        Returns:
            Connection URL for worker-role SQL.

        Raises:
            JobRepositoryError: When ``supabase_db_url`` is unset.
        """

        if self._settings.supabase_db_url is None:
            raise JobRepositoryError("supabase_db_url_unconfigured")
        return self._settings.supabase_db_url.get_secret_value()

    def _parade_url(self) -> str | None:
        """Return the ParadeDB URL when BM25 projection is configured.

        Returns:
            ParadeDB connection URL, or ``None`` when unset.
        """

        if self._settings.paradedb_url is None:
            return None
        return self._settings.paradedb_url.get_secret_value()

    def _lease_owner(self) -> str:
        """Return the stable lease owner id for this worker process.

        Returns:
            ``{instance_id}@{hostname}`` owner string.
        """

        import socket

        hostname = socket.gethostname()
        return f"{self._settings.worker_instance_id}@{hostname}"
