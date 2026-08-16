# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false
"""DOCX adapter preserving logical block/table/list order."""

from __future__ import annotations

import time
from pathlib import Path

from docx import Document
from docx.oxml.table import CT_Tbl
from docx.oxml.text.paragraph import CT_P
from docx.table import Table
from docx.text.paragraph import Paragraph

from smart_rag_core.ingestion.parser.exceptions import ParserLimitExceeded
from smart_rag_core.ingestion.parser.helpers import (
    build_coverage,
    element_id,
    vendor_attr,
    vendor_items,
)
from smart_rag_core.ingestion.parser.limits import (
    CLEANING_POLICY_VERSION,
    DOCX_MAX_BLOCKS,
    PARSER_CONFIG_VERSION,
)
from smart_rag_core.ingestion.parser.types import (
    DocxLocator,
    ElementKind,
    ParseDisposition,
    ParseResult,
    ParserResourceMetrics,
    TypedElement,
)


def parse_docx(path: Path, content_hash: str, format_key: str) -> ParseResult:
    """Parse DOCX body blocks in logical order without page geometry."""

    started = time.monotonic()
    document = Document(str(path))
    elements: list[TypedElement] = []
    block_index = 0
    body = vendor_items(vendor_attr(vendor_attr(document, "element"), "body"))
    for index, block in enumerate(body):
        if block_index > DOCX_MAX_BLOCKS:
            raise ParserLimitExceeded(
                "blocks", f"block count exceeds {DOCX_MAX_BLOCKS}"
            )
        block_path = (index,)
        if isinstance(block, CT_P):
            paragraph = Paragraph(block, document)
            text = paragraph.text.strip()
            if not text:
                continue
            style = paragraph.style
            raw_name = style.name if style is not None else ""
            style_name = raw_name if isinstance(raw_name, str) else ""
            kind = (
                ElementKind.HEADING
                if style_name.lower().startswith("heading")
                else ElementKind.PARAGRAPH
            )
            elements.append(
                _element(
                    content_hash,
                    block_index,
                    kind,
                    DocxLocator(block_path=block_path),
                    text,
                )
            )
            block_index += 1
        elif isinstance(block, CT_Tbl):
            table = Table(block, document)
            table_locator = DocxLocator(block_path=block_path)
            elements.append(
                TypedElement(
                    element_id=element_id(
                        content_hash,
                        block_index,
                        ElementKind.TABLE,
                        table_locator,
                        None,
                    ),
                    kind=ElementKind.TABLE,
                    text=None,
                    reading_order=block_index,
                    locator=table_locator,
                )
            )
            block_index += 1
            for row_index, row in enumerate(table.rows):
                for cell_index, cell in enumerate(row.cells):
                    cell_text = cell.text.strip()
                    if not cell_text:
                        continue
                    cell_path = (*block_path, row_index, cell_index)
                    elements.append(
                        _element(
                            content_hash,
                            block_index,
                            ElementKind.TABLE_CELL,
                            DocxLocator(block_path=cell_path),
                            cell_text,
                        )
                    )
                    block_index += 1

    elements_tuple = tuple(
        element.model_copy(update={"reading_order": index})
        for index, element in enumerate(elements)
    )
    config_hash = ParseResult.stable_config_hash(
        PARSER_CONFIG_VERSION, CLEANING_POLICY_VERSION
    )
    return ParseResult(
        disposition=ParseDisposition.SUPPORTED,
        format=format_key,
        content_hash=content_hash,
        parser_version=PARSER_CONFIG_VERSION,
        cleaning_version=CLEANING_POLICY_VERSION,
        config_hash=config_hash,
        elements=elements_tuple,
        coverage=build_coverage(elements_tuple),
        resource_metrics=ParserResourceMetrics(wall_seconds=time.monotonic() - started),
        detail="docx parsed",
    )


def _element(
    content_hash: str,
    order: int,
    kind: ElementKind,
    locator: DocxLocator,
    text: str,
) -> TypedElement:
    """Build one DOCX typed element."""

    return TypedElement(
        element_id=element_id(content_hash, order, kind, locator, text),
        kind=kind,
        text=text,
        reading_order=order,
        locator=locator,
    )
