"""Typed parser element tree and format-specific locator contracts."""

from __future__ import annotations

import hashlib
import json
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, Field


class ElementKind(StrEnum):
    """Supported typed element kinds emitted by format adapters."""

    HEADING = "heading"
    PARAGRAPH = "paragraph"
    LIST = "list"
    LIST_ITEM = "list_item"
    TABLE = "table"
    TABLE_ROW = "table_row"
    TABLE_CELL = "table_cell"
    TABLE_HEADER = "table_header"
    CODE = "code"
    PAGE_BREAK = "page_break"
    SLIDE_BREAK = "slide_break"
    FIGURE = "figure"
    CAPTION = "caption"
    LINK = "link"


class ParseDisposition(StrEnum):
    """Closed parse outcome for one object."""

    SUPPORTED = "supported"
    CONDITIONAL = "conditional"
    UNSUPPORTED = "unsupported"
    FAILED = "failed"


class PdfLocator(BaseModel):
    """PDF page and optional normalized bounding box."""

    format: Literal["pdf"] = "pdf"
    page_index: int = Field(ge=0)
    char_start: int | None = Field(default=None, ge=0)
    char_end: int | None = Field(default=None, ge=0)
    bbox_x0: float | None = None
    bbox_y0: float | None = None
    bbox_x1: float | None = None
    bbox_y1: float | None = None
    rotation: int | None = None


class OcrLocator(BaseModel):
    """OCR page with pixel/normalized boxes and confidence."""

    format: Literal["ocr"] = "ocr"
    page_index: int = Field(ge=0)
    bbox_x0: float
    bbox_y0: float
    bbox_x1: float
    bbox_y1: float
    confidence: float = Field(ge=0.0, le=100.0)
    rendered_page_hash: str | None = None
    engine_version: str | None = None
    trained_data_version: str | None = None


class DocxLocator(BaseModel):
    """Ordered OOXML block/table/list path without fabricated page geometry."""

    format: Literal["docx"] = "docx"
    block_path: tuple[int, ...]
    relationship_id: str | None = None
    revision_tracked: bool = False
    page_geometry_unsupported: bool = True


class PptxLocator(BaseModel):
    """Slide/shape geometry with versioned reading-order evidence."""

    format: Literal["pptx"] = "pptx"
    slide_index: int = Field(ge=0)
    shape_id: int | None = None
    group_path: tuple[int, ...] = Field(default_factory=tuple)
    z_order: int | None = None
    reading_order_index: int = Field(ge=0)
    geometry_x: float | None = None
    geometry_y: float | None = None
    geometry_w: float | None = None
    geometry_h: float | None = None


class XlsxLocator(BaseModel):
    """Workbook/sheet/cell coordinates with formula/cache authority."""

    format: Literal["xlsx"] = "xlsx"
    sheet_name: str
    sheet_index: int = Field(ge=0)
    row: int = Field(ge=1)
    col: int = Field(ge=1)
    cell_ref: str
    range_ref: str | None = None
    hidden_sheet: bool = False
    date_epoch: Literal["1900", "1904"] = "1900"
    number_format: str | None = None


class CsvLocator(BaseModel):
    """CSV record/column ordinals and optional byte span."""

    format: Literal["csv"] = "csv"
    record_index: int = Field(ge=0)
    column_index: int = Field(ge=0)
    header_text: str | None = None
    header_ordinal: int | None = Field(default=None, ge=0)
    line_start: int | None = Field(default=None, ge=0)
    byte_start: int | None = Field(default=None, ge=0)
    byte_end: int | None = Field(default=None, ge=0)
    encoding: str = "utf-8"
    dialect: str = "excel"
    null_policy: str = "empty_string"


class HtmlLocator(BaseModel):
    """DOM path and crawl/snapshot provenance."""

    format: Literal["html"] = "html"
    dom_path: tuple[str, ...]
    element_index: int = Field(ge=0)
    source_url: str | None = None
    crawl_version: str | None = None
    removed_boilerplate: bool = False


class MarkdownLocator(BaseModel):
    """Line/character spans and optional token path."""

    format: Literal["markdown"] = "markdown"
    line_start: int = Field(ge=1)
    line_end: int = Field(ge=1)
    char_start: int | None = Field(default=None, ge=0)
    char_end: int | None = Field(default=None, ge=0)
    token_path: tuple[str, ...] | None = None
    encoding: str = "utf-8"
    encoding_confidence: float | None = Field(default=None, ge=0.0, le=1.0)


class TextLocator(BaseModel):
    """Plain-text line/character spans."""

    format: Literal["text"] = "text"
    line_start: int = Field(ge=1)
    line_end: int = Field(ge=1)
    char_start: int | None = Field(default=None, ge=0)
    char_end: int | None = Field(default=None, ge=0)
    encoding: str = "utf-8"
    encoding_confidence: float | None = Field(default=None, ge=0.0, le=1.0)


SourceLocator = Annotated[
    PdfLocator
    | OcrLocator
    | DocxLocator
    | PptxLocator
    | XlsxLocator
    | CsvLocator
    | HtmlLocator
    | MarkdownLocator
    | TextLocator,
    Field(discriminator="format"),
]


class TypedElement(BaseModel):
    """One typed node in deterministic reading order."""

    element_id: str
    kind: ElementKind
    text: str | None = None
    reading_order: int = Field(ge=0)
    locator: SourceLocator
    media_only: bool = False
    children: tuple[str, ...] = Field(default_factory=tuple)
    metadata: dict[str, str | int | float | bool | None] = Field(default_factory=dict)


class RemovalDiagnostic(BaseModel):
    """Accounted removed content (headers/footers/boilerplate)."""

    reason: str
    text_preview: str
    locator: SourceLocator | None = None
    occurrences: int = Field(default=1, ge=1)


class CoverageAccounting(BaseModel):
    """Coverage and removal metrics for one parse."""

    total_elements: int = Field(ge=0)
    text_elements: int = Field(ge=0)
    media_only_elements: int = Field(ge=0)
    removed_nodes: int = Field(ge=0)
    unsupported_regions: int = Field(ge=0)
    char_coverage_ratio: float = Field(ge=0.0, le=1.0)


class ParserResourceMetrics(BaseModel):
    """Observed sandbox resource use."""

    wall_seconds: float = Field(ge=0.0)
    peak_memory_mb: float | None = None
    pages_processed: int = Field(default=0, ge=0)
    ocr_pages: int = Field(default=0, ge=0)


class ParseWarning(BaseModel):
    """Non-fatal parse diagnostic."""

    code: str
    detail: str


class ParseResult(BaseModel):
    """Closed typed parse output for one Storage object."""

    disposition: ParseDisposition
    format: str
    content_hash: str
    parser_version: str
    cleaning_version: str
    config_hash: str
    elements: tuple[TypedElement, ...] = Field(default_factory=tuple)
    removals: tuple[RemovalDiagnostic, ...] = Field(default_factory=tuple)
    coverage: CoverageAccounting
    warnings: tuple[ParseWarning, ...] = Field(default_factory=tuple)
    resource_metrics: ParserResourceMetrics
    detail: str = ""

    @staticmethod
    def stable_config_hash(
        parser_version: str,
        cleaning_version: str,
        extra: dict[str, object] | None = None,
    ) -> str:
        """Compute deterministic config hash for replay comparisons.

        Args:
            parser_version: Pinned parser bundle version string.
            cleaning_version: Versioned cleaning policy identifier.
            extra: Optional adapter-specific config keys.

        Returns:
            Lowercase hex SHA-256 of canonical JSON config.
        """

        payload = {
            "parser_version": parser_version,
            "cleaning_version": cleaning_version,
            "extra": extra or {},
        }
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
