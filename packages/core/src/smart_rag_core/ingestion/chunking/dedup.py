"""Near and exact duplicate detection within one document version."""

from __future__ import annotations

import re
from dataclasses import dataclass

from smart_rag_core.ingestion.chunking.limits import (
    DEDUP_POLICY_VERSION,
    NEAR_DUP_MIN_PRECISION,
    NEAR_DUP_MIN_RECALL,
    NEAR_DUP_SHINGLE_SIZE,
    NEAR_DUP_SIMILARITY_THRESHOLD,
)
from smart_rag_core.ingestion.chunking.normalize import (
    content_hash,
    normalize_for_dedup,
)
from smart_rag_core.ingestion.chunking.types import CanonicalChunk, DedupMetrics

_WORD_RE = re.compile(r"\w+", flags=re.UNICODE)


@dataclass(frozen=True, slots=True)
class LabeledPair:
    """One labeled near-duplicate evaluation pair."""

    text_a: str
    text_b: str
    is_near_duplicate: bool


def apply_deduplication(
    chunks: list[CanonicalChunk],
) -> tuple[list[CanonicalChunk], DedupMetrics]:
    """Apply exact and optional near deduplication while preserving provenance.

    Args:
        chunks: Passage and parent chunks for one version.

    Returns:
        Updated chunks and measured dedup metrics.
    """

    exact_groups: dict[str, list[CanonicalChunk]] = {}
    for chunk in chunks:
        if chunk.kind.value != "passage":
            continue
        digest = chunk.provenance.normalized_content_hash
        exact_groups.setdefault(digest, []).append(chunk)

    exact_duplicate_groups = sum(1 for group in exact_groups.values() if len(group) > 1)
    for group in exact_groups.values():
        if len(group) <= 1:
            continue
        representative = group[0]
        for duplicate in group[1:]:
            _mark_duplicate(duplicate, representative)

    fuzzy_enabled = evaluate_fuzzy_policy(DEFAULT_FUZZY_FIXTURES)
    near_duplicate_pairs = 0
    if fuzzy_enabled:
        passage_chunks = [chunk for chunk in chunks if chunk.kind.value == "passage"]
        for index, left in enumerate(passage_chunks):
            if left.duplicate_of_chunk_id is not None:
                continue
            for right in passage_chunks[index + 1 :]:
                if right.duplicate_of_chunk_id is not None:
                    continue
                if (
                    left.provenance.normalized_content_hash
                    == right.provenance.normalized_content_hash
                ):
                    continue
                if (
                    _near_similarity(left.raw_text, right.raw_text)
                    >= NEAR_DUP_SIMILARITY_THRESHOLD
                ):
                    _mark_duplicate(right, left)
                    near_duplicate_pairs += 1

    precision, recall = (
        measure_fuzzy_metrics(DEFAULT_FUZZY_FIXTURES) if fuzzy_enabled else (None, None)
    )
    return chunks, DedupMetrics(
        exact_duplicate_groups=exact_duplicate_groups,
        near_duplicate_pairs=near_duplicate_pairs,
        fuzzy_enabled=fuzzy_enabled,
        fuzzy_precision=precision,
        fuzzy_recall=recall,
        dedup_mode="exact_and_near" if fuzzy_enabled else "exact_only",
    )


def _mark_duplicate(duplicate: CanonicalChunk, representative: CanonicalChunk) -> None:
    """Point one chunk at its representative while retaining locators."""

    duplicate.duplicate_of_chunk_id = representative.chunk_id
    duplicate.is_search_representative = False
    duplicate_locators = tuple(duplicate.provenance.locators)
    duplicate.provenance = duplicate.provenance.model_copy(
        update={
            "duplicate_locators": (
                *duplicate.provenance.duplicate_locators,
                *duplicate_locators,
            ),
            "dedup_mode": representative.provenance.dedup_mode,
        }
    )


def _shingles(text: str) -> set[str]:
    """Build word shingles for near-duplicate comparison."""

    words = _WORD_RE.findall(normalize_for_dedup(text))
    if len(words) < NEAR_DUP_SHINGLE_SIZE:
        return {" ".join(words)} if words else set()
    return {
        " ".join(words[index : index + NEAR_DUP_SHINGLE_SIZE])
        for index in range(len(words) - NEAR_DUP_SHINGLE_SIZE + 1)
    }


def _near_similarity(left: str, right: str) -> float:
    """Compute Jaccard similarity over word shingles."""

    left_shingles = _shingles(left)
    right_shingles = _shingles(right)
    if not left_shingles or not right_shingles:
        return 0.0
    intersection = left_shingles & right_shingles
    union = left_shingles | right_shingles
    return len(intersection) / len(union)


def measure_fuzzy_metrics(pairs: tuple[LabeledPair, ...]) -> tuple[float, float]:
    """Measure precision and recall for the near-duplicate policy on fixtures.

    Args:
        pairs: Labeled evaluation pairs.

    Returns:
        Tuple of precision and recall in ``[0, 1]``.
    """

    true_positive = 0
    false_positive = 0
    false_negative = 0
    for pair in pairs:
        predicted = (
            _near_similarity(pair.text_a, pair.text_b) >= NEAR_DUP_SIMILARITY_THRESHOLD
        )
        if pair.is_near_duplicate and predicted:
            true_positive += 1
        elif not pair.is_near_duplicate and predicted:
            false_positive += 1
        elif pair.is_near_duplicate and not predicted:
            false_negative += 1
    precision = true_positive / (true_positive + false_positive or 1)
    recall = true_positive / (true_positive + false_negative or 1)
    return precision, recall


def evaluate_fuzzy_policy(pairs: tuple[LabeledPair, ...]) -> bool:
    """Return whether fuzzy dedup meets precision/recall gates.

    Args:
        pairs: Labeled evaluation fixtures.

    Returns:
        ``True`` when fuzzy dedup is approved; otherwise exact-only fallback.
    """

    precision, recall = measure_fuzzy_metrics(pairs)
    return precision >= NEAR_DUP_MIN_PRECISION and recall >= NEAR_DUP_MIN_RECALL


DEFAULT_FUZZY_FIXTURES: tuple[LabeledPair, ...] = (
    LabeledPair(
        "The quarterly revenue increased by twelve percent in Q1.",
        "Quarterly revenue increased 12 percent during Q1.",
        True,
    ),
    LabeledPair(
        "Policy section 4.2 requires owner approval before external processing.",
        "Section 4.2 policy mandates owner approval for external processing.",
        True,
    ),
    LabeledPair(
        "مرحبا بالعالم this mixed Arabic English sentence remains unique.",
        "مرحبا بالعالم this mixed Arabic English sentence remains unique.",
        True,
    ),
    LabeledPair(
        "Widget assembly instructions for model A-100.",
        "Widget assembly instructions for model B-200 with different torque values.",
        False,
    ),
    LabeledPair(
        "Approved budget for travel is five thousand USD.",
        "Graph indexing requires admin approval and separate workspace.",
        False,
    ),
    LabeledPair(
        "Exact duplicate authority text from document one.",
        "Exact duplicate authority text from document one.",
        True,
    ),
)


def normalized_hash(text: str) -> str:
    """Expose normalized content hashing for chunk builders."""

    return content_hash(text)


def dedup_policy_version() -> str:
    """Return the pinned dedup policy version."""

    return DEDUP_POLICY_VERSION
