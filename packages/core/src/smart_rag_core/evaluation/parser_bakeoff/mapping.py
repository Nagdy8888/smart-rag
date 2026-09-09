"""Parser-neutral labels and deterministic fact-to-chunk mapping."""

from __future__ import annotations

import unicodedata
from uuid import UUID

from smart_rag_core.evaluation.parser_bakeoff.artifacts import canonical_json, sha256_text
from smart_rag_core.evaluation.parser_bakeoff.constants import (
    ALLOWED_SPLITS,
    FORBIDDEN_SPLIT,
    LaneId,
)
from smart_rag_core.evaluation.parser_bakeoff.models import (
    BakeoffError,
    GoldMap,
    GoldMappingItem,
    MappingStatus,
    NeutralCase,
    NeutralCaseSet,
)
from smart_rag_core.evaluation.private_pdf.schema import PrivatePdfLabeledCase
from smart_rag_core.ingestion.chunking.types import CanonicalChunk, ChunkKind


def normalize_mapping_text(value: str) -> str:
    """Normalize mapping text without stemming or translating Arabic.

    Args:
        value: Fact or chunk text.

    Returns:
        NFKC, Latin case-folded, whitespace-collapsed text.
    """

    nfkc = unicodedata.normalize("NFKC", value)
    folded_chars: list[str] = []
    for char in nfkc:
        if "ARABIC" in unicodedata.name(char, ""):
            folded_chars.append(char)
            continue
        folded_chars.append(char.casefold())
    return " ".join("".join(folded_chars).split())


def drop_holdout_cases(cases: tuple[PrivatePdfLabeledCase, ...]) -> None:
    """Reject any holdout-bearing payload.

    Args:
        cases: Labeled cases.

    Raises:
        BakeoffError: When a holdout split is present.
    """

    for case in cases:
        if case.meta.split == FORBIDDEN_SPLIT:
            raise BakeoffError("holdout_sealed", "holdout cases are forbidden")


def to_neutral_cases(
    labeled: tuple[PrivatePdfLabeledCase, ...],
    *,
    source_sha256: str,
    original_seal_sha256: str,
    split: str,
) -> NeutralCaseSet:
    """Strip parser-specific chunk IDs from sealed open-split cases.

    Args:
        labeled: Human-sealed labeled cases.
        source_sha256: PDF hash.
        original_seal_sha256: Hash of the source sealed file.
        split: Requested open split.

    Returns:
        Neutral case set with a content hash.

    Raises:
        BakeoffError: On holdout leakage or empty input.
    """

    if split == FORBIDDEN_SPLIT:
        raise BakeoffError("holdout_sealed", "holdout split is forbidden")
    drop_holdout_cases(labeled)
    selected = tuple(item for item in labeled if item.meta.split == split)
    if not selected:
        raise BakeoffError("no_scored_cases", "no open-split cases")
    cases = tuple(
        NeutralCase(
            case_id=item.meta.case_id,
            split=item.meta.split,
            source_family_id=item.meta.source_family_id,
            query_class=item.meta.query_class,
            question=item.question,
            expected_answer=item.expected_answer,
            atomic_facts=item.atomic_facts,
            required_terms=item.meta.required_terms,
            page_numbers=item.meta.page_numbers,
            expected_refusal=item.meta.expected_refusal,
            expected_profile_id=item.meta.expected_profile_id,
            expected_scope=item.meta.expected_scope,
            acl_actor_id=item.meta.acl_actor_id,
            human_approved=item.meta.human_approved,
            reviewer=item.meta.reviewer,
        )
        for item in selected
    )
    payload = NeutralCaseSet(
        source_sha256=source_sha256,
        original_seal_sha256=original_seal_sha256,
        split=split,
        cases=cases,
    )
    digest = sha256_text(canonical_json(payload.model_dump(mode="json")))
    return payload.model_copy(update={"case_set_sha256": digest})


def map_facts_to_chunks(
    cases: tuple[NeutralCase, ...],
    chunks: tuple[CanonicalChunk, ...],
    *,
    lane_id: LaneId,
    source_sha256: str,
    version_id: UUID,
) -> GoldMap:
    """Map non-refusal atomic facts by exact normalized containment.

    Zero, multi, or cross-chunk matches require human review. Unmapped facts
    stay in the denominator as extraction failures after review.

    Args:
        cases: Neutral cases.
        chunks: Lane chunks after shared chunking.
        lane_id: Lane token.
        source_sha256: PDF hash.
        version_id: Lane version.

    Returns:
        Unapproved gold map plus review items.
    """

    passages = tuple(
        chunk
        for chunk in chunks
        if chunk.kind is ChunkKind.PASSAGE and chunk.is_search_representative
    )
    items: list[GoldMappingItem] = []
    for case in cases:
        if case.expected_refusal:
            continue
        facts = case.atomic_facts or (
            (case.expected_answer,) if case.expected_answer.strip() else ()
        )
        for fact_index, fact in enumerate(facts):
            needle = normalize_mapping_text(fact)
            if not needle:
                items.append(
                    GoldMappingItem(
                        case_id=case.case_id,
                        fact_index=fact_index,
                        status=MappingStatus.REVIEW_REQUIRED,
                        extraction_failure=True,
                    )
                )
                continue
            matches = tuple(
                chunk.chunk_id
                for chunk in passages
                if needle in normalize_mapping_text(chunk.raw_text)
            )
            if len(matches) == 1:
                items.append(
                    GoldMappingItem(
                        case_id=case.case_id,
                        fact_index=fact_index,
                        status=MappingStatus.AUTOMATIC,
                        chunk_ids=(matches[0],),
                    )
                )
                continue
            items.append(
                GoldMappingItem(
                    case_id=case.case_id,
                    fact_index=fact_index,
                    status=MappingStatus.REVIEW_REQUIRED,
                    candidate_chunk_ids=matches,
                    extraction_failure=len(matches) == 0,
                )
            )
    mapping = GoldMap(
        lane_id=lane_id,
        source_sha256=source_sha256,
        version_id=version_id,
        items=tuple(items),
    )
    digest = sha256_text(canonical_json(mapping.model_dump(mode="json")))
    return mapping.model_copy(update={"gold_map_sha256": digest})


def apply_review(
    mapping: GoldMap,
    *,
    decisions: dict[tuple[str, int], tuple[UUID, ...]],
    reviewer: str,
    rejected: set[tuple[str, int]] | None = None,
) -> GoldMap:
    """Apply human review selections without dropping the denominator.

    Args:
        mapping: Pending gold map.
        decisions: Selected chunk ids keyed by ``(case_id, fact_index)``.
        reviewer: Named reviewer.
        rejected: Facts explicitly rejected as unmapped extraction failures.

    Returns:
        Approved map when every review item is resolved.

    Raises:
        BakeoffError: When review is incomplete.
    """

    rejected_keys = rejected or set()
    resolved: list[GoldMappingItem] = []
    pending = 0
    for item in mapping.items:
        key = (item.case_id, item.fact_index)
        if item.status is MappingStatus.AUTOMATIC:
            resolved.append(item)
            continue
        if key in rejected_keys:
            resolved.append(
                item.model_copy(
                    update={
                        "status": MappingStatus.UNMAPPED,
                        "chunk_ids": (),
                        "extraction_failure": True,
                    }
                )
            )
            continue
        selected = decisions.get(key)
        if selected is None:
            pending += 1
            resolved.append(item)
            continue
        resolved.append(
            item.model_copy(
                update={
                    "status": MappingStatus.APPROVED,
                    "chunk_ids": tuple(selected),
                    "extraction_failure": len(selected) == 0,
                }
            )
        )
    if pending:
        raise BakeoffError("gold_review_incomplete", f"unresolved review items {pending}")
    approved = mapping.model_copy(
        update={"items": tuple(resolved), "reviewer": reviewer, "approved": True}
    )
    digest = sha256_text(canonical_json(approved.model_dump(mode="json")))
    return approved.model_copy(update={"gold_map_sha256": digest})


def assert_allowed_split(split: str, *, protocol_frozen: bool) -> None:
    """Reject holdout and unfrozen qualification.

    Args:
        split: Requested split token.
        protocol_frozen: Whether development protocol hashes are frozen.

    Raises:
        BakeoffError: When the split is forbidden for this experiment.
    """

    if split == FORBIDDEN_SPLIT:
        raise BakeoffError("holdout_sealed", "holdout split is forbidden")
    if split == "qualification" and not protocol_frozen:
        raise BakeoffError(
            "qualification_blocked",
            "qualification requires a frozen development protocol",
        )
    if split not in ALLOWED_SPLITS:
        raise BakeoffError("unknown_split", "split is not allow-listed")


def review_pending_count(mapping: GoldMap) -> int:
    """Count unresolved review items.

    Args:
        mapping: Gold map.

    Returns:
        Number of ``review_required`` items.
    """

    return sum(
        1 for item in mapping.items if item.status is MappingStatus.REVIEW_REQUIRED
    )


def fact_chunk_ids_for_case(
    mapping: GoldMap, case_id: str
) -> tuple[tuple[UUID, ...], ...]:
    """Return per-fact supporting ids, including empty extraction failures.

    Args:
        mapping: Gold map.
        case_id: Case id.

    Returns:
        One tuple of chunk ids per fact for that case.
    """

    groups: list[tuple[UUID, ...]] = []
    for item in mapping.items:
        if item.case_id != case_id:
            continue
        groups.append(item.chunk_ids)
    return tuple(groups)


def gold_ids_for_case(mapping: GoldMap, case_id: str) -> tuple[UUID, ...]:
    """Return unique mapped chunk ids for one case.

    Args:
        mapping: Approved gold map.
        case_id: Case id.

    Returns:
        Chunk UUIDs. Empty when every fact is an extraction failure.
    """

    seen: list[UUID] = []
    for item in mapping.items:
        if item.case_id != case_id:
            continue
        for chunk_id in item.chunk_ids:
            if chunk_id not in seen:
                seen.append(chunk_id)
    return tuple(seen)
