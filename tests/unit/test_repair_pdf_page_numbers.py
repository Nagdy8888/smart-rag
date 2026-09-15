"""Unit tests for PDF page-number repair from locator ``page_index``."""

from __future__ import annotations

from uuid import uuid4

import pytest

from scripts.ops.repair_pdf_page_numbers import (
    PageAmbiguousError,
    parse_args,
    pdf_locator_page_indexes,
    viewer_page_from_locators,
)


def test_viewer_page_ignores_page_label() -> None:
    """Printed ``page_label`` never changes the 1-based viewer page."""

    provenance = {
        "locators": [
            {"format": "pdf", "page_index": 24, "page_label": "12"},
        ]
    }
    assert pdf_locator_page_indexes(provenance) == (24,)
    assert viewer_page_from_locators(provenance) == 25


def test_viewer_page_rejects_multi_page_locators() -> None:
    """A leaf spanning two PDF pages cannot be repaired without guessing."""

    provenance = {
        "locators": [
            {"format": "pdf", "page_index": 24, "page_label": "25"},
            {"format": "pdf", "page_index": 25, "page_label": "26"},
        ]
    }
    with pytest.raises(ValueError, match="page_ambiguous"):
        viewer_page_from_locators(provenance)


def test_viewer_page_rejects_pdf_locators_without_index() -> None:
    """PDF locators that omit ``page_index`` fail closed."""

    provenance = {"locators": [{"format": "pdf", "page_label": "12"}]}
    with pytest.raises(ValueError, match="page_ambiguous"):
        viewer_page_from_locators(provenance)


def test_non_pdf_locators_return_none() -> None:
    """Docx locators do not invent a PDF viewer page."""

    provenance = {"locators": [{"format": "docx", "block_path": [0]}]}
    assert viewer_page_from_locators(provenance) is None


def test_parse_args_requires_version_and_defaults_dry_run() -> None:
    """CLI requires ``--version-id`` and stays dry-run without ``--apply``."""

    version_id = uuid4()
    args = parse_args(["--version-id", str(version_id), "--batch-size", "500"])
    assert args.version_id == str(version_id)
    assert args.batch_size == 500
    assert args.apply is False
    apply_args = parse_args(["--version-id", str(version_id), "--apply"])
    assert apply_args.apply is True


def test_page_ambiguous_error_exposes_chunk_id_only() -> None:
    """Ambiguous repair failures report the chunk id, not source text."""

    chunk_id = uuid4()
    error = PageAmbiguousError(chunk_id)
    assert error.chunk_id == chunk_id
    assert str(chunk_id) in str(error)
    assert "Refund" not in str(error)
