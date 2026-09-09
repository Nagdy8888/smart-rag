"""Print count-only ``[hybrid]`` lines from the laptop ingest log."""

from __future__ import annotations

import json
from pathlib import Path


def main() -> int:
    """Write ``[hybrid]`` messages to stdout. Never prints source text.

    Returns:
        Process exit code.
    """

    log = Path("logs/laptop-ingest-worker.log")
    if not log.is_file():
        print("hybrid_log_missing")
        return 2
    count = 0
    for raw in log.read_text(encoding="utf-8", errors="replace").splitlines():
        if "[hybrid]" not in raw:
            continue
        message = raw
        try:
            payload = json.loads(raw)
            if isinstance(payload, dict) and isinstance(payload.get("message"), str):
                message = str(payload["message"])
        except json.JSONDecodeError:
            message = raw
        if "[hybrid]" in message:
            print(message)
            count += 1
    print(f"hybrid_line_count={count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
