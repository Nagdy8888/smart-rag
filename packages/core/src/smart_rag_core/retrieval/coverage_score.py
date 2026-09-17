"""Deterministic HybridCoverage score, class thresholds, and answer/refusal."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from uuid import UUID

from smart_rag_core.evaluation.classes import QueryClass
from smart_rag_core.evaluation.schema import FailureStage, QueryType
from smart_rag_core.retrieval.coverage import (
    CoverageDecision,
    CoverageSignal,
    HybridCoverage,
)
from smart_rag_core.retrieval.frozen_profile import (
    COVERAGE_SCORE_BASELINE,
    coverage_threshold_for,
)
from smart_rag_core.retrieval.types import RetrievalCandidate
from smart_rag_core.text.arabic_normalize import normalize_arabic_v1

_REFUSAL_SIGNALS = frozenset(
    {
        CoverageSignal.WEAK_EVIDENCE,
        CoverageSignal.SCOPED_SUMMARY,
        CoverageSignal.MEDIA_LIMITATION,
        CoverageSignal.NEGATION_UNSCOPED,
        CoverageSignal.CONFLICT,
    }
)


@dataclass(frozen=True, slots=True)
class CoverageComponents:
    """Named coverage_score inputs from the Phase 4 formula.

    Attributes:
        required_term_entity_coverage: Fraction of required terms/entities
            present in authorized evidence. ``1.0`` when none are required.
        subquestion_coverage: Fraction of subquestions with a supporting unit.
        evidence_ratio: ``min(1, distinct_evidence_count / profile_minimum)``.
        support_confidence: Bounded reranker support or channel heuristic.
        distinct_evidence_count: Distinct authorized evidence units.
        profile_minimum: Class/type minimum from the plan.
    """

    required_term_entity_coverage: float
    subquestion_coverage: float
    evidence_ratio: float
    support_confidence: float
    distinct_evidence_count: int
    profile_minimum: int


def profile_minimum_for(query_type: QueryType, *, subquestion_count: int) -> int:
    """Return the plan's distinct-evidence minimum for one query type.

    Args:
        query_type: Profile query type.
        subquestion_count: Decomposition size; used for multi-part only.

    Returns:
        Simple ``1``, relationship ``2``, broad synthesis ``3``, multi-part
        one unit per subquestion (at least one).
    """

    if query_type is QueryType.RELATIONSHIP_MULTI_HOP:
        return 2
    if query_type is QueryType.BROAD_SUMMARY:
        return 3
    if query_type is QueryType.MULTI_PART:
        return max(1, subquestion_count)
    return 1


def support_confidence(
    *,
    rerank_top_support: float | None,
    exact_phrase_or_code: bool,
    winner_channel_count: int,
) -> float:
    """Return the bounded support feature. Not a calibrated probability.

    Args:
        rerank_top_support: Top rerank support in ``[0, 1]`` when rerank ran.
        exact_phrase_or_code: Winner is an exact phrase or code match.
        winner_channel_count: Independent channels that retrieved the winner.

    Returns:
        Rerank support when present, else ``1.0`` for exact or two-channel
        winners, else ``0.60``.
    """

    if rerank_top_support is not None:
        return max(0.0, min(1.0, rerank_top_support))
    if exact_phrase_or_code or winner_channel_count >= 2:
        return 1.0
    return 0.60


def coverage_term_key(text: str) -> str:
    """Return the retrieval-normalized key used for coverage term matching.

    Args:
        text: Required term, alias, or evidence token.

    Returns:
        ``arabic_norm_v1`` form, casefolded. Empty when the term vanishes.
    """

    return normalize_arabic_v1(text).casefold()


def exclude_source_selector_terms(
    required: Sequence[str],
    selectors: Sequence[str],
) -> tuple[str, ...]:
    """Drop required terms that only name a source selector.

    Naming an authorized document cannot force a coverage refusal. Codes
    and identifiers that contain digits stay required even when they also
    appear in a title.

    Args:
        required: Profile exact terms, codes, entities, and aliases.
        selectors: Authorized titles or high-confidence requested names.

    Returns:
        Required terms that must appear in answer evidence.
    """

    phrases: set[str] = set()
    tokens: set[str] = set()
    for raw in selectors:
        key = coverage_term_key(raw)
        if not key:
            continue
        phrases.add(key)
        tokens.update(part for part in key.split() if part)
    kept: list[str] = []
    seen: set[str] = set()
    for term in required:
        key = coverage_term_key(term)
        if not key or key in seen:
            continue
        seen.add(key)
        parts = [part for part in key.split() if part]
        selector_only = key in phrases or (
            bool(parts) and all(part in tokens for part in parts)
        )
        if selector_only and not any(any(ch.isdigit() for ch in part) for part in parts):
            continue
        kept.append(term)
    return tuple(kept)


def coverage_score(components: CoverageComponents) -> float:
    """Compute ``min`` of the four plan coverage terms.

    Args:
        components: Named formula inputs already clamped to ``[0, 1]``.

    Returns:
        Coverage score in ``[0, 1]``.
    """

    return min(
        components.required_term_entity_coverage,
        components.subquestion_coverage,
        components.evidence_ratio,
        components.support_confidence,
    )


def build_coverage_components(
    *,
    fused: tuple[RetrievalCandidate, ...],
    query_type: QueryType,
    required_terms: tuple[str, ...],
    matched_terms: tuple[str, ...],
    subquestion_count: int,
    supported_subquestions: int,
    rerank_top_support: float | None,
    exact_phrase_or_code: bool,
    winner_channel_count: int,
) -> CoverageComponents:
    """Build formula components from authorized evidence and profile fields.

    Args:
        fused: Authorized fused candidates.
        query_type: Profile query type.
        required_terms: Exact terms, codes, and entities that must appear.
        matched_terms: Subset of ``required_terms`` found in evidence.
        subquestion_count: Decomposition size.
        supported_subquestions: Subquestions with at least one unit.
        rerank_top_support: Optional rerank support.
        exact_phrase_or_code: Exact lookup winner.
        winner_channel_count: Channels that retrieved the fused winner.

    Returns:
        Named coverage components.
    """

    minimum = profile_minimum_for(query_type, subquestion_count=subquestion_count)
    documents = {item.document_id for item in fused}
    distinct = max(len(fused), len(documents))
    if required_terms:
        required_set = {coverage_term_key(item) for item in required_terms}
        required_set.discard("")
        matched_set = {coverage_term_key(item) for item in matched_terms}
        matched_set.discard("")
        term_coverage = (
            len(required_set & matched_set) / len(required_set) if required_set else 1.0
        )
    else:
        term_coverage = 1.0
    if subquestion_count <= 0:
        sub_coverage = 1.0
    else:
        sub_coverage = min(1.0, max(0, supported_subquestions) / subquestion_count)
    evidence_ratio = min(1.0, distinct / minimum) if minimum else 1.0
    support = support_confidence(
        rerank_top_support=rerank_top_support,
        exact_phrase_or_code=exact_phrase_or_code,
        winner_channel_count=winner_channel_count,
    )
    return CoverageComponents(
        required_term_entity_coverage=term_coverage,
        subquestion_coverage=sub_coverage,
        evidence_ratio=evidence_ratio,
        support_confidence=support,
        distinct_evidence_count=distinct,
        profile_minimum=minimum,
    )


def first_failing_stage(
    *,
    profile_ok: bool,
    pre_recheck_count: int,
    authorized_count: int,
    fused_count: int,
    context_ok: bool,
    coverage: HybridCoverage,
) -> FailureStage:
    """Attribute the first failing stage. Ranking is not blamed earlier.

    Args:
        profile_ok: Query profile fields were produced without a hard failure.
        pre_recheck_count: Channel IDs before authorization recheck.
        authorized_count: IDs that survived recheck.
        fused_count: Fused authorized candidates.
        context_ok: Parent/context expansion stayed authorized.
        coverage: Coverage object including numeric decision when present.

    Returns:
        First failing ``FailureStage``. ``NONE`` when the run may claim ranking.
    """

    if not profile_ok:
        return FailureStage.PROFILE
    if pre_recheck_count <= 0:
        return FailureStage.CANDIDATE
    if authorized_count <= 0:
        return FailureStage.AUTHORIZATION
    if fused_count <= 0:
        return FailureStage.FUSION
    if not context_ok:
        return FailureStage.CONTEXT
    if coverage.decision is CoverageDecision.REFUSE:
        return FailureStage.COVERAGE
    return FailureStage.NONE


_BLOCK_RANKING_CLAIMS = frozenset(
    {
        FailureStage.PROFILE,
        FailureStage.CANDIDATE,
        FailureStage.AUTHORIZATION,
        FailureStage.CONTEXT,
        FailureStage.FUSION,
    }
)


def ranking_claim_allowed(stage: FailureStage) -> bool:
    """Return whether ranking quality may be claimed for a run.

    Ranking is not blamed when profiling, candidate generation,
    authorization, fusion, or context already failed.

    Args:
        stage: First failing stage from :func:`first_failing_stage`.

    Returns:
        True only when earlier pipeline stages succeeded.
    """

    return stage not in _BLOCK_RANKING_CLAIMS


def attach_numeric_coverage(
    coverage: HybridCoverage,
    *,
    fused: tuple[RetrievalCandidate, ...],
    channel_hits: dict[UUID, frozenset[str]] | None,
    query_type: QueryType = QueryType.FACTUAL,
    query_class: QueryClass | None = None,
    required_terms: tuple[str, ...] = (),
    matched_terms: tuple[str, ...] = (),
    source_selectors: tuple[str, ...] = (),
    subquestion_count: int = 0,
    supported_subquestions: int | None = None,
    rerank_top_support: float | None = None,
    exact_phrase_or_code: bool = False,
    profile_ok: bool = True,
    pre_recheck_count: int | None = None,
    authorized_count: int | None = None,
    context_ok: bool = True,
) -> HybridCoverage:
    """Attach score, threshold, decision, and first-failing stage.

    Numeric weak-evidence refuse applies only when the existing signal is
    ``none`` or ``full_coverage``. Media, negation, conflict, scoped summary,
    and historical weak-evidence keep their signals. BM25 degradation stays
    visible and does not by itself refuse; the numeric threshold still can.

    Args:
        coverage: Signal coverage from Packet 4 rules.
        fused: Authorized fused candidates.
        channel_hits: Channels that retrieved each fused ID.
        query_type: Profile query type.
        query_class: Evaluation class for the frozen threshold.
        required_terms: Required codes/entities/terms.
        matched_terms: Required terms found in evidence.
        source_selectors: Authorized titles excluded from answer-evidence
            requirements.
        subquestion_count: Decomposition size. ``0`` means no decomposition
            and subquestion coverage is ``1.0``.
        supported_subquestions: Supported subquestions; defaults to ``0``
            when omitted so fused occupancy is never guessed as support.
        rerank_top_support: Optional rerank support.
        exact_phrase_or_code: Exact lookup winner.
        profile_ok: Profile stage succeeded.
        pre_recheck_count: Channel IDs before recheck.
        authorized_count: Recheck survivors.
        context_ok: Context expansion stayed authorized.

    Returns:
        New ``HybridCoverage`` with numeric fields populated.
    """

    winner_channels = 0
    if fused and channel_hits is not None:
        winner_channels = len(channel_hits.get(fused[0].chunk_id, frozenset()))
    elif fused:
        winner_channels = 1
    supported = supported_subquestions if supported_subquestions is not None else 0
    answer_terms = exclude_source_selector_terms(required_terms, source_selectors)
    answer_matched = exclude_source_selector_terms(matched_terms, source_selectors)
    components = build_coverage_components(
        fused=fused,
        query_type=query_type,
        required_terms=answer_terms,
        matched_terms=answer_matched,
        subquestion_count=subquestion_count,
        supported_subquestions=supported,
        rerank_top_support=rerank_top_support,
        exact_phrase_or_code=exact_phrase_or_code,
        winner_channel_count=winner_channels,
    )
    score = coverage_score(components)
    threshold = coverage_threshold_for(query_class)
    signal = coverage.signal
    notes = coverage.notes
    if signal in _REFUSAL_SIGNALS:
        decision = CoverageDecision.REFUSE
    elif not fused:
        decision = CoverageDecision.REFUSE
        if signal is not CoverageSignal.BM25_DEGRADED:
            signal = CoverageSignal.WEAK_EVIDENCE
            notes = (*notes, "no_authorized_evidence")
    elif score < threshold:
        decision = CoverageDecision.REFUSE
        notes = (*notes, "coverage_score_below_threshold")
        if signal in {CoverageSignal.NONE, CoverageSignal.FULL_COVERAGE}:
            signal = CoverageSignal.WEAK_EVIDENCE
    else:
        decision = CoverageDecision.ANSWER
    fused_count = len(fused)
    pre = pre_recheck_count if pre_recheck_count is not None else fused_count
    authorized = authorized_count if authorized_count is not None else fused_count
    staged = HybridCoverage(
        signal=signal,
        uncovered_headings=coverage.uncovered_headings,
        conflict_chunk_ids=coverage.conflict_chunk_ids,
        notes=notes,
        coverage_score=score,
        decision=decision,
        threshold=threshold,
        query_class=query_class.value if query_class is not None else None,
        term_coverage=components.required_term_entity_coverage,
        subquestion_coverage=components.subquestion_coverage,
        evidence_ratio=components.evidence_ratio,
        support_confidence=components.support_confidence,
    )
    stage = first_failing_stage(
        profile_ok=profile_ok,
        pre_recheck_count=pre,
        authorized_count=authorized,
        fused_count=fused_count,
        context_ok=context_ok,
        coverage=staged,
    )
    return HybridCoverage(
        signal=staged.signal,
        uncovered_headings=staged.uncovered_headings,
        conflict_chunk_ids=staged.conflict_chunk_ids,
        notes=staged.notes,
        coverage_score=staged.coverage_score,
        decision=staged.decision,
        threshold=staged.threshold,
        query_class=staged.query_class,
        term_coverage=staged.term_coverage,
        subquestion_coverage=staged.subquestion_coverage,
        evidence_ratio=staged.evidence_ratio,
        support_confidence=staged.support_confidence,
        first_failing_stage=stage,
        baseline=COVERAGE_SCORE_BASELINE,
    )
