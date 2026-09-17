"""CLI that rescores full company Ask answers with the shared dual-metric scorer.

Live gold stays under gitignored ``.private-eval/``. Credentials are never
read by this rescore path.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping
from pathlib import Path

from smart_rag_core.evaluation.company_ask_regression import (
    AskRegressionConfigError,
    CompanyAskQuestion,
    load_private_gold,
    run_scored_questions,
    write_redacted_summary,
)
from smart_rag_core.evaluation.dual_metric import (
    RetrievalStageAttribution,
    SourceResolutionStage,
)


def main(argv: list[str] | None = None) -> int:
    """Rescore full-answer JSON through the shared dual-metric scorer.

    Args:
        argv: Optional CLI arguments.

    Returns:
        ``0`` on success, ``2`` on configuration failure.
    """

    parser = argparse.ArgumentParser(
        description=(
            "Rescore full company Ask answers. Pass complete answer text, "
            "never a truncated excerpt. Use a fresh conversation per question "
            "when collecting results."
        )
    )
    parser.add_argument(
        "--gold",
        type=Path,
        required=True,
        help="Gitignored .private-eval gold JSON array.",
    )
    parser.add_argument(
        "--answers",
        type=Path,
        required=True,
        help="JSON object of question id to full answer text.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        required=True,
        help="Redacted summary JSON destination.",
    )
    args = parser.parse_args(argv)
    try:
        questions = load_private_gold(args.gold)
        answers_payload = json.loads(args.answers.read_text(encoding="utf-8"))
        answers, stages, statuses, reasons = _parse_answers(answers_payload, questions)
        results = run_scored_questions(
            questions,
            answers=answers,
            stages=stages,
            answer_status=statuses,
            terminal_reason=reasons,
        )
        summary = write_redacted_summary(results, args.out)
    except (AskRegressionConfigError, OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"rescore_failed={exc}", file=sys.stderr)
        return 2
    print(
        "questions={questions} strict_pass={strict_pass} "
        "grounded_fact_pass={grounded_fact_pass} "
        "deadline_failures={deadline_failures}".format(**summary)
    )
    return 0


def _parse_answers(
    payload: object,
    questions: tuple[CompanyAskQuestion, ...],
) -> tuple[
    dict[str, str],
    dict[str, RetrievalStageAttribution],
    dict[str, str],
    dict[str, str],
]:
    """Parse full-answer JSON keyed by question id.

    Args:
        payload: JSON object.
        questions: Loaded gold questions.

    Returns:
        Answers, stages, statuses, and reasons.

    Raises:
        AskRegressionConfigError: If the payload is not an object.
    """

    del questions
    if not isinstance(payload, dict):
        raise AskRegressionConfigError("answers JSON must be an object")
    answers: dict[str, str] = {}
    stages: dict[str, RetrievalStageAttribution] = {}
    statuses: dict[str, str] = {}
    reasons: dict[str, str] = {}
    for key, raw in payload.items():
        question_id = str(key)
        if isinstance(raw, str):
            answers[question_id] = raw
            continue
        if not isinstance(raw, dict):
            raise AskRegressionConfigError("answer row must be a string or object")
        answers[question_id] = str(raw.get("answer_text", ""))
        if raw.get("status"):
            statuses[question_id] = str(raw["status"])
        if raw.get("reason"):
            reasons[question_id] = str(raw["reason"])
        stages[question_id] = _stage_from_mapping(raw.get("stages", {}))
    return answers, stages, statuses, reasons


def _stage_from_mapping(raw: object) -> RetrievalStageAttribution:
    """Parse optional stage attribution.

    Args:
        raw: JSON object or empty.

    Returns:
        Frozen stage attribution.
    """

    if not isinstance(raw, Mapping):
        return RetrievalStageAttribution()
    resolution = str(raw.get("source_resolution", "unscoped"))
    try:
        source_resolution = SourceResolutionStage(resolution)
    except ValueError:
        source_resolution = SourceResolutionStage.UNSCOPED
    return RetrievalStageAttribution(
        source_resolution=source_resolution,
        dense_hit=_optional_bool(raw.get("dense_hit")),
        bm25_hit=_optional_bool(raw.get("bm25_hit")),
        term_hit=_optional_bool(raw.get("term_hit")),
        fused_rank=_optional_int(raw.get("fused_rank")),
        rerank_rank=_optional_int(raw.get("rerank_rank")),
        rerank_fallback=(
            str(raw["rerank_fallback"]) if raw.get("rerank_fallback") else None
        ),
        post_mmr_rank=_optional_int(raw.get("post_mmr_rank")),
        coverage_score=_optional_float(raw.get("coverage_score")),
        correction_outcome=str(raw.get("correction_outcome", "none")),
        fused_count=int(raw.get("fused_count", 0) or 0),
        verifier_status=(
            str(raw["verifier_status"]) if raw.get("verifier_status") else None
        ),
        retrieval_empty=bool(raw.get("retrieval_empty", False)),
    )


def _optional_bool(value: object) -> bool | None:
    """Return a boolean or None.

    Args:
        value: JSON value.

    Returns:
        Boolean when provided, otherwise None.
    """

    if value is None:
        return None
    return bool(value)


def _optional_int(value: object) -> int | None:
    """Return an int or None.

    Args:
        value: JSON value.

    Returns:
        Integer when provided, otherwise None.
    """

    if value is None or value == "":
        return None
    return int(value)


def _optional_float(value: object) -> float | None:
    """Return a float or None.

    Args:
        value: JSON value.

    Returns:
        Float when provided, otherwise None.
    """

    if value is None or value == "":
        return None
    return float(value)


if __name__ == "__main__":
    raise SystemExit(main())
