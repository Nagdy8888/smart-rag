"""Deterministic private-PDF agent scorers. Judge averages cannot hide ACL."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from uuid import UUID

CITATION_CORRECTNESS_GATE = 0.98
CITATION_COMPLETENESS_GATE = 0.90
FAITHFULNESS_GATE = 0.90
ROUTING_GATE = 0.90
UNSCORED = "unscored"


@dataclass(frozen=True, slots=True)
class PrivatePdfAgentScore:
    """Per-case deterministic agent score. No answer text.

    Attributes:
        case_id: Case id hash.
        citation_precision: Cited ids that are allowed supporting ids.
        citation_completeness: Fraction of atomic facts with a supporting cite.
        locator_ok: Cited locators match gold.
        forbidden_cited: True when a forbidden id was cited.
        route_ok: Profile/route matched the sealed expectation.
        refusal_ok: Refusal matched gold.
        judge_status: ``complete`` or ``unscored``. Never a pass when unscored.
        judge_faithfulness: Judge score when complete, otherwise None.
    """

    case_id: str
    citation_precision: float
    citation_completeness: float
    locator_ok: bool
    forbidden_cited: bool
    route_ok: bool
    refusal_ok: bool
    judge_status: str
    judge_faithfulness: float | None


def citation_precision(
    cited_ids: Sequence[UUID],
    allowed_ids: Sequence[UUID],
) -> float:
    """Return the fraction of cited ids that are allowed supporting ids.

    Args:
        cited_ids: Cited canonical chunk ids.
        allowed_ids: Gold supporting ids.

    Returns:
        1.0 when nothing is cited and nothing is required; otherwise precision.
    """

    if not cited_ids:
        return 1.0 if not allowed_ids else 0.0
    allowed = set(allowed_ids)
    return sum(1 for item in cited_ids if item in allowed) / len(cited_ids)


def citation_completeness(
    cited_ids: Sequence[UUID],
    fact_chunk_ids: Sequence[Sequence[UUID]],
) -> float:
    """Return the fraction of atomic facts with at least one supporting cite.

    Args:
        cited_ids: Cited canonical chunk ids.
        fact_chunk_ids: Per-fact supporting chunk ids.

    Returns:
        1.0 when there are no required facts; otherwise completeness.
    """

    if not fact_chunk_ids:
        return 1.0
    cited = set(cited_ids)
    supported = 0
    for group in fact_chunk_ids:
        if any(item in cited for item in group):
            supported += 1
    return supported / len(fact_chunk_ids)


def resolved_citation_ids(
    cited_leaf_ids: Sequence[UUID],
    retrieved_ids: Sequence[UUID] = (),
) -> tuple[UUID, ...]:
    """Return persist-resolved leaf IDs, never retrieved occupancy.

    Retrieved IDs that were not cited are discarded. Cited leaves remain
    even when they are absent from the retrieve list after parent-to-leaf
    resolution.

    Args:
        cited_leaf_ids: Leaf chunk IDs stored on citation rows.
        retrieved_ids: Hybrid ranked IDs. Never treated as citations.

    Returns:
        Cited leaf IDs in the given order.
    """

    del retrieved_ids
    return tuple(cited_leaf_ids)


def paragraph_completeness(supported: Sequence[bool]) -> float:
    """Return the fraction of factual paragraphs with a surviving citation.

    Args:
        supported: Per-paragraph flag, true when at least one verified
            citation survived.

    Returns:
        1.0 when there are no factual paragraphs; otherwise completeness.
    """

    if not supported:
        return 1.0
    return sum(1 for item in supported if item) / len(supported)


def pdf_locator_ok(
    cited_pdf_pages: Sequence[int | None],
    gold_page_numbers: Sequence[int],
    *,
    page_labels: Sequence[str] | None = None,
) -> bool:
    """Return whether cited PDF toolbar pages match gold ``page_number``.

    Printed ``page_label`` is ignored even when supplied.

    Args:
        cited_pdf_pages: Typed ``pdf_page_number`` values from authorized rows.
        gold_page_numbers: Gold 1-based viewer pages.
        page_labels: Printed labels. Never consulted.

    Returns:
        True when every cited page is in gold and at least one gold page is
        cited when gold pages exist.
    """

    del page_labels
    gold = tuple(gold_page_numbers)
    if any(page is None for page in cited_pdf_pages):
        return False
    cited = tuple(int(page) for page in cited_pdf_pages if page is not None)
    if not gold:
        return not cited
    if not cited:
        return False
    gold_set = set(gold)
    return all(page in gold_set for page in cited)


def score_agent_case(
    *,
    case_id: str,
    cited_ids: Sequence[UUID],
    allowed_ids: Sequence[UUID],
    fact_chunk_ids: Sequence[Sequence[UUID]],
    forbidden_ids: Sequence[UUID] = (),
    locator_ok: bool,
    route_ok: bool,
    expected_refusal: bool,
    refused: bool,
    judge_status: str,
    judge_faithfulness: float | None,
    paragraph_supported: Sequence[bool] | None = None,
) -> PrivatePdfAgentScore:
    """Score one agent answer with deterministic metrics.

    Args:
        case_id: Case id.
        cited_ids: Persist-resolved leaf chunk ids, not retrieved occupancy.
        allowed_ids: Gold supporting ids.
        fact_chunk_ids: Per-fact supporting ids.
        forbidden_ids: Ids that must never be cited.
        locator_ok: Locator check from ``pdf_locator_ok``, never ``page_label``.
        route_ok: Expected profile/route matched.
        expected_refusal: Gold refusal.
        refused: Observed refusal.
        judge_status: Judge completion status.
        judge_faithfulness: Faithfulness in ``[0, 1]`` when complete.
        paragraph_supported: Optional per-paragraph surviving-citation flags.
            When set, completeness uses those flags instead of fact groups.

    Returns:
        Per-case score. Invalid judge output is ``unscored``, never a pass.
    """

    status = judge_status if judge_status == "complete" else UNSCORED
    faithfulness = judge_faithfulness if status == "complete" else None
    forbidden = any(item in set(forbidden_ids) for item in cited_ids)
    completeness = (
        paragraph_completeness(paragraph_supported)
        if paragraph_supported is not None
        else citation_completeness(cited_ids, fact_chunk_ids)
    )
    return PrivatePdfAgentScore(
        case_id=case_id,
        citation_precision=citation_precision(cited_ids, allowed_ids),
        citation_completeness=completeness,
        locator_ok=locator_ok,
        forbidden_cited=forbidden,
        route_ok=route_ok,
        refusal_ok=expected_refusal == refused,
        judge_status=status,
        judge_faithfulness=faithfulness,
    )


def aggregate_agent_gates(
    scores: tuple[PrivatePdfAgentScore, ...],
) -> dict[str, object]:
    """Aggregate agent gates. A judge average cannot hide ACL or citation fails.

    Args:
        scores: Per-case scores.

    Returns:
        Git-safe aggregates with ``holdout_opened=false``.
    """

    if not scores:
        return {
            "case_count": 0,
            "holdout_opened": False,
            "citation_correctness": 0.0,
            "citation_completeness": 0.0,
            "routing": 0.0,
            "forbidden_cited": 0,
            "judge_scored_count": 0,
            "judge_unscored_count": 0,
            "mean_judge_faithfulness": UNSCORED,
            "deterministic_pass": False,
        }
    precision = sum(item.citation_precision for item in scores) / len(scores)
    completeness = sum(item.citation_completeness for item in scores) / len(scores)
    routing = sum(1 for item in scores if item.route_ok) / len(scores)
    forbidden = sum(1 for item in scores if item.forbidden_cited)
    scored = tuple(
        item.judge_faithfulness
        for item in scores
        if item.judge_status == "complete" and item.judge_faithfulness is not None
    )
    unscored = sum(1 for item in scores if item.judge_status != "complete")
    mean_faith: float | str
    if scored:
        mean_faith = sum(scored) / len(scored)
    else:
        mean_faith = UNSCORED
    deterministic_pass = (
        precision >= CITATION_CORRECTNESS_GATE
        and completeness >= CITATION_COMPLETENESS_GATE
        and routing >= ROUTING_GATE
        and forbidden == 0
        and all(item.locator_ok and item.refusal_ok for item in scores)
    )
    return {
        "case_count": len(scores),
        "holdout_opened": False,
        "citation_correctness": precision,
        "citation_completeness": completeness,
        "routing": routing,
        "forbidden_cited": forbidden,
        "judge_scored_count": len(scored),
        "judge_unscored_count": unscored,
        "mean_judge_faithfulness": mean_faith,
        "deterministic_pass": deterministic_pass,
        "gates": {
            "citation_correctness": CITATION_CORRECTNESS_GATE,
            "citation_completeness": CITATION_COMPLETENESS_GATE,
            "faithfulness": FAITHFULNESS_GATE,
            "routing": ROUTING_GATE,
        },
    }
