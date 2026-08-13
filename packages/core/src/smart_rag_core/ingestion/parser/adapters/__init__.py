"""Format adapter registry and dispatch."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from smart_rag_core.ingestion.parser.adapters import (
    csv_adapter,
    docx_adapter,
    html_adapter,
    markdown_adapter,
    pdf_adapter,
    pptx_adapter,
    text_adapter,
    xlsx_adapter,
)
from smart_rag_core.ingestion.parser.exceptions import ParserUnsupportedFormat
from smart_rag_core.ingestion.parser.types import ParseResult

AdapterFn = Callable[[Path, str, str], ParseResult]

_ADAPTERS: dict[str, AdapterFn] = {
    "pdf": pdf_adapter.parse_pdf,
    "docx": docx_adapter.parse_docx,
    "pptx": pptx_adapter.parse_pptx,
    "xlsx": xlsx_adapter.parse_xlsx,
    "csv": csv_adapter.parse_csv,
    "html": html_adapter.parse_html,
    "markdown": markdown_adapter.parse_markdown,
    "text": text_adapter.parse_text,
    "htm": html_adapter.parse_html,
    "md": markdown_adapter.parse_markdown,
    "txt": text_adapter.parse_text,
}


def infer_format(path: Path, media_type: str | None = None) -> str:
    """Infer parser format from extension or media type.

    Args:
        path: Input file path.
        media_type: Optional MIME type hint.

    Returns:
        Normalized format key.

    Raises:
        ParserUnsupportedFormat: When format cannot be resolved.
    """

    suffix = path.suffix.lower().lstrip(".")
    if suffix in _ADAPTERS:
        return suffix if suffix != "htm" else "html"
    if media_type:
        mime_map = {
            "application/pdf": "pdf",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
            "application/vnd.openxmlformats-officedocument.presentationml.presentation": "pptx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "xlsx",
            "text/csv": "csv",
            "text/html": "html",
            "text/markdown": "markdown",
            "text/plain": "text",
        }
        mapped = mime_map.get(media_type.lower())
        if mapped:
            return mapped
    raise ParserUnsupportedFormat(f"unsupported format for {path.name}")


def parse_file(path: Path, content_hash: str, format_key: str | None = None) -> ParseResult:
    """Parse one local file through the selected adapter.

    Args:
        path: Readable input path inside sandbox temp dir.
        content_hash: Expected SHA-256 of source bytes.
        format_key: Optional explicit format override.

    Returns:
        Closed typed parse result.

    Raises:
        ParserUnsupportedFormat: When no adapter exists.
    """

    resolved = format_key or infer_format(path)
    adapter = _ADAPTERS.get(resolved)
    if adapter is None:
        raise ParserUnsupportedFormat(f"no adapter registered for {resolved}")
    return adapter(path, content_hash, resolved)
