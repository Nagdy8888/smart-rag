"""Host-side OpenAI Vision OCR for AnyDoc bake-off pages.

Renders named/empty pages outside the parser sandbox, calls the shared OpenAI
gateway, and splices Markdown back into AnyDoc reading order. Firecrawl is
never used.

PyMuPDF/pypdf stubs are incomplete; unknown-member diagnostics are suppressed
in this module only.
"""

# pyright: reportMissingImports=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
# pyright: reportUnknownArgumentType=false
# pyright: reportAttributeAccessIssue=false

from __future__ import annotations

import hashlib
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from smart_rag_core.evaluation.parser_bakeoff.anydoc import probe_anydoc_ocr_pages
from smart_rag_core.evaluation.parser_bakeoff.constants import (
    OPENAI_OCR_DPI,
    OPENAI_OCR_MAX_IMAGE_BYTES,
    OPENAI_OCR_MAX_PAGES,
    OPENAI_OCR_TIMEOUT_SECONDS,
)
from smart_rag_core.evaluation.parser_bakeoff.models import BakeoffError
from smart_rag_core.gateways.openai_page_ocr import (
    OpenAIPageOcrError,
    default_page_ocr_model,
    execute_openai_page_ocr,
)
from smart_rag_core.models.env_pins import ANSWER_MODEL_ID

PageKind = Literal["anydoc", "openai_ocr"]
AnydocMarkdownFn = Callable[[Path], str]
OcrPageFn = Callable[[int, bytes], str]

_OCR_CACHE: dict[tuple[str, int, str], str] = {}


@dataclass(frozen=True, slots=True)
class PageRun:
    """One contiguous run of AnyDoc pages or OpenAI OCR pages."""

    kind: PageKind
    pages: tuple[int, ...]


def empty_text_pages(path: Path) -> tuple[int, ...]:
    """Return 1-indexed pages with no selectable PDF text.

    Args:
        path: Readable PDF.

    Returns:
        Pages where ``get_text()`` is blank.

    Raises:
        BakeoffError: When PyMuPDF cannot open the file.
    """

    try:
        import fitz
    except ImportError as exc:
        raise BakeoffError(
            "anydoc_missing", "PyMuPDF is required to classify pages"
        ) from exc
    document = fitz.open(path)
    try:
        empty: list[int] = []
        for index in range(int(document.page_count)):
            page = document.load_page(index)
            text = str(page.get_text("text") or "")
            if not text.strip():
                empty.append(index + 1)
        return tuple(empty)
    finally:
        document.close()


def pages_needing_openai_ocr(
    path: Path, *, named: tuple[int, ...] | None = None
) -> tuple[int, ...]:
    """Union AnyDoc-named OCR pages with empty selectable-text pages.

    Args:
        path: Original PDF.
        named: Optional 1-indexed pages already probed (Docker). ``None``
            probes local AnyDoc on the host.

    Returns:
        Sorted 1-indexed pages to send to OpenAI Vision.

    Raises:
        BakeoffError: When the union exceeds ``OPENAI_OCR_MAX_PAGES``.
    """

    named_pages = probe_anydoc_ocr_pages(path) if named is None else named
    empty = empty_text_pages(path)
    pages = tuple(sorted(set(named_pages) | set(empty)))
    if len(pages) > OPENAI_OCR_MAX_PAGES:
        raise BakeoffError("openai_ocr_limit", "too many OpenAI OCR pages")
    return pages


def page_runs(page_count: int, ocr_pages: tuple[int, ...]) -> tuple[PageRun, ...]:
    """Group 1-indexed pages into contiguous AnyDoc and OpenAI runs.

    Args:
        page_count: Total PDF pages.
        ocr_pages: Pages that must use OpenAI Vision.

    Returns:
        Ordered runs covering ``1..page_count``.
    """

    ocr = set(ocr_pages)
    runs: list[PageRun] = []
    current_kind: PageKind | None = None
    bucket: list[int] = []
    for page in range(1, page_count + 1):
        kind: PageKind = "openai_ocr" if page in ocr else "anydoc"
        if current_kind is None:
            current_kind = kind
            bucket = [page]
            continue
        if kind == current_kind:
            bucket.append(page)
            continue
        runs.append(PageRun(kind=current_kind, pages=tuple(bucket)))
        current_kind = kind
        bucket = [page]
    if current_kind is not None and bucket:
        runs.append(PageRun(kind=current_kind, pages=tuple(bucket)))
    return tuple(runs)


def write_pdf_pages(source: Path, pages: tuple[int, ...], dest: Path) -> None:
    """Copy selected 1-indexed pages into a new PDF. Never extracts text.

    Args:
        source: Original PDF.
        pages: 1-indexed pages to keep, in order.
        dest: Destination path.

    Raises:
        BakeoffError: When PyMuPDF is missing or ``pages`` is empty.
    """

    if not pages:
        raise BakeoffError("openai_ocr_invalid_page", "page run is empty")
    try:
        import fitz
    except ImportError as exc:
        raise BakeoffError(
            "anydoc_missing", "PyMuPDF is required to split page runs"
        ) from exc
    source_doc = fitz.open(source)
    kept_doc = fitz.open()
    try:
        for page in pages:
            index = int(page) - 1
            if index < 0 or index >= int(source_doc.page_count):
                raise BakeoffError("openai_ocr_invalid_page", "page is out of range")
            kept_doc.insert_pdf(source_doc, from_page=index, to_page=index)
        dest.parent.mkdir(parents=True, exist_ok=True)
        kept_doc.save(dest, garbage=4, deflate=True)
    finally:
        kept_doc.close()
        source_doc.close()


def render_page_png(
    path: Path, page_1indexed: int, *, dpi: int = OPENAI_OCR_DPI
) -> bytes:
    """Rasterize one PDF page as PNG.

    Args:
        path: Original PDF.
        page_1indexed: 1-indexed page.
        dpi: Render DPI.

    Returns:
        PNG bytes.

    Raises:
        BakeoffError: When the page is missing, PyMuPDF is missing, or the
            PNG exceeds ``OPENAI_OCR_MAX_IMAGE_BYTES``.
    """

    try:
        import fitz
    except ImportError as exc:
        raise BakeoffError(
            "anydoc_missing", "PyMuPDF is required to rasterize pages"
        ) from exc
    document = fitz.open(path)
    try:
        index = int(page_1indexed) - 1
        if index < 0 or index >= int(document.page_count):
            raise BakeoffError("openai_ocr_invalid_page", "page is out of range")
        page = document.load_page(index)
        pixmap = page.get_pixmap(dpi=dpi)
        png = bytes(pixmap.tobytes("png"))
    finally:
        document.close()
    if len(png) > OPENAI_OCR_MAX_IMAGE_BYTES:
        raise BakeoffError(
            "openai_ocr_image_limit", "page raster exceeds the image bound"
        )
    return png


def ocr_page_with_openai(
    path: Path,
    page_1indexed: int,
    *,
    api_key: str,
    model_id: str = ANSWER_MODEL_ID,
    content_hash: str,
) -> str:
    """OCR one page with the shared gateway. Replay uses an in-process cache.

    Args:
        path: Original PDF.
        page_1indexed: 1-indexed page.
        api_key: Provider credential.
        model_id: Allow-listed chat model.
        content_hash: Original PDF SHA-256 for the cache key.

    Returns:
        Markdown transcription. May be empty for a blank page.

    Raises:
        BakeoffError: When the gateway fails or bounds are exceeded.

    Side Effects:
        Prints ``openai_ocr_page=<n>`` on a cache miss. Never prints page text.
    """

    png = render_page_png(path, page_1indexed)
    digest = hashlib.sha256(png).hexdigest()
    cache_key = (content_hash, page_1indexed, digest)
    cached = _OCR_CACHE.get(cache_key)
    if cached is not None:
        return cached
    print(f"openai_ocr_page={page_1indexed}")
    try:
        markdown, _request_id, _input_tokens, _output_tokens = execute_openai_page_ocr(
            api_key=api_key,
            model_id=model_id or default_page_ocr_model(),
            image_png=png,
            image_sha256=digest,
            page_index=page_1indexed,
            timeout_seconds=OPENAI_OCR_TIMEOUT_SECONDS,
        )
    except OpenAIPageOcrError as exc:
        raise BakeoffError(exc.reason, "OpenAI page OCR failed") from exc
    _OCR_CACHE[cache_key] = markdown
    return markdown


def clear_openai_ocr_cache() -> None:
    """Drop the in-process OCR cache. Tests and failed runs use this."""

    _OCR_CACHE.clear()


def assemble_anydoc_markdown(
    path: Path,
    *,
    content_hash: str,
    convert_anydoc: AnydocMarkdownFn,
    ocr_page: OcrPageFn | None = None,
    api_key: str | None = None,
    model_id: str = ANSWER_MODEL_ID,
    ocr_pages: tuple[int, ...] | None = None,
    named_ocr_pages: tuple[int, ...] | None = None,
) -> tuple[str, tuple[int, ...]]:
    """Convert AnyDoc-safe runs and OpenAI-OCR the remaining pages in order.

    Args:
        path: Original PDF.
        content_hash: Original SHA-256.
        convert_anydoc: Converts one PDF path to Markdown (Docker or local).
        ocr_page: Optional test double ``(page, png) -> markdown``.
        api_key: Required when ``ocr_page`` is omitted and pages need OCR.
        model_id: Allow-listed chat model.
        ocr_pages: Optional precomputed OpenAI page list (Docker union).
        named_ocr_pages: Optional AnyDoc-named pages when ``ocr_pages`` is
            omitted.

    Returns:
        Merged Markdown and the 1-indexed OpenAI OCR page list.

    Raises:
        BakeoffError: When classification, conversion, or OCR fails.
    """

    try:
        import fitz
    except ImportError as exc:
        raise BakeoffError(
            "anydoc_missing", "PyMuPDF is required to assemble pages"
        ) from exc
    document = fitz.open(path)
    try:
        page_count = int(document.page_count)
    finally:
        document.close()
    resolved = (
        ocr_pages
        if ocr_pages is not None
        else pages_needing_openai_ocr(path, named=named_ocr_pages)
    )
    if not resolved:
        return convert_anydoc(path), ()
    runs = page_runs(page_count, resolved)
    parts: list[str] = []
    with tempfile.TemporaryDirectory(prefix="anydoc-runs-") as temp_dir:
        for index, run in enumerate(runs):
            if run.kind == "anydoc":
                slice_path = Path(temp_dir) / f"run-{index}.pdf"
                write_pdf_pages(path, run.pages, slice_path)
                parts.append(convert_anydoc(slice_path))
                continue
            for page in run.pages:
                if ocr_page is not None:
                    png = render_page_png(path, page)
                    parts.append(ocr_page(page, png))
                    continue
                if not api_key:
                    raise BakeoffError(
                        "openai_required", "live OpenAI settings are required"
                    )
                parts.append(
                    ocr_page_with_openai(
                        path,
                        page,
                        api_key=api_key,
                        model_id=model_id,
                        content_hash=content_hash,
                    )
                )
    merged = "\n\n".join(part.strip() for part in parts if part.strip())
    if not merged.strip():
        raise BakeoffError("malformed", "merged AnyDoc Markdown is empty")
    return merged, resolved
