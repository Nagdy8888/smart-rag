"""Limitation mapping from verifier omissions."""

from __future__ import annotations

from typing import cast

from smart_rag_core.query_routing.constants import LIMITATION_VERIFIER_OMITTED_LINKS


def limitation_from_update(
    update: dict[str, object],
) -> tuple[str, dict[str, object]] | None:
    """Return a signed limitation when the verifier omitted links.

    Args:
        update: Node return mapping.

    Returns:
        ``limitation`` event or None.
    """

    verification = update.get("verification")
    if not isinstance(verification, dict):
        return None
    typed_verification = cast(dict[object, object], verification)
    omitted = typed_verification.get("omitted_link_ids")
    if omitted:
        return ("limitation", {"code": LIMITATION_VERIFIER_OMITTED_LINKS})
    return None
