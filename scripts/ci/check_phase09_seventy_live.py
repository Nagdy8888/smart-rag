"""Classify live 8-doc 70% pause without completing Packet 7."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from smart_rag_core.release.io import as_json_object
from smart_rag_core.release.old_api_smoke import issue_smoke_access_token
from smart_rag_core.release.packet4_seventy_live import measure_live_seventy_pause

REPO_ROOT = Path(__file__).resolve().parents[2]


def main(argv: list[str] | None = None) -> int:
    """Measure live Composite p95 and CPU peaks on the 8-doc subset.

    Missing Auth is Blocked (exit 0). A 70% busy-loop is not used.
    ``Passed`` means p95 held or the 70% trigger fired.

    Args:
        argv: Optional argument vector excluding the program name.

    Returns:
        ``0`` for Passed or Blocked. ``1`` for Failed live HTTP besides 401.
    """

    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args(argv)
    token = issue_smoke_access_token(REPO_ROOT)
    if token is None:
        sys.stderr.write("live 70% probe: local Auth bootstrap failed\n")
        return 0
    payload = measure_live_seventy_pause(REPO_ROOT, token=token)
    seventy_raw: object = payload.get("seventy_percent")
    classification = "Blocked"
    try:
        raw = as_json_object(seventy_raw).get("classification")
    except ValueError:
        raw = None
    if isinstance(raw, str):
        classification = raw
    print(
        "seventy_percent_pause "
        f"classification={classification} "
        f"cpu_peaks={payload.get('cpu_peaks')}",
        flush=True,
    )
    if classification == "Failed":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
