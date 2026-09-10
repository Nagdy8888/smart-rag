"""Printed PDF page labels stay off element identity and land on locators."""

from __future__ import annotations

from pathlib import Path
from uuid import UUID

from smart_rag_core.ingestion.chunking import chunk_parse_result
from smart_rag_core.ingestion.parser.adapters import parse_file
from smart_rag_core.ingestion.provenance import attach_page_label

from tests.fixtures.parser import build_pdf_page_label_fixture

DOCUMENT_ID = UUID("11111111-1111-4111-8111-111111111111")
VERSION_ID = UUID("22222222-2222-4222-8222-222222222222")


def test_attach_page_label_skips_unlabeled_and_non_pdf() -> None:
    """Labels attach only when page_index has a non-empty map entry."""

    labeled = attach_page_label({"format": "pdf", "page_index": 0}, ("50",))
    assert labeled["page_label"] == "50"
    unlabeled = attach_page_label({"format": "pdf", "page_index": 0}, ("",))
    assert "page_label" not in unlabeled
    sheet = attach_page_label({"format": "xlsx", "sheet_name": "Q1"}, ("50",))
    assert "page_label" not in sheet


def test_pdf_page_labels_are_stamped_on_chunk_locators(tmp_path: Path) -> None:
    """Printed labels survive chunking; file page_number stays 1-based index."""

    payload, digest = build_pdf_page_label_fixture()
    path = tmp_path / "labeled.pdf"
    path.write_bytes(payload)
    parsed = parse_file(path, digest, "pdf")
    assert parsed.page_labels == ("50",)
    first_ids = [element.element_id for element in parsed.elements]
    replay = parse_file(path, digest, "pdf")
    assert [element.element_id for element in replay.elements] == first_ids
    assert all(
        "page_label" not in element.locator.model_dump()
        or element.locator.model_dump().get("page_label") is None
        for element in parsed.elements
    )
    chunking = chunk_parse_result(
        parsed,
        document_id=DOCUMENT_ID,
        version_id=VERSION_ID,
    )
    locators = [
        locator
        for chunk in chunking.chunks
        for locator in chunk.provenance.locators
        if locator.get("format") == "pdf"
    ]
    assert locators
    assert all(locator.get("page_label") == "50" for locator in locators)
    assert any(chunk.page_number == 1 for chunk in chunking.chunks)
