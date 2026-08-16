"""Optional-intent detection from untrusted user text."""

from __future__ import annotations

from smart_rag_core.tools.models import OptionalIntent

_ADMIN_MARKERS: tuple[str, ...] = (
    "invite user",
    "change role",
    "adjust budget",
    "grant tool",
    "audit export",
)


def detect_optional_intent(query: str) -> OptionalIntent:
    """Map original user text onto a typed optional intent.

    Core Hybrid/LightRAG/table questions return ``NONE`` so the catalog is
    never consulted. Explicit CSV/XLSX export maps deterministically.
    Bare "export" without a format is ``AMBIGUOUS_EXPORT``.

    Args:
        query: Original user text. Untrusted.

    Returns:
        Typed optional intent. Never a core retrieve tool key.
    """

    lowered = query.strip().lower()
    if not lowered:
        return OptionalIntent.NONE
    if any(marker in lowered for marker in _ADMIN_MARKERS):
        return OptionalIntent.ADMINISTRATION
    exportish = "export" in lowered or "download" in lowered
    if not exportish:
        return OptionalIntent.NONE
    wants_csv = "csv" in lowered or ".csv" in lowered
    wants_xlsx = "xlsx" in lowered or "excel" in lowered or ".xlsx" in lowered
    if wants_csv and not wants_xlsx:
        return OptionalIntent.EXPORT_CSV
    if wants_xlsx and not wants_csv:
        return OptionalIntent.EXPORT_XLSX
    if wants_csv and wants_xlsx:
        return OptionalIntent.AMBIGUOUS_EXPORT
    return OptionalIntent.AMBIGUOUS_EXPORT
