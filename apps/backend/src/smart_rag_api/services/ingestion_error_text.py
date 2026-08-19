"""Sanitize operator-visible ingestion diagnostics for HTTP clients."""

from __future__ import annotations

import re

_SECRETISH = re.compile(
    r"(traceback|password=|secret|postgres(ql)?://|sk-[A-Za-z0-9]|begin |exception)",
    re.IGNORECASE,
)


def sanitize_ingestion_last_error(
    value: str | None,
    *,
    category: str | None = None,
) -> str | None:
    """Return a bounded last_error without stack traces or secret-like text.

    Args:
        value: Raw job ``last_error``.
        category: Optional machine-readable ``error_category`` used as fallback.

    Returns:
        Sanitized diagnostic, a category code, or ``None``.
    """

    if value is None:
        return None
    stripped = value.strip()
    if stripped == "":
        return None
    if _SECRETISH.search(stripped) or "\n" in stripped or len(stripped) > 240:
        fallback = (category or "ingestion_error").strip()
        return (fallback or "ingestion_error")[:64]
    return stripped[:240]
