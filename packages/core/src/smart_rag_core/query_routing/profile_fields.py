"""Helpers to flatten frozen ``ExpectedProfile`` fields."""

from __future__ import annotations

from smart_rag_core.evaluation.schema import ExpectedProfile, ProfileField


def profile_strings(field: ProfileField) -> tuple[str, ...]:
    """Return string items from one profile field.

    Args:
        field: Frozen profile field.

    Returns:
        A tuple of strings. Non-list values become a one-item tuple when set.
    """

    value = field.value
    if value is None:
        return ()
    if isinstance(value, list):
        return tuple(str(item) for item in value)
    if isinstance(value, bool):
        return ()
    return (str(value),)


def profile_bool(field: ProfileField) -> bool:
    """Return a boolean profile field.

    Args:
        field: Frozen profile field.

    Returns:
        The boolean value, or False when missing.
    """

    return field.value is True


def profile_str(field: ProfileField, default: str = "none") -> str:
    """Return a string profile field.

    Args:
        field: Frozen profile field.
        default: Fallback when the value is empty.

    Returns:
        String value or ``default``.
    """

    value = field.value
    if value is None or value == "":
        return default
    if isinstance(value, list):
        return str(value[0]) if value else default
    return str(value)


def keyword_tuple(profile: ExpectedProfile, name: str) -> tuple[str, ...]:
    """Return non-empty keywords from ``hl_keywords`` or ``ll_keywords``.

    Args:
        profile: Frozen expected profile.
        name: Field name.

    Returns:
        Stripped non-empty keyword strings.
    """

    field = getattr(profile, name)
    if not isinstance(field, ProfileField):
        return ()
    return tuple(item.strip() for item in profile_strings(field) if item.strip())
