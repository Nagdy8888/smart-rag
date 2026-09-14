"""Local AnyDoc conversion helpers with no Firecrawl network fallback.

Optional pypdf and PyMuPDF stubs are incomplete; unknown-member diagnostics
are suppressed in this module only.
"""

# pyright: reportMissingImports=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
# pyright: reportUnknownArgumentType=false
# pyright: reportAttributeAccessIssue=false

from __future__ import annotations

import os
import tempfile
from collections.abc import Callable
from pathlib import Path

from smart_rag_core.evaluation.parser_bakeoff.constants import (
    ANYDOC_CLEANING_VERSION,
    ANYDOC_OCR_MODE,
    ANYDOC_PACKAGE_VERSION,
    ANYDOC_PARSER_VERSION,
    ANYDOC_SCANNED_PAGES,
)
from smart_rag_core.evaluation.parser_bakeoff.models import BakeoffError
from smart_rag_core.ingestion.parser.adapters.markdown_adapter import parse_markdown
from smart_rag_core.ingestion.parser.types import (
    CoverageAccounting,
    ParseDisposition,
    ParseResult,
    ParserResourceMetrics,
)

MarkdownConverter = Callable[[Path], str]


def anydoc_config_extra() -> dict[str, object]:
    """Return config-hash extras for the local AnyDoc lane.

    Returns:
        Stable extra mapping.
    """

    return {
        "anydoc_version": ANYDOC_PACKAGE_VERSION,
        "ocr": ANYDOC_OCR_MODE,
        "output": "markdown",
        "scanned_pages": ANYDOC_SCANNED_PAGES,
    }


def failed_lane_result(
    *,
    content_hash: str,
    parser_version: str,
    cleaning_version: str,
    format_key: str,
    code: str,
    extra: dict[str, object] | None = None,
) -> ParseResult:
    """Return a fail-closed parse with zero elements.

    Args:
        content_hash: Source SHA-256.
        parser_version: Lane parser pin.
        cleaning_version: Lane cleaning pin.
        format_key: Reported format token.
        code: Sanitized failure code written to ``detail``.
        extra: Optional config-hash extras.

    Returns:
        Failed ``ParseResult``.
    """

    return ParseResult(
        disposition=ParseDisposition.FAILED,
        format=format_key,
        content_hash=content_hash,
        parser_version=parser_version,
        cleaning_version=cleaning_version,
        config_hash=ParseResult.stable_config_hash(
            parser_version, cleaning_version, extra=extra
        ),
        coverage=CoverageAccounting(
            total_elements=0,
            text_elements=0,
            media_only_elements=0,
            removed_nodes=0,
            unsupported_regions=0,
            char_coverage_ratio=0.0,
        ),
        resource_metrics=ParserResourceMetrics(wall_seconds=0.0),
        detail=code,
    )


def stamp_anydoc_parse(
    result: ParseResult, content_hash: str, *, ocr_pages: int = 0
) -> ParseResult:
    """Rewrite Markdown-adapter identity onto AnyDoc pins.

    Args:
        result: Markdown adapter output.
        content_hash: Original PDF SHA-256.
        ocr_pages: Host OpenAI Vision pages merged into this result.

    Returns:
        Parse result with AnyDoc versions, original hash, and Markdown locators.
    """

    extra = anydoc_config_extra()
    return result.model_copy(
        update={
            "format": "pdf",
            "content_hash": content_hash,
            "parser_version": ANYDOC_PARSER_VERSION,
            "cleaning_version": ANYDOC_CLEANING_VERSION,
            "config_hash": ParseResult.stable_config_hash(
                ANYDOC_PARSER_VERSION, ANYDOC_CLEANING_VERSION, extra=extra
            ),
            "resource_metrics": result.resource_metrics.model_copy(
                update={"pages_processed": 0, "ocr_pages": ocr_pages}
            ),
        }
    )


def _write_pdf_without_pages(source: Path, omit: tuple[int, ...], dest: Path) -> int:
    """Copy a PDF excluding 1-indexed scanned pages. Never extracts text.

    Args:
        source: Original PDF.
        omit: 1-indexed pages AnyDoc named as needing OCR.
        dest: Destination path.

    Returns:
        Number of pages kept.

    Raises:
        BakeoffError: When every page was omitted or no writer is available.
    """

    omitted = {int(page) for page in omit if int(page) > 0}
    if not omitted:
        raise BakeoffError("needs_ocr", "NeedsOcrError listed no pages")
    try:
        from pypdf import PdfReader, PdfWriter
    except ImportError:
        return _write_pdf_without_pages_fitz(source, omitted, dest)
    reader = PdfReader(str(source))
    writer = PdfWriter()
    kept = 0
    for index, page in enumerate(reader.pages, start=1):
        if index in omitted:
            continue
        writer.add_page(page)
        kept += 1
    if kept == 0:
        raise BakeoffError("needs_ocr", "all pages need OCR")
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("wb") as handle:
        writer.write(handle)
    return kept


def _write_pdf_without_pages_fitz(source: Path, omitted: set[int], dest: Path) -> int:
    """Omit scanned pages with PyMuPDF when pypdf is not installed.

    Args:
        source: Original PDF.
        omitted: 1-indexed pages to drop.
        dest: Destination path.

    Returns:
        Number of pages kept.

    Raises:
        BakeoffError: When PyMuPDF is missing or every page was omitted.
    """

    try:
        import fitz
    except ImportError as exc:
        raise BakeoffError(
            "anydoc_missing", "pypdf or PyMuPDF is required to omit scanned pages"
        ) from exc
    source_doc = fitz.open(source)
    kept_doc = fitz.open()
    try:
        kept = 0
        for index in range(int(source_doc.page_count)):
            if (index + 1) in omitted:
                continue
            kept_doc.insert_pdf(source_doc, from_page=index, to_page=index)
            kept += 1
        if kept == 0:
            raise BakeoffError("needs_ocr", "all pages need OCR")
        dest.parent.mkdir(parents=True, exist_ok=True)
        kept_doc.save(dest, garbage=4, deflate=True)
        return kept
    finally:
        kept_doc.close()
        source_doc.close()


def probe_anydoc_ocr_pages(path: Path) -> tuple[int, ...]:
    """Return 1-indexed pages AnyDoc names as needing OCR. No omit, no Firecrawl.

    Args:
        path: Readable PDF path.

    Returns:
        Named pages, or empty when AnyDoc converts the file.

    Raises:
        BakeoffError: When AnyDoc is missing or hosted OCR is requested.
    """

    try:
        import anydoc
    except ImportError as exc:
        raise BakeoffError(
            "anydoc_missing", "firecrawl-anydoc is not installed"
        ) from exc
    if ANYDOC_OCR_MODE != "reject":
        raise BakeoffError("hosted_forbidden", "hosted AnyDoc OCR is forbidden")
    try:
        anydoc.to_markdown(str(path), ocr="reject")
    except anydoc.NeedsOcrError as exc:
        pages = tuple(int(page) for page in (getattr(exc, "pages", ()) or ()))
        if not pages:
            raise BakeoffError("needs_ocr", "NeedsOcrError listed no pages") from exc
        return pages
    return ()


def convert_with_anydoc(path: Path) -> str:
    """Convert one local PDF to Markdown. Hosted OCR is never used.

    AnyDoc 0.2.4 raises ``NeedsOcrError`` for the whole file when any page is
    image-only. This helper drops those named pages and converts the rest
    locally. Live bake-off assembly OCRs named/empty pages on the host and
    only sends AnyDoc-safe slices here. It does not call Firecrawl Parse.

    Args:
        path: Readable PDF path.

    Returns:
        Markdown string.

    Raises:
        BakeoffError: When AnyDoc is missing, hosted OCR is requested, or the
            remaining pages still need OCR.
    """

    try:
        import anydoc
    except ImportError as exc:
        raise BakeoffError(
            "anydoc_missing", "firecrawl-anydoc is not installed"
        ) from exc
    if ANYDOC_OCR_MODE != "reject":
        raise BakeoffError("hosted_forbidden", "hosted AnyDoc OCR is forbidden")
    try:
        return str(anydoc.to_markdown(str(path), ocr="reject"))
    except anydoc.NeedsOcrError as exc:
        pages = tuple(int(page) for page in (getattr(exc, "pages", ()) or ()))
        if not pages:
            raise BakeoffError("needs_ocr", "NeedsOcrError listed no pages") from exc
        handle, stripped_name = tempfile.mkstemp(
            prefix="anydoc-textpages-", suffix=".pdf"
        )
        os.close(handle)
        stripped = Path(stripped_name)
        try:
            _write_pdf_without_pages(path, pages, stripped)
            return str(anydoc.to_markdown(str(stripped), ocr="reject"))
        except anydoc.NeedsOcrError as retry_exc:
            raise BakeoffError(
                "needs_ocr", "remaining pages still need OCR"
            ) from retry_exc
        finally:
            stripped.unlink(missing_ok=True)


def map_anydoc_exception(exc: BaseException) -> str:
    """Map an AnyDoc exception to a sanitized failure code.

    Args:
        exc: Raised vendor or OS error.

    Returns:
        Failure code. Never includes exception text.
    """

    names = {type(exc).__name__, *(base.__name__ for base in type(exc).mro())}
    if "NeedsOcrError" in names:
        return "needs_ocr"
    if "EncryptedError" in names:
        return "encrypted"
    if "UnsupportedError" in names:
        return "unsupported"
    if "HostedError" in names:
        return "hosted_forbidden"
    if "ResourceLimitError" in names:
        return "resource_limit"
    if "MissingPartError" in names:
        return "missing_part"
    if "MalformedError" in names:
        return "malformed"
    if isinstance(exc, UnicodeError):
        return "invalid_utf8"
    if isinstance(exc, OSError):
        return "io"
    if isinstance(exc, ValueError):
        return "malformed"
    return "convert_failed"


def parse_anydoc_markdown_bytes(
    markdown: str, *, content_hash: str, ocr_pages: int = 0
) -> ParseResult:
    """Parse AnyDoc Markdown through the existing Markdown adapter.

    Args:
        markdown: AnyDoc Markdown output.
        content_hash: Original PDF SHA-256.
        ocr_pages: Host OpenAI Vision pages included in ``markdown``.

    Returns:
        Stamped AnyDoc ``ParseResult``.
    """

    with tempfile.TemporaryDirectory(prefix="anydoc-md-") as temp_dir:
        path = Path(temp_dir) / "anydoc.md"
        path.write_text(markdown, encoding="utf-8")
        parsed = parse_markdown(path, content_hash, "markdown")
    return stamp_anydoc_parse(parsed, content_hash, ocr_pages=ocr_pages)
