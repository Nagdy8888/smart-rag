"""Conservative PDF heading classification and structure-aware chunking."""

from __future__ import annotations

from pathlib import Path
from uuid import UUID

from smart_rag_core.ingestion.chunking import chunk_parse_result
from smart_rag_core.ingestion.parser.adapters import parse_file
from smart_rag_core.ingestion.parser.helpers import classify_pdf_text_block
from smart_rag_core.ingestion.parser.limits import PDF_PARSER_VERSION
from smart_rag_core.ingestion.parser.types import ElementKind

from tests.fixtures.parser import build_encrypted_pdf, build_pdf_heading_fixture

DOCUMENT_ID = UUID("11111111-1111-4111-8111-111111111111")
VERSION_ID = UUID("22222222-2222-4222-8222-222222222222")


def test_short_large_or_bold_titles_are_headings() -> None:
    """Short large or bold titles classify as headings."""

    assert (
        classify_pdf_text_block(
            text="Chapter One Title",
            max_size=18.0,
            median_size=11.0,
            bold=True,
        )
        is ElementKind.HEADING
    )


def test_bold_body_sentences_stay_paragraphs() -> None:
    """Bold sentence-like body copy is not promoted to a heading."""

    assert (
        classify_pdf_text_block(
            text="This bold sentence stays a paragraph because it is long enough to look like body copy.",
            max_size=11.0,
            median_size=11.0,
            bold=True,
        )
        is ElementKind.PARAGRAPH
    )


def test_mixed_script_short_title_is_heading() -> None:
    """Short mixed-script titles still classify as headings."""

    assert (
        classify_pdf_text_block(
            text="Mixed heading path مقدمة",
            max_size=16.0,
            median_size=11.0,
            bold=True,
        )
        is ElementKind.HEADING
    )


def test_heading_fixture_populates_section_path(tmp_path: Path) -> None:
    """Large titles become headings, repeated headers are removed, chunking keeps ancestry."""

    payload, digest = build_pdf_heading_fixture()
    path = tmp_path / "headings.pdf"
    path.write_bytes(payload)
    parsed = parse_file(path, digest, "pdf")
    assert parsed.parser_version == PDF_PARSER_VERSION
    first_ids = [element.element_id for element in parsed.elements]
    replay = parse_file(path, digest, "pdf")
    assert [element.element_id for element in replay.elements] == first_ids
    headings = [
        element.text
        for element in parsed.elements
        if element.kind is ElementKind.HEADING and element.text
    ]
    paragraphs = [
        element.text
        for element in parsed.elements
        if element.kind is ElementKind.PARAGRAPH and element.text
    ]
    assert any(text == "Chapter One Title" for text in headings)
    assert all("HEADER" not in (text or "") for text in headings)
    assert all("HEADER" not in (text or "") for text in paragraphs)
    assert any(
        text is not None and "bold sentence stays a paragraph" in text
        for text in paragraphs
    )
    chunking = chunk_parse_result(
        parsed,
        document_id=DOCUMENT_ID,
        version_id=VERSION_ID,
    )
    assert any("Chapter One Title" in chunk.section_path for chunk in chunking.chunks)


def test_encrypted_pdf_still_fails_closed(tmp_path: Path) -> None:
    """Heading extraction does not weaken encrypted-PDF rejection."""

    from smart_rag_core.ingestion.parser.exceptions import ParserEncryptedError

    payload, digest = build_encrypted_pdf()
    path = tmp_path / "secret.pdf"
    path.write_bytes(payload)
    try:
        parse_file(path, digest, "pdf")
    except ParserEncryptedError:
        return
    raise AssertionError("encrypted PDF must fail closed")
