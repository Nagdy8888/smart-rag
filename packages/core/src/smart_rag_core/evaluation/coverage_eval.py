"""Holdout-blind coverage/refusal metrics from labeled gold occupancy."""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast
from uuid import UUID, uuid4

from smart_rag_core.evaluation.classes import QueryClass
from smart_rag_core.evaluation.schema import (
    EvaluationCase,
    ExpectedRoute,
    FailureStage,
    QueryType,
    RefusalKind,
)
from smart_rag_core.retrieval.coverage import (
    CoverageDecision,
    CoverageSignal,
    HybridCoverage,
)
from smart_rag_core.retrieval.coverage_score import (
    build_coverage_components,
    coverage_score,
    first_failing_stage,
    ranking_claim_allowed,
)
from smart_rag_core.retrieval.frozen_profile import coverage_threshold_for
from smart_rag_core.retrieval.types import RetrievalCandidate


@dataclass(frozen=True, slots=True)
class CoverageCaseOutcome:
    """One labeled case scored by the frozen coverage rule.

    Attributes:
        case_id: Evaluation case id.
        query_class: Labeled class.
        gold_answer: Whether gold expects a supported answer.
        predicted: Model coverage decision.
        score: Coverage score.
        threshold: Class threshold.
        false_supported: Predicted answer when gold refuses.
        unnecessary_refusal: Predicted refuse when gold answers.
        first_failing_stage: Attribution; ranking is blocked for early stages.
        ranking_claim_allowed: False when profile/candidate/auth/context/fusion
            failed first.
    """

    case_id: str
    query_class: QueryClass
    gold_answer: bool
    predicted: CoverageDecision
    score: float
    threshold: float
    false_supported: bool
    unnecessary_refusal: bool
    first_failing_stage: FailureStage
    ranking_claim_allowed: bool


def gold_should_answer(case: EvaluationCase) -> bool:
    """Return whether the label expects a supported Hybrid answer.

    Args:
        case: Labeled evaluation case.

    Returns:
        True when the labeled route is Hybrid and refusal is ``none``.
        Combined, structured-table, and graph-inspection labels are not
        Hybrid supported-answer targets.
    """

    return (
        case.refusal_kind is RefusalKind.NONE
        and case.expected_route is ExpectedRoute.HYBRID
    )


def _field_list(value: object) -> tuple[str, ...]:
    """Return string items from a profile field value.

    Args:
        value: Profile field JSON value.

    Returns:
        String tuple.
    """

    if isinstance(value, list):
        texts: list[str] = []
        for raw_item in cast(list[object], value):
            if raw_item:
                texts.append(str(raw_item))
        return tuple(texts)
    if isinstance(value, str) and value:
        return (value,)
    return ()


def _query_type(case: EvaluationCase) -> QueryType:
    """Parse the labeled query type.

    Args:
        case: Labeled case.

    Returns:
        Query type enum. Unknown values become ``factual``.
    """

    raw = case.expected_profile.query_type.value
    try:
        return QueryType(str(raw))
    except ValueError:
        return QueryType.FACTUAL


def simulate_fused(case: EvaluationCase) -> tuple[RetrievalCandidate, ...]:
    """Build placeholder candidates from visible gold evidence links.

    Args:
        case: Labeled case.

    Returns:
        One synthetic authorized candidate per visible evidence link.
    """

    visible = [link for link in case.evidence_links if link.visible_to_actor]
    fused: list[RetrievalCandidate] = []
    for index, _link in enumerate(visible, start=1):
        fused.append(
            RetrievalCandidate(
                chunk_id=uuid4(),
                document_id=uuid4(),
                version_id=UUID(int=index),
                channel_rank=index,
                channel_score=1.0,
            )
        )
    return tuple(fused)


def specific_signal_refuses(case: EvaluationCase) -> bool:
    """Return whether profile signals refuse before the numeric threshold.

    Args:
        case: Labeled case.

    Returns:
        True for media dependence, unscoped negation, contradictory labels,
        or a whole-document summary without complete evidence.
    """

    profile = case.expected_profile
    if profile.media_dependence.value is True:
        return True
    if str(profile.negation_scope.value) == "set_complement":
        return True
    if case.refusal_kind is RefusalKind.CONTRADICTORY_AUTHORITY:
        return True
    if case.query_class is QueryClass.DOCUMENT_SUMMARY:
        inventory = _field_list(profile.document_scope.value)
        if inventory and len(simulate_fused(case)) < len(inventory):
            return True
    return False


def score_case(
    case: EvaluationCase, *, threshold: float | None = None
) -> CoverageCaseOutcome:
    """Score one case from gold occupancy features. Never reads holdout.

    Args:
        case: Development or qualification case.
        threshold: Optional override. Default is the frozen class threshold.

    Returns:
        Outcome with false-supported and unnecessary-refusal flags.
    """

    fused = simulate_fused(case)
    query_type = _query_type(case)
    required = _field_list(case.expected_profile.codes.value) + _field_list(
        case.expected_profile.entities.value
    )
    matched = required if fused else ()
    subquestions = _field_list(case.expected_profile.subquestions.value)
    sub_count = max(1, len(subquestions))
    supported = min(sub_count, len(fused)) if fused else 0
    exact = query_type is QueryType.EXACT_IDENTIFIER and bool(fused)
    components = build_coverage_components(
        fused=fused,
        query_type=query_type,
        required_terms=required,
        matched_terms=matched,
        subquestion_count=sub_count,
        supported_subquestions=supported,
        rerank_top_support=None,
        exact_phrase_or_code=exact,
        winner_channel_count=2 if exact else (1 if fused else 0),
    )
    score = coverage_score(components)
    resolved = (
        threshold if threshold is not None else coverage_threshold_for(case.query_class)
    )
    if specific_signal_refuses(case) or not fused or score < resolved:
        predicted = CoverageDecision.REFUSE
    else:
        predicted = CoverageDecision.ANSWER
    gold = gold_should_answer(case)
    coverage = HybridCoverage(signal=CoverageSignal.NONE, decision=predicted)
    stage = first_failing_stage(
        profile_ok=True,
        pre_recheck_count=len(case.evidence_links),
        authorized_count=len(fused),
        fused_count=len(fused),
        context_ok=True,
        coverage=coverage,
    )
    return CoverageCaseOutcome(
        case_id=case.case_id,
        query_class=case.query_class,
        gold_answer=gold,
        predicted=predicted,
        score=score,
        threshold=resolved,
        false_supported=predicted is CoverageDecision.ANSWER and not gold,
        unnecessary_refusal=predicted is CoverageDecision.REFUSE and gold,
        first_failing_stage=stage,
        ranking_claim_allowed=ranking_claim_allowed(stage),
    )


def class_metrics(
    outcomes: tuple[CoverageCaseOutcome, ...],
) -> dict[str, dict[str, float | int]]:
    """Aggregate per-class false-supported and unnecessary-refusal rates.

    Args:
        outcomes: Scored cases.

    Returns:
        Mapping of class name to counts and rates.
    """

    grouped: dict[str, list[CoverageCaseOutcome]] = {}
    for item in outcomes:
        grouped.setdefault(item.query_class.value, []).append(item)
    report: dict[str, dict[str, float | int]] = {}
    for name, rows in grouped.items():
        total = len(rows)
        false_supported = sum(item.false_supported for item in rows)
        unnecessary = sum(item.unnecessary_refusal for item in rows)
        answers = sum(item.gold_answer for item in rows)
        report[name] = {
            "n": total,
            "gold_answer": answers,
            "false_supported": false_supported,
            "unnecessary_refusal": unnecessary,
            "false_supported_rate": false_supported / total if total else 0.0,
            "unnecessary_refusal_rate": unnecessary / total if total else 0.0,
            "weighted_loss": (2.0 * false_supported + 1.0 * unnecessary) / total
            if total
            else 0.0,
        }
    return report


def weighted_loss(outcomes: tuple[CoverageCaseOutcome, ...]) -> float:
    """Return the Packet 6 weighted loss over all outcomes.

    Args:
        outcomes: Scored cases.

    Returns:
        ``(2 * false_supported + unnecessary_refusal) / n``.
    """

    total = len(outcomes)
    if total == 0:
        return 0.0
    false_supported = sum(item.false_supported for item in outcomes)
    unnecessary = sum(item.unnecessary_refusal for item in outcomes)
    return (2.0 * false_supported + 1.0 * unnecessary) / total


def first_failure_matrix(
    outcomes: tuple[CoverageCaseOutcome, ...],
) -> dict[str, int]:
    """Count first-failing stages. Ranking is not claimed for early failures.

    Args:
        outcomes: Scored cases.

    Returns:
        Mapping of ``FailureStage`` value to count.
    """

    counts: dict[str, int] = {}
    for item in outcomes:
        key = item.first_failing_stage.value
        counts[key] = counts.get(key, 0) + 1
    return counts


def sweep_thresholds(
    cases: list[EvaluationCase],
    *,
    candidates: tuple[float, ...] = (
        0.50,
        0.55,
        0.60,
        0.65,
        0.70,
        0.75,
        0.80,
        0.85,
        0.90,
    ),
) -> dict[str, float]:
    """Select one threshold per class on development data.

    Ties prefer the development baseline ``0.65``, then the higher (more
    conservative) threshold. Unequal RRF weights are not considered.

    Args:
        cases: Development cases only.
        candidates: Sweep grid.

    Returns:
        Mapping of query class to selected threshold.
    """

    selected: dict[str, float] = {}
    classes = {case.query_class for case in cases}
    for query_class in classes:
        subset = [case for case in cases if case.query_class is query_class]
        best_threshold = 0.65
        best_key: tuple[float, int, float] | None = None
        for threshold in candidates:
            outcomes = tuple(score_case(case, threshold=threshold) for case in subset)
            loss = weighted_loss(outcomes)
            key = (
                loss,
                0 if abs(threshold - 0.65) < 1e-12 else 1,
                -threshold,
            )
            if best_key is None or key < best_key:
                best_key = key
                best_threshold = threshold
        selected[query_class.value] = best_threshold
    return selected
