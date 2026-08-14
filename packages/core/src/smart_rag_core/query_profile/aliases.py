"""Approved-alias lookup for Packet 3 deterministic profiling.

The synthetic corpus uses ``orion-widget-NN`` aliases keyed by ``SKU-P4-*``.
Unknown aliases never become hard filters.
"""

from __future__ import annotations

import re

from smart_rag_core.text.arabic_normalize import normalize_arabic_v1

_SKU = re.compile(r"\bSKU-P4-[A-Z0-9]{3}\b")
_ORION_SURFACE = "orion widget"


def resolve_approved_aliases(query: str) -> tuple[str, ...]:
    """Resolve approved aliases that the query actually supports.

    Args:
        query: Original query text.

    Returns:
        Canonical alias identifiers. Empty when no approved surface matches.

    Side Effects:
        None. Does not load holdout labels.
    """

    normalized = normalize_arabic_v1(query)
    if _ORION_SURFACE not in normalized:
        return ()
    sku_match = _SKU.search(query.upper().replace("sku-p4", "SKU-P4"))
    if sku_match is None:
        sku_match = _SKU.search(query)
    if sku_match is None:
        return ()
    sku = sku_match.group(0)
    digits = sku[-2:]
    if not digits.isdigit():
        return ()
    return (f"orion-widget-{digits}",)
