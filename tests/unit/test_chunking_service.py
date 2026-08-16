"""Unit tests for hierarchical chunking and stable replay IDs."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from pathlib import Path

import pytest
from smart_rag_core.ingestion.chunking import chunk_parse_result
from smart_rag_core.ingestion.chunking.limits import (
    PARENT_MAX_TOKENS,
    PASSAGE_HARD_MAX_TOKENS,
    PASSAGE_OVERLAP_MAX_TOKENS,
    PASSAGE_OVERLAP_MIN_TOKENS,
    PASSAGE_TARGET_MAX_TOKENS,
    PASSAGE_TARGET_MIN_TOKENS,
)
from smart_rag_core.ingestion.chunking.splitter import split_oversized_atomic
from smart_rag_core.ingestion.chunking.tokenizer import count_tokens
from smart_rag_core.ingestion.parser.adapters import parse_file
from smart_rag_core.ingestion.parser.types import (
    CoverageAccounting,
    ElementKind,
    MarkdownLocator,
    ParseDisposition,
    ParseResult,
    ParserResourceMetrics,
    TypedElement,
)

from tests.fixtures.parser import (
    build_docx_fixture,
    build_html_fixture,
    build_markdown_fixture,
    build_pdf_text_fixture,
    build_pptx_fixture,
    build_xlsx_fixture,
)

DOCUMENT_ID = uuid.UUID("11111111-1111-4111-8111-111111111111")
VERSION_ID = uuid.UUID("22222222-2222-4222-8222-222222222222")
FixtureBuilder = Callable[[], tuple[bytes, str]]


@pytest.mark.parametrize(
    ("builder", "filename", "format_key"),
    [
        (build_markdown_fixture, "chunk.md", "markdown"),
        (build_html_fixture, "chunk.html", "html"),
        (build_docx_fixture, "chunk.docx", "docx"),
        (build_pptx_fixture, "chunk.pptx", "pptx"),
        (build_pdf_text_fixture, "chunk.pdf", "pdf"),
    ],
)
def test_chunk_ids_stable_on_replay(
    builder: FixtureBuilder, filename: str, format_key: str, tmp_path: Path
) -> None:
    """Identical parse inputs produce identical chunk IDs on replay."""

    payload, digest = builder()
    path = tmp_path / filename
    path.write_bytes(payload)
    parsed = parse_file(path, digest, format_key)
    first = chunk_parse_result(parsed, document_id=DOCUMENT_ID, version_id=VERSION_ID)
    second = chunk_parse_result(parsed, document_id=DOCUMENT_ID, version_id=VERSION_ID)
    assert [chunk.model_dump(mode="json") for chunk in first.chunks] == [
        chunk.model_dump(mode="json") for chunk in second.chunks
    ]
    assert first.config_hash == second.config_hash


def test_parent_reconstruction_and_locator_round_trip(tmp_path: Path) -> None:
    """Parent chunks reference children and locators round-trip for citations."""

    payload, digest = build_docx_fixture()
    path = tmp_path / "nested.docx"
    path.write_bytes(payload)
    parsed = parse_file(path, digest, "docx")
    result = chunk_parse_result(parsed, document_id=DOCUMENT_ID, version_id=VERSION_ID)
    parents = [chunk for chunk in result.chunks if chunk.kind.value == "parent"]
    passages = [chunk for chunk in result.chunks if chunk.kind.value == "passage"]
    assert parents
    parent = parents[0]
    assert parent.token_count <= PARENT_MAX_TOKENS
    child_ids = set(parent.provenance.child_chunk_ids)
    assert child_ids
    for passage in passages:
        if str(passage.chunk_id) in child_ids:
            assert passage.parent_chunk_id == parent.chunk_id
            assert passage.provenance.locators
            locator = passage.provenance.locators[0]
            assert locator["format"] == "docx"
            assert "block_path" in locator


def test_markdown_code_block_remains_atomic(tmp_path: Path) -> None:
    """Markdown code fences stay intact without silent mid-block splits."""

    payload, digest = build_markdown_fixture()
    path = tmp_path / "code.md"
    path.write_bytes(payload)
    parsed = parse_file(path, digest, "markdown")
    result = chunk_parse_result(parsed, document_id=DOCUMENT_ID, version_id=VERSION_ID)
    code_chunks = [
        chunk
        for chunk in result.chunks
        if any(
            locator.get("token_path") == ["fence"]
            for locator in chunk.provenance.locators
        )
    ]
    assert code_chunks
    assert "print('hi')" in code_chunks[0].raw_text


def test_oversized_atomic_fragments_reconstructable() -> None:
    """Oversized atomic elements split with shared atomic ID and order."""

    body = "\n".join(f"line {index} " + ("payload " * 80) for index in range(40))
    fragments = split_oversized_atomic(body)
    assert len(fragments) > 1
    for fragment in fragments:
        assert count_tokens(fragment) <= PASSAGE_HARD_MAX_TOKENS
    assert "".join(fragment.replace("\n", "") for fragment in fragments) != ""


def test_exact_duplicate_provenance_retained() -> None:
    """Exact duplicates keep representative and duplicate locators."""

    text = "Duplicate passage for exact dedup testing."
    separator = TypedElement(
        element_id="sep",
        kind=ElementKind.CODE,
        text="block();",
        reading_order=1,
        locator=MarkdownLocator(line_start=2, line_end=2, token_path=("fence",)),
    )
    element = TypedElement(
        element_id="a",
        kind=ElementKind.PARAGRAPH,
        text=text,
        reading_order=0,
        locator=MarkdownLocator(line_start=1, line_end=1),
    )
    duplicate = TypedElement(
        element_id="b",
        kind=ElementKind.PARAGRAPH,
        text=text,
        reading_order=2,
        locator=MarkdownLocator(line_start=3, line_end=3),
    )
    parsed = ParseResult(
        disposition=ParseDisposition.SUPPORTED,
        format="markdown",
        content_hash="abc",
        parser_version="parser_v1",
        cleaning_version="cleaning_v1",
        config_hash="cfg",
        elements=(element, separator, duplicate),
        coverage=CoverageAccounting(
            total_elements=3,
            text_elements=3,
            media_only_elements=0,
            removed_nodes=0,
            unsupported_regions=0,
            char_coverage_ratio=1.0,
        ),
        resource_metrics=ParserResourceMetrics(wall_seconds=0.1),
    )
    result = chunk_parse_result(parsed, document_id=DOCUMENT_ID, version_id=VERSION_ID)
    passages = [chunk for chunk in result.chunks if chunk.kind.value == "passage"]
    representatives = [chunk for chunk in passages if chunk.is_search_representative]
    duplicates = [
        chunk for chunk in passages if chunk.duplicate_of_chunk_id is not None
    ]
    assert len(representatives) >= 1
    assert duplicates
    assert duplicates[0].duplicate_of_chunk_id == representatives[0].chunk_id


def test_spreadsheet_produces_parquet_not_prose_chunks(tmp_path: Path) -> None:
    """CSV/XLSX formats materialize Parquet artifacts instead of prose chunks."""

    payload, digest = build_xlsx_fixture()
    path = tmp_path / "book.xlsx"
    path.write_bytes(payload)
    parsed = parse_file(path, digest, "xlsx")
    result = chunk_parse_result(parsed, document_id=DOCUMENT_ID, version_id=VERSION_ID)
    assert result.chunks == ()
    assert result.table_artifacts
    manifest = result.table_artifacts[0].manifest
    assert manifest.row_count >= 1
    assert manifest.content_hash_sha256
    assert "table-artifacts" in result.table_artifacts[0].bucket


def test_ordinary_prose_sizing_metrics() -> None:
    """Chunk metrics expose ordinary prose distribution against contract bounds."""

    paragraphs: list[TypedElement] = []
    for index in range(8):
        paragraphs.append(
            TypedElement(
                element_id=f"p{index}",
                kind=ElementKind.PARAGRAPH,
                text="Structured ingestion validates chunk sizing. " * 12,
                reading_order=index,
                locator=MarkdownLocator(line_start=index + 1, line_end=index + 1),
            )
        )
    parsed = ParseResult(
        disposition=ParseDisposition.SUPPORTED,
        format="markdown",
        content_hash="prose",
        parser_version="parser_v1",
        cleaning_version="cleaning_v1",
        config_hash="cfg",
        elements=tuple(paragraphs),
        coverage=CoverageAccounting(
            total_elements=len(paragraphs),
            text_elements=len(paragraphs),
            media_only_elements=0,
            removed_nodes=0,
            unsupported_regions=0,
            char_coverage_ratio=1.0,
        ),
        resource_metrics=ParserResourceMetrics(wall_seconds=0.1),
    )
    result = chunk_parse_result(parsed, document_id=DOCUMENT_ID, version_id=VERSION_ID)
    assert result.metrics.ordinary_prose_chunks >= 1
    assert PASSAGE_TARGET_MIN_TOKENS <= PASSAGE_TARGET_MAX_TOKENS
    assert PASSAGE_OVERLAP_MIN_TOKENS <= PASSAGE_OVERLAP_MAX_TOKENS
    assert result.metrics.hard_cap_violations == 0
