"""Classify old-API/new-schema smoke without completing Packet 7."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from smart_rag_core.release.old_api_smoke import (
    evaluate_old_api_new_schema_smoke,
    running_api_image_id,
)
from smart_rag_core.release.packet2 import PACKET1_EXPECTED_IMAGE_IDS

REPO_ROOT = Path(__file__).resolve().parents[2]


def main(argv: list[str] | None = None) -> int:
    """Evaluate the drain smoke and fail only on Failed.

    Missing ``SMART_RAG_OLD_API_IMAGE`` is Blocked (exit 0, recorded).
    Pointing the env at the running API slot is Failed (exit 1).
    When Packet 1 freeze is invalidated, the running Compose ``api`` image
    is the current slot that must be restored after the drain.

    Args:
        argv: Optional argument vector excluding the program name.

    Returns:
        ``0`` for Passed or Blocked. ``1`` for Failed.
    """

    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args(argv)
    freeze = running_api_image_id(REPO_ROOT) or PACKET1_EXPECTED_IMAGE_IDS["api"]
    outcome = evaluate_old_api_new_schema_smoke(
        REPO_ROOT,
        freeze_api_id=freeze,
    )
    print(
        "old_api_new_schema_smoke "
        f"classification={outcome.classification} "
        f"smoke_ran={outcome.smoke_ran} "
        f"restored_freeze={outcome.restored_freeze}",
        flush=True,
    )
    if outcome.classification == "Failed":
        sys.stderr.write(f"{outcome.reason}\n")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
