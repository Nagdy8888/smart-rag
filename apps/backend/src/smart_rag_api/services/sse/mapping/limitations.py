"""Limitation mapping from verifier omissions and skipped verifier calls."""

from __future__ import annotations

from typing import cast

from smart_rag_core.query_routing.constants import (
    LIMITATION_VERIFIER_OMITTED_LINKS,
    LIMITATION_VERIFIER_SKIPPED,
)


def limitations_from_update(
    update: dict[str, object],
) -> list[tuple[str, dict[str, object]]]:
    """Return every signed limitation carried by a verify update.

    Args:
        update: Node return mapping.

    Returns:
        ``limitation`` events in emission order: omitted links first, then
        skipped verifier. Empty when the update carries none.
    """

    verification = update.get("verification")
    if not isinstance(verification, dict):
        return []
    typed_verification = cast(dict[object, object], verification)
    events: list[tuple[str, dict[str, object]]] = []
    if typed_verification.get("omitted_link_ids"):
        events.append(("limitation", {"code": LIMITATION_VERIFIER_OMITTED_LINKS}))
    if typed_verification.get("verifier_skipped_reason"):
        events.append(("limitation", {"code": LIMITATION_VERIFIER_SKIPPED}))
    return events


def limitation_from_update(
    update: dict[str, object],
) -> tuple[str, dict[str, object]] | None:
    """Return the first signed limitation, kept for existing callers.

    Args:
        update: Node return mapping.

    Returns:
        First ``limitation`` event or None.
    """

    events = limitations_from_update(update)
    return events[0] if events else None
