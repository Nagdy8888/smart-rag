"""Shared parser test fixtures."""

from __future__ import annotations

import csv
import hashlib
import io
import zipfile
from collections.abc import Callable
from pathlib import Path
from typing import cast

import fitz
from docx import Document
from openpyxl import Workbook
from pptx import Presentation
from pptx.util import Inches

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "parser"


def sha256_bytes(payload: bytes) -> str:
    """Return SHA-256 hex digest."""

    return hashlib.sha256(payload).hexdigest()


def _call_vendor(
    obj: object,
    method: str,
    *args: object,
    **kwargs: object,
) -> object:
    """Call a named method on an untyped third-party object.

    Args:
        obj: Vendor instance such as a PyMuPDF document or page.
        method: Method attribute name.
        *args: Positional arguments forwarded to the method.
        **kwargs: Keyword arguments forwarded to the method.

    Returns:
        The vendor method's return value.

    Raises:
        AttributeError: If ``obj`` has no attribute named ``method``.
    """

    caller = cast("Callable[..., object]", getattr(obj, method))
    return caller(*args, **kwargs)


def _vendor_attr(obj: object, name: str) -> object:
    """Return a named attribute from an untyped third-party object.

    Args:
        obj: Vendor instance or module.
        name: Attribute name.

    Returns:
        Attribute value boxed as ``object``.
    """

    return cast(object, getattr(obj, name))


def _open_pdf(*, stream: bytes | None = None) -> object:
    """Open a PyMuPDF document for fixture construction.

    Args:
        stream: Optional PDF bytes. ``None`` opens an empty document.

    Returns:
        Vendor document boxed as ``object``.
    """

    if stream is None:
        return cast(object, fitz.open())
    return cast(object, fitz.open(stream=stream, filetype="pdf"))


def pdf_selectable_text(payload: bytes, page_index: int = 0) -> str:
    """Return selectable text-layer content for one PDF page.

    Args:
        payload: PDF bytes.
        page_index: Zero-based page index.

    Returns:
        Text extracted from the PDF text layer. Empty for image-only pages.
    """

    document = _open_pdf(stream=payload)
    try:
        page = _call_vendor(document, "__getitem__", page_index)
        return cast(str, _call_vendor(page, "get_text", "text"))
    finally:
        _call_vendor(document, "close")


def write_text_fixture(name: str, content: str) -> tuple[Path, str]:
    """Write a UTF-8 text fixture and return path/hash."""

    path = FIXTURES_DIR / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path, sha256_bytes(path.read_bytes())


def build_markdown_fixture() -> tuple[bytes, str]:
    """Build deterministic Markdown bytes."""

    content = "# Title\n\nParagraph one.\n\n```python\nprint('hi')\n```\n"
    return content.encode("utf-8"), sha256_bytes(content.encode("utf-8"))


def build_csv_fixture() -> tuple[bytes, str]:
    """Build CSV with duplicate headers and mixed content."""

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["name", "name", "amount"])
    writer.writerow(["Widget", "Widget", "10"])
    writer.writerow(["مرحبا", "Hello", "20"])
    payload = buffer.getvalue().encode("utf-8")
    return payload, sha256_bytes(payload)


def build_html_fixture() -> tuple[bytes, str]:
    """Build HTML with boilerplate and main content."""

    content = """
    <html><body>
    <nav>Skip to content</nav>
    <div class="cookie-banner">Accept cookies</div>
    <main><h1>Article</h1><p>Body text.</p><a href="/x">Link</a></main>
    </body></html>
    """
    payload = content.encode("utf-8")
    return payload, sha256_bytes(payload)


def build_docx_fixture() -> tuple[bytes, str]:
    """Build DOCX with heading and nested table."""

    document = Document()
    document.add_heading("Heading", level=1)
    document.add_paragraph("Paragraph English.")
    document.add_paragraph("فقرة عربية.")
    table = document.add_table(rows=1, cols=2)
    table.rows[0].cells[0].text = "A1"
    table.rows[0].cells[1].text = "B1"
    buffer = io.BytesIO()
    document.save(buffer)
    payload = buffer.getvalue()
    return payload, sha256_bytes(payload)


def build_pptx_fixture() -> tuple[bytes, str]:
    """Build PPTX with text shape and media-only placeholder."""

    presentation = Presentation()
    slide = presentation.slides.add_slide(presentation.slide_layouts[5])
    textbox = slide.shapes.add_textbox(Inches(1), Inches(1), Inches(4), Inches(1))
    textbox.text = "Slide caption text"
    picture = slide.shapes.add_textbox(Inches(1), Inches(2), Inches(2), Inches(2))
    picture.text = ""
    buffer = io.BytesIO()
    presentation.save(buffer)
    payload = buffer.getvalue()
    return payload, sha256_bytes(payload)


def build_xlsx_fixture() -> tuple[bytes, str]:
    """Build XLSX with formula, cached value, hidden sheet."""

    workbook = Workbook()
    sheet = workbook.active
    assert sheet is not None
    sheet.title = "Visible"
    sheet["A1"] = "=1+1"
    sheet["A2"] = 42
    hidden = workbook.create_sheet("Hidden")
    hidden.sheet_state = "hidden"
    hidden["A1"] = "secret"
    buffer = io.BytesIO()
    workbook.save(buffer)
    payload = buffer.getvalue()
    return payload, sha256_bytes(payload)


def build_pdf_text_fixture() -> tuple[bytes, str]:
    """Build simple text PDF with repeated header/footer."""

    document = _open_pdf()
    for page_number in range(2):
        page = _call_vendor(document, "new_page")
        _call_vendor(page, "insert_text", (72, 50), "HEADER")
        _call_vendor(page, "insert_text", (72, 72), f"Body page {page_number + 1}")
        _call_vendor(page, "insert_text", (72, 750), "FOOTER")
    payload = cast(bytes, _call_vendor(document, "tobytes"))
    _call_vendor(document, "close")
    return payload, sha256_bytes(payload)


def build_pdf_hyphen_fixture() -> tuple[bytes, str]:
    """Build a one-page PDF whose body is split on a trailing hyphen.

    Returns:
        PDF bytes and SHA-256 digest.
    """

    document = _open_pdf()
    page = _call_vendor(document, "new_page")
    _call_vendor(
        page, "insert_text", (72, 120), "The parser rejoins hyphen-", fontsize=11
    )
    _call_vendor(
        page,
        "insert_text",
        (72, 136),
        "ated words in body copy.",
        fontsize=11,
    )
    payload = cast(bytes, _call_vendor(document, "tobytes"))
    _call_vendor(document, "close")
    return payload, sha256_bytes(payload)


def build_pdf_layout_fixture() -> tuple[bytes, str]:
    """Build a one-page PDF with a captioned table, a code listing, and prose.

    Returns:
        PDF bytes and SHA-256 digest.
    """

    document = _open_pdf()
    page = _call_vendor(document, "new_page")
    _call_vendor(page, "insert_text", (72, 50), "Table 2-1. Sample costs", fontsize=10)
    rows = (
        (80, ("Name", "Kind", "Cost")),
        (93, ("alpha", "tool", "low")),
        (106, ("beta", "agent", "high")),
    )
    for y, cells in rows:
        for x, text in zip((75.6, 150.0, 250.0), cells, strict=True):
            _call_vendor(page, "insert_text", (x, y), text, fontsize=9)
    _call_vendor(
        page, "insert_text", (72, 140), "def f(x):", fontsize=8.5, fontname="cour"
    )
    _call_vendor(
        page, "insert_text", (92, 151), "return x", fontsize=8.5, fontname="cour"
    )
    _call_vendor(
        page,
        "insert_text",
        (72, 180),
        "Body text after the table and the code.",
        fontsize=10.5,
        fontname="tiro",
    )
    payload = cast(bytes, _call_vendor(document, "tobytes"))
    _call_vendor(document, "close")
    return payload, sha256_bytes(payload)


def build_pdf_page_label_fixture() -> tuple[bytes, str]:
    """Build a one-page PDF whose printed label is 50, not file page 1.

    Returns:
        PDF bytes and SHA-256 digest.
    """

    document = _open_pdf()
    page = _call_vendor(document, "new_page")
    _call_vendor(page, "insert_text", (72, 120), "Printed label body")
    _call_vendor(
        document,
        "set_page_labels",
        [{"startpage": 0, "prefix": "", "style": "D", "firstpagenum": 50}],
    )
    payload = cast(bytes, _call_vendor(document, "tobytes"))
    _call_vendor(document, "close")
    return payload, sha256_bytes(payload)


def build_pdf_heading_fixture() -> tuple[bytes, str]:
    """Build a two-page PDF with a large heading, bold body, and repeated header.

    Returns:
        PDF bytes and SHA-256 digest.
    """

    document = _open_pdf()
    for page_number in range(2):
        page = _call_vendor(document, "new_page")
        _call_vendor(page, "insert_text", (72, 50), "HEADER")
        heading = "Chapter One Title" if page_number == 0 else "Chapter Two Title"
        _call_vendor(
            page,
            "insert_text",
            (72, 96),
            heading,
            fontsize=18,
            fontname="hebo",
        )
        _call_vendor(
            page,
            "insert_text",
            (72, 160),
            (
                "This bold sentence stays a paragraph because it is long enough "
                f"to look like body copy on page {page_number + 1}."
            ),
            fontsize=11,
            fontname="hebo",
        )
        _call_vendor(
            page,
            "insert_text",
            (72, 220),
            f"Regular body paragraph about policies and leave on page {page_number + 1}.",
            fontsize=11,
            fontname="helv",
        )
        mixed = "Mixed heading path" if page_number == 0 else "Second mixed heading"
        _call_vendor(
            page,
            "insert_text",
            (72, 280),
            mixed,
            fontsize=16,
            fontname="hebo",
        )
        _call_vendor(page, "insert_text", (72, 750), "FOOTER")
    payload = cast(bytes, _call_vendor(document, "tobytes"))
    _call_vendor(document, "close")
    return payload, sha256_bytes(payload)


def build_encrypted_zip_bomb_attempt() -> bytes:
    """Return a small zip with high declared ratio (not extracted by parser)."""

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("bomb.txt", b"0" * 1000)
    return buffer.getvalue()


def build_archive_bomb() -> tuple[bytes, str]:
    """Build a ZIP whose uncompressed size/ratio trips parser expansion limits.

    Compressed payload stays well under ``PARSER_SANDBOX_MAX_INPUT_BYTES``;
    declared uncompressed size exceeds the 250x expansion ratio.
    """

    buffer = io.BytesIO()
    zeros = b"\x00" * (2 * 1024 * 1024)
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("bomb.bin", zeros)
    payload = buffer.getvalue()
    return payload, sha256_bytes(payload)


def build_ocr_scanned_pdf() -> tuple[bytes, str]:
    """Build an image-only scanned PDF with no selectable text layer."""

    source = _open_pdf()
    source_page = _call_vendor(source, "new_page")
    _call_vendor(
        source_page,
        "insert_text",
        (72, 120),
        "Scanned OCR fixture line",
        fontsize=28,
    )
    pixmap = _call_vendor(source_page, "get_pixmap", dpi=150)
    _call_vendor(source, "close")

    document = _open_pdf()
    page = _call_vendor(document, "new_page")
    _call_vendor(page, "insert_image", _vendor_attr(page, "rect"), pixmap=pixmap)
    payload = cast(bytes, _call_vendor(document, "tobytes"))
    _call_vendor(document, "close")
    return payload, sha256_bytes(payload)


def build_encrypted_pdf() -> tuple[bytes, str]:
    """Build a password-protected PDF that parsers must reject."""

    document = _open_pdf()
    page = _call_vendor(document, "new_page")
    _call_vendor(page, "insert_text", (72, 72), "secret body")
    payload = cast(
        bytes,
        _call_vendor(
            document,
            "tobytes",
            encryption=cast(int, _vendor_attr(fitz, "PDF_ENCRYPT_AES_256")),
            user_pw="secret",
            owner_pw="owner",
        ),
    )
    _call_vendor(document, "close")
    return payload, sha256_bytes(payload)


AI_AGENTS_TITLE = "AI Agents"
AI_AGENTS_UNIQUE_SPAN = "Refunds close in thirty calendar days."
AI_AGENTS_DUPLICATE_SPAN = "Shared child span used for ambiguity."
AI_AGENTS_PAGE_INDEX = 24
AI_AGENTS_VIEWER_PAGE = 25
AI_AGENTS_PAGE_LABEL = "12"
AI_AGENTS_CHIP_LABEL = "AI Agents · PDF page 25"
AI_AGENTS_PAGE_COUNT = 26


def build_ai_agents_paragraph_citation_fixture() -> tuple[bytes, str]:
    """Build a 26-page PDF whose toolbar page 25 prints as label 12.

    Page index 24 carries the unique refund span. Pages 22 and 23 carry the
    same child span so leaf resolution can fail on duplicates. A parent
    heading on page 22 starts a multi-page section.

    Returns:
        PDF bytes and SHA-256 digest. Title metadata is ``AI Agents``.
    """

    document = _open_pdf()
    _call_vendor(document, "set_metadata", {"title": AI_AGENTS_TITLE})
    for page_index in range(AI_AGENTS_PAGE_COUNT):
        page = _call_vendor(document, "new_page")
        _call_vendor(page, "insert_text", (72, 72), f"Filler page {page_index + 1}.")
        if page_index == 22:
            _call_vendor(
                page,
                "insert_text",
                (72, 120),
                "Chapter Refunds",
                fontsize=18,
                fontname="hebo",
            )
            _call_vendor(page, "insert_text", (72, 160), AI_AGENTS_DUPLICATE_SPAN)
        if page_index == 23:
            _call_vendor(page, "insert_text", (72, 160), AI_AGENTS_DUPLICATE_SPAN)
        if page_index == 24:
            _call_vendor(page, "insert_text", (72, 160), AI_AGENTS_UNIQUE_SPAN)
    _call_vendor(
        document,
        "set_page_labels",
        [
            {"startpage": 0, "prefix": "", "style": "D", "firstpagenum": 1},
            {
                "startpage": AI_AGENTS_PAGE_INDEX,
                "prefix": "",
                "style": "D",
                "firstpagenum": 12,
            },
        ],
    )
    payload = cast(bytes, _call_vendor(document, "tobytes"))
    _call_vendor(document, "close")
    return payload, sha256_bytes(payload)
