"""Markdown adapter preserving line/token spans."""

from __future__ import annotations

import time
from pathlib import Path

from markdown_it import MarkdownIt

from smart_rag_core.ingestion.parser.helpers import build_coverage, element_id
from smart_rag_core.ingestion.parser.limits import (
    CLEANING_POLICY_VERSION,
    MARKDOWN_MAX_LINES,
    PARSER_CONFIG_VERSION,
)
from smart_rag_core.ingestion.parser.types import (
    ElementKind,
    MarkdownLocator,
    ParseDisposition,
    ParseResult,
    ParserResourceMetrics,
    TypedElement,
)


def parse_markdown(path: Path, content_hash: str, format_key: str) -> ParseResult:
    """Parse Markdown into typed elements with line spans."""

    started = time.monotonic()
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    if len(lines) > MARKDOWN_MAX_LINES:
        lines = lines[:MARKDOWN_MAX_LINES]
    md = MarkdownIt("commonmark")
    tokens = md.parse(text)
    elements: list[TypedElement] = []
    order = 0
    for token in tokens:
        if token.type == "heading_open":
            continue
        if token.type == "inline" and token.content.strip():
            line = token.map[0] + 1 if token.map else 1
            locator = MarkdownLocator(
                line_start=line,
                line_end=token.map[1] + 1 if token.map else line,
                token_path=(token.type,),
                encoding_confidence=1.0,
            )
            kind = ElementKind.PARAGRAPH
            elements.append(
                TypedElement(
                    element_id=element_id(
                        content_hash, order, kind, locator, token.content
                    ),
                    kind=kind,
                    text=token.content,
                    reading_order=order,
                    locator=locator,
                )
            )
            order += 1
        elif token.type == "fence":
            line = token.map[0] + 1 if token.map else 1
            locator = MarkdownLocator(
                line_start=line, line_end=line, token_path=("fence",)
            )
            elements.append(
                TypedElement(
                    element_id=element_id(
                        content_hash, order, ElementKind.CODE, locator, token.content
                    ),
                    kind=ElementKind.CODE,
                    text=token.content,
                    reading_order=order,
                    locator=locator,
                    metadata={"info": token.info or ""},
                )
            )
            order += 1
    if not elements:
        for line_number, line in enumerate(lines, start=1):
            if not line.strip():
                continue
            locator = MarkdownLocator(line_start=line_number, line_end=line_number)
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
        detail="markdown parsed",
    )
