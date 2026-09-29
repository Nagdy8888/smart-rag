"""Private-safe dual-metric scoring and retrieval stage attribution.

The scorer is generic. Committed callers must not embed sample-document
hashes, book titles, question identifiers, or gold phrases from a private
regression set. Gold remains in gitignored files or synthetic fixtures.
"""

from __future__ import annotations

import html
import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum

from smart_rag_core.query_answer.assembly import DEADLINE_RESERVE_REFUSAL_TEXT
from smart_rag_core.query_answer.paragraphs import INSUFFICIENT_EVIDENCE_TEXT

_DEADLINE_REASONS = frozenset(
    {
        "answer_deadline_reserve_exhausted",
        "deadline_exhausted",
        "deadline",
    }
)
_REFUSAL_STATUSES = frozenset(
    {
        "insufficient_evidence",
        "refused",
    }
)
_ERROR_STATUSES = frozenset({"error", "failed"})


class DualOutcome(StrEnum):
    """First-class dual-metric outcome for one company answer."""

    STRICT_PHRASE = "strict_phrase"
    FACT_COVERED = "fact_covered"
    PARTIAL = "partial"
    WRONG_PHRASING = "wrong_phrasing"
    VERIFIER_REFUSAL_AFTER_FUSION = "verifier_refusal_after_fusion"
    EMPTY_RETRIEVAL = "empty_retrieval"
    DEADLINE = "deadline"
    ERROR = "error"


class SourceResolutionStage(StrEnum):
    """Named-source resolution recorded before ranking."""

    UNSCOPED = "unscoped"
    EXACT_ONE = "exact_one"
    AMBIGUOUS = "ambiguous"
    UNAUTHORIZED = "unauthorized"


@dataclass(frozen=True, slots=True)
class RequiredFact:
    """One required fact with a canonical phrase and approved aliases.

    Attributes:
        fact_id: Stable synthetic or private identifier. Never a sample
            question number from a committed production module.
        canonical_phrases: Phrases that must all appear for a strict hit.
        approved_aliases: Additional phrases that count for fact coverage
            only. Empty when no alias is approved.
    """

    fact_id: str
    canonical_phrases: tuple[str, ...]
    approved_aliases: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        """Reject empty identifiers or empty canonical phrase lists.

        Raises:
            ValueError: If ``fact_id`` is blank or no canonical phrase is
                supplied.
        """

        if not self.fact_id.strip():
            raise ValueError("fact_id must be a non-empty identifier")
        if not self.canonical_phrases:
            raise ValueError("canonical_phrases must contain at least one phrase")
        if any(not item.strip() for item in self.canonical_phrases):
            raise ValueError("canonical phrases must be non-empty")
        if any(not item.strip() for item in self.approved_aliases):
            raise ValueError("approved aliases must be non-empty when present")


@dataclass(frozen=True, slots=True)
class RetrievalStageAttribution:
    """Per-question retrieval stages used to attribute misses.

    Attributes:
        source_resolution: Named-source outcome before ranking.
        dense_hit: True when a supporting chunk appeared in dense results.
        bm25_hit: True when a supporting chunk appeared in BM25 results.
        term_hit: True when a supporting chunk appeared in term results.
        fused_rank: One-based fused rank of the first supporting chunk.
        rerank_rank: One-based rerank rank of the first supporting chunk.
        rerank_fallback: Recorded RRF fallback reason, if rerank was skipped.
        post_mmr_rank: One-based post-MMR rank of the first supporting chunk.
        coverage_term: Required-term coverage component.
        coverage_subquestion: Subquestion coverage component.
        coverage_evidence_ratio: Distinct-evidence ratio component.
        coverage_support_confidence: Support-confidence component.
        coverage_score: Frozen min() coverage score.
        correction_outcome: ``none``, ``identical_skipped``,
            ``applied_alternate``, or ``applied_same_route``.
        fused_count: Authorized fused survivors after ACL recheck.
        verifier_status: Verifier or answer-status token when known.
        retrieval_empty: True only when every channel returned no survivors.
    """

    source_resolution: SourceResolutionStage = SourceResolutionStage.UNSCOPED
    dense_hit: bool | None = None
    bm25_hit: bool | None = None
    term_hit: bool | None = None
    fused_rank: int | None = None
    rerank_rank: int | None = None
    rerank_fallback: str | None = None
    post_mmr_rank: int | None = None
    coverage_term: float | None = None
    coverage_subquestion: float | None = None
    coverage_evidence_ratio: float | None = None
    coverage_support_confidence: float | None = None
    coverage_score: float | None = None
    correction_outcome: str = "none"
    fused_count: int = 0
    verifier_status: str | None = None
    retrieval_empty: bool = False


@dataclass(frozen=True, slots=True)
class DualMetricScore:
    """Strict phrase and alias-aware fact coverage for one full answer.

    Attributes:
        outcome: First-class bucket. Verifier refusals after fusion are
            never reported as empty retrieval.
        strict_pass: True when every canonical phrase is a substring of the
            normalized full answer.
        fact_coverage: Fraction of required facts hit by a canonical phrase
            or an approved alias.
        grounded_fact_pass: True when ``fact_coverage`` is ``1.0``.
        deadline_failure: True when the product deadline path fired.
        verifier_refusal_after_fusion: True when fused evidence existed and
            the answer still refused for insufficient evidence.
        empty_retrieval: True only when retrieval stages prove no survivors.
        canonical_hits: Canonical phrases found in the answer.
        alias_hits: Approved aliases found without a canonical hit.
        missed_canonical: Canonical phrases that did not match.
    """

    outcome: DualOutcome
    strict_pass: bool
    fact_coverage: float
    grounded_fact_pass: bool
    deadline_failure: bool
    verifier_refusal_after_fusion: bool
    empty_retrieval: bool
    canonical_hits: tuple[str, ...]
    alias_hits: tuple[str, ...]
    missed_canonical: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class DisjointQualificationCase:
    """Synthetic disjoint query class used to qualify generalization.

    Attributes:
        case_id: Synthetic identifier. Must not be a sample-PDF question id.
        query_class: Query class such as ``acronym`` or ``arabic_mixed``.
        document_fixture: Synthetic document fixture name, not a live book
            title.
    """

    case_id: str
    query_class: str
    document_fixture: str

    def __post_init__(self) -> None:
        """Reject blank synthetic case fields.

        Raises:
            ValueError: If any field is blank.
        """

        if not self.case_id.strip() or not self.query_class.strip():
            raise ValueError("disjoint case identifiers must be non-empty")
        if not self.document_fixture.strip():
            raise ValueError("document_fixture must be a synthetic name")


_APOSTROPHE_CHARS = {
    "\u2018": "'",  # left single quotation
    "\u2019": "'",  # right single quotation / curly apostrophe
    "\u201a": "'",  # single low-9 quotation
    "\u2032": "'",  # prime
    "\u00b4": "'",  # acute accent used as apostrophe
    "\u201c": '"',  # left double quotation
    "\u201d": '"',  # right double quotation
}


def normalize_answer_text(answer_text: str) -> str:
    """Return the full answer ready for lexical matching.

    HTML entities are unescaped, curly quotes and apostrophes are folded to
    ASCII, Unicode is NFKC-normalized, and the result is casefolded. Callers
    must pass the complete answer, not a truncated excerpt.

    Args:
        answer_text: Full streamed or persisted answer prose.

    Returns:
        Normalized answer text. Empty input stays empty.
    """

    unescaped = html.unescape(answer_text)
    folded = "".join(_APOSTROPHE_CHARS.get(char, char) for char in unescaped)
    return unicodedata.normalize("NFKC", folded).casefold()


def phrase_is_present(answer_text: str, phrase: str) -> bool:
    """Return whether ``phrase`` is a substring of the normalized answer.

    Args:
        answer_text: Full answer prose.
        phrase: Required or alias phrase.

    Returns:
        True when the normalized phrase occurs in the normalized answer.
    """

    needle = normalize_answer_text(phrase)
    if not needle:
        return False
    return needle in normalize_answer_text(answer_text)


def score_company_answer(
    *,
    answer_text: str,
    facts: Sequence[RequiredFact],
    stages: RetrievalStageAttribution,
    answer_status: str | None = None,
    terminal_reason: str | None = None,
) -> DualMetricScore:
    """Score one full company answer with strict and alias-aware metrics.

    Args:
        answer_text: Complete answer text. Excerpt-only scoring is a contract
            failure for this function.
        facts: Required facts. May be empty only for refusal/deadline cases.
        stages: Retrieval stage attribution for the same question.
        answer_status: Optional product status such as ``insufficient_evidence``.
        terminal_reason: Optional reason such as
            ``answer_deadline_reserve_exhausted``.

    Returns:
        Frozen dual-metric score. Verifier refusals after fusion are distinct
        from proven empty retrieval.

    Raises:
        ValueError: If ``fused_count`` is negative.
    """

    if stages.fused_count < 0:
        raise ValueError("fused_count must be >= 0")
    status = (answer_status or "").strip().casefold()
    reason = (terminal_reason or stages.verifier_status or "").strip().casefold()
    deadline_failure = _is_deadline(
        answer_text=answer_text,
        status=status,
        reason=reason,
    )
    error = status in _ERROR_STATUSES or reason in _ERROR_STATUSES
    fused = stages.fused_count > 0
    empty_retrieval = _is_empty_retrieval(stages=stages, fused=fused)
    refusal = _is_insufficient_refusal(answer_text=answer_text, status=status)
    verifier_refusal_after_fusion = fused and refusal and not empty_retrieval

    canonical_hits, alias_hits, missed_canonical, facts_hit, fact_count = _match_facts(
        answer_text=answer_text, facts=facts
    )
    fact_coverage = 1.0 if fact_count == 0 else facts_hit / fact_count
    strict_pass = bool(facts) and not missed_canonical
    grounded_fact_pass = bool(facts) and facts_hit == fact_count
    outcome = _resolve_outcome(
        deadline_failure=deadline_failure,
        error=error,
        empty_retrieval=empty_retrieval,
        verifier_refusal_after_fusion=verifier_refusal_after_fusion,
        strict_pass=strict_pass,
        grounded_fact_pass=grounded_fact_pass,
        facts_hit=facts_hit,
        fact_count=fact_count,
    )
    return DualMetricScore(
        outcome=outcome,
        strict_pass=strict_pass and outcome is DualOutcome.STRICT_PHRASE,
        fact_coverage=fact_coverage,
        grounded_fact_pass=grounded_fact_pass
        and outcome in {DualOutcome.STRICT_PHRASE, DualOutcome.FACT_COVERED},
        deadline_failure=deadline_failure,
        verifier_refusal_after_fusion=verifier_refusal_after_fusion,
        empty_retrieval=empty_retrieval,
        canonical_hits=canonical_hits,
        alias_hits=alias_hits,
        missed_canonical=missed_canonical,
    )


def summarize_scores(scores: Sequence[DualMetricScore]) -> Mapping[str, float | int]:
    """Return aggregate dual-metric counts for a development run.

    Args:
        scores: Per-question scores from :func:`score_company_answer`.

    Returns:
        Counts and rates. An empty sequence yields zeros rather than NaN.
    """

    total = len(scores)
    if total == 0:
        return {
            "questions": 0,
            "strict_pass": 0,
            "grounded_fact_pass": 0,
            "deadline_failures": 0,
            "verifier_refusal_after_fusion": 0,
            "empty_retrieval": 0,
            "strict_rate": 0.0,
            "grounded_fact_rate": 0.0,
        }
    strict = sum(1 for item in scores if item.strict_pass)
    grounded = sum(1 for item in scores if item.grounded_fact_pass)
    deadlines = sum(1 for item in scores if item.deadline_failure)
    refusals = sum(1 for item in scores if item.verifier_refusal_after_fusion)
    empty = sum(1 for item in scores if item.empty_retrieval)
    return {
        "questions": total,
        "strict_pass": strict,
        "grounded_fact_pass": grounded,
        "deadline_failures": deadlines,
        "verifier_refusal_after_fusion": refusals,
        "empty_retrieval": empty,
        "strict_rate": strict / total,
        "grounded_fact_rate": grounded / total,
    }


def synthetic_disjoint_cases() -> tuple[DisjointQualificationCase, ...]:
    """Return committed synthetic disjoint qualification classes.

    Returns:
        Query classes covering short/long, duplicate, acronym, paraphrase,
        Arabic/mixed, negation, stale version, ACL denial, and BM25 outage
        without referencing a live sample PDF.
    """

    return (
        DisjointQualificationCase("syn-short-exact", "exact_identifier", "synth-short"),
        DisjointQualificationCase("syn-long-heading", "heading", "synth-long"),
        DisjointQualificationCase("syn-multi-doc", "multi_document", "synth-corpus"),
        DisjointQualificationCase("syn-duplicate", "duplicate_copy", "synth-dup"),
        DisjointQualificationCase("syn-acronym", "acronym", "synth-terms"),
        DisjointQualificationCase("syn-paraphrase", "paraphrase", "synth-short"),
        DisjointQualificationCase("syn-list", "list", "synth-long"),
        DisjointQualificationCase(
            "syn-ambiguous-title", "ambiguous_source", "synth-corpus"
        ),
        DisjointQualificationCase("syn-ocr", "ocr_layout", "synth-long"),
        DisjointQualificationCase("syn-arabic", "arabic_mixed", "synth-mixed"),
        DisjointQualificationCase("syn-negation", "negation", "synth-short"),
        DisjointQualificationCase("syn-stale", "stale_version", "synth-dup"),
        DisjointQualificationCase("syn-acl", "acl_denial", "synth-restricted"),
        DisjointQualificationCase("syn-bm25-outage", "bm25_outage", "synth-short"),
    )


def _match_facts(
    *,
    answer_text: str,
    facts: Sequence[RequiredFact],
) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...], int, int]:
    """Return canonical hits, alias hits, misses, and fact-hit counts.

    Args:
        answer_text: Full answer prose.
        facts: Required facts.

    Returns:
        Canonical hits, alias-only hits, missed canonical phrases, facts
        covered, and fact count.
    """

    canonical_hits: list[str] = []
    alias_hits: list[str] = []
    missed_canonical: list[str] = []
    facts_hit = 0
    for fact in facts:
        canonical_ok = True
        for phrase in fact.canonical_phrases:
            if phrase_is_present(answer_text, phrase):
                canonical_hits.append(phrase)
            else:
                canonical_ok = False
                missed_canonical.append(phrase)
        alias_ok = any(
            phrase_is_present(answer_text, alias) for alias in fact.approved_aliases
        )
        if canonical_ok or alias_ok:
            facts_hit += 1
            if not canonical_ok:
                alias_hits.extend(
                    alias
                    for alias in fact.approved_aliases
                    if phrase_is_present(answer_text, alias)
                )
    return (
        tuple(canonical_hits),
        tuple(alias_hits),
        tuple(missed_canonical),
        facts_hit,
        len(facts),
    )


def _is_deadline(*, answer_text: str, status: str, reason: str) -> bool:
    """Return whether the product deadline path fired.

    Args:
        answer_text: Full answer prose.
        status: Casefolded product status.
        reason: Casefolded terminal reason.

    Returns:
        True when the deadline reserve copy or reason is present.
    """

    if status in _DEADLINE_REASONS or reason in _DEADLINE_REASONS:
        return True
    marker = normalize_answer_text(DEADLINE_RESERVE_REFUSAL_TEXT.split(".")[0])
    return bool(marker) and marker in normalize_answer_text(answer_text)


def _is_insufficient_refusal(*, answer_text: str, status: str) -> bool:
    """Return whether the answer is an insufficient-evidence refusal.

    Args:
        answer_text: Full answer prose.
        status: Casefolded product status.

    Returns:
        True when the status or canonical refusal copy indicates refusal.
    """

    if status in _REFUSAL_STATUSES:
        return INSUFFICIENT_EVIDENCE_TEXT.casefold() in normalize_answer_text(
            answer_text
        ) or status in {"insufficient_evidence", "refused"}
    return INSUFFICIENT_EVIDENCE_TEXT.casefold() in normalize_answer_text(answer_text)


def _is_empty_retrieval(
    *,
    stages: RetrievalStageAttribution,
    fused: bool,
) -> bool:
    """Return whether retrieval stages prove zero authorized survivors.

    Args:
        stages: Retrieval attribution.
        fused: True when fused_count is positive.

    Returns:
        True only when fusion is empty and channels did not hit, or the
        explicit ``retrieval_empty`` flag is set without fusion.
    """

    if fused:
        return False
    if stages.retrieval_empty:
        return True
    hits = (stages.dense_hit, stages.bm25_hit, stages.term_hit)
    if any(item is True for item in hits):
        return False
    if stages.fused_count == 0 and all(item is False for item in hits):
        return True
    return False


def _resolve_outcome(
    *,
    deadline_failure: bool,
    error: bool,
    empty_retrieval: bool,
    verifier_refusal_after_fusion: bool,
    strict_pass: bool,
    grounded_fact_pass: bool,
    facts_hit: int,
    fact_count: int,
) -> DualOutcome:
    """Choose the first-class outcome in diagnostic priority order.

    Args:
        deadline_failure: Product deadline fired.
        error: Terminal error fired.
        empty_retrieval: Proven empty retrieval.
        verifier_refusal_after_fusion: Refusal after fused evidence.
        strict_pass: Every canonical phrase matched.
        grounded_fact_pass: Every fact matched by phrase or alias.
        facts_hit: Number of facts covered.
        fact_count: Number of required facts.

    Returns:
        Outcome bucket. Deadline and error beat lexical pass so product
        failures stay visible.
    """

    if deadline_failure:
        return DualOutcome.DEADLINE
    if error:
        return DualOutcome.ERROR
    # A released answer that already holds every canonical phrase is scored
    # as a phrase pass even when stage export marked retrieval empty (for
    # example selected evidence present while fused_ids were not persisted).
    if empty_retrieval and not strict_pass and not grounded_fact_pass:
        return DualOutcome.EMPTY_RETRIEVAL
    if verifier_refusal_after_fusion:
        return DualOutcome.VERIFIER_REFUSAL_AFTER_FUSION
    if strict_pass:
        return DualOutcome.STRICT_PHRASE
    if grounded_fact_pass:
        return DualOutcome.FACT_COVERED
    if facts_hit and fact_count:
        return DualOutcome.PARTIAL
    return DualOutcome.WRONG_PHRASING
