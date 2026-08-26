"""Parse LangGraph 1.2.11 stream parts without guessing unknown shapes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, cast

KNOWN_STREAM_MODES: frozenset[str] = frozenset({"updates", "custom"})
V2_TYPE_KEY = "type"
V2_NS_KEY = "ns"
V2_DATA_KEY = "data"


@dataclass(frozen=True)
class ParsedStreamPart:
    """One recognized ``updates`` or ``custom`` stream part.

    Attributes:
        mode: Catalog-relevant stream mode.
        namespace: Subgraph namespace, empty for the parent graph.
        data: Mode payload. Shape is not guessed here.
    """

    mode: Literal["updates", "custom"]
    namespace: tuple[str, ...]
    data: object


def _namespace_from(raw: object) -> tuple[str, ...] | None:
    """Return a string namespace tuple, or None when the value is invalid.

    Args:
        raw: Candidate ``ns`` field or v1 subgraph prefix.

    Returns:
        Empty tuple for missing namespaces, a string tuple for valid lists,
        or None when the value cannot be a namespace.
    """

    if raw is None:
        return ()
    if isinstance(raw, (list, tuple)):
        items = [item for item in cast(list[object] | tuple[object, ...], raw)]
        if all(isinstance(item, str) for item in items):
            return tuple(cast(list[str], items))
        return None
    return None


def _as_known_mode(raw: object) -> Literal["updates", "custom"] | None:
    """Return a known progress mode, or None for every other label.

    Args:
        raw: Candidate stream-mode name.

    Returns:
        ``updates`` or ``custom`` only.
    """

    if raw == "updates" or raw == "custom":
        return raw
    return None


def _parse_v2_mapping(raw_chunk: dict[object, object]) -> ParsedStreamPart | None:
    """Parse a v2 ``{type, ns, data}`` mapping.

    Args:
        raw_chunk: Candidate StreamPart dict.

    Returns:
        Parsed part, or None when type/ns is not a known progress shape.
    """

    mode = _as_known_mode(raw_chunk.get(V2_TYPE_KEY))
    if mode is None:
        return None
    if V2_DATA_KEY not in raw_chunk:
        return None
    namespace = _namespace_from(raw_chunk.get(V2_NS_KEY, ()))
    if namespace is None:
        return None
    return ParsedStreamPart(
        mode=mode,
        namespace=namespace,
        data=raw_chunk[V2_DATA_KEY],
    )


def _looks_like_v2_part(raw_chunk: dict[object, object]) -> bool:
    """Return whether a mapping uses the v2 StreamPart key set.

    Args:
        raw_chunk: Candidate dict.

    Returns:
        True when ``type`` is present so the mapping is not a legacy node
        update.
    """

    return V2_TYPE_KEY in raw_chunk


def _parse_v1_tuple(raw_chunk: tuple[object, ...]) -> ParsedStreamPart | None:
    """Parse a v1 multi-mode or subgraph tuple.

    Args:
        raw_chunk: ``(mode, data)`` or ``(ns, (mode, data))``.

    Returns:
        Parsed part, or None when the tuple is not a known progress shape.
    """

    if len(raw_chunk) != 2:
        return None
    head, tail = raw_chunk[0], raw_chunk[1]
    mode = _as_known_mode(head)
    if mode is not None:
        return ParsedStreamPart(mode=mode, namespace=(), data=tail)
    namespace = _namespace_from(head)
    if namespace is None:
        return None
    if isinstance(tail, tuple):
        inner = cast(tuple[object, ...], tail)
        if len(inner) != 2:
            return None
        inner_mode = _as_known_mode(inner[0])
        if inner_mode is None:
            return None
        return ParsedStreamPart(
            mode=inner_mode,
            namespace=namespace,
            data=inner[1],
        )
    if isinstance(tail, dict):
        return ParsedStreamPart(mode="updates", namespace=namespace, data=tail)
    return None


def parse_stream_part(raw_chunk: object) -> ParsedStreamPart | None:
    """Normalize one LangGraph stream chunk into a typed progress part.

    Supported shapes:

    * v2 ``{"type": "updates"|"custom", "ns": (...), "data": ...}``
    * v1 multi-mode ``("updates"|"custom", data)``
    * v1 subgraph ``(ns, (mode, data))`` or ``(ns, mapping)``
    * legacy raw node mapping treated as updates-only

    Unknown modes and shapes return None. They are never guessed as updates.

    Args:
        raw_chunk: One ``stream`` / ``astream`` item.

    Returns:
        Parsed part, or None when the chunk is not a known progress shape.
    """

    if isinstance(raw_chunk, dict):
        typed = cast(dict[object, object], raw_chunk)
        if _looks_like_v2_part(typed):
            return _parse_v2_mapping(typed)
        return ParsedStreamPart(mode="updates", namespace=(), data=typed)
    if isinstance(raw_chunk, tuple):
        return _parse_v1_tuple(cast(tuple[object, ...], raw_chunk))
    return None


def updates_mapping_from_part(
    part: ParsedStreamPart,
) -> dict[str, object] | None:
    """Return the node-keyed updates mapping from one parsed part.

    Args:
        part: Parsed stream part.

    Returns:
        String-keyed mapping, or None when the part is not updates data.
    """

    if part.mode != "updates" or not isinstance(part.data, dict):
        return None
    return {
        str(key): value
        for key, value in cast(dict[object, object], part.data).items()
    }


def custom_mapping_from_part(
    part: ParsedStreamPart,
) -> dict[str, object] | None:
    """Return the custom writer mapping from one parsed part.

    Args:
        part: Parsed stream part.

    Returns:
        String-keyed mapping, or None when the part is not custom data.
    """

    if part.mode != "custom" or not isinstance(part.data, dict):
        return None
    return {
        str(key): value
        for key, value in cast(dict[object, object], part.data).items()
    }


def updates_mapping_from_chunk(raw_chunk: object) -> dict[str, object] | None:
    """Compatibility unwrap of one updates payload.

    Args:
        raw_chunk: v2 part, v1 tuple, or legacy node mapping.

    Returns:
        Node-keyed mapping, or None when the chunk is not updates data.
    """

    part = parse_stream_part(raw_chunk)
    if part is None:
        return None
    return updates_mapping_from_part(part)
