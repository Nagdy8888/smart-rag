"""Hierarchical chunk construction from typed parser elements."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from smart_rag_core.ingestion.chunking import tokenizer
from smart_rag_core.ingestion.chunking.dedup import (
    dedup_policy_version,
    normalized_hash,
)
from smart_rag_core.ingestion.chunking.limits import (
    CHUNKING_POLICY_VERSION,
    PARENT_MAX_TOKENS,
    PASSAGE_HARD_MAX_TOKENS,
    TOKENIZER_VERSION,
)
from smart_rag_core.ingestion.chunking.splitter import (
    ProseSegment,
    split_oversized_atomic,
    split_prose_segments,
)
from smart_rag_core.ingestion.chunking.stable_id import stable_chunk_id
from smart_rag_core.ingestion.chunking.types import (
    CanonicalChunk,
    ChunkKind,
    ChunkProvenance,
)
from smart_rag_core.ingestion.parser.types import ElementKind, ParseResult, TypedElement
from smart_rag_core.ingestion.provenance import locator_to_dict


@dataclass
class _DraftChunk:
    """Mutable builder state before stable IDs are assigned."""

    kind: ChunkKind
    raw_text: str
    element_ids: tuple[str, ...]
    locators: tuple[dict[str, Any], ...]
    heading_ancestry: tuple[str, ...]
    page_number: int | None
    atomic_element_id: str | None = None
    fragment_ordinal: int = 0
    is_fragment: bool = False
    is_atomic_exception: bool = False
    child_chunk_ids: tuple[str, ...] = field(default_factory=tuple)


def build_hierarchical_chunks(
    parse_result: ParseResult,
    *,
    document_id: UUID,
    version_id: UUID,
) -> list[CanonicalChunk]:
    """Build passage and parent chunks from one typed parse result.

    Args:
        parse_result: Closed parser output with typed elements.
        document_id: Canonical document identifier.
        version_id: Immutable version identifier.

    Returns:
        Ordered canonical chunks with stable IDs and provenance.
    """

    if parse_result.format in {"csv", "xlsx"}:
        return []

    drafts: list[_DraftChunk] = []
    heading_stack: list[str] = []
    prose_buffer: list[ProseSegment] = []
    table_rows: dict[int, list[TypedElement]] = {}
    table_headers: list[str] = []
    list_intro: str | None = None
    list_items: list[TypedElement] = []

    def flush_prose() -> None:
        nonlocal prose_buffer
        if not prose_buffer:
            return
        for segment in split_prose_segments(prose_buffer):
            drafts.append(
                _DraftChunk(
                    kind=ChunkKind.PASSAGE,
                    raw_text=segment.text,
                    element_ids=segment.element_ids,
                    locators=segment.locators,
                    heading_ancestry=tuple(heading_stack),
                    page_number=_page_from_locators(segment.locators),
                )
            )
        prose_buffer = []

    def flush_table() -> None:
        nonlocal table_rows, table_headers
        if not table_rows:
            return
        header_line = " | ".join(table_headers) if table_headers else ""
        for row_index in sorted(table_rows):
            cells = table_rows[row_index]
            row_text = " | ".join(cell.text or "" for cell in cells)
            body = f"{header_line}\n{row_text}" if header_line else row_text
            element_ids = tuple(cell.element_id for cell in cells)
            locators = tuple(locator_to_dict(cell.locator) for cell in cells)
            drafts.append(
                _DraftChunk(
                    kind=ChunkKind.PASSAGE,
                    raw_text=body,
                    element_ids=element_ids,
                    locators=locators,
                    heading_ancestry=tuple(heading_stack),
                    page_number=_page_from_locators(locators),
                )
            )
        table_rows = {}
        table_headers = []

    def flush_list() -> None:
        nonlocal list_intro, list_items
        if not list_items:
            list_intro = None
            return
        intro = f"{list_intro}\n" if list_intro else ""
        for item in list_items:
            body = f"{intro}- {item.text or ''}".strip()
            drafts.append(
                _DraftChunk(
                    kind=ChunkKind.PASSAGE,
                    raw_text=body,
                    element_ids=(item.element_id,),
                    locators=(locator_to_dict(item.locator),),
                    heading_ancestry=tuple(heading_stack),
                    page_number=_page_from_locators((locator_to_dict(item.locator),)),
                )
            )
        list_intro = None
        list_items = []

    for element in parse_result.elements:
        if element.media_only:
            continue
        kind = element.kind
        if kind is ElementKind.HEADING and element.text:
            flush_prose()
            flush_table()
            flush_list()
            heading_stack = _update_heading_stack(heading_stack, element.text)
            prose_buffer.append(
                ProseSegment(
                    text=element.text,
                    element_ids=(element.element_id,),
                    locators=(locator_to_dict(element.locator),),
                )
            )
            continue
        if kind in {ElementKind.PAGE_BREAK, ElementKind.SLIDE_BREAK}:
            flush_prose()
            flush_table()
            flush_list()
            continue
        if kind is ElementKind.CODE:
            flush_prose()
            flush_table()
            flush_list()
            drafts.extend(
                _atomic_chunks(
                    element,
                    heading_stack=tuple(heading_stack),
                )
            )
            continue
        if kind is ElementKind.CAPTION:
            flush_prose()
            flush_table()
            flush_list()
            drafts.extend(
                _atomic_chunks(
                    element,
                    heading_stack=tuple(heading_stack),
                )
            )
            continue
        if kind in {ElementKind.TABLE_HEADER, ElementKind.TABLE_CELL, ElementKind.TABLE_ROW}:
            flush_prose()
            flush_list()
            if kind is ElementKind.TABLE_HEADER and element.text:
                table_headers.append(element.text)
                continue
            row_index = _table_row_index(element)
            table_rows.setdefault(row_index, []).append(element)
            continue
        if kind is ElementKind.TABLE:
            flush_prose()
            flush_list()
            continue
        if kind is ElementKind.LIST:
            flush_prose()
            flush_table()
            list_intro = element.text
            continue
        if kind is ElementKind.LIST_ITEM:
            flush_prose()
            flush_table()
            list_items.append(element)
            continue
        if kind is ElementKind.PARAGRAPH and element.text:
            flush_table()
            flush_list()
            prose_buffer.append(
                ProseSegment(
                    text=element.text,
                    element_ids=(element.element_id,),
                    locators=(locator_to_dict(element.locator),),
                )
            )
            continue
        if element.text:
            flush_table()
            flush_list()
            prose_buffer.append(
                ProseSegment(
                    text=element.text,
                    element_ids=(element.element_id,),
                    locators=(locator_to_dict(element.locator),),
                )
            )

    flush_prose()
    flush_table()
    flush_list()

    passage_chunks = _materialize_passages(
        drafts,
        parse_result=parse_result,
        document_id=document_id,
        version_id=version_id,
    )
    parent_chunks = _build_parent_chunks(
        passage_chunks,
        parse_result=parse_result,
        document_id=document_id,
        version_id=version_id,
    )
    return passage_chunks + parent_chunks


def _atomic_chunks(
    element: TypedElement,
    *,
    heading_stack: tuple[str, ...],
) -> list[_DraftChunk]:
    """Build one or more atomic drafts for code/caption elements."""

    text = element.text or ""
    token_count = tokenizer.count_tokens(text)
    if token_count <= PASSAGE_HARD_MAX_TOKENS:
        return [
            _DraftChunk(
                kind=ChunkKind.PASSAGE,
                raw_text=text,
                element_ids=(element.element_id,),
                locators=(locator_to_dict(element.locator),),
                heading_ancestry=heading_stack,
                page_number=_page_from_locators((locator_to_dict(element.locator),)),
                atomic_element_id=element.element_id,
            )
        ]
    fragments = split_oversized_atomic(text)
    return [
        _DraftChunk(
            kind=ChunkKind.PASSAGE,
            raw_text=fragment,
            element_ids=(element.element_id,),
            locators=(locator_to_dict(element.locator),),
            heading_ancestry=heading_stack,
            page_number=_page_from_locators((locator_to_dict(element.locator),)),
            atomic_element_id=element.element_id,
            fragment_ordinal=index,
            is_fragment=True,
            is_atomic_exception=True,
        )
        for index, fragment in enumerate(fragments)
    ]


def _materialize_passages(
    drafts: list[_DraftChunk],
    *,
    parse_result: ParseResult,
    document_id: UUID,
    version_id: UUID,
) -> list[CanonicalChunk]:
    """Assign stable IDs and provenance to passage drafts."""

    chunks: list[CanonicalChunk] = []
    for index, draft in enumerate(drafts):
        normalized = normalized_hash(draft.raw_text)
        chunk_id = stable_chunk_id(
            document_id=document_id,
            version_id=version_id,
            element_ids=draft.element_ids,
            element_path=draft.heading_ancestry,
            normalized_content_hash=normalized,
            parser_version=parse_result.parser_version,
            cleaning_version=parse_result.cleaning_version,
            fragment_ordinal=draft.fragment_ordinal,
        )
        chunks.append(
            CanonicalChunk(
                chunk_id=chunk_id,
                chunk_index=index,
                kind=draft.kind,
                raw_text=draft.raw_text,
                token_count=tokenizer.count_tokens(draft.raw_text),
                section_path=list(draft.heading_ancestry),
                page_number=draft.page_number,
                provenance=ChunkProvenance(
                    element_ids=draft.element_ids,
                    atomic_element_id=draft.atomic_element_id,
                    fragment_ordinal=draft.fragment_ordinal,
                    is_fragment=draft.is_fragment,
                    is_atomic_exception=draft.is_atomic_exception,
                    locators=draft.locators,
                    heading_ancestry=draft.heading_ancestry,
                    parser_version=parse_result.parser_version,
                    cleaning_version=parse_result.cleaning_version,
                    chunking_version=CHUNKING_POLICY_VERSION,
                    tokenizer_version=TOKENIZER_VERSION,
                    dedup_policy_version=dedup_policy_version(),
                    normalized_content_hash=normalized,
                ),
            )
        )
    return chunks


def _build_parent_chunks(
    passages: list[CanonicalChunk],
    *,
    parse_result: ParseResult,
    document_id: UUID,
    version_id: UUID,
) -> list[CanonicalChunk]:
    """Assemble parent sections from ordered child passages."""

    if not passages:
        return []
    grouped: dict[tuple[str, ...], list[CanonicalChunk]] = {}
    for passage in passages:
        grouped.setdefault(tuple(passage.section_path), []).append(passage)

    parents: list[CanonicalChunk] = []
    base_index = len(passages)
    for section_path, section_passages in grouped.items():
        combined_parts: list[str] = []
        child_ids: list[str] = []
        locators: list[dict[str, Any]] = []
        element_ids: list[str] = []
        token_total = 0
        page_number = section_passages[0].page_number if section_passages else None
        for passage in section_passages:
            if token_total and token_total + passage.token_count > PARENT_MAX_TOKENS:
                break
            combined_parts.append(passage.raw_text)
            child_ids.append(str(passage.chunk_id))
            locators.extend(passage.provenance.locators)
            element_ids.extend(passage.provenance.element_ids)
            token_total += passage.token_count
        if not combined_parts:
            continue
        raw_text = "\n\n".join(combined_parts)
        normalized = normalized_hash(raw_text)
        parent_id = stable_chunk_id(
            document_id=document_id,
            version_id=version_id,
            element_ids=tuple(element_ids),
            element_path=section_path,
            normalized_content_hash=normalized,
            parser_version=parse_result.parser_version,
            cleaning_version=parse_result.cleaning_version,
            fragment_ordinal=9999,
        )
        parent = CanonicalChunk(
            chunk_id=parent_id,
            chunk_index=base_index + len(parents),
            kind=ChunkKind.PARENT,
            raw_text=raw_text,
            token_count=tokenizer.count_tokens(raw_text),
            section_path=list(section_path),
            page_number=page_number,
            provenance=ChunkProvenance(
                element_ids=tuple(element_ids),
                locators=tuple(locators),
                heading_ancestry=section_path,
                child_chunk_ids=tuple(child_ids),
                parser_version=parse_result.parser_version,
                cleaning_version=parse_result.cleaning_version,
                chunking_version=CHUNKING_POLICY_VERSION,
                tokenizer_version=TOKENIZER_VERSION,
                dedup_policy_version=dedup_policy_version(),
                normalized_content_hash=normalized,
            ),
        )
        for passage in section_passages:
            if str(passage.chunk_id) in child_ids:
                passage.parent_chunk_id = parent_id
        parents.append(parent)
    return parents


def _update_heading_stack(stack: list[str], heading: str) -> list[str]:
    """Replace the current heading level with the new heading text."""

    return [heading]


def _table_row_index(element: TypedElement) -> int:
    """Extract a stable row index from one table cell locator."""

    locator = element.locator
    block_path = getattr(locator, "block_path", None)
    if isinstance(block_path, tuple) and len(block_path) >= 2:
        return int(block_path[-2])
    record_index = getattr(locator, "record_index", None)
    if isinstance(record_index, int):
        return record_index
    return element.reading_order


def _page_from_locators(locators: tuple[dict[str, Any], ...]) -> int | None:
    """Return the first page/slide index found in provenance locators."""

    for locator in locators:
        if "page_index" in locator:
            return int(locator["page_index"]) + 1
        if "slide_index" in locator:
            return int(locator["slide_index"]) + 1
    return None


def collect_chunking_metrics(
    chunks: list[CanonicalChunk],
    *,
    dedup_metrics: Any,
) -> Any:
    """Compute chunk sizing metrics for evidence reporting."""

    from smart_rag_core.ingestion.chunking.limits import (
        PASSAGE_HARD_MAX_TOKENS,
        PASSAGE_TARGET_MAX_TOKENS,
        PASSAGE_TARGET_MIN_TOKENS,
    )
    from smart_rag_core.ingestion.chunking.types import ChunkingMetrics

    ordinary = [
        chunk
        for chunk in chunks
        if chunk.kind.value == "passage" and not chunk.provenance.is_atomic_exception
    ]
    in_target = [
        chunk
        for chunk in ordinary
        if PASSAGE_TARGET_MIN_TOKENS <= chunk.token_count <= PASSAGE_TARGET_MAX_TOKENS
    ]
    hard_violations = [
        chunk
        for chunk in ordinary
        if chunk.token_count > PASSAGE_HARD_MAX_TOKENS and not chunk.provenance.is_atomic_exception
    ]
    return ChunkingMetrics(
        total_chunks=len(chunks),
        passage_chunks=sum(1 for chunk in chunks if chunk.kind.value == "passage"),
        parent_chunks=sum(1 for chunk in chunks if chunk.kind.value == "parent"),
        ordinary_prose_chunks=len(ordinary),
        ordinary_prose_in_target=len(in_target),
        overlap_violations=0,
        hard_cap_violations=len(hard_violations),
        atomic_exceptions=sum(1 for chunk in chunks if chunk.provenance.is_atomic_exception),
        dedup=dedup_metrics,
    )
