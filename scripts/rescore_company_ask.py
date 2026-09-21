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
from typing import cast

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
    typed_payload = cast(dict[object, object], payload)
    for key, raw in typed_payload.items():
        question_id = str(key)
        if isinstance(raw, str):
            answers[question_id] = raw
            continue
        if not isinstance(raw, dict):
            raise AskRegressionConfigError("answer row must be a string or object")
        row = _json_mapping(cast(object, raw))
        answers[question_id] = str(row.get("answer_text", ""))
        if row.get("status"):
            statuses[question_id] = str(row["status"])
        if row.get("reason"):
            reasons[question_id] = str(row["reason"])
        stages[question_id] = _stage_from_mapping(row.get("stages", {}))
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
    mapping = _json_mapping(cast(object, raw))
    resolution = str(mapping.get("source_resolution", "unscoped"))
    try:
        source_resolution = SourceResolutionStage(resolution)
    except ValueError:
        source_resolution = SourceResolutionStage.UNSCOPED
    return RetrievalStageAttribution(
        source_resolution=source_resolution,
        dense_hit=_optional_bool(mapping.get("dense_hit")),
        bm25_hit=_optional_bool(mapping.get("bm25_hit")),
        term_hit=_optional_bool(mapping.get("term_hit")),
        fused_rank=_optional_int(mapping.get("fused_rank")),
        rerank_rank=_optional_int(mapping.get("rerank_rank")),
        rerank_fallback=(
            str(mapping["rerank_fallback"]) if mapping.get("rerank_fallback") else None
        ),
        post_mmr_rank=_optional_int(mapping.get("post_mmr_rank")),
        coverage_score=_optional_float(mapping.get("coverage_score")),
        correction_outcome=str(mapping.get("correction_outcome", "none")),
        fused_count=_as_int(mapping.get("fused_count", 0)),
        verifier_status=(
            str(mapping["verifier_status"]) if mapping.get("verifier_status") else None
        ),
        retrieval_empty=bool(mapping.get("retrieval_empty", False)),
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
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        return int(value)
    raise ValueError("invalid_optional_int")


def _optional_float(value: object) -> float | None:
    """Return a float or None.

    Args:
        value: JSON value.

    Returns:
        Float when provided, otherwise None.
    """

    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        return float(value)
    raise ValueError("invalid_optional_float")


def _json_mapping(value: object) -> dict[str, object]:
    """Coerce JSON objects to a string-keyed mapping.

    Args:
        value: Parsed JSON value.

    Returns:
        String-keyed mapping, or empty when the value is not an object.
    """

    if not isinstance(value, Mapping):
        return {}
    typed = cast(Mapping[object, object], value)
    return {str(key): item for key, item in typed.items()}


def _as_int(value: object) -> int:
    """Coerce a JSON number to int.

    Args:
        value: Parsed JSON value.

    Returns:
        Integer, or ``0`` when the value is missing or not numeric.
    """

    if isinstance(value, bool) or value is None:
        return 0
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip():
        return int(value)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
