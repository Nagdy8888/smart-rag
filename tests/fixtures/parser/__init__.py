"""Shared parser test fixtures."""

from __future__ import annotations

import csv
import hashlib
import io
import zipfile
from pathlib import Path

import fitz
from docx import Document
from openpyxl import Workbook
from pptx import Presentation
from pptx.util import Inches

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "parser"


def sha256_bytes(payload: bytes) -> str:
    """Return SHA-256 hex digest."""

    return hashlib.sha256(payload).hexdigest()


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

    document = fitz.open()
    for page_number in range(2):
        page = document.new_page()
        page.insert_text((72, 50), "HEADER")
        page.insert_text((72, 72), f"Body page {page_number + 1}")
        page.insert_text((72, 750), "FOOTER")
    payload = document.tobytes()
    document.close()
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

    source = fitz.open()
    source_page = source.new_page()
    source_page.insert_text((72, 120), "Scanned OCR fixture line", fontsize=28)
    pixmap = source_page.get_pixmap(dpi=150)
    source.close()

    document = fitz.open()
    page = document.new_page()
    page.insert_image(page.rect, pixmap=pixmap)
    payload = document.tobytes()
    document.close()
    return payload, sha256_bytes(payload)


def build_encrypted_pdf() -> tuple[bytes, str]:
    """Build a password-protected PDF that parsers must reject."""

    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), "secret body")
    payload = document.tobytes(
        encryption=fitz.PDF_ENCRYPT_AES_256,
        user_pw="secret",
        owner_pw="owner",
    )
    document.close()
    return payload, sha256_bytes(payload)
