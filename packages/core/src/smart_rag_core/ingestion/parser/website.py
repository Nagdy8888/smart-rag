"""Merge per-page website snapshot parses into one version element tree."""

from __future__ import annotations

from smart_rag_core.ingestion.parser.helpers import build_coverage
from smart_rag_core.ingestion.parser.types import (
    ParseDisposition,
    ParseResult,
    ParserResourceMetrics,
    TypedElement,
)


def merge_website_parse_results(
    pages: tuple[ParseResult, ...],
    *,
    combined_hash: str,
) -> ParseResult:
    """Combine per-snapshot HTML parses into one website version tree.

    Args:
        pages: Parse results in crawl fetch order. Empty input fails closed.
        combined_hash: SHA-256 of concatenated page content hashes.

    Returns:
        One ``ParseResult`` with concatenated reading order. Failed or empty
        page parses make the combined disposition ``failed``.

    Side Effects:
        None. Does not persist or call the parser sandbox.
    """

    if not pages:
        return ParseResult(
            disposition=ParseDisposition.FAILED,
            format="website",
            content_hash=combined_hash,
            parser_version="website_merge_v1",
            cleaning_version="website_merge_v1",
            config_hash=ParseResult.stable_config_hash(
                "website_merge_v1",
                "website_merge_v1",
            ),
            coverage=build_coverage(()),
            resource_metrics=ParserResourceMetrics(wall_seconds=0.0),
            detail="no website snapshots to parse",
        )

    elements: list[TypedElement] = []
    removals = []
    warnings = []
    wall_seconds = 0.0
    failed = False
    for page in pages:
        if page.disposition is ParseDisposition.FAILED:
            failed = True
        for element in page.elements:
            elements.append(
                element.model_copy(update={"reading_order": len(elements)})
            )
        removals.extend(page.removals)
        warnings.extend(page.warnings)
        wall_seconds += page.resource_metrics.wall_seconds

    first = pages[0]
    disposition = (
        ParseDisposition.FAILED
        if failed or not elements
        else ParseDisposition.SUPPORTED
    )
    return ParseResult(
        disposition=disposition,
        format="website",
        content_hash=combined_hash,
        parser_version=first.parser_version,
        cleaning_version=first.cleaning_version,
        config_hash=ParseResult.stable_config_hash(
            first.parser_version,
            first.cleaning_version,
            extra={"pages": len(pages), "combined_hash": combined_hash},
        ),
        elements=tuple(elements),
        removals=tuple(removals),
        coverage=build_coverage(tuple(elements), removed=len(removals)),
        warnings=tuple(warnings),
        resource_metrics=ParserResourceMetrics(
            wall_seconds=wall_seconds,
            pages_processed=len(pages),
        ),
        detail=f"merged {len(pages)} website snapshots",
    )
