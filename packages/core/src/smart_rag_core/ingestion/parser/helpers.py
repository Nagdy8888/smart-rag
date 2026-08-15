"""Shared helpers for deterministic parser output."""

from __future__ import annotations

import hashlib
import uuid

from smart_rag_core.ingestion.parser.types import (
    CoverageAccounting,
    SourceLocator,
    TypedElement,
)


def element_id(
    content_hash: str,
    reading_order: int,
    kind: str,
    locator: SourceLocator,
    text: str | None,
) -> str:
    """Build a stable element identifier for one parse replay.

    Args:
        content_hash: SHA-256 of source bytes.
        reading_order: Zero-based reading order index.
        kind: Element kind string.
        locator: Format-specific locator model.
        text: Optional element text.

    Returns:
        Deterministic lowercase hex identifier.
    """

    payload = f"{content_hash}|{reading_order}|{kind}|{locator.model_dump_json()}|{text or ''}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]


def build_coverage(
    elements: tuple[TypedElement, ...], removed: int = 0
) -> CoverageAccounting:
    """Compute coverage accounting from emitted elements.

    Args:
        elements: Typed elements in reading order.
        removed: Count of removed boilerplate/header nodes.

    Returns:
        Coverage metrics with char coverage ratio.
    """

    text_elements = [
        element for element in elements if element.text and element.text.strip()
    ]
    media_only = [element for element in elements if element.media_only]
    unsupported = [
        element
        for element in elements
        if element.metadata.get("unsupported_region") is True
    ]
    total_chars = sum(len(element.text or "") for element in text_elements)
    source_chars = max(total_chars, 1)
    return CoverageAccounting(
        total_elements=len(elements),
        text_elements=len(text_elements),
        media_only_elements=len(media_only),
        removed_nodes=removed,
        unsupported_regions=len(unsupported),
        char_coverage_ratio=min(1.0, total_chars / source_chars),
    )


def namespace_seed(content_hash: str) -> uuid.UUID:
    """Derive a deterministic UUID namespace from content hash."""

    return uuid.UUID(hex=content_hash[:32])
