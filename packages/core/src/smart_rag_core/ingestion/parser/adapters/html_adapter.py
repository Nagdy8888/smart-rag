# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportAttributeAccessIssue=false
"""HTML adapter with deterministic boilerplate removal."""

from __future__ import annotations

import time
from pathlib import Path

from bs4.element import NavigableString, Tag

from smart_rag_core.ingestion.parser.cleaning.html_boilerplate import (
    extract_main_content,
)
from smart_rag_core.ingestion.parser.helpers import build_coverage, element_id
from smart_rag_core.ingestion.parser.limits import (
    CLEANING_POLICY_VERSION,
    HTML_MAX_NODES,
    PARSER_CONFIG_VERSION,
)
from smart_rag_core.ingestion.parser.types import (
    ElementKind,
    HtmlLocator,
    ParseDisposition,
    ParseResult,
    ParserResourceMetrics,
    TypedElement,
)


def parse_html(path: Path, content_hash: str, format_key: str) -> ParseResult:
    """Parse HTML snapshot into typed elements with DOM locators."""

    started = time.monotonic()
    html = path.read_text(encoding="utf-8", errors="replace")
    main, removals = extract_main_content(html)
    elements: list[TypedElement] = []
    order = 0
    node_count = 0
    for index, node in enumerate(main.descendants):
        node_count += 1
        if node_count > HTML_MAX_NODES:
            break
        if isinstance(node, NavigableString):
            text = str(node).strip()
            if not text:
                continue
            parent = node.parent if isinstance(node.parent, Tag) else main
            locator = HtmlLocator(
                dom_path=_dom_path(parent),
                element_index=index,
            )
            kind = _kind_for_tag(parent)
            elements.append(
                TypedElement(
                    element_id=element_id(content_hash, order, kind, locator, text),
                    kind=kind,
                    text=text,
                    reading_order=order,
                    locator=locator,
                )
            )
            order += 1
        elif isinstance(node, Tag) and node.name == "a" and node.get("href"):
            text = node.get_text(" ", strip=True)
            if text:
                locator = HtmlLocator(dom_path=_dom_path(node), element_index=index)
                elements.append(
                    TypedElement(
                        element_id=element_id(
                            content_hash, order, ElementKind.LINK, locator, text
                        ),
                        kind=ElementKind.LINK,
                        text=text,
                        reading_order=order,
                        locator=locator,
                        metadata={"href": str(node.get("href"))},
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
        removals=removals,
        coverage=build_coverage(elements_tuple, removed=len(removals)),
        resource_metrics=ParserResourceMetrics(wall_seconds=time.monotonic() - started),
        detail="html parsed",
    )


def _dom_path(tag: Tag) -> tuple[str, ...]:
    """Build DOM path segments for one tag."""

    parts: list[str] = []
    current: Tag | None = tag
    while current is not None and current.name:
        parts.append(current.name)
        current = current.parent if isinstance(current.parent, Tag) else None
    parts.reverse()
    return tuple(parts)


def _kind_for_tag(tag: Tag) -> ElementKind:
    """Map HTML tag to typed element kind."""

    if tag.name in {"h1", "h2", "h3", "h4", "h5", "h6"}:
        return ElementKind.HEADING
    if tag.name in {"pre", "code"}:
        return ElementKind.CODE
    if tag.name == "li":
        return ElementKind.LIST_ITEM
    if tag.name in {"ul", "ol"}:
        return ElementKind.LIST
    if tag.name == "table":
        return ElementKind.TABLE
    return ElementKind.PARAGRAPH
