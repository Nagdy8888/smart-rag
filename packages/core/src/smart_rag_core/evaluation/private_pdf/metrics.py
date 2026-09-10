"""Private PDF retrieval gates. Occupancy and fused IDs are not Recall@K."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from uuid import UUID

from smart_rag_core.evaluation.private_pdf.schema import (
    PRIVATE_PDF_CLASS_MINIMUMS,
    PrivatePdfQueryClass,
)
from smart_rag_core.evaluation.ranked_ids import (
    QT_EVAL_002_LOCATOR_CORRECTNESS,
    QT_EVAL_006_RECALL_AT_10,
    QT_EVAL_007_EXACT_CODE_RECALL_AT_5,
    QT_EVAL_008_ALIAS_RECALL_AT_10,
    recall_hit_at_k,
)

NOT_APPLICABLE = "not_applicable"
HYBRID_RECALL_AT_10_GATE = QT_EVAL_006_RECALL_AT_10
EXACT_RECALL_AT_5_GATE = QT_EVAL_007_EXACT_CODE_RECALL_AT_5
ALIAS_RECALL_AT_10_GATE = QT_EVAL_008_ALIAS_RECALL_AT_10
LOCATOR_GATE = QT_EVAL_002_LOCATOR_CORRECTNESS
FIRST_EVIDENCE_P95_MS_GATE = 2000.0


@dataclass(frozen=True, slots=True)
class PrivatePdfRetrieveScore:
    """Per-case ranked-ID score. No question or excerpt text.

    Attributes:
        case_id: Case id hash.
        query_class: Overlay class token.
        recall_hit_at_10: Recall@10 on final ranked ids, or None for refusals.
        exact_hit_at_5: Exact-term hit at 5 when class is exact_acronym.
        alias_hit_at_10: Alias hit at 10 when required_terms are present.
        locator_ok: Selected locators match gold pages/chunk ids.
        expected_refusal: Gold refusal.
        refused: System refused.
        acl_leak: Unauthorized or forbidden id in ranked/cited evidence.
        first_evidence_ms: First evidence latency, when measured.
        rerank_call_count: Counted rerank calls.
        bm25_fallback: Named BM25 fallback, or ``none``.
        fused_hit_at_10: Occupancy hit on fused IDs. Not Recall@10.
        fused_hit_any: Gold present anywhere in fused IDs. Not a pass gate.
        fused_gold_rank: One-based rank of the first gold ID in fused IDs.
        rerank_fallback: Named rerank fallback token.
    """

    case_id: str
    query_class: str
    recall_hit_at_10: bool | None
    exact_hit_at_5: bool | None
    alias_hit_at_10: bool | None
    locator_ok: bool
    expected_refusal: bool
    refused: bool
    acl_leak: bool
    first_evidence_ms: float | None = None
    rerank_call_count: int = 0
    bm25_fallback: str = "none"
    fused_hit_at_10: bool | None = None
    fused_hit_any: bool | None = None
    fused_gold_rank: int | None = None
    rerank_fallback: str = ""


def score_retrieve_case(
    *,
    case_id: str,
    query_class: str,
    ranked_ids: Sequence[UUID],
    gold_ids: Sequence[UUID],
    gold_pages: Sequence[int],
    evidence_pages: Sequence[int],
    expected_refusal: bool,
    refused: bool,
    acl_leak: bool,
    required_terms: Sequence[str] = (),
    first_evidence_ms: float | None = None,
    rerank_call_count: int = 0,
    bm25_fallback: str = "none",
    fused_ids: Sequence[UUID] = (),
    rerank_fallback: str = "",
) -> PrivatePdfRetrieveScore:
    """Score one Hybrid retrieve against sealed gold chunk ids.

    Args:
        case_id: Case id.
        query_class: Overlay class.
        ranked_ids: Final ``HybridRunResult.ranked_ids``, never fused occupancy.
        gold_ids: Sealed current chunk UUIDs.
        gold_pages: Gold page locators.
        evidence_pages: Pages of selected evidence.
        expected_refusal: Gold refusal flag.
        refused: Observed refusal.
        acl_leak: True when a forbidden or unauthorized id survived.
        required_terms: Exact terms or aliases for the alias denominator.
        first_evidence_ms: Observed first-evidence latency.
        rerank_call_count: Counted rerank calls.
        bm25_fallback: Named BM25 fallback token.
        fused_ids: Fused occupancy IDs. Occupancy is never the Recall@10
            gate.
        rerank_fallback: Named rerank fallback token.

    Returns:
        Per-case score without source text.
    """

    locator_ok = bool(gold_ids) and all(
        item in set(ranked_ids[:12]) for item in gold_ids
    )
    if gold_pages and evidence_pages:
        locator_ok = locator_ok and bool(set(gold_pages) & set(evidence_pages))
    if expected_refusal:
        return PrivatePdfRetrieveScore(
            case_id=case_id,
            query_class=query_class,
            recall_hit_at_10=None,
            exact_hit_at_5=None,
            alias_hit_at_10=None,
            locator_ok=locator_ok or refused,
            expected_refusal=True,
            refused=refused,
            acl_leak=acl_leak,
            first_evidence_ms=first_evidence_ms,
            rerank_call_count=rerank_call_count,
            bm25_fallback=bm25_fallback,
            rerank_fallback=rerank_fallback,
        )
    recall10 = recall_hit_at_k(ranked_ids, gold_ids, 10)
    fused10 = recall_hit_at_k(fused_ids, gold_ids, 10) if fused_ids else None
    fused_any = (
        recall_hit_at_k(fused_ids, gold_ids, len(fused_ids)) if fused_ids else False
    )
    gold_set = set(gold_ids)
    fused_rank: int | None = None
    for index, chunk_id in enumerate(fused_ids):
        if chunk_id in gold_set:
            fused_rank = index + 1
            break
    exact5 = (
        recall_hit_at_k(ranked_ids, gold_ids, 5)
        if query_class == PrivatePdfQueryClass.EXACT_ACRONYM.value
        else None
    )
    alias10 = recall_hit_at_k(ranked_ids, gold_ids, 10) if required_terms else None
    return PrivatePdfRetrieveScore(
        case_id=case_id,
        query_class=query_class,
        recall_hit_at_10=recall10,
        exact_hit_at_5=exact5,
        alias_hit_at_10=alias10,
        locator_ok=locator_ok,
        expected_refusal=False,
        refused=refused,
        acl_leak=acl_leak,
        first_evidence_ms=first_evidence_ms,
        rerank_call_count=rerank_call_count,
        bm25_fallback=bm25_fallback,
        fused_hit_at_10=fused10,
        fused_hit_any=fused_any,
        fused_gold_rank=fused_rank,
        rerank_fallback=rerank_fallback,
    )


def _mean(flags: Sequence[bool]) -> float | str:
    """Return a mean or ``not_applicable`` when the denominator is empty.

    Args:
        flags: Boolean hits.

    Returns:
        Mean in ``[0, 1]`` or ``not_applicable``.
    """

    if not flags:
        return NOT_APPLICABLE
    return sum(1 for item in flags if item) / len(flags)


def aggregate_retrieve_gates(
    scores: tuple[PrivatePdfRetrieveScore, ...],
    *,
    class_counts: dict[str, int] | None = None,
) -> dict[str, object]:
    """Aggregate overlay retrieval gates. Missing class minima are not a pass.

    Args:
        scores: Per-case scores.
        class_counts: Sealed class counts used as denominators.

    Returns:
        Git-safe aggregates. Holdout is never implied open.
    """

    counts = class_counts or {}
    recall_flags = tuple(
        bool(item.recall_hit_at_10)
        for item in scores
        if item.recall_hit_at_10 is not None
    )
    exact_flags = tuple(
        bool(item.exact_hit_at_5) for item in scores if item.exact_hit_at_5 is not None
    )
    alias_flags = tuple(
        bool(item.alias_hit_at_10)
        for item in scores
        if item.alias_hit_at_10 is not None
    )
    locator_flags = tuple(item.locator_ok for item in scores)
    latencies = tuple(
        item.first_evidence_ms for item in scores if item.first_evidence_ms is not None
    )
    exact_denom = counts.get(PrivatePdfQueryClass.EXACT_ACRONYM.value, len(exact_flags))
    exact_minimum = PRIVATE_PDF_CLASS_MINIMUMS[PrivatePdfQueryClass.EXACT_ACRONYM]
    alias_minimum = PRIVATE_PDF_CLASS_MINIMUMS[PrivatePdfQueryClass.EXACT_ACRONYM]
    exact_metric: float | str = (
        _mean(exact_flags) if exact_denom >= exact_minimum else NOT_APPLICABLE
    )
    alias_metric: float | str = (
        _mean(alias_flags) if exact_denom >= alias_minimum else NOT_APPLICABLE
    )
    p95: float | None = None
    if latencies:
        ordered = tuple(sorted(latencies))
        index = min(len(ordered) - 1, max(0, round(0.95 * (len(ordered) - 1))))
        p95 = ordered[index]
    acl_leaks = sum(1 for item in scores if item.acl_leak)
    full_hybrid = tuple(
        item
        for item in scores
        if item.bm25_fallback == "none" and not item.expected_refusal
    )
    degraded = tuple(item for item in scores if item.bm25_fallback != "none")
    rerank_eligible = tuple(
        item
        for item in scores
        if not item.expected_refusal
        and item.query_class != PrivatePdfQueryClass.EXACT_ACRONYM.value
    )
    rerank_ones = sum(1 for item in rerank_eligible if item.rerank_call_count == 1)
    fallback_histogram: dict[str, int] = {}
    rerank_fallback_histogram: dict[str, int] = {}
    for item in scores:
        token = item.bm25_fallback or "none"
        fallback_histogram[token] = fallback_histogram.get(token, 0) + 1
        rerank_token = item.rerank_fallback or "none"
        rerank_fallback_histogram[rerank_token] = (
            rerank_fallback_histogram.get(rerank_token, 0) + 1
        )
    fused_flags = tuple(
        bool(item.fused_hit_at_10)
        for item in scores
        if item.fused_hit_at_10 is not None
    )
    fused_any_flags = tuple(
        bool(item.fused_hit_any) for item in scores if item.fused_hit_any is not None
    )
    fused_ranks = tuple(
        item.fused_gold_rank for item in scores if item.fused_gold_rank is not None
    )
    fused_rank_p50: int | None = None
    if fused_ranks:
        ordered_ranks = tuple(sorted(fused_ranks))
        fused_rank_p50 = ordered_ranks[len(ordered_ranks) // 2]
    return {
        "case_count": len(scores),
        "holdout_opened": False,
        "acl_leaks": acl_leaks,
        "hybrid_recall_at_10": _mean(recall_flags),
        "exact_term_recall_at_5": exact_metric,
        "alias_recall_at_10": alias_metric,
        "locator_correctness": _mean(locator_flags),
        "first_evidence_p95_ms": p95,
        "full_hybrid_case_count": len(full_hybrid),
        "dense_term_degraded_count": len(degraded),
        "eligible_rerank_case_count": len(rerank_eligible),
        "eligible_rerank_ones": rerank_ones,
        "fallback_histogram": fallback_histogram,
        "rerank_fallback_histogram": rerank_fallback_histogram,
        "fused_occupancy_at_10": _mean(fused_flags),
        "gold_in_fused_any": _mean(fused_any_flags),
        "fused_gold_rank_p50": fused_rank_p50,
        "gates": {
            "hybrid_recall_at_10": HYBRID_RECALL_AT_10_GATE,
            "exact_term_recall_at_5": EXACT_RECALL_AT_5_GATE,
            "alias_recall_at_10": ALIAS_RECALL_AT_10_GATE,
            "locator_correctness": LOCATOR_GATE,
            "first_evidence_p95_ms": FIRST_EVIDENCE_P95_MS_GATE,
            "acl_leaks": 0,
        },
    }


def retrieve_gates_pass(report: dict[str, object]) -> bool:
    """Return whether overlay retrieval gates pass for a split report.

    Args:
        report: Aggregates from ``aggregate_retrieve_gates``.

    Returns:
        True when ACL, Recall@10, locator, latency, exact/alias, and
        eligible rerank gates all hold. ``not_applicable`` exact/alias
        metrics are not treated as failures.
    """

    if int(str(report.get("acl_leaks", 1))) != 0:
        return False
    if int(str(report.get("dense_term_degraded_count", 1))) != 0:
        return False
    recall = report.get("hybrid_recall_at_10")
    locator = report.get("locator_correctness")
    if not isinstance(recall, float) or recall < HYBRID_RECALL_AT_10_GATE:
        return False
    if not isinstance(locator, float) or locator < LOCATOR_GATE:
        return False
    p95 = report.get("first_evidence_p95_ms")
    if not isinstance(p95, (int, float)) or float(p95) > FIRST_EVIDENCE_P95_MS_GATE:
        return False
    exact = report.get("exact_term_recall_at_5")
    alias = report.get("alias_recall_at_10")
    if exact != NOT_APPLICABLE:
        if not isinstance(exact, float) or exact < EXACT_RECALL_AT_5_GATE:
            return False
    if alias != NOT_APPLICABLE:
        if not isinstance(alias, float) or alias < ALIAS_RECALL_AT_10_GATE:
            return False
    eligible = int(str(report.get("eligible_rerank_case_count", 0)))
    ones = int(str(report.get("eligible_rerank_ones", -1)))
    if eligible > 0 and ones != eligible:
        return False
    return True


def gold_id_overlap_counts(
    *,
    gold_id_groups: Sequence[Sequence[UUID]],
    current_ids: frozenset[UUID],
) -> dict[str, int]:
    """Count gold-ID overlap with current version chunk IDs.

    Args:
        gold_id_groups: Per-case gold UUID tuples. No question text.
        current_ids: Current version chunk IDs (representatives or all).

    Returns:
        Count-only overlap. Never includes questions, excerpts, or raw IDs.
    """

    gold = frozenset(item for group in gold_id_groups for item in group)
    missing_all = 0
    for group in gold_id_groups:
        if group and not any(item in current_ids for item in group):
            missing_all += 1
    sizes = tuple(len(group) for group in gold_id_groups)
    return {
        "gold_unique": len(gold),
        "current": len(current_ids),
        "intersection": len(gold & current_ids),
        "cases": len(gold_id_groups),
        "cases_missing_all": missing_all,
        "gold_ids_per_case_min": min(sizes) if sizes else 0,
        "gold_ids_per_case_max": max(sizes) if sizes else 0,
    }
