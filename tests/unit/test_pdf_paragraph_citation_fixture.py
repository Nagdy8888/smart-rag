"""AI Agents PDF fixture: toolbar page 25 is not printed label 12."""

from __future__ import annotations

from pathlib import Path
from uuid import UUID

from smart_rag_core.ingestion.chunking import chunk_parse_result
from smart_rag_core.ingestion.chunking.types import ChunkKind
from smart_rag_core.ingestion.parser.adapters import parse_file

from tests.fixtures.parser import (
    AI_AGENTS_CHIP_LABEL,
    AI_AGENTS_DUPLICATE_SPAN,
    AI_AGENTS_PAGE_COUNT,
    AI_AGENTS_PAGE_INDEX,
    AI_AGENTS_PAGE_LABEL,
    AI_AGENTS_TITLE,
    AI_AGENTS_UNIQUE_SPAN,
    AI_AGENTS_VIEWER_PAGE,
    build_ai_agents_paragraph_citation_fixture,
)

DOCUMENT_ID = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
VERSION_ID = UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")


def test_ai_agents_fixture_keeps_viewer_page_off_printed_label(tmp_path: Path) -> None:
    """Page index 24 prints as 12 and the unique span lives on viewer page 25."""

    payload, digest = build_ai_agents_paragraph_citation_fixture()
    path = tmp_path / "ai-agents.pdf"
    path.write_bytes(payload)
    parsed = parse_file(path, digest, "pdf")
    assert parsed.page_labels[AI_AGENTS_PAGE_INDEX] == AI_AGENTS_PAGE_LABEL
    assert len(parsed.page_labels) == AI_AGENTS_PAGE_COUNT
    unique_pages = tuple(
        element.locator.model_dump().get("page_index")
        for element in parsed.elements
        if element.text and AI_AGENTS_UNIQUE_SPAN in element.text
    )
    duplicate_pages = tuple(
        element.locator.model_dump().get("page_index")
        for element in parsed.elements
        if element.text and AI_AGENTS_DUPLICATE_SPAN in element.text
    )
    assert unique_pages == (AI_AGENTS_PAGE_INDEX,)
    assert 22 in duplicate_pages and 23 in duplicate_pages
    assert any(
        element.text and "Chapter Refunds" in element.text
        for element in parsed.elements
    )
    chunking = chunk_parse_result(
        parsed,
        document_id=DOCUMENT_ID,
        version_id=VERSION_ID,
    )
    unique_passages = [
        chunk
        for chunk in chunking.chunks
        if chunk.kind is ChunkKind.PASSAGE and AI_AGENTS_UNIQUE_SPAN in chunk.raw_text
    ]
    assert unique_passages
    assert all(chunk.page_number == AI_AGENTS_VIEWER_PAGE for chunk in unique_passages)
    unique_locators = [
        locator
        for chunk in unique_passages
        for locator in chunk.provenance.locators
        if locator.get("format") == "pdf"
    ]
    assert unique_locators
    assert all(
        int(locator["page_index"]) + 1 == AI_AGENTS_VIEWER_PAGE
        for locator in unique_locators
    )
    assert all(
        locator.get("page_label") == AI_AGENTS_PAGE_LABEL for locator in unique_locators
    )
    assert any(
        chunk.kind is ChunkKind.PARENT and AI_AGENTS_UNIQUE_SPAN in chunk.raw_text
        for chunk in chunking.chunks
    )
    duplicate_pages = {
        chunk.page_number
        for chunk in chunking.chunks
        if chunk.kind is ChunkKind.PASSAGE
        and AI_AGENTS_DUPLICATE_SPAN in chunk.raw_text
    }
    assert 23 in duplicate_pages and 24 in duplicate_pages
    assert (
        AI_AGENTS_CHIP_LABEL == f"{AI_AGENTS_TITLE} · PDF page {AI_AGENTS_VIEWER_PAGE}"
    )
    assert "p. 12" not in AI_AGENTS_CHIP_LABEL
    assert "PDF page 12" not in AI_AGENTS_CHIP_LABEL
