"""Shared provenance serialization helpers."""

from __future__ import annotations

from typing import Any

from smart_rag_core.ingestion.parser.types import SourceLocator


def locator_to_dict(locator: SourceLocator) -> dict[str, Any]:
    """Serialize one typed locator for provenance storage.

    Args:
        locator: Format-specific locator model.

    Returns:
        JSON-serializable locator dictionary.
    """

    return locator.model_dump(mode="json")


def attach_page_label(
    locator: dict[str, Any],
    page_labels: tuple[str, ...],
) -> dict[str, Any]:
    """Copy a printed PDF page label onto one serialized locator.

    Args:
        locator: One ``locator_to_dict`` payload.
        page_labels: Labels aligned with zero-based ``page_index``.

    Returns:
        A copy of ``locator``. Sets ``page_label`` when the matching label is
        non-empty. Leaves non-PDF locators and unlabeled pages unchanged.
    """

    payload = dict(locator)
    raw_index = payload.get("page_index")
    if not isinstance(raw_index, int):
        return payload
    if raw_index < 0 or raw_index >= len(page_labels):
        return payload
    label = page_labels[raw_index].strip()
    if not label:
        return payload
    payload["page_label"] = label
    return payload
