"""Worker process entrypoint.

Importing this module must not construct provider clients, database pools, or
queue consumers. The ``main`` callable exists for console-script and smoke
tests only.
"""

from __future__ import annotations


def main() -> int:
    """Start the foundation worker process contract.

    Returns:
        Process exit code ``0`` after printing that the worker is unconfigured.
        Does not claim jobs, process ingestion, or connect to external systems.

    Side Effects:
        Writes a single status line to stdout.
    """

    print(
        "smart-rag-worker: Phase 1 foundation scaffold; "
        "queue processing is unconfigured.",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
