"""Normalize LangGraph stream chunks and token fields once."""

from __future__ import annotations

from collections.abc import Mapping
from typing import cast

STREAM_MODE_NAMES = frozenset({"updates", "values", "messages", "debug"})


def coerce_stream_token_count(value: object) -> int | None:
    """Return a non-negative token count from a node or SSE field.

    Args:
        value: Graph or catalog token field.

    Returns:
        Integer count, or None when the value is missing or invalid.
    """

    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value >= 0 else None
    if isinstance(value, float) and value.is_integer() and value >= 0:
        return int(value)
    return None


def updates_mapping_from_chunk(raw_chunk: object) -> dict[str, object] | None:
    """Unwrap one LangGraph ``astream`` updates payload.

    Args:
        raw_chunk: Dict ``{node: update}`` or ``(stream_mode, payload)``.

    Returns:
        Node-keyed mapping, or None when the chunk is not updates data.
    """

    chunk: object = raw_chunk
    if isinstance(chunk, tuple):
        parts = [item for item in cast(tuple[object, ...], chunk)]
        if (
            len(parts) == 2
            and isinstance(parts[0], str)
            and parts[0] in STREAM_MODE_NAMES
        ):
            chunk = parts[1]
    if not isinstance(chunk, dict):
        return None
    return {str(key): value for key, value in cast(dict[object, object], chunk).items()}


def token_counts_from_update(
    typed_update: Mapping[str, object],
) -> tuple[int | None, int | None]:
    """Read prompt and completion totals from one node update.

    Args:
        typed_update: Node return mapping.

    Returns:
        ``(prompt_tokens, completion_tokens)`` with None for missing sides.
    """

    prompt = coerce_stream_token_count(typed_update.get("prompt_tokens"))
    if prompt is None:
        prompt = coerce_stream_token_count(typed_update.get("input_tokens"))
    completion = coerce_stream_token_count(typed_update.get("completion_tokens"))
    if completion is None:
        completion = coerce_stream_token_count(typed_update.get("output_tokens"))
    return prompt, completion
