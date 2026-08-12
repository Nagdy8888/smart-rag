"""HTTP correlation identifier validation for structured request logs."""

from __future__ import annotations

import re
from uuid import uuid4

_CORRELATION_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


def normalized_request_id(candidate: str | None) -> str:
    """Return a safe caller ID or generate a new request identifier.

    Args:
        candidate: Optional ``X-Request-ID`` header value.

    Returns:
        The validated caller value, or a generated hexadecimal UUID when the
        value is absent or unsafe for logs.

    Side Effects:
        Uses the operating system UUID entropy source when generating an ID.
    """

    if candidate is not None and _CORRELATION_ID_PATTERN.fullmatch(candidate):
        return candidate
    return uuid4().hex
