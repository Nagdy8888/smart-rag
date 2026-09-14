"""Unit tests for AnyDoc bake-off OpenAI page OCR assembly."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, cast
from unittest.mock import patch
from uuid import uuid4

import fitz
import pytest
from smart_rag_core.evaluation.parser_bakeoff.anydoc import parse_anydoc_markdown_bytes
from smart_rag_core.evaluation.parser_bakeoff.models import BakeoffError
from smart_rag_core.evaluation.parser_bakeoff.page_ocr import (
    PageRun,
    assemble_anydoc_markdown,
    clear_openai_ocr_cache,
    empty_text_pages,
    ocr_page_with_openai,
    page_runs,
)
from smart_rag_core.evaluation.parser_bakeoff.summaries import summarize_parse_chunk
from smart_rag_core.gateways.openai_page_ocr import OpenAIPageOcrError


def _write_pdf(path: Path, pages: list[str | None]) -> None:
    """Write a tiny PDF with optional per-page text.

    Args:
        path: Destination path.
        pages: Text per page, or ``None`` for an empty page.
    """

    document = cast(Any, fitz.open())
    for text in pages:
        page = document.new_page()
        if text:
            page.insert_text((72, 72), text)
    path.write_bytes(bytes(document.tobytes()))
    document.close()


def test_page_runs_group_contiguous_anydoc_and_ocr_pages() -> None:
    """Runs keep original page order for splice."""

    runs = page_runs(10, (3, 4, 7))
    assert runs == (
        PageRun(kind="anydoc", pages=(1, 2)),
        PageRun(kind="openai_ocr", pages=(3, 4)),
        PageRun(kind="anydoc", pages=(5, 6)),
        PageRun(kind="openai_ocr", pages=(7,)),
        PageRun(kind="anydoc", pages=(8, 9, 10)),
    )


def test_empty_text_pages_are_one_indexed(tmp_path: Path) -> None:
    """Selectable-text classification uses 1-indexed pages."""

    source = tmp_path / "book.pdf"
    _write_pdf(source, ["Keep", None, "Keep"])
    assert empty_text_pages(source) == (2,)


def test_assemble_splices_openai_pages_in_order(tmp_path: Path) -> None:
    """AnyDoc slice Markdown and OCR pages join in original order."""

    source = tmp_path / "book.pdf"
    _write_pdf(source, ["KeepA", None, "KeepC", "KeepD"])
    converted: list[int] = []

    def _convert(path: Path) -> str:
        """Return a marker for the slice page count.

        Args:
            path: Slice PDF.

        Returns:
            Marker Markdown.
        """

        document = cast(Any, fitz.open(path))
        count = int(document.page_count)
        document.close()
        converted.append(count)
        return f"anydoc-run-{count}"

    def _ocr(page: int, png: bytes) -> str:
        """Return a marker for the OCR page.

        Args:
            page: 1-indexed page.
            png: Raster bytes.

        Returns:
            Marker Markdown.
        """

        assert png
        return f"ocr-{page}"

    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    merged, pages = assemble_anydoc_markdown(
        source,
        content_hash=digest,
        convert_anydoc=_convert,
        ocr_page=_ocr,
        ocr_pages=(2,),
    )
    assert pages == (2,)
    assert converted == [1, 2]
    assert merged == "anydoc-run-1\n\nocr-2\n\nanydoc-run-2"


def test_ocr_cache_replays_without_a_second_provider_call(tmp_path: Path) -> None:
    """Replay uses the in-process cache keyed by hash, page, and PNG digest."""

    source = tmp_path / "book.pdf"
    _write_pdf(source, [None])
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    clear_openai_ocr_cache()
    calls = {"count": 0}

    def _execute(**_kwargs: object) -> tuple[str, str, int, int]:
        """Count provider calls.

        Args:
            **_kwargs: Unused adapter arguments.

        Returns:
            Fake OCR tuple.
        """

        calls["count"] += 1
        return "cached-ocr", "resp", 1, 1

    with patch(
        "smart_rag_core.evaluation.parser_bakeoff.page_ocr.execute_openai_page_ocr",
        _execute,
    ):
        first = ocr_page_with_openai(source, 1, api_key="sk-test", content_hash=digest)
        second = ocr_page_with_openai(source, 1, api_key="sk-test", content_hash=digest)
    assert first == "cached-ocr"
    assert second == first
    assert calls["count"] == 1
    clear_openai_ocr_cache()


def test_ocr_provider_failure_fails_the_lane(tmp_path: Path) -> None:
    """A failed OpenAI OCR call becomes a bake-off error."""

    source = tmp_path / "book.pdf"
    _write_pdf(source, [None])
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    clear_openai_ocr_cache()

    def _execute(**_kwargs: object) -> tuple[str, str, int, int]:
        """Raise a typed provider failure.

        Args:
            **_kwargs: Unused adapter arguments.

        Returns:
            Never returns.

        Raises:
            OpenAIPageOcrError: Always.
        """

        raise OpenAIPageOcrError("openai_ocr_timeout")

    with (
        patch(
            "smart_rag_core.evaluation.parser_bakeoff.page_ocr.execute_openai_page_ocr",
            _execute,
        ),
        pytest.raises(BakeoffError) as raised,
    ):
        ocr_page_with_openai(source, 1, api_key="sk-test", content_hash=digest)
    assert raised.value.code == "openai_ocr_timeout"
    clear_openai_ocr_cache()


def test_anydoc_summary_reports_openai_ocr_pages() -> None:
    """AnyDoc summaries expose OpenAI OCR page counts when greater than zero."""

    result = parse_anydoc_markdown_bytes(
        "# Title\n\nHello bakeoff world.\n",
        content_hash="ab" * 32,
        ocr_pages=3,
    )
    summary = summarize_parse_chunk(
        result,
        lane_id="anydoc_local",
        document_id=uuid4(),
        version_id=uuid4(),
        replay_matched=True,
    )
    assert summary.ocr_pages == 3
    zero = parse_anydoc_markdown_bytes(
        "# Title\n\nHello bakeoff world.\n",
        content_hash="ab" * 32,
        ocr_pages=0,
    )
    zero_summary = summarize_parse_chunk(
        zero,
        lane_id="anydoc_local",
        document_id=uuid4(),
        version_id=uuid4(),
        replay_matched=True,
    )
    assert zero_summary.ocr_pages is None
