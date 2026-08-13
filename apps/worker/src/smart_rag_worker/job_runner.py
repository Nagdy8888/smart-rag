"""Job runner entrypoints for worker-owned queue processing."""

from __future__ import annotations

from smart_rag_core.settings import load_worker_settings

from smart_rag_worker.lifecycle import WorkerLifecycle


def run_worker() -> int:
    """Start the worker poll/claim lifecycle.

    Returns:
        Process exit code ``0`` on normal termination.
    """

    settings = load_worker_settings()
    lifecycle = WorkerLifecycle(settings)
    lifecycle.run_forever()
    return 0
