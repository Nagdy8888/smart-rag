"""Evidence locators and units from authorized chunk context."""

from __future__ import annotations

from smart_rag_core.retrieval.context_loader import ChunkContext
from smart_rag_core.retrieval.hybrid_run.types import EvidenceLocator, EvidenceUnit
from smart_rag_core.retrieval.profiles import FINAL_EVIDENCE_MAX
from smart_rag_core.retrieval.rerank import RerankPassage
from smart_rag_core.retrieval.types import RetrievalCandidate


def _evidence_units(
    passages: tuple[RerankPassage, ...],
    contexts: tuple[ChunkContext, ...],
) -> tuple[EvidenceUnit, ...]:
    """Join selected passages to canonical locator rows.

    Args:
        passages: MMR-trimmed passages. Citation text is canonical raw_text.
        contexts: Authorized rows for those IDs, including parents.

    Returns:
        Evidence units capped by selection order. BM25 text is unused.
    """

    by_id = {item.chunk_id: item for item in contexts}
    units: list[EvidenceUnit] = []
    for passage in passages:
        candidate = passage.candidate
        record = by_id.get(candidate.chunk_id)
        citation = record.raw_text if record is not None else passage.raw_text
        locator = _locator_from_context(record, passage)
        units.append(
            EvidenceUnit(
                chunk_id=candidate.chunk_id,
                document_id=candidate.document_id,
                version_id=candidate.version_id,
                citation_text=citation,
                locator=locator,
            )
        )
        if len(units) >= FINAL_EVIDENCE_MAX:
            break
    return tuple(units)


def _evidence_units_from_context(
    fused: tuple[RetrievalCandidate, ...],
    contexts: tuple[ChunkContext, ...],
) -> tuple[EvidenceUnit, ...]:
    """Build evidence from fused IDs when no profile/rerank ran.

    Args:
        fused: Fused authorized candidates, already trimmed.
        contexts: Authorized canonical rows.

    Returns:
        Evidence units using ``ChunkContext.raw_text`` only.
    """

    by_id = {item.chunk_id: item for item in contexts}
    units: list[EvidenceUnit] = []
    for candidate in fused:
        record = by_id.get(candidate.chunk_id)
        if record is None:
            continue
        units.append(
            EvidenceUnit(
                chunk_id=record.chunk_id,
                document_id=record.document_id,
                version_id=record.version_id,
                citation_text=record.raw_text,
                locator=_locator_from_context(record, None),
            )
        )
        if len(units) >= FINAL_EVIDENCE_MAX:
            break
    return tuple(units)


def _locator_from_context(
    record: ChunkContext | None,
    passage: RerankPassage | None,
) -> EvidenceLocator:
    """Copy locator fields from canonical context, then passage page/section.

    Args:
        record: Authorized chunk row when present.
        passage: Selected passage used only for page/section fallback.

    Returns:
        Locator with canonical sheet/range/URL when the row exists.
    """

    if record is not None:
        return EvidenceLocator(
            page_number=record.page_number,
            section_path=record.section_path,
            sheet_name=record.sheet_name,
            range_ref=record.range_ref,
            source_url=record.source_url,
        )
    if passage is None:
        return EvidenceLocator()
    return EvidenceLocator(
        page_number=passage.page_number,
        section_path=passage.section_path,
    )
