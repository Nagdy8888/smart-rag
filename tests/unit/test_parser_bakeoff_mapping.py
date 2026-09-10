"""Unit tests for parser-neutral mapping and review."""

from __future__ import annotations

from uuid import uuid4

import pytest
from smart_rag_core.evaluation.parser_bakeoff.mapping import (
    apply_review,
    assert_allowed_split,
    fact_chunk_ids_for_case,
    gold_ids_for_case,
    map_facts_to_chunks,
    normalize_mapping_text,
    review_pending_count,
    to_neutral_cases,
)
from smart_rag_core.evaluation.parser_bakeoff.models import (
    BakeoffError,
    MappingStatus,
    NeutralCase,
)
from smart_rag_core.evaluation.private_pdf.schema import (
    PrivatePdfCase,
    PrivatePdfLabeledCase,
)
from smart_rag_core.ingestion.chunking.types import (
    CanonicalChunk,
    ChunkKind,
    ChunkProvenance,
)


def _provenance() -> ChunkProvenance:
    """Return a minimal provenance record.

    Returns:
        Provenance model.
    """

    return ChunkProvenance(
        parser_version="parser_v1",
        cleaning_version="cleaning_v1",
        chunking_version="chunking_v2",
        tokenizer_version="cl100k_base_v1",
        dedup_policy_version="dedup_v1",
        normalized_content_hash="abc",
    )


def _chunk(text: str) -> CanonicalChunk:
    """Build one representative passage.

    Args:
        text: Raw chunk text.

    Returns:
        Canonical chunk.
    """

    return CanonicalChunk(
        chunk_id=uuid4(),
        chunk_index=0,
        kind=ChunkKind.PASSAGE,
        raw_text=text,
        token_count=12,
        provenance=_provenance(),
        is_search_representative=True,
    )


def _case(*, facts: tuple[str, ...], refusal: bool = False) -> NeutralCase:
    """Build one neutral case.

    Args:
        facts: Atomic facts.
        refusal: Expected refusal.

    Returns:
        Neutral case.
    """

    return NeutralCase(
        case_id="case-0010",
        split="development",
        source_family_id="family-0010",
        query_class="factual_definition",
        question="What is the definition?",
        expected_answer=facts[0] if facts else "",
        atomic_facts=facts,
        expected_refusal=refusal,
        human_approved=True,
        reviewer="Nagdy",
    )


def test_normalize_preserves_arabic_and_folds_latin() -> None:
    """NFKC plus Latin case-fold must not stem or translate Arabic."""

    assert normalize_mapping_text("  Hello   WORLD  ") == "hello world"
    arabic = "الوكيل الذكي"
    assert arabic in normalize_mapping_text(f"  {arabic}  ")
    assert normalize_mapping_text(arabic) == arabic


def test_exact_containment_maps_automatically() -> None:
    """A unique normalized containment is automatic gold."""

    chunk = _chunk("The orchestrator routes tasks to specialist agents.")
    mapping = map_facts_to_chunks(
        (_case(facts=("orchestrator routes tasks",)),),
        (chunk,),
        lane_id="current",
        source_sha256="a" * 64,
        version_id=uuid4(),
    )
    assert mapping.items[0].status is MappingStatus.AUTOMATIC
    assert mapping.items[0].chunk_ids == (chunk.chunk_id,)
    assert review_pending_count(mapping) == 0


def test_zero_and_multi_match_require_review_and_stay_in_denominator() -> None:
    """Ambiguous and missing facts stay in the gold map for review."""

    left = _chunk("Alpha appears here and also later.")
    right = CanonicalChunk(
        chunk_id=uuid4(),
        chunk_index=1,
        kind=ChunkKind.PASSAGE,
        raw_text="Alpha appears here and also later in a second chunk.",
        token_count=16,
        provenance=_provenance(),
    )
    mapping = map_facts_to_chunks(
        (_case(facts=("Alpha appears here", "missing fact never present")),),
        (left, right),
        lane_id="anydoc_local",
        source_sha256="b" * 64,
        version_id=uuid4(),
    )
    assert review_pending_count(mapping) == 2
    assert len(mapping.items) == 2
    with pytest.raises(BakeoffError) as err:
        apply_review(mapping, decisions={}, reviewer="Nagdy")
    assert err.value.code == "gold_review_incomplete"
    approved = apply_review(
        mapping,
        decisions={(mapping.items[0].case_id, 0): (left.chunk_id,)},
        reviewer="Nagdy",
        rejected={(mapping.items[1].case_id, 1)},
    )
    assert approved.approved is True
    groups = fact_chunk_ids_for_case(approved, "case-0010")
    assert groups[1] == ()
    assert gold_ids_for_case(approved, "case-0010") == (left.chunk_id,)


def test_holdout_and_qualification_gates() -> None:
    """Holdout is forbidden and qualification waits for a frozen protocol."""

    with pytest.raises(BakeoffError) as err:
        assert_allowed_split("holdout", protocol_frozen=False)
    assert err.value.code == "holdout_sealed"
    with pytest.raises(BakeoffError) as blocked:
        assert_allowed_split("qualification", protocol_frozen=False)
    assert blocked.value.code == "qualification_blocked"
    labeled = (
        PrivatePdfLabeledCase(
            meta=PrivatePdfCase(
                case_id="case-hold1",
                split="holdout",
                source_family_id="family-hold1",
                query_class="factual_definition",
                human_approved=True,
                generated_only=False,
                reviewer="Nagdy",
            ),
            question="secret holdout question",
        ),
    )
    with pytest.raises(BakeoffError) as err:
        to_neutral_cases(
            labeled,
            source_sha256="c" * 64,
            original_seal_sha256="d" * 64,
            split="development",
        )
    assert err.value.code == "holdout_sealed"


def test_neutral_cases_strip_chunk_ids() -> None:
    """Parser-specific chunk ids are removed from sealed open-split cases."""

    chunk_id = uuid4()
    labeled = (
        PrivatePdfLabeledCase(
            meta=PrivatePdfCase(
                case_id="case-open01",
                split="development",
                source_family_id="family-open01",
                query_class="factual_definition",
                chunk_ids=(chunk_id,),
                page_numbers=(3,),
                human_approved=True,
                generated_only=False,
                reviewer="Nagdy",
            ),
            question="What is orchestration?",
            expected_answer="routing",
            atomic_facts=("routing",),
        ),
    )
    neutral = to_neutral_cases(
        labeled,
        source_sha256="e" * 64,
        original_seal_sha256="f" * 64,
        split="development",
    )
    assert "chunk_ids" not in neutral.cases[0].model_dump()
    assert neutral.cases[0].page_numbers == (3,)
    assert neutral.holdout_opened is False
