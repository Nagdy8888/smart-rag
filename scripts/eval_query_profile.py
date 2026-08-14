"""Run Packet 3 query-profile gates on development then qualification."""

from __future__ import annotations

import json
import sys

from smart_rag_core.query_profile.metrics import FieldScore, ProfileEvalReport
from smart_rag_core.query_profile.runner import evaluate_open_splits


def _serialize_score(score: FieldScore) -> dict[str, object]:
    """Convert one field score to JSON-safe values.

    Args:
        score: Metric row.

    Returns:
        JSON object.
    """

    return {
        "name": score.name,
        "value": round(score.value, 6),
        "threshold": score.threshold,
        "passed": score.passed,
    }


def _serialize_report(report: ProfileEvalReport) -> dict[str, object]:
    """Convert one split report to JSON-safe values.

    Args:
        report: Split evaluation report.

    Returns:
        JSON object without holdout case payloads.
    """

    return {
        "split": report.split,
        "case_count": report.case_count,
        "model_calls": report.model_calls,
        "passed": report.passed,
        "scores": [_serialize_score(item) for item in report.scores],
        "extra": [_serialize_score(item) for item in report.extra],
        "profile_failure_count": sum(
            stage == "profile" for stage in report.first_failures.values()
        ),
    }


def main() -> int:
    """Score open splits and exit nonzero when a signed gate misses.

    Returns:
        ``0`` when development and qualification pass; ``1`` otherwise.

    Side Effects:
        Writes a JSON summary to stdout. Holdout is not loaded.
    """

    development, qualification = evaluate_open_splits()
    payload = {
        "development": _serialize_report(development),
        "qualification": _serialize_report(qualification),
    }
    sys.stdout.write(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    if development.passed and qualification.passed:
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
