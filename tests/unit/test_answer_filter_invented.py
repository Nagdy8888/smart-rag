"""filter_invented_ids must drop ungrounded citations before verify."""

from __future__ import annotations

from smart_rag_core.query_answer.generate import filter_invented_ids
from smart_rag_core.query_answer.models import AnswerCitation, AnswerPayload, AtomicLink
from smart_rag_core.query_fusion import fusion_config_hash
from smart_rag_core.query_fusion.models import (
    FusionAlgorithm,
    FusionResult,
    PassageOrigin,
    ScoredPassage,
)
from smart_rag_core.query_routing.models import TableEvidenceRecord


def _uid(n: int) -> str:
    """Return a synthetic UUID.

    Args:
        n: Discriminator.

    Returns:
        Canonical UUID string.
    """

    return f"{n:08x}-0000-4000-8000-000000000000"


def _fusion(*texts: tuple[int, str]) -> FusionResult:
    """Build Hybrid-effective fusion from chunk discriminators.

    Args:
        texts: ``(n, citation_text)`` pairs.

    Returns:
        Frozen fusion result.
    """

    passages = tuple(
        ScoredPassage(
            chunk_id=_uid(n),
            document_id=_uid(10_000 + n),
            version_id=_uid(20_000 + n),
            citation_text=text,
            hybrid_rank=index,
            combined_score=1.0 / (60 + index),
            origin=PassageOrigin.HYBRID,
            graph_discovered_only=False,
        )
        for index, (n, text) in enumerate(texts, start=1)
    )
    return FusionResult(
        algorithm=FusionAlgorithm.RESOLVED_PATH_FUSION,
        config_hash=fusion_config_hash(FusionAlgorithm.RESOLVED_PATH_FUSION),
        requested_route="hybrid",
        effective_route="hybrid",
        evidence=passages,
        graph_discovered_only_ratio=0.0,
    )


def _table() -> TableEvidenceRecord:
    """Return one sandbox table snapshot.

    Returns:
        Deterministic table evidence.
    """

    return TableEvidenceRecord(
        table_id=_uid(700),
        version_id=_uid(701),
        document_id=_uid(702),
        source_ranges=("Sheet1!B2:B4",),
        operation="sum:revenue",
        rows=({"region": "north", "revenue": 10.0},),
        sheet="Sheet1",
        units="USD",
    )


def test_filter_drops_none_chunk_id_without_allowed_table() -> None:
    """``chunk_id is None`` is dropped unless ``table_id`` is an allowed table."""

    fusion = _fusion((1, "Refunds are issued within 30 days."))
    payload = AnswerPayload(
        answer_text="Invented citation.",
        citations=(
            AnswerCitation(chunk_id=None, table_id=None),
            AnswerCitation(chunk_id=_uid(1)),
        ),
        atomic_links=(
            AtomicLink(
                link_id="ok",
                claim="Refunds are issued within 30 days.",
                chunk_ids=(_uid(1),),
            ),
        ),
        status="complete",
    )
    filtered = filter_invented_ids(payload, fusion, ())
    assert all(item.chunk_id is not None for item in filtered.citations)
    assert tuple(item.chunk_id for item in filtered.citations) == (_uid(1),)


def test_filter_keeps_none_chunk_id_when_table_id_allowed() -> None:
    """Table-only citations survive when the table id is in composition."""

    fusion = _fusion()
    table = _table()
    payload = AnswerPayload(
        answer_text="North revenue is 10.",
        citations=(
            AnswerCitation(
                chunk_id=None,
                table_id=table.table_id,
                source_ranges=("Sheet1!B2:B4",),
            ),
        ),
        table_citations=(
            AnswerCitation(
                table_id=table.table_id,
                source_ranges=("Sheet1!B2:B4",),
            ),
        ),
        status="complete",
    )
    filtered = filter_invented_ids(payload, fusion, (table,))
    assert len(filtered.citations) == 1
    assert filtered.citations[0].table_id == table.table_id
    assert filtered.table_citations[0].table_id == table.table_id


def test_filter_drops_invented_chunk_and_unknown_table() -> None:
    """IDs not in fusion or table composition are stripped."""

    fusion = _fusion((1, "Canonical passage."))
    payload = AnswerPayload(
        answer_text="Invented ids.",
        citations=(
            AnswerCitation(chunk_id=_uid(99)),
            AnswerCitation(chunk_id=None, table_id=_uid(800)),
        ),
        table_citations=(AnswerCitation(table_id=_uid(800)),),
        status="complete",
    )
    filtered = filter_invented_ids(payload, fusion, ())
    assert filtered.citations == ()
    assert filtered.table_citations == ()
