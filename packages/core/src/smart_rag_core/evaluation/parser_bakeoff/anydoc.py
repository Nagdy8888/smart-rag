"""Local AnyDoc conversion helpers with no Firecrawl network fallback."""

from __future__ import annotations

import tempfile
from collections.abc import Callable
from pathlib import Path

from smart_rag_core.evaluation.parser_bakeoff.constants import (
    ANYDOC_CLEANING_VERSION,
    ANYDOC_OCR_MODE,
    ANYDOC_PACKAGE_VERSION,
    ANYDOC_PARSER_VERSION,
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


def stamp_anydoc_parse(result: ParseResult, content_hash: str) -> ParseResult:
    """Rewrite Markdown-adapter identity onto AnyDoc pins.

    Args:
        result: Markdown adapter output.
        content_hash: Original PDF SHA-256.

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
                update={"pages_processed": 0, "ocr_pages": 0}
            ),
        }
    )


def convert_with_anydoc(path: Path) -> str:
    """Convert one local PDF to Markdown with OCR rejected.

    Args:
        path: Readable PDF path.

    Returns:
        Markdown string.

    Raises:
        BakeoffError: When AnyDoc is missing.
    """

    try:
        import anydoc
    except ImportError as exc:
        raise BakeoffError(
            "anydoc_missing", "firecrawl-anydoc is not installed"
        ) from exc
    return str(anydoc.to_markdown(str(path), ocr=ANYDOC_OCR_MODE))


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


def parse_anydoc_markdown_bytes(markdown: str, *, content_hash: str) -> ParseResult:
    """Parse AnyDoc Markdown through the existing Markdown adapter.

    Args:
        markdown: AnyDoc Markdown output.
        content_hash: Original PDF SHA-256.

    Returns:
        Stamped AnyDoc ``ParseResult``.
    """

    with tempfile.TemporaryDirectory(prefix="anydoc-md-") as temp_dir:
        path = Path(temp_dir) / "anydoc.md"
        path.write_text(markdown, encoding="utf-8")
        parsed = parse_markdown(path, content_hash, "markdown")
    return stamp_anydoc_parse(parsed, content_hash)
