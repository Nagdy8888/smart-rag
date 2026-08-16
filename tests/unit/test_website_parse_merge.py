"""Unit tests for website snapshot parse merging."""

from __future__ import annotations

from smart_rag_core.ingestion.parser.helpers import build_coverage
from smart_rag_core.ingestion.parser.types import (
    ElementKind,
    HtmlLocator,
    ParseDisposition,
    ParseResult,
    ParserResourceMetrics,
    TypedElement,
)
from smart_rag_core.ingestion.parser.website import merge_website_parse_results


def _page(text: str, content_hash: str) -> ParseResult:
    """Build one HTML page parse result with a single paragraph.

    Args:
        text: Paragraph text.
        content_hash: Content hash also used to derive the element id.

    Returns:
        Supported HTML ``ParseResult`` for merge tests.
    """

    locator = HtmlLocator(
        dom_path=("body", "p"), element_index=0, source_url="https://example.test/"
    )
    element = TypedElement(
        element_id=content_hash[:32],
        kind=ElementKind.PARAGRAPH,
        text=text,
        reading_order=0,
        locator=locator,
    )
    return ParseResult(
        disposition=ParseDisposition.SUPPORTED,
        format="html",
        content_hash=content_hash,
        parser_version="html_v1",
        cleaning_version="html_v1",
        config_hash=ParseResult.stable_config_hash("html_v1", "html_v1"),
        elements=(element,),
        coverage=build_coverage((element,)),
        resource_metrics=ParserResourceMetrics(wall_seconds=0.01, pages_processed=1),
    )


def test_merge_website_parse_results_concatenates_reading_order() -> None:
    """Two page parses become one version tree with sequential reading order."""

    merged = merge_website_parse_results(
        (_page("one", "a" * 64), _page("two", "b" * 64)),
        combined_hash="c" * 64,
    )
    assert merged.format == "website"
    assert merged.disposition is ParseDisposition.SUPPORTED
    assert [element.text for element in merged.elements] == ["one", "two"]
    assert [element.reading_order for element in merged.elements] == [0, 1]


def test_merge_website_parse_results_empty_fails_closed() -> None:
    """A crawl with no snapshots cannot produce a version tree."""

    merged = merge_website_parse_results((), combined_hash="d" * 64)
    assert merged.disposition is ParseDisposition.FAILED
    assert merged.elements == ()
