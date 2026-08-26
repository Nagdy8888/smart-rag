"""LangSmith evaluator factories and optional judge wiring."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any, Literal, cast

from smart_rag_core.evaluation.agent_eval.mapping import (
    parse_reference,
    parse_target_output,
)
from smart_rag_core.evaluation.agent_eval.schema import (
    AgentEvalOutput,
    AgentEvalReference,
    AgentJudgeResult,
    EvaluatorResult,
    LangSmithEvaluator,
)
from smart_rag_core.evaluation.agent_eval.scorers import (
    score_acl_leak_free,
    score_answer_reference_overlap,
    score_bounds_respected,
    score_citation_precision,
    score_citation_recall,
    score_profile_fields_correct,
    score_refusal_correct,
    score_route_correct,
    score_target_completed,
)


def _evaluator(
    key: str,
    score_fn: Callable[[AgentEvalOutput, AgentEvalReference], float],
    *,
    comment: str,
) -> LangSmithEvaluator:
    """Build one LangSmith evaluator callback.

    Args:
        key: Stable evaluator key.
        score_fn: Deterministic scorer.
        comment: Bounded comment without source text.

    Returns:
        Callback compatible with ``Client.evaluate``.
    """

    def _run(run: Any, example: Any) -> EvaluatorResult:
        """Score one LangSmith run against its example reference.

        Args:
            run: LangSmith run with ``outputs``.
            example: LangSmith example with ``outputs``.

        Returns:
            Evaluator dict with ``key``, ``score``, and ``comment``.
        """

        outputs = _run_outputs(run)
        reference = parse_reference(_example_outputs(example))
        output = parse_target_output(outputs)
        score = score_fn(output, reference)
        return {"key": key, "score": score, "comment": comment}

    _run.__name__ = f"eval_{key}"
    _run.__qualname__ = f"eval_{key}"
    return _run


def deterministic_evaluators() -> tuple[LangSmithEvaluator, ...]:
    """Return the pinned deterministic LangSmith evaluators.

    Returns:
        Ordered evaluator callbacks. ``answer_reference_overlap`` is labeled
        diagnostic in its comment and is not a release gate.
    """

    return (
        _evaluator(
            "route_correct",
            score_route_correct,
            comment="effective route equals labeled route, with refusal aliases",
        ),
        _evaluator(
            "refusal_correct",
            score_refusal_correct,
            comment="refusal or complete-answer behavior matches labeled truth",
        ),
        _evaluator(
            "citation_precision",
            score_citation_precision,
            comment="cited ids versus visible gold; empty/empty=1",
        ),
        _evaluator(
            "citation_recall",
            score_citation_recall,
            comment="visible gold coverage; empty/empty=1",
        ),
        _evaluator(
            "acl_leak_free",
            score_acl_leak_free,
            comment="hard failure when cited or selected ids are forbidden",
        ),
        _evaluator(
            "profile_fields_correct",
            lambda output, reference: score_profile_fields_correct(output, reference)[
                0
            ],
            comment="preparation fields versus frozen expected profile",
        ),
        _evaluator(
            "bounds_respected",
            lambda output, _reference: score_bounds_respected(output),
            comment="deadline and remaining ceilings stayed non-negative",
        ),
        _evaluator(
            "answer_reference_overlap",
            score_answer_reference_overlap,
            comment="diagnostic token overlap; not a release gate",
        ),
        _evaluator(
            "target_completed",
            lambda output, _reference: score_target_completed(output),
            comment="infrastructure errors score 0 and remain visible",
        ),
    )


def judge_evaluator(
    judge: Callable[[AgentEvalOutput, AgentEvalReference], AgentJudgeResult],
    *,
    metric: Literal["correctness", "groundedness", "refusal_quality"],
) -> LangSmithEvaluator:
    """Wrap one judge metric as a LangSmith evaluator.

    Args:
        judge: One-call-per-case judge. Failures must not raise.
        metric: Which judge field to export.

    Returns:
        Evaluator callback. Judge failure is a named evaluator failure.
    """

    def _run(run: Any, example: Any) -> EvaluatorResult:
        """Export one judge metric, or a named failure score of 0.

        Args:
            run: LangSmith run.
            example: LangSmith example.

        Returns:
            Evaluator dict.
        """

        output = parse_target_output(_run_outputs(run))
        reference = parse_reference(_example_outputs(example))
        result = judge(output, reference)
        if result.failed:
            return {
                "key": f"judge_{metric}",
                "score": 0.0,
                "comment": result.failure_kind or "judge_failed",
            }
        return {
            "key": f"judge_{metric}",
            "score": getattr(result, metric),
            "comment": "optional_llm_judge",
        }

    _run.__name__ = f"eval_judge_{metric}"
    return _run


def _run_outputs(run: Any) -> dict[str, Any]:
    """Extract outputs from a LangSmith run-like object.

    Args:
        run: Run object or mapping.

    Returns:
        Outputs mapping.
    """

    if isinstance(run, Mapping):
        mapped = cast(Mapping[str, object], run)
        outputs = mapped.get("outputs")
        if isinstance(outputs, Mapping):
            return dict(cast(Mapping[str, Any], outputs))
        return dict(mapped)
    outputs = getattr(run, "outputs", None)
    if isinstance(outputs, Mapping):
        return dict(cast(Mapping[str, Any], outputs))
    return {}


def _example_outputs(example: Any) -> dict[str, Any]:
    """Extract reference outputs from a LangSmith example-like object.

    Args:
        example: Example object or mapping.

    Returns:
        Outputs mapping.
    """

    if isinstance(example, Mapping):
        mapped = cast(Mapping[str, object], example)
        outputs = mapped.get("outputs")
        if isinstance(outputs, Mapping):
            return dict(cast(Mapping[str, Any], outputs))
        return dict(mapped)
    outputs = getattr(example, "outputs", None)
    if isinstance(outputs, Mapping):
        return dict(cast(Mapping[str, Any], outputs))
    return {}
