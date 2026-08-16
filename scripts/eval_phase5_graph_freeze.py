#!/usr/bin/env python3
"""Record Phase 5 Packet 8 freeze hashes without opening holdout labels."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

from smart_rag_core.evaluation.graph_eval import (
    build_phase5_packet8_report,
    render_frozen_manifest_markdown,
    render_graph_eval_markdown,
)

_ROOT = Path(__file__).resolve().parents[1]
_MANIFEST = _ROOT / "docs" / "graph" / "FROZEN_GRAPH_MANIFEST.md"
_EVAL = _ROOT / "docs" / "evaluation" / "PHASE5_GRAPH_EVAL.md"


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
    """Write freeze and evaluation markdown and print JSON including git HEAD.

    Returns:
        ``0`` when the Packet 8 freeze is recorded. ``1`` on freeze errors.

    Side Effects:
        Overwrites ``docs/graph/FROZEN_GRAPH_MANIFEST.md`` and
        ``docs/evaluation/PHASE5_GRAPH_EVAL.md``. Prints JSON to stdout.
        Does not enable or read sealed holdout labels.
    """

    report = build_phase5_packet8_report()
    _MANIFEST.write_text(render_frozen_manifest_markdown(report), encoding="utf-8")
    _EVAL.write_text(render_graph_eval_markdown(report), encoding="utf-8")
    payload = report.model_dump(mode="json")
    payload["code_revision_git_sha"] = report.pins.get(
        "code_revision_git_sha", _git_head()
    )
    sys.stdout.write(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
