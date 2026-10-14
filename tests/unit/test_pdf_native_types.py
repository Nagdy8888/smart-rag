"""PDF code, tables, and figures stay typed through parse and chunking."""

from __future__ import annotations

import hashlib
from pathlib import Path
from uuid import uuid4

import fitz
from smart_rag_core.ingestion.chunking.limits import CHUNKING_POLICY_VERSION
from smart_rag_core.ingestion.chunking.service import chunk_parse_result
from smart_rag_core.ingestion.figures.materialize import materialize_pdf_figures
from smart_rag_core.ingestion.parser.adapters import parse_file
from smart_rag_core.ingestion.parser.limits import PDF_PARSER_VERSION
from smart_rag_core.ingestion.parser.types import ElementKind
from smart_rag_core.ingestion.tables.parquet_io import read_parquet_artifact
from smart_rag_core.query_answer.models import AnswerParagraph, AnswerPayload
from smart_rag_core.query_answer.native_blocks import attach_native_evidence
from smart_rag_core.query_fusion.models import (
    FusionAlgorithm,
    FusionResult,
    PassageOrigin,
    ScoredPassage,
)


def _pdf_bytes() -> bytes:
    """Build a one-page PDF with a captioned table, code, and a large image."""

    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), "Table 1. Rates", fontsize=12)
    page.insert_text((72, 100), "Name", fontsize=11)
    page.insert_text((220, 100), "Count", fontsize=11)
    page.insert_text((360, 100), "Note", fontsize=11)
    page.insert_text((72, 122), "Alpha", fontsize=11)
    page.insert_text((220, 122), "3", fontsize=11)
    page.insert_text((360, 122), "ok", fontsize=11)
    page.insert_text((72, 144), "Beta", fontsize=11)
    page.insert_text((220, 144), "4", fontsize=11)
    page.insert_text((360, 144), "no", fontsize=11)
    page.insert_text((72, 200), "def run():", fontname="cour", fontsize=10)
    page.insert_text((72, 214), "    return 1", fontname="cour", fontsize=10)
    pixmap = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 120, 80), 1)
    pixmap.clear_with(255)
    page.insert_image(fitz.Rect(72, 280, 192, 360), pixmap=pixmap)
    tiny = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 8, 8), 1)
    page.insert_image(fitz.Rect(400, 20, 408, 28), pixmap=tiny)
    page.insert_text((72, 372), "Figure 1. Rates plot", fontsize=11)
    payload = document.tobytes()
    document.close()
    return payload


def test_pdf_emits_code_table_and_figure(tmp_path: Path) -> None:
    """A synthetic page keeps code, a pipe table, and a figure locator."""

    payload = _pdf_bytes()
    path = tmp_path / "native.pdf"
    path.write_bytes(payload)
    digest = hashlib.sha256(payload).hexdigest()
    parsed = parse_file(path, digest, "pdf")
    assert parsed.parser_version == PDF_PARSER_VERSION
    kinds = {element.kind for element in parsed.elements}
    assert ElementKind.CODE in kinds
    assert ElementKind.TABLE_CELL in kinds
    assert ElementKind.FIGURE in kinds
    code = next(
        element for element in parsed.elements if element.kind is ElementKind.CODE
    )
    assert "\n" in (code.text or "")
    assert "def run" in (code.text or "")
    figures = [
        element for element in parsed.elements if element.kind is ElementKind.FIGURE
    ]
    assert len(figures) == 1
    chunking = chunk_parse_result(parsed, document_id=uuid4(), version_id=uuid4())
    assert chunking.config_hash
    assert CHUNKING_POLICY_VERSION == "chunking_v3"
    tables = [
        chunk for chunk in chunking.chunks if chunk.provenance.content_kind == "table"
    ]
    assert tables
    assert tables[0].raw_text.startswith("|")
    assert "| Note |" in tables[0].raw_text
    assert chunking.table_artifacts
    stored = read_parquet_artifact(chunking.table_artifacts[0].parquet_bytes)
    assert stored.num_rows == 2
    assert "Count" in stored.column_names
    assert stored.column("Count").to_pylist() == [3, 4]
    described, assets = materialize_pdf_figures(
        parsed, payload, lambda _png: "A red square."
    )
    assert assets
    figure = next(
        element for element in described.elements if element.kind is ElementKind.FIGURE
    )
    assert figure.media_only is False
    assert "red square" in (figure.text or "")


def _continued_pdf_bytes() -> bytes:
    """Build a two-page captioned table that continues with the same columns."""

    document = fitz.open()
    first = document.new_page()
    first.insert_text((72, 72), "Table 2. Inventory", fontsize=12)
    for y, cells in (
        (100, ("Item", "Qty", "Bin")),
        (122, ("Bolt", "2", "A")),
        (144, ("Nut", "9", "B")),
    ):
        for x, text in zip((72, 220, 360), cells, strict=True):
            first.insert_text((x, y), text, fontsize=11)
    second = document.new_page()
    for y, cells in (
        (100, ("Washer", "5", "C")),
        (122, ("Screw", "8", "D")),
    ):
        for x, text in zip((72, 220, 360), cells, strict=True):
            second.insert_text((x, y), text, fontsize=11)
    payload = document.tobytes()
    document.close()
    return payload


def test_pdf_table_continues_on_the_next_page(tmp_path: Path) -> None:
    """A captioned table keeps the same columns on the following page."""

    payload = _continued_pdf_bytes()
    path = tmp_path / "continued.pdf"
    path.write_bytes(payload)
    parsed = parse_file(path, hashlib.sha256(payload).hexdigest(), "pdf")
    cells = [
        element
        for element in parsed.elements
        if element.kind is ElementKind.TABLE_CELL
    ]
    pages = {
        element.locator.page_index
        for element in cells
        if hasattr(element.locator, "page_index")
    }
    names = {str(element.metadata.get("table_name")) for element in cells}
    texts = {element.text for element in cells}
    assert pages == {0, 1}
    assert len(names) == 1
    assert "Bolt" in texts
    assert "Screw" in texts


def test_attach_native_evidence_adds_code_block() -> None:
    """A cited code passage is appended when the prose omitted it."""

    payload = AnswerPayload(
        answer_text="The helper returns one.",
        paragraphs=(
            AnswerParagraph(
                paragraph_index=0,
                text="The helper returns one.",
                link_ids=("l1",),
            ),
        ),
        atomic_links=(),
    )
    fusion = FusionResult(
        algorithm=FusionAlgorithm.NAIVE_UNION,
        config_hash="a" * 64,
        requested_route="hybrid",
        effective_route="hybrid",
        graph_discovered_only_ratio=0.0,
        evidence=(
            ScoredPassage(
                chunk_id="11111111-1111-1111-1111-111111111111",
                document_id="22222222-2222-2222-2222-222222222222",
                version_id="33333333-3333-3333-3333-333333333333",
                citation_text="def run():\n    return 1",
                combined_score=1.0,
                origin=PassageOrigin.HYBRID,
                graph_discovered_only=False,
                content_kind="code",
            ),
        ),
    )
    released = attach_native_evidence(payload, fusion)
    assert "```" in released.answer_text
    assert "def run" in released.answer_text
