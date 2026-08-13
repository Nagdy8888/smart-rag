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
