"""Worker process entrypoint.

Importing this module must not construct provider clients, database pools, or
queue consumers. The ``main`` callable exists for console-script and smoke
tests only.
"""

from __future__ import annotations

import os
import time


def main() -> int:
    """Start the foundation worker process contract.

    Returns:
        Process exit code ``0`` after a one-shot run when ``WORKER_ONCE=1``.
        Otherwise blocks forever so the container stays healthy without claiming
        queue processing (Phase 3 owns claiming).

    Side Effects:
        Writes a status line to stdout. Sleeps indefinitely unless ``WORKER_ONCE``.
    """

    print(
        "smart-rag-worker: Phase 1 foundation scaffold; "
        "queue processing is unconfigured.",
        flush=True,
    )
    if os.environ.get("WORKER_ONCE", "").lower() in {"1", "true", "yes"}:
        return 0
    while True:
        time.sleep(3600)


if __name__ == "__main__":
    raise SystemExit(main())
