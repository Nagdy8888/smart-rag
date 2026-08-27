"""Dispatch LangGraph v2 stream parts to the decomposed SSE mapper."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, cast

from smart_rag_api.services.sse.stream_parts import (
    custom_mapping_from_part,
    parse_stream_part,
    updates_mapping_from_part,
)

if TYPE_CHECKING:
    from smart_rag_api.services.query_sse_mapping import QuerySseMapper

PRODUCTION_STREAM_MODE: Final[list[str]] = ["updates", "custom"]
PRODUCTION_STREAM_VERSION: Final[str] = "v2"


def production_astream_options() -> dict[str, object]:
    """Return the production ``astream`` mode and version.

    Returns:
        Keyword arguments for compiled ``astream``.
    """

    return {
        "stream_mode": list(PRODUCTION_STREAM_MODE),
        "version": PRODUCTION_STREAM_VERSION,
    }


@dataclass(frozen=True)
class DispatchedStreamPart:
    """Mapper drafts and node updates from one stream part.

    Attributes:
        drafts: Catalog SSE drafts to persist one at a time.
        node_updates: Update mappings used only for token/status counters.
    """

    drafts: tuple[tuple[str, dict[str, object]], ...]
    node_updates: tuple[dict[str, object], ...]


def dispatch_stream_part(
    raw_chunk: object,
    mapper: QuerySseMapper,
) -> DispatchedStreamPart:
    """Parse one stream part and map it to catalog drafts.

    Custom parts call ``consume_custom``. Updates parts call
    ``consume_chunk``. Unknown shapes are dropped.

    Args:
        raw_chunk: One ``astream`` item.
        mapper: Per-run mapper that owns first-terminal-wins.

    Returns:
        Drafts plus node updates for counter maintenance.
    """

    part = parse_stream_part(raw_chunk)
    if part is None:
        return DispatchedStreamPart(drafts=(), node_updates=())
    if part.mode == "custom":
        mapping = custom_mapping_from_part(part)
        drafts = mapper.consume_custom(mapping if mapping is not None else part.data)
        return DispatchedStreamPart(drafts=tuple(drafts), node_updates=())
    updates = updates_mapping_from_part(part)
    if updates is None:
        return DispatchedStreamPart(drafts=(), node_updates=())
    node_updates: list[dict[str, object]] = []
    for raw_update in updates.values():
        if isinstance(raw_update, dict):
            node_updates.append(
                {
                    str(key): value
                    for key, value in cast(dict[object, object], raw_update).items()
                }
            )
    drafts = mapper.consume_chunk(updates)
    return DispatchedStreamPart(
        drafts=tuple(drafts),
        node_updates=tuple(node_updates),
    )
