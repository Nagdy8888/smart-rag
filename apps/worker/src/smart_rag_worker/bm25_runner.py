"""BM25 projection worker loop."""

from __future__ import annotations

import logging
import threading
from uuid import UUID

import psycopg
from smart_rag_core.ingestion.bm25_projection import Bm25ProjectionService
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
        """Claim and process one BM25 job when configured."""

        postgres_url = self._postgres_url()
        parade_url = self._parade_url()
        if parade_url is None:
            return False
        with psycopg.connect(postgres_url) as supabase:
            supabase.execute("SET ROLE app_worker")
            repository = Bm25IndexJobRepository(
                supabase,
                lease_owner=self._lease_owner(),
                lease_seconds=self._settings.job_lease_seconds,
            )
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
            while not stop_heartbeat.wait(
                timeout=self._settings.job_heartbeat_interval_seconds
            ):
                try:
                    with psycopg.connect(postgres_url) as connection:
                        connection.execute("SET ROLE app_worker")
                        repository = Bm25IndexJobRepository(
                            connection,
                            lease_owner=self._lease_owner(),
                            lease_seconds=self._settings.job_lease_seconds,
                        )
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
            with psycopg.connect(postgres_url) as supabase, psycopg.connect(
                parade_url
            ) as parade:
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
                repository = Bm25IndexJobRepository(
                    connection,
                    lease_owner=self._lease_owner(),
                    lease_seconds=self._settings.job_lease_seconds,
                )
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

    def _postgres_url(self) -> str:
        if self._settings.supabase_db_url is None:
            raise JobRepositoryError("supabase_db_url_unconfigured")
        return self._settings.supabase_db_url.get_secret_value()

    def _parade_url(self) -> str | None:
        if self._settings.paradedb_url is None:
            return None
        return self._settings.paradedb_url.get_secret_value()

    def _lease_owner(self) -> str:
        import socket

        hostname = socket.gethostname()
        return f"{self._settings.worker_instance_id}@{hostname}"
