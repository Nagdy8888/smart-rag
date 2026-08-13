"""Plain-text adapter."""

from __future__ import annotations

import time
from pathlib import Path

from smart_rag_core.ingestion.parser.helpers import build_coverage, element_id
from smart_rag_core.ingestion.parser.limits import (
    CLEANING_POLICY_VERSION,
    PARSER_CONFIG_VERSION,
)
from smart_rag_core.ingestion.parser.types import (
    ElementKind,
    ParseDisposition,
    ParseResult,
    ParserResourceMetrics,
    TextLocator,
    TypedElement,
)


def parse_text(path: Path, content_hash: str, format_key: str) -> ParseResult:
    """Parse plain text into paragraph elements by line groups."""

    started = time.monotonic()
    text = path.read_text(encoding="utf-8", errors="replace")
    elements: list[TypedElement] = []
    order = 0
    for line_number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        locator = TextLocator(
            line_start=line_number,
            line_end=line_number,
            encoding_confidence=1.0,
        )
        elements.append(
            TypedElement(
                element_id=element_id(
                    content_hash, order, ElementKind.PARAGRAPH, locator, line
                ),
                kind=ElementKind.PARAGRAPH,
                text=line,
                reading_order=order,
                locator=locator,
            )
        )
        order += 1
    elements_tuple = tuple(elements)
    config_hash = ParseResult.stable_config_hash(PARSER_CONFIG_VERSION, CLEANING_POLICY_VERSION)
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
        detail="text parsed",
    )
