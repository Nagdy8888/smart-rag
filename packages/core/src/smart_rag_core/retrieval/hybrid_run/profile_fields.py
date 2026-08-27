"""Typed ExpectedProfile field readers for Hybrid retrieve."""

from __future__ import annotations

from datetime import date

from smart_rag_core.evaluation.schema import ExpectedProfile, ProfileField, QueryType
from smart_rag_core.retrieval.temporal import TemporalIntent


def str_list_field(profile: ExpectedProfile | None, name: str) -> tuple[str, ...]:
    """Read a list-or-string profile field.

    Args:
        profile: Optional typed profile.
        name: Attribute name on ``ExpectedProfile``.

    Returns:
        String values, or empty when missing.
    """

    field = _profile_field(profile, name)
    if field is None:
        return ()
    value = field.value
    if isinstance(value, list):
        return tuple(str(item) for item in value if str(item).strip())
    if isinstance(value, str) and value.strip():
        return (value,)
    return ()


def str_field(profile: ExpectedProfile | None, name: str) -> str | None:
    """Read a string profile field.

    Args:
        profile: Optional typed profile.
        name: Attribute name.

    Returns:
        String value or ``None``.
    """

    field = _profile_field(profile, name)
    if field is None:
        return None
    value = field.value
    if isinstance(value, str):
        return value
    return None


def bool_field(profile: ExpectedProfile | None, name: str) -> bool:
    """Read a boolean profile field.

    Args:
        profile: Optional typed profile.
        name: Attribute name.

    Returns:
        The boolean value, or ``False`` when missing.
    """

    field = _profile_field(profile, name)
    if field is None:
        return False
    value = field.value
    return bool(value) if isinstance(value, bool) else False


def _profile_field(profile: ExpectedProfile | None, name: str) -> ProfileField | None:
    """Return a named ``ProfileField`` from the typed profile.

    Args:
        profile: Optional typed profile.
        name: Attribute name on ``ExpectedProfile``.

    Returns:
        The field when present, otherwise ``None``.
    """

    if profile is None:
        return None
    raw: object = getattr(profile, name, None)
    if isinstance(raw, ProfileField):
        return raw
    return None


def query_type_field(profile: ExpectedProfile | None) -> QueryType:
    """Parse an existing ``QueryType`` enum value without adding a map.

    Wave 1C owns QueryType mapping. This only accepts values already on
    ``QueryType``.

    Args:
        profile: Optional typed profile.

    Returns:
        Profile query type when it is a ``QueryType`` member, else ``factual``.
    """

    raw = str_field(profile, "query_type")
    if raw is None:
        return QueryType.FACTUAL
    try:
        return QueryType(raw)
    except ValueError:
        return QueryType.FACTUAL


def temporal_intent_field(profile: ExpectedProfile | None) -> TemporalIntent:
    """Parse an allow-listed temporal intent from the profile.

    Args:
        profile: Optional typed profile.

    Returns:
        Matching ``TemporalIntent``, or ``none``.
    """

    raw = str_field(profile, "temporal_intent")
    if raw is None:
        return TemporalIntent.NONE
    try:
        return TemporalIntent(raw)
    except ValueError:
        return TemporalIntent.NONE


def target_date_field(profile: ExpectedProfile | None) -> date | None:
    """Parse an ISO ``YYYY-MM-DD`` target date when present.

    Args:
        profile: Optional typed profile.

    Returns:
        UTC calendar date, or ``None``.
    """

    raw = str_field(profile, "target_date")
    if raw is None:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None
