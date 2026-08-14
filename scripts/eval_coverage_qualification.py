#!/usr/bin/env python3
"""Confirm frozen coverage thresholds once on qualification. Do not retune."""

from __future__ import annotations

import json
from pathlib import Path

from smart_rag_core.evaluation.coverage_eval import (
    class_metrics,
    first_failure_matrix,
    score_case,
    weighted_loss,
)
from smart_rag_core.evaluation.loader import load_qualification_cases
from smart_rag_core.retrieval.frozen_profile import (
    FROZEN_HYBRID_PROFILE_SHA256,
    load_frozen_profile,
)
from smart_rag_core.retrieval.profiles import HYBRID_DEFAULT_PROFILE_ID

_ROOT = Path(__file__).resolve().parents[1]
_REPORT = _ROOT / "docs" / "evaluation" / "COVERAGE_QUALIFICATION.md"


def main() -> int:
    """Write the one-shot qualification confirmation.

    Returns:
        ``0`` when false-supported rate is zero; ``1`` on a recorded fail.
        The report never relabels a fail as pass.

    Raises:
        RuntimeError: If qualification cases are missing.
    """

    profile = load_frozen_profile(HYBRID_DEFAULT_PROFILE_ID)
    cases = load_qualification_cases()
    if not cases:
        raise RuntimeError("qualification split is empty")
    outcomes = tuple(score_case(case) for case in cases)
    metrics = class_metrics(outcomes)
    loss = weighted_loss(outcomes)
    false_supported = sum(item.false_supported for item in outcomes)
    passed = false_supported == 0
    status = "PASS" if passed else "FAIL"
    stages = first_failure_matrix(outcomes)
    lines = [
        "---",
        "title: Coverage qualification confirmation",
        "owner: engineering-lead",
        "status: draft",
        "last-reviewed: 2026-08-14",
        "audience: engineering, reviewers",
        "---",
        "",
        "# Coverage qualification confirmation",
        "",
        "One frozen confirmation on qualification cases. Thresholds were not",
        "retuned. Holdout stays sealed.",
        "",
        "## Result",
        "",
        f"Recorded `{status}`. False supported `{false_supported}`.",
        "",
        f"- Profile `{profile.profile_id}` SHA-256 `{FROZEN_HYBRID_PROFILE_SHA256}`",
        f"- Qualification n `{len(cases)}`",
        f"- Weighted loss `{loss:.4f}`",
        f"- False supported `{false_supported}`",
        "",
        "| Class | n | Weighted loss | False supported | Unnecessary refusal |",
        "| --- | --- | --- | --- | --- |",
    ]
    for name in sorted(metrics):
        row = metrics[name]
        lines.append(
            f"| `{name}` | {row['n']} | {float(row['weighted_loss']):.3f} | "
            f"{int(row['false_supported'])} | {int(row['unnecessary_refusal'])} |"
        )
    lines.extend(
        [
            "",
            "## First-failing stage",
            "",
            "| Stage | Count |",
            "| --- | --- |",
        ]
    )
    for stage_name in sorted(stages):
        lines.append(f"| `{stage_name}` | {stages[stage_name]} |")
    lines.extend(
        [
            "",
            "A failed confirmation is evidence, not a license to tune on",
            "qualification or to relabel the run as pass.",
            "",
            "```mermaid",
            "flowchart LR",
            '  frozen["FrozenProfile"] --> qualification["QualificationOnce"]',
            '  qualification --> passFail["PassOrFailRecorded"]',
            '  passFail --> holdout["HoldoutSealed"]',
            "```",
            "",
            "[COVERAGE_CALIBRATION.md](./COVERAGE_CALIBRATION.md)",
            "[docs index](../README.md)",
            "",
        ]
    )
    _REPORT.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"status": status, "false_supported": false_supported}))
    print(f"Wrote {_REPORT.relative_to(_ROOT)}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
