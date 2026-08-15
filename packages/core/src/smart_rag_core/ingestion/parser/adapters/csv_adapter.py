"""CSV adapter with encoding/dialect/null policy."""

from __future__ import annotations

import csv
import time
from pathlib import Path

from smart_rag_core.ingestion.parser.exceptions import ParserLimitExceeded
from smart_rag_core.ingestion.parser.helpers import build_coverage, element_id
from smart_rag_core.ingestion.parser.limits import (
    CLEANING_POLICY_VERSION,
    PARSER_CONFIG_VERSION,
    PARSER_SANDBOX_MAX_ROWS,
)
from smart_rag_core.ingestion.parser.types import (
    CsvLocator,
    ElementKind,
    ParseDisposition,
    ParseResult,
    ParserResourceMetrics,
    TypedElement,
)


def parse_csv(path: Path, content_hash: str, format_key: str) -> ParseResult:
    """Parse CSV rows into typed table cells with ordinals."""

    started = time.monotonic()
    raw = path.read_bytes()
    encoding = "utf-8"
    text = raw.decode(encoding, errors="replace")
    reader = csv.reader(text.splitlines())
    rows = list(reader)
    if len(rows) > PARSER_SANDBOX_MAX_ROWS:
        raise ParserLimitExceeded("rows", f"row count {len(rows)}")
    headers = rows[0] if rows else []
    elements: list[TypedElement] = []
    order = 0
    byte_offset = 0
    for record_index, row in enumerate(rows):
        for column_index, value in enumerate(row):
            header_text = (
                headers[column_index]
                if record_index > 0 and column_index < len(headers)
                else (value if record_index == 0 else None)
            )
            if record_index == 0:
                kind = ElementKind.TABLE_HEADER
            else:
                kind = ElementKind.TABLE_CELL
            locator = CsvLocator(
                record_index=record_index,
                column_index=column_index,
                header_text=header_text,
                header_ordinal=column_index,
                byte_start=byte_offset,
                byte_end=byte_offset + len(value.encode(encoding)),
                encoding=encoding,
            )
            elements.append(
                TypedElement(
                    element_id=element_id(content_hash, order, kind, locator, value),
                    kind=kind,
                    text=value,
                    reading_order=order,
                    locator=locator,
                )
            )
            order += 1
            byte_offset = locator.byte_end or byte_offset
    elements_tuple = tuple(elements)
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
        detail="csv parsed",
    )
