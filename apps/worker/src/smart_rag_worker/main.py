"""Worker process entrypoint."""

from __future__ import annotations

from smart_rag_core.observability.langsmith_tracing import configure_langsmith
from smart_rag_core.observability.logging import configure_json_logging
from smart_rag_core.settings import load_worker_settings

from smart_rag_worker.job_runner import run_worker


def main() -> int:
    """Start the worker process.

    Returns:
        Process exit code from :func:`run_worker`, or ``0`` when queue
        processing is unconfigured and ``WORKER_ONCE`` is set.

    Side Effects:
        Configures structured logging, LangSmith hide/tracing flags, and runs
        the poll/claim lifecycle when ``SUPABASE_DB_URL`` is configured.
    """

    settings = load_worker_settings()
    configure_json_logging(
        service=settings.service_name,
        environment=settings.app_env.value,
        level=settings.log_level.value,
    )
    configure_langsmith(settings)
    if settings.supabase_db_url is None:
        print(
            "smart-rag-worker: SUPABASE_DB_URL unset; queue processing idle",
            flush=True,
        )
        if settings.worker_once:
            return 0
    return run_worker()


if __name__ == "__main__":
    raise SystemExit(main())
