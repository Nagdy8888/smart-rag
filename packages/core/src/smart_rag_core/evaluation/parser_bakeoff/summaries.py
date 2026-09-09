"""Count-only parse and chunk summaries for bake-off lanes."""

from __future__ import annotations

import hashlib
from uuid import UUID

from smart_rag_core.evaluation.parser_bakeoff.constants import LaneId
from smart_rag_core.evaluation.parser_bakeoff.models import ChunkSummary
from smart_rag_core.ingestion.chunking.service import (
    chunk_parse_result,
    stable_chunking_config_hash,
)
from smart_rag_core.ingestion.chunking.types import ChunkKind
from smart_rag_core.ingestion.parser.types import (
    ParseDisposition,
    ParseResult,
    PdfLocator,
)


def element_text_hash(result: ParseResult) -> str:
    """Hash ordered element ids and normalized text without storing text.

    Args:
        result: Closed parse result.

    Returns:
        SHA-256 hex digest.
    """

    digest = hashlib.sha256()
    for element in result.elements:
        text = " ".join((element.text or "").split())
        digest.update(f"{element.element_id}|{element.kind}|{text}".encode())
    return digest.hexdigest()


def summarize_parse_chunk(
    result: ParseResult,
    *,
    lane_id: LaneId,
    document_id: UUID,
    version_id: UUID,
    replay_matched: bool,
) -> ChunkSummary:
    """Build a count-only summary after shared chunking.

    Args:
        result: Closed parse result.
        lane_id: Lane token.
        document_id: Replay document id.
        version_id: Replay version id.
        replay_matched: Whether a second parse matched.

    Returns:
        Safe chunk summary. ``char_coverage_ratio`` is intentionally omitted.
    """

    failure_code = None
    if result.disposition is ParseDisposition.FAILED:
        failure_code = result.detail or "failed"
    chunking = chunk_parse_result(
        result, document_id=document_id, version_id=version_id
    )
    kind_counts: dict[str, int] = {}
    extracted_chars = 0
    for element in result.elements:
        kind_counts[element.kind.value] = kind_counts.get(element.kind.value, 0) + 1
        extracted_chars += len(element.text or "")
    locator_chunks = 0
    pdf_page_chunks = 0
    for chunk in chunking.chunks:
        locators = chunk.provenance.locators
        if locators:
            locator_chunks += 1
        if chunk.page_number is not None or any(
            item.get("format") == "pdf" for item in locators
        ):
            pdf_page_chunks += 1
    token_band_counts = {"under_200": 0, "in_200_400": 0, "over_400": 0}
    for chunk in chunking.chunks:
        if chunk.token_count < 200:
            token_band_counts["under_200"] += 1
        elif chunk.token_count <= 400:
            token_band_counts["in_200_400"] += 1
        else:
            token_band_counts["over_400"] += 1
    total = max(len(chunking.chunks), 1)
    pages: int | None
    ocr_pages: int | None
    if lane_id == "current":
        pages = result.resource_metrics.pages_processed
        ocr_pages = result.resource_metrics.ocr_pages
    else:
        pages = None
        ocr_pages = None
    return ChunkSummary(
        lane_id=lane_id,
        disposition=result.disposition.value,
        failure_code=failure_code,
        parser_version=result.parser_version,
        cleaning_version=result.cleaning_version,
        config_hash=result.config_hash,
        chunking_config_hash=stable_chunking_config_hash(result.config_hash),
        wall_seconds=result.resource_metrics.wall_seconds,
        peak_memory_mb=result.resource_metrics.peak_memory_mb,
        pages_processed=pages,
        ocr_pages=ocr_pages,
        locator_available=lane_id == "current"
        and any(isinstance(element.locator, PdfLocator) for element in result.elements),
        element_kind_counts=kind_counts,
        extracted_chars=extracted_chars,
        chunk_count=chunking.metrics.total_chunks,
        passage_count=sum(
            1 for chunk in chunking.chunks if chunk.kind is ChunkKind.PASSAGE
        ),
        parent_count=chunking.metrics.parent_chunks,
        table_count=len(chunking.table_artifacts),
        ordinary_prose_in_target=chunking.metrics.ordinary_prose_in_target,
        ordinary_prose_chunks=chunking.metrics.ordinary_prose_chunks,
        exact_duplicate_groups=chunking.metrics.dedup.exact_duplicate_groups,
        near_duplicate_pairs=chunking.metrics.dedup.near_duplicate_pairs,
        chunks_with_locator=locator_chunks,
        chunks_with_pdf_page=pdf_page_chunks,
        locator_chunk_ratio=locator_chunks / total,
        pdf_page_chunk_ratio=pdf_page_chunks / total,
        token_band_counts=token_band_counts,
        replay_matched=replay_matched,
        element_text_hash=element_text_hash(result),
    )


def replay_matches(first: ParseResult, second: ParseResult) -> bool:
    """Return whether two parses are deterministic.

    Args:
        first: First parse.
        second: Second parse.

    Returns:
        True when config hash, element ids, and normalized text hash match.
    """

    if first.config_hash != second.config_hash:
        return False
    if [item.element_id for item in first.elements] != [
        item.element_id for item in second.elements
    ]:
        return False
    return element_text_hash(first) == element_text_hash(second)
