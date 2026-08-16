"""Compare client versions against ``min_client_version`` before paid work."""

from __future__ import annotations

import re

_SEMVER = re.compile(r"^(\d+)\.(\d+)\.(\d+)(?:[-+].*)?$")


def parse_semver_tuple(value: str) -> tuple[int, int, int] | None:
    """Parse a semver-like ``major.minor.patch`` string.

    Args:
        value: Client or configured version.

    Returns:
        Integer triple, or None when the value is not comparable.
    """

    match = _SEMVER.fullmatch(value.strip())
    if match is None:
        return None
    return int(match.group(1)), int(match.group(2)), int(match.group(3))


def client_version_is_supported(client_version: str | None, minimum: str) -> bool:
    """Return whether ``client_version`` meets ``minimum``.

    Missing, empty, or unparsable versions are unsupported.

    Args:
        client_version: ``X-Client-Version`` header value.
        minimum: ``BackendSettings.min_client_version``.

    Returns:
        True only when both parse and client >= minimum.
    """

    if client_version is None or not client_version.strip():
        return False
    parsed = parse_semver_tuple(client_version)
    minimum_parsed = parse_semver_tuple(minimum)
    if parsed is None or minimum_parsed is None:
        return False
    return parsed >= minimum_parsed
