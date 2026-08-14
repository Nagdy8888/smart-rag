#!/usr/bin/env python3
"""Sweep coverage thresholds on development cases. Qualification is not used."""

from __future__ import annotations

import json
from pathlib import Path

from smart_rag_core.evaluation.coverage_eval import (
    class_metrics,
    first_failure_matrix,
    score_case,
    sweep_thresholds,
    weighted_loss,
)
from smart_rag_core.evaluation.loader import load_development_cases
from smart_rag_core.retrieval.frozen_profile import (
    COVERAGE_SCORE_BASELINE,
    FROZEN_HYBRID_PROFILE_SHA256,
    ROLLBACK_PROFILE_ID,
)

_ROOT = Path(__file__).resolve().parents[1]
_REPORT = _ROOT / "docs" / "evaluation" / "COVERAGE_CALIBRATION.md"


def main() -> int:
    """Write the development calibration report.

    Returns:
        Process exit code ``0``.

    Raises:
        RuntimeError: If development cases are missing.
    """

    cases = load_development_cases()
    if not cases:
        raise RuntimeError("development split is empty")
    selected = sweep_thresholds(cases)
    outcomes = tuple(score_case(case) for case in cases)
    metrics = class_metrics(outcomes)
    stages = first_failure_matrix(outcomes)
    rejected = {
        name: value
        for name, value in selected.items()
        if value + 1e-12 < COVERAGE_SCORE_BASELINE
    }
    lines = [
        "---",
        "title: Coverage and refusal calibration",
        "owner: engineering-lead",
        "status: draft",
        "last-reviewed: 2026-08-14",
        "audience: engineering, reviewers",
        "---",
        "",
        "# Coverage and refusal calibration",
        "",
        "Development-only sweep of `coverage_score` thresholds. Qualification",
        "is confirmed separately and is not a tuning set. Holdout stays sealed.",
        "",
        "Related: [HYBRID_RETRIEVAL_CONTRACT.md](../retrieval/HYBRID_RETRIEVAL_CONTRACT.md)",
        " · [HYBRID_TUNING.md](../retrieval/HYBRID_TUNING.md)",
        " · [COVERAGE_QUALIFICATION.md](./COVERAGE_QUALIFICATION.md)",
        " · [docs index](../README.md)",
        "",
        "## Formula",
        "",
        "```text",
        "coverage_score = min(",
        "  required_term_entity_coverage,",
        "  subquestion_coverage,",
        "  min(1, distinct_evidence_count / profile_minimum),",
        "  support_confidence",
        ")",
        "```",
        "",
        f"Development baseline `{COVERAGE_SCORE_BASELINE}`. False-supported",
        "answers carry loss weight 2; unnecessary refusals carry weight 1.",
        "Unequal RRF channel weights were **not selected** (no ranked-ID",
        "evidence to retune `rrf_k=60` or equal weights).",
        "",
        "## Frozen artifact",
        "",
        f"- Profile `hybrid_default_v1` SHA-256 `{FROZEN_HYBRID_PROFILE_SHA256}`",
        f"- Rollback id `{ROLLBACK_PROFILE_ID}` (Packet 5 signals only)",
        f"- Frozen threshold `{COVERAGE_SCORE_BASELINE}` for every class",
        "",
        "## Frozen thresholds at baseline",
        "",
        "Occupancy scores non-exact winners with `support_confidence=0.60`",
        "because channel mix is unknown. That value is the plan's weak-coverage",
        "feature, so a freeze below `0.65` would permit single-channel answers",
        "without rerank and would let a one-unit relationship score (`0.50`)",
        "pass the two-unit rule. Sweep values below the baseline are rejected.",
        "",
        "| Class | Frozen | Occupancy sweep | n | Weighted loss | False supported | Unnecessary refusal |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for name in sorted(metrics):
        row = metrics[name]
        swept = selected.get(name, COVERAGE_SCORE_BASELINE)
        lines.append(
            f"| `{name}` | {COVERAGE_SCORE_BASELINE:.2f} | {swept:.2f} | "
            f"{row['n']} | {float(row['weighted_loss']):.3f} | "
            f"{int(row['false_supported'])} | {int(row['unnecessary_refusal'])} |"
        )
    lines.extend(
        [
            "",
            f"Overall development weighted loss at frozen `{COVERAGE_SCORE_BASELINE}`: "
            f"`{weighted_loss(outcomes):.4f}` on `{len(cases)}` cases.",
            "",
            "## Rejected occupancy candidates",
            "",
        ]
    )
    if rejected:
        lines.append(
            "These occupancy-loss minima sit below the weak-coverage floor and "
            "were not frozen:"
        )
        lines.append("")
        lines.append("| Class | Rejected sweep | Reason |")
        lines.append("| --- | --- | --- |")
        for name in sorted(rejected):
            lines.append(
                f"| `{name}` | {rejected[name]:.2f} | below baseline {COVERAGE_SCORE_BASELINE:.2f} |"
            )
        lines.append("")
    else:
        lines.append("No occupancy sweep value fell below the `0.65` floor.")
        lines.append("")
    lines.extend(
        [
            "## First-failing stage",
            "",
            "| Stage | Count | Ranking claim allowed |",
            "| --- | --- | --- |",
        ]
    )
    ranking_blocked = {"profile", "candidate", "authorization", "context", "fusion"}
    for stage_name in sorted(stages):
        allowed = "no" if stage_name in ranking_blocked else "yes"
        lines.append(f"| `{stage_name}` | {stages[stage_name]} | {allowed} |")
    lines.extend(
        [
            "",
            "Ranking quality is not claimed when profile, candidate,",
            "authorization, fusion, or context failed first.",
            "",
            "## Sweep note",
            "",
            "Occupancy features are taken from visible gold evidence links and",
            "profile fields, not a live Hybrid run. Live ranked-ID recall for",
            "depth/skip tightening remains Packet 5 counterfactuals; this packet",
            "does not retune channel depths.",
            "",
            "```mermaid",
            "flowchart LR",
            '  development["DevelopmentCases"] --> sweep["ThresholdSweep"]',
            '  sweep --> freeze["FrozenProfile"]',
            '  freeze --> qualification["QualificationOnce"]',
            '  qualification --> holdout["HoldoutSealed"]',
            "```",
            "",
            "[docs index](../README.md)",
            "",
        ]
    )
    _REPORT.write_text("\n".join(lines), encoding="utf-8")
    print(
        json.dumps(
            {
                "swept": selected,
                "frozen": COVERAGE_SCORE_BASELINE,
                "rejected_below_baseline": rejected,
                "n": len(cases),
            },
            indent=2,
        )
    )
    print(f"Wrote {_REPORT.relative_to(_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
