"""Coverage, conflict, media, and negation signals. No answer generation."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from smart_rag_core.evaluation.schema import FailureStage
from smart_rag_core.retrieval.types import RetrievalCandidate


class CoverageSignal(StrEnum):
    """Whole-document and refusal signals emitted by Hybrid Packet 4."""

    NONE = "none"
    FULL_COVERAGE = "full_coverage"
    SCOPED_SUMMARY = "scoped_summary"
    MEDIA_LIMITATION = "media_limitation"
    NEGATION_UNSCOPED = "negation_unscoped"
    CONFLICT = "conflict"
    WEAK_EVIDENCE = "weak_evidence"
    BM25_DEGRADED = "bm25_degraded"


class CoverageDecision(StrEnum):
    """Whether Hybrid may support an answer from the selected evidence."""

    ANSWER = "answer"
    REFUSE = "refuse"


@dataclass(frozen=True, slots=True)
class HybridCoverage:
    """Coverage and refusal diagnostics for one Hybrid retrieval.

    Attributes:
        signal: Primary signal.
        uncovered_headings: Major headings not represented in fused evidence.
        conflict_chunk_ids: Equally authoritative contradictory current IDs.
        notes: Safe machine-readable reasons. No BM25 snippets.
        coverage_score: Packet 6 ``min`` formula, or None before scoring.
        decision: Answer versus refuse after class thresholding.
        threshold: Frozen per-class threshold that produced ``decision``.
        query_class: Evaluation class id when known.
        term_coverage: Required term/entity coverage component.
        subquestion_coverage: Subquestion coverage component.
        evidence_ratio: Distinct-evidence / profile-minimum component.
        support_confidence: Bounded support feature, not a probability.
        first_failing_stage: Attribution; ranking is not blamed earlier.
        baseline: Development baseline ``0.65``.
    """

    signal: CoverageSignal
    uncovered_headings: tuple[str, ...] = ()
    conflict_chunk_ids: tuple[UUID, ...] = ()
    notes: tuple[str, ...] = ()
    coverage_score: float | None = None
    decision: CoverageDecision | None = None
    threshold: float | None = None
    query_class: str | None = None
    term_coverage: float | None = None
    subquestion_coverage: float | None = None
    evidence_ratio: float | None = None
    support_confidence: float | None = None
    first_failing_stage: FailureStage = FailureStage.NONE
    baseline: float | None = None


def coverage_for_summary(
    *,
    fused: tuple[RetrievalCandidate, ...],
    heading_inventory: tuple[str, ...],
    covered_headings: tuple[str, ...],
    want_full_summary: bool,
) -> HybridCoverage:
    """Refuse a full-summary claim when major headings are missing.

    Args:
        fused: Authorized fused candidates.
        heading_inventory: Current document major headings.
        covered_headings: Headings represented in fused evidence.
        want_full_summary: Whether the profile requested a whole-document answer.

    Returns:
        ``full_coverage`` or ``scoped_summary`` with uncovered headings.
    """

    if not want_full_summary:
        return HybridCoverage(signal=CoverageSignal.NONE)
    if not fused:
        return HybridCoverage(
            signal=CoverageSignal.WEAK_EVIDENCE,
            uncovered_headings=heading_inventory,
            notes=("no_authorized_evidence",),
        )
    missing = tuple(
        heading for heading in heading_inventory if heading not in covered_headings
    )
    if len(heading_inventory) > 12:
        overflow = missing or heading_inventory[12:]
        return HybridCoverage(
            signal=CoverageSignal.SCOPED_SUMMARY,
            uncovered_headings=overflow,
            notes=("inventory_exceeds_evidence_cap",),
        )
    if missing:
        return HybridCoverage(
            signal=CoverageSignal.SCOPED_SUMMARY,
            uncovered_headings=missing,
            notes=("uncovered_major_headings",),
        )
    return HybridCoverage(signal=CoverageSignal.FULL_COVERAGE)


def media_limitation_coverage(*, media_dependence: bool) -> HybridCoverage | None:
    """Return the signed media limitation when figure-only evidence is required.

    Args:
        media_dependence: Query-profile media flag.

    Returns:
        Media-limitation coverage, or None when not applicable.
    """

    if not media_dependence:
        return None
    return HybridCoverage(
        signal=CoverageSignal.MEDIA_LIMITATION,
        notes=("figure_only_evidence_not_in_v1",),
    )


def negation_coverage(*, negation_scope: str) -> HybridCoverage | None:
    """Refuse unscoped negation complements.

    Args:
        negation_scope: Profile negation enum.

    Returns:
        Negation coverage when the complement is not a closed set.
    """

    if negation_scope in {"none", "entity_exclusion", "policy_exclusion"}:
        return None
    if negation_scope == "set_complement":
        return HybridCoverage(
            signal=CoverageSignal.NEGATION_UNSCOPED,
            notes=("negation_requires_closed_set",),
        )
    return None


def conflict_coverage(
    candidates: tuple[RetrievalCandidate, ...],
    *,
    contradictory_ids: tuple[UUID, ...],
) -> HybridCoverage | None:
    """Emit conflict evidence when two current authorities disagree.

    Args:
        candidates: Fused list.
        contradictory_ids: IDs labeled as equally authoritative contradictions.

    Returns:
        Conflict coverage when those IDs are both present.
    """

    present = {item.chunk_id for item in candidates}
    hits = tuple(item for item in contradictory_ids if item in present)
    if len(hits) < 2:
        return None
    return HybridCoverage(signal=CoverageSignal.CONFLICT, conflict_chunk_ids=hits)
