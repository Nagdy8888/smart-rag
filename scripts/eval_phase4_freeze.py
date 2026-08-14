#!/usr/bin/env python3
"""Record Phase 4 Packet 8 freeze hashes without opening holdout labels."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

from smart_rag_core.evaluation.phase4_freeze import (
    build_phase4_freeze_report,
    render_freeze_markdown,
)

_ROOT = Path(__file__).resolve().parents[1]
_REPORT = _ROOT / "docs" / "evaluation" / "PHASE4_FREEZE.md"


def _git_head() -> str:
    """Return the current git commit SHA when available.

    Returns:
        40-character SHA, or ``unverified`` if git is unavailable.

    Side Effects:
        Runs ``git rev-parse HEAD`` in the repository root.
    """

    git = shutil.which("git")
    if git is None:
        return "unverified"
    try:
        completed = subprocess.run(  # noqa: S603
            [git, "rev-parse", "HEAD"],
            cwd=_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return "unverified"
    return completed.stdout.strip()


def main() -> int:
    """Write the freeze markdown and print JSON including git HEAD.

    Returns:
        ``0`` when the no-go freeze is recorded. ``1`` on freeze errors.

    Side Effects:
        Overwrites ``docs/evaluation/PHASE4_FREEZE.md``. Prints JSON to stdout.
        Does not enable or read sealed holdout labels.
    """

    report = build_phase4_freeze_report()
    _REPORT.write_text(render_freeze_markdown(report), encoding="utf-8")
    payload = report.model_dump(mode="json")
    payload["code_revision_git_sha"] = _git_head()
    sys.stdout.write(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
