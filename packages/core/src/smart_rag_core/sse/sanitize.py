"""Strip secrets, source HTML, passages, and exception text from SSE payloads."""

from __future__ import annotations

from collections.abc import Mapping
from typing import cast

from pydantic import ValidationError

from smart_rag_core.security.untrusted import isolate_untrusted_text
from smart_rag_core.sse.catalog import (
    ALLOWED_SSE_EVENT_TYPES,
    FORBIDDEN_PAYLOAD_KEYS,
    PAYLOAD_MODELS,
)

_SANITIZED_ERROR_CODE = "run_failed"


def as_json_object(value: object) -> dict[str, object]:
    """Narrow a JSON-like mapping to a string-keyed object.

    Args:
        value: Decoded JSON value.

    Returns:
        String-keyed mapping. Non-dicts become empty.
    """

    if not isinstance(value, dict):
        return {}
    mapped: dict[str, object] = {}
    for key, item in cast(dict[object, object], value).items():
        mapped[str(key)] = item
    return mapped


def _is_forbidden_key(key: str) -> bool:
    """Return whether a payload key is forbidden on the wire or in storage.

    Args:
        key: JSON object key.

    Returns:
        True when the key must be dropped.
    """

    lowered = key.lower()
    if lowered in FORBIDDEN_PAYLOAD_KEYS:
        return True
    return any(part in lowered for part in ("passage", "snippet", "traceback", "html"))


def strip_forbidden_payload(payload: Mapping[str, object]) -> dict[str, object]:
    """Recursively drop forbidden keys and escape remaining strings.

    Args:
        payload: Untrusted mapping.

    Returns:
        A new mapping safe to persist. Nested mappings are stripped. Lists
        keep only JSON-safe scalars and stripped mappings.
    """

    cleaned: dict[str, object] = {}
    for key, value in payload.items():
        if _is_forbidden_key(str(key)):
            continue
        if isinstance(value, dict):
            cleaned[str(key)] = strip_forbidden_payload(
                as_json_object(cast(object, value))
            )
            continue
        if isinstance(value, list):
            cleaned[str(key)] = [
                _sanitize_list_item(item) for item in cast(list[object], value)
            ]
            continue
        if isinstance(value, str):
            cleaned[str(key)] = isolate_untrusted_text(value)
            continue
        cleaned[str(key)] = value
    return cleaned


def _sanitize_list_item(item: object) -> object:
    """Sanitize one JSON array element.

    Args:
        item: Array value.

    Returns:
        Escaped string, stripped mapping, or the original scalar.
    """

    if isinstance(item, dict):
        return strip_forbidden_payload(as_json_object(cast(object, item)))
    if isinstance(item, str):
        return isolate_untrusted_text(item)
    return item


def sanitize_error_payload(_exc: BaseException | None = None) -> dict[str, object]:
    """Return a generic error payload. Exception text is discarded.

    Args:
        _exc: Optional exception. Message, traceback, and type details are
            never copied into the payload.

    Returns:
        ``{"code": "run_failed"}``.
    """

    del _exc
    return {"code": _SANITIZED_ERROR_CODE}


def validate_sse_payload(
    event_type: str, payload: Mapping[str, object]
) -> dict[str, object]:
    """Strip forbidden keys then validate against the extra=forbid model.

    Args:
        event_type: Allow-listed event name.
        payload: Candidate payload.

    Returns:
        Model dump suitable for JSON persistence.

    Raises:
        ValueError: When the event type is unknown or the payload fails
            extra=forbid validation after stripping.
    """

    if event_type not in ALLOWED_SSE_EVENT_TYPES:
        raise ValueError("sse_event_type_unknown")
    stripped = strip_forbidden_payload(payload)
    model = PAYLOAD_MODELS[event_type]
    try:
        parsed = model.model_validate(stripped)
    except ValidationError as exc:
        raise ValueError("sse_payload_invalid") from exc
    dumped = parsed.model_dump(mode="json")
    return as_json_object(dumped)
