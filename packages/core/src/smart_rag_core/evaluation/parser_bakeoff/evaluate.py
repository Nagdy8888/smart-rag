"""Version-scoped retrieval helpers for the bake-off."""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from smart_rag_core.evaluation.parser_bakeoff.constants import ANYDOC_LANE, CURRENT_LANE
from smart_rag_core.evaluation.parser_bakeoff.mapping import (
    fact_chunk_ids_for_case,
    gold_ids_for_case,
)
from smart_rag_core.evaluation.parser_bakeoff.metrics import recall_hit, reciprocal_rank
from smart_rag_core.evaluation.parser_bakeoff.models import (
    BakeoffError,
    GoldMap,
    LaneAgentScore,
    LaneRetrieveScore,
    NeutralCase,
)
from smart_rag_core.evaluation.private_pdf.agent_scores import (
    citation_completeness,
    citation_precision,
)
from smart_rag_core.evaluation.private_pdf.schema import (
    PrivatePdfCase,
    PrivatePdfLabeledCase,
    PrivatePdfQueryClass,
)
from smart_rag_core.retrieval.coverage import CoverageDecision
from smart_rag_core.retrieval.hybrid_run import HybridRunResult


def labeled_for_lane(
    cases: tuple[NeutralCase, ...],
    mapping: GoldMap,
) -> tuple[PrivatePdfLabeledCase, ...]:
    """Bind neutral cases to one lane's approved gold chunk ids.

    Args:
        cases: Neutral cases.
        mapping: Approved gold map.

    Returns:
        Labeled cases for ``PdfEvalRuntime``.

    Raises:
        BakeoffError: When the map is not approved.
    """

    if not mapping.approved:
        raise BakeoffError("gold_unapproved", "gold map is not approved")
    labeled: list[PrivatePdfLabeledCase] = []
    for case in cases:
        gold = gold_ids_for_case(mapping, case.case_id)
        labeled.append(
            PrivatePdfLabeledCase(
                meta=PrivatePdfCase(
                    case_id=case.case_id,
                    split=case.split,
                    source_family_id=case.source_family_id,
                    query_class=case.query_class,
                    chunk_ids=gold,
                    page_numbers=case.page_numbers,
                    required_terms=case.required_terms,
                    expected_profile_id=case.expected_profile_id,
                    expected_scope=case.expected_scope,
                    expected_refusal=case.expected_refusal,
                    acl_actor_id=case.acl_actor_id,
                    human_approved=case.human_approved,
                    generated_only=False,
                    reviewer=case.reviewer,
                ),
                question=case.question,
                expected_answer=case.expected_answer,
                atomic_facts=case.atomic_facts,
            )
        )
    return tuple(labeled)


def assert_version_scoped(
    result: HybridRunResult,
    *,
    allowed_chunk_ids: frozenset[UUID],
    version_id: UUID,
    foreign_chunk_ids: frozenset[UUID],
) -> int:
    """Fail closed when retrieval crosses lane or version boundaries.

    Args:
        result: Hybrid retrieve result.
        allowed_chunk_ids: Chunk ids belonging to this lane version.
        version_id: Lane version.
        foreign_chunk_ids: Chunk ids belonging to the other lane.

    Returns:
        Cross-lane leak count (always ``0`` when the function returns).

    Raises:
        BakeoffError: When a ranked or evidence id is out of scope.
    """

    for chunk_id in result.ranked_ids:
        if chunk_id in foreign_chunk_ids:
            raise BakeoffError("cross_lane_id", "ranked id escaped version scope")
        if allowed_chunk_ids and chunk_id not in allowed_chunk_ids:
            raise BakeoffError("version_scope", "ranked id is not in the lane version")
    for unit in result.evidence:
        if unit.version_id != version_id:
            raise BakeoffError("version_scope", "evidence version mismatch")
        if unit.chunk_id in foreign_chunk_ids:
            raise BakeoffError("cross_lane_id", "evidence id escaped version scope")
        if allowed_chunk_ids and unit.chunk_id not in allowed_chunk_ids:
            raise BakeoffError("version_scope", "evidence id is not in the lane version")
    return 0


def score_retrieve(
    case: NeutralCase,
    result: HybridRunResult,
    *,
    gold_ids: Sequence[UUID],
    locator_available: bool,
    cross_lane_leaks: int,
    acl_leak: bool,
) -> LaneRetrieveScore:
    """Score one retrieval without storing question text.

    Args:
        case: Neutral case.
        result: Hybrid result.
        gold_ids: Lane gold chunk ids.
        locator_available: Whether physical PDF locators exist.
        cross_lane_leaks: Leak count.
        acl_leak: ACL leak flag.

    Returns:
        Per-case retrieval score.
    """

    refused = result.coverage.decision is CoverageDecision.REFUSE
    recall: bool | None
    if case.expected_refusal:
        recall = None
    else:
        recall = recall_hit(result.ranked_ids, gold_ids, 10) if gold_ids else False
    exact = None
    if case.query_class == PrivatePdfQueryClass.EXACT_ACRONYM.value:
        exact = recall_hit(result.ranked_ids, gold_ids, 5) if gold_ids else False
    alias = None
    if case.required_terms:
        alias = recall_hit(result.ranked_ids, gold_ids, 10) if gold_ids else False
    locator_ok = False
    if locator_available and gold_ids:
        locator_ok = all(item in set(result.ranked_ids[:12]) for item in gold_ids)
        evidence_pages = tuple(
            unit.locator.page_number
            for unit in result.evidence
            if unit.locator.page_number is not None
        )
        if case.page_numbers and evidence_pages:
            locator_ok = locator_ok and bool(set(case.page_numbers) & set(evidence_pages))
    return LaneRetrieveScore(
        case_id=case.case_id,
        recall_hit_at_10=recall,
        exact_hit_at_5=exact,
        alias_hit_at_10=alias,
        reciprocal_rank=reciprocal_rank(result.ranked_ids, gold_ids),
        locator_ok=locator_ok,
        locator_available=locator_available,
        refusal_ok=case.expected_refusal == refused,
        first_evidence_ms=result.first_evidence_ms,
        bm25_fallback=str(result.fallback_reason),
        rerank_call_count=result.rerank_call_count,
        ranked_id_count=len(result.ranked_ids),
        cross_lane_leaks=cross_lane_leaks,
        acl_leak=acl_leak,
    )


def score_agent(
    case: NeutralCase,
    mapping: GoldMap,
    *,
    cited_ids: Sequence[UUID],
    judge_status: str,
    faithfulness: float | None,
    refused: bool,
    answer_calls: int,
    judge_calls: int,
    input_tokens: int,
    output_tokens: int,
    cost_usd: float | None,
    budget_failed: bool,
) -> LaneAgentScore:
    """Score one answer/judge pair without storing answer text.

    Args:
        case: Neutral case.
        mapping: Approved gold map.
        cited_ids: Cited chunk ids.
        judge_status: ``complete`` or ``unscored``.
        faithfulness: Judge score when complete.
        refused: Observed refusal.
        answer_calls: Answer gateway calls.
        judge_calls: Judge calls.
        input_tokens: Counted input tokens.
        output_tokens: Counted output tokens.
        cost_usd: Ledger cost when proven.
        budget_failed: Budget or deadline failure.

    Returns:
        Per-case agent score.
    """

    gold_ids = gold_ids_for_case(mapping, case.case_id)
    fact_ids = fact_chunk_ids_for_case(mapping, case.case_id)
    status = judge_status if judge_status == "complete" else "unscored"
    return LaneAgentScore(
        case_id=case.case_id,
        citation_correctness=citation_precision(cited_ids, gold_ids),
        citation_completeness=citation_completeness(cited_ids, fact_ids),
        fact_completeness=citation_completeness(cited_ids, fact_ids),
        faithfulness=faithfulness if status == "complete" else None,
        judge_status=status,
        refusal_ok=case.expected_refusal == refused,
        invented_or_forbidden=sum(1 for item in cited_ids if item not in set(gold_ids)),
        answer_calls=answer_calls,
        judge_calls=judge_calls,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=cost_usd,
        budget_or_deadline_failed=budget_failed,
    )


def alternate_lane_order(index: int) -> tuple[str, str]:
    """Return sequential pair order that alternates starting lane.

    Args:
        index: Zero-based case index.

    Returns:
        Ordered lane ids for this case.
    """

    if index % 2 == 0:
        return CURRENT_LANE, ANYDOC_LANE
    return ANYDOC_LANE, CURRENT_LANE
