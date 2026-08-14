"""Unit tests for typed parser adapters."""

from __future__ import annotations

import hashlib

import pytest
from smart_rag_core.ingestion.parser.adapters import infer_format, parse_file
from smart_rag_core.ingestion.parser.types import ParseDisposition

from tests.fixtures.parser import (
    build_csv_fixture,
    build_docx_fixture,
    build_html_fixture,
    build_markdown_fixture,
    build_pdf_text_fixture,
    build_pptx_fixture,
    build_xlsx_fixture,
)


def build_text_fixture() -> tuple[bytes, str]:
    """Build plain-text fixture bytes and digest."""

    content = "Line one English.\nLine two Arabic مرحبا.\n"
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
    return content.encode("utf-8"), digest


@pytest.mark.parametrize(
    ("builder", "filename", "format_key"),
    [
        (build_text_fixture, "sample.txt", "text"),
        (build_markdown_fixture, "sample.md", "markdown"),
        (build_csv_fixture, "sample.csv", "csv"),
        (build_html_fixture, "sample.html", "html"),
        (build_docx_fixture, "sample.docx", "docx"),
        (build_pptx_fixture, "sample.pptx", "pptx"),
        (build_xlsx_fixture, "sample.xlsx", "xlsx"),
        (build_pdf_text_fixture, "sample.pdf", "pdf"),
    ],
)
def test_adapter_emits_deterministic_elements(
    builder,
    filename: str,
    format_key: str,
    tmp_path,
) -> None:
    """Supported formats emit deterministic typed elements on replay."""

    payload, digest = builder()
    path = tmp_path / filename
    path.write_bytes(payload)
    first = parse_file(path, digest, format_key)
    second = parse_file(path, digest, format_key)
    assert first.disposition is ParseDisposition.SUPPORTED
    assert first.config_hash == second.config_hash
    assert [element.model_dump() for element in first.elements] == [
        element.model_dump() for element in second.elements
    ]
    assert first.coverage.total_elements == len(first.elements)
    assert all(element.reading_order >= 0 for element in first.elements)


def test_ocr_scanned_pdf_has_no_selectable_text(tmp_path) -> None:
    """Image-only scanned PDF has no text layer and takes the OCR path."""

    import fitz

    from tests.fixtures.parser import build_ocr_scanned_pdf

    payload, digest = build_ocr_scanned_pdf()
    rendered = fitz.open(stream=payload, filetype="pdf")
    try:
        assert not rendered[0].get_text("text").strip()
    finally:
        rendered.close()
    path = tmp_path / "scanned.pdf"
    path.write_bytes(payload)
    result = parse_file(path, digest, "pdf")
    assert result.resource_metrics.ocr_pages >= 1
    kinds = {element.kind.value for element in result.elements}
    assert kinds & {"figure", "paragraph", "page_break"}


def test_encrypted_pdf_fails_closed(tmp_path) -> None:
    """Password-protected PDFs fail closed without partial elements."""

    from smart_rag_core.ingestion.parser.exceptions import ParserEncryptedError

    from tests.fixtures.parser import build_encrypted_pdf

    payload, digest = build_encrypted_pdf()
    path = tmp_path / "secret.pdf"
    path.write_bytes(payload)
    with pytest.raises(ParserEncryptedError):
        parse_file(path, digest, "pdf")


def test_pdf_header_footer_removed(tmp_path) -> None:
    """Repeated PDF header/footer lines produce removal diagnostics."""

    payload, digest = build_pdf_text_fixture()
    path = tmp_path / "headers.pdf"
    path.write_bytes(payload)
    result = parse_file(path, digest, "pdf")
    assert any(removal.reason == "repeated_header_footer" for removal in result.removals)


def test_html_boilerplate_removed(tmp_path) -> None:
    """HTML adapter removes nav/cookie boilerplate with diagnostics."""

    payload, digest = build_html_fixture()
    path = tmp_path / "page.html"
    path.write_bytes(payload)
    result = parse_file(path, digest, "html")
    joined = " ".join(element.text or "" for element in result.elements)
    assert "cookie" not in joined.lower()
    assert any(removal.reason == "html_boilerplate" for removal in result.removals)


def test_pptx_emits_slide_and_text(tmp_path) -> None:
    """PPTX adapter emits slide breaks and text with reading-order locators."""

    payload, digest = build_pptx_fixture()
    path = tmp_path / "deck.pptx"
    path.write_bytes(payload)
    result = parse_file(path, digest, "pptx")
    assert any(element.kind.value == "slide_break" for element in result.elements)
    assert any((element.text or "").startswith("Slide caption") for element in result.elements)


def test_xlsx_formula_not_recalculated(tmp_path) -> None:
    """XLSX adapter preserves formula text without recalculation."""

    payload, digest = build_xlsx_fixture()
    path = tmp_path / "book.xlsx"
    path.write_bytes(payload)
    result = parse_file(path, digest, "xlsx")
    formula_cells = [
        element
        for element in result.elements
        if element.metadata.get("formula_text") == "=1+1"
    ]
    assert formula_cells
    assert formula_cells[0].metadata.get("cache_authority") == "unevaluated"


def test_infer_format_from_extension(tmp_path) -> None:
    """Format inference resolves common extensions."""

    path = tmp_path / "doc.pdf"
    path.write_bytes(b"%PDF-1.4\n")
    assert infer_format(path) == "pdf"
