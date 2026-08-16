"""Shared helpers for deterministic parser output."""

from __future__ import annotations

import hashlib
import uuid
from collections.abc import Iterable
from typing import cast

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


def as_int(value: object) -> int:
    """Return ``int(value)`` for an untyped vendor scalar.

    Args:
        value: Vendor numeric value (int, float, or numeric string).

    Returns:
        The same integer conversion as ``int(value)`` for those scalars.

    Raises:
        TypeError: If ``value`` is not an int, float, or str.
        ValueError: If a string value is not a valid integer literal.
    """

    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        return int(value)
    raise TypeError(f"value is not convertible to int: {type(value).__name__}")


def as_float(value: object) -> float:
    """Return ``float(value)`` for an untyped vendor scalar.

    Args:
        value: Vendor numeric value (int, float, or numeric string).

    Returns:
        The same float conversion as ``float(value)`` for those scalars.

    Raises:
        TypeError: If ``value`` is not an int, float, or str.
        ValueError: If a string value is not a valid float literal.
    """

    if isinstance(value, bool):
        return float(value)
    if isinstance(value, int):
        return float(value)
    if isinstance(value, float):
        return value
    if isinstance(value, str):
        return float(value)
    raise TypeError(f"value is not convertible to float: {type(value).__name__}")


_VENDOR_ATTR_MISSING: object = object()


def vendor_attr(
    owner: object, name: str, default: object = _VENDOR_ATTR_MISSING
) -> object:
    """Return ``getattr(owner, name)`` with the same defaulting as builtins.

    Args:
        owner: Vendor module, document, page, or shape handle.
        name: Attribute name resolved at the call site.
        default: Optional fallback passed to ``getattr`` when not omitted.

    Returns:
        The attribute value, or ``default`` when provided and missing.
    """

    if default is _VENDOR_ATTR_MISSING:
        return getattr(owner, name)
    return getattr(owner, name, default)


def vendor_call(func: object, /, *args: object) -> object:
    """Invoke one vendor callable with the original positional arguments.

    Args:
        func: Vendor method or function.
        *args: Positional arguments forwarded unchanged.

    Returns:
        Opaque vendor result.

    Raises:
        TypeError: If ``func`` is not callable.
    """

    if not callable(func):
        raise TypeError("vendor callable is not callable")
    return func(*args)


def vendor_items(value: object) -> list[object]:
    """Return a vendor collection as a list of opaque items.

    Args:
        value: Iterable vendor payload such as a page body or PDF blocks list.

    Returns:
        The same items in list form.

    Raises:
        TypeError: If ``value`` is not iterable (excluding str/bytes).
    """

    if isinstance(value, list):
        return cast(list[object], value)
    if isinstance(value, tuple):
        return list(cast(tuple[object, ...], value))
    if isinstance(value, Iterable) and not isinstance(value, (str, bytes)):
        return list(cast(Iterable[object], value))
    raise TypeError(f"vendor collection is not iterable: {type(value).__name__}")
