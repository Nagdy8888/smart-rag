"""Worker process entrypoint."""

from __future__ import annotations

from smart_rag_core.observability.error_telemetry import (
    configure_error_telemetry,
    flush_error_telemetry,
)
from smart_rag_core.observability.langsmith_tracing import configure_langsmith
from smart_rag_core.observability.logging import configure_json_logging
from smart_rag_core.settings import WorkerSettings, load_worker_settings

from smart_rag_worker.job_runner import run_worker


def main() -> int:
    """Start the worker process.

    Returns:
        Process exit code from :func:`run_worker`, or ``0`` when queue
        processing is unconfigured and ``WORKER_ONCE`` is set.

    Side Effects:
        Configures structured logging, LangSmith hide/tracing flags, optional
        GlitchTip and Grafana export, and runs the poll/claim lifecycle when
        ``SUPABASE_DB_URL`` is configured. Flushes error telemetry on exit.
    """

    settings = load_worker_settings()
    configure_json_logging(
        service=settings.service_name,
        environment=settings.app_env.value,
        level=settings.log_level.value,
    )
    configure_langsmith(settings)
    configure_error_telemetry(settings)
    try:
        return _run_configured_worker(settings)
    finally:
        flush_error_telemetry(timeout_seconds=2.0)


def _run_configured_worker(settings: WorkerSettings) -> int:
    """Run the queue loop after logging and telemetry are configured.

    Args:
        settings: Validated worker settings.

    Returns:
        Process exit code from :func:`run_worker`, or ``0`` when queue
        processing is unconfigured and ``WORKER_ONCE`` is set.
    """

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
