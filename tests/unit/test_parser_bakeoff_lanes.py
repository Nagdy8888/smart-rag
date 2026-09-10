"""Unit tests for isolated bake-off parser lanes."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, cast

import fitz
from smart_rag_core.evaluation.parser_bakeoff.anydoc import map_anydoc_exception
from smart_rag_core.evaluation.parser_bakeoff.constants import (
    ANYDOC_CLEANING_VERSION,
    ANYDOC_PARSER_VERSION,
)
from smart_rag_core.evaluation.parser_bakeoff.lanes import (
    LaneParseRequest,
    parse_lane,
)
from smart_rag_core.ingestion.parser.types import (
    MarkdownLocator,
    ParseDisposition,
    PdfLocator,
)


class NeedsOcrError(RuntimeError):
    """Synthetic AnyDoc OCR rejection."""


class EncryptedError(RuntimeError):
    """Synthetic encrypted PDF."""


class UnsupportedError(RuntimeError):
    """Synthetic unsupported format."""


class HostedError(RuntimeError):
    """Synthetic hosted OCR attempt."""


class ResourceLimitError(RuntimeError):
    """Synthetic resource limit."""


class MissingPartError(RuntimeError):
    """Synthetic missing embedded part."""


class MalformedError(RuntimeError):
    """Synthetic malformed document."""


def _pdf_bytes(text: str = "Bakeoff current lane") -> bytes:
    """Build a tiny in-memory PDF.

    Args:
        text: Page text.

    Returns:
        PDF bytes.
    """

    document = cast(Any, fitz.open())
    page = document.new_page()
    page.insert_text((72, 72), text)
    payload = bytes(document.tobytes())
    document.close()
    return payload


def _request(
    payload: bytes, lane_id: str, *, use_docker: bool = False
) -> LaneParseRequest:
    """Build one parse request.

    Args:
        payload: Source bytes.
        lane_id: Lane token.
        use_docker: Docker flag.

    Returns:
        Request model.
    """

    return LaneParseRequest(
        payload=payload,
        content_hash=hashlib.sha256(payload).hexdigest(),
        filename="book.pdf",
        media_type="application/pdf",
        lane_id=lane_id,  # type: ignore[arg-type]
        run_id="run-test",
        use_docker=use_docker,
    )


def test_anydoc_success_preserves_pdf_hash_and_markdown_locators() -> None:
    """Successful AnyDoc conversion keeps the PDF hash and Markdown locators."""

    payload = _pdf_bytes()
    digest = hashlib.sha256(payload).hexdigest()

    def _convert(_path: Path) -> str:
        """Return deterministic Markdown.

        Args:
            _path: Unused PDF path.

        Returns:
            Markdown.
        """

        return "# Title\n\nHello bakeoff world.\n"

    result = parse_lane(_request(payload, "anydoc_local"), converter=_convert)
    assert result.disposition is ParseDisposition.SUPPORTED
    assert result.content_hash == digest
    assert result.parser_version == ANYDOC_PARSER_VERSION
    assert result.cleaning_version == ANYDOC_CLEANING_VERSION
    assert result.elements
    assert all(isinstance(item.locator, MarkdownLocator) for item in result.elements)
    assert not any(isinstance(item.locator, PdfLocator) for item in result.elements)


def test_anydoc_failure_codes_emit_zero_elements() -> None:
    """Documented AnyDoc errors fail closed with zero elements."""

    payload = _pdf_bytes()
    mapping = {
        NeedsOcrError: "needs_ocr",
        EncryptedError: "encrypted",
        UnsupportedError: "unsupported",
        HostedError: "hosted_forbidden",
        ResourceLimitError: "resource_limit",
        MissingPartError: "missing_part",
        MalformedError: "malformed",
    }
    for exc_type, code in mapping.items():

        def _convert(_path: Path, error: type[Exception] = exc_type) -> str:
            """Raise one vendor error.

            Args:
                _path: Unused path.
                error: Exception class.

            Returns:
                Never returns.

            Raises:
                Exception: The mapped vendor error.
            """

            raise error("redacted")

        result = parse_lane(_request(payload, "anydoc_local"), converter=_convert)
        assert result.disposition is ParseDisposition.FAILED
        assert result.detail == code
        assert result.elements == ()
        assert result.coverage.total_elements == 0
        assert result.content_hash == hashlib.sha256(payload).hexdigest()


def test_anydoc_hash_mismatch_fails_closed() -> None:
    """A tampered content hash fails before conversion."""

    payload = _pdf_bytes()
    request = _request(payload, "anydoc_local")
    request = LaneParseRequest(
        payload=payload,
        content_hash="0" * 64,
        filename="book.pdf",
        media_type="application/pdf",
        lane_id="anydoc_local",
        run_id="run-test",
        use_docker=False,
    )
    result = parse_lane(request, converter=lambda _path: "# x\n")
    assert result.disposition is ParseDisposition.FAILED
    assert result.detail == "hash_mismatch"
    assert result.elements == ()


def test_map_anydoc_exception_never_uses_payload() -> None:
    """Exception mapping uses class names, not message text."""

    class NeedsOcrError(RuntimeError):
        """Local OCR error."""

    assert map_anydoc_exception(NeedsOcrError("secret source text")) == "needs_ocr"


def test_current_lane_inprocess_pdf() -> None:
    """Current lane in-process path returns the original PDF hash."""

    payload = _pdf_bytes("Current parser path")
    result = parse_lane(_request(payload, "current"))
    assert result.content_hash == hashlib.sha256(payload).hexdigest()
    assert result.disposition in {
        ParseDisposition.SUPPORTED,
        ParseDisposition.CONDITIONAL,
        ParseDisposition.FAILED,
    }
    if result.disposition is not ParseDisposition.FAILED:
        assert result.elements
        assert any(isinstance(item.locator, PdfLocator) for item in result.elements)
