"""One optional catalog discovery round. Core retrieve paths never call this."""

from __future__ import annotations

from smart_rag_core.security.identity import UserRole
from smart_rag_core.tools.catalog import default_registry
from smart_rag_core.tools.constants import L1_TOP_K, consume_remaining
from smart_rag_core.tools.disclosure import level0_payload, level1_cards
from smart_rag_core.tools.models import Level0Payload, Level1Payload, ToolDefinition
from smart_rag_core.tools.permissions import visible_tools
from smart_rag_core.tools.ranking import Embedder, lexical_score


def run_catalog_search(
    query: str,
    *,
    role: UserRole,
    remaining_discovery_rounds: int,
    registry: tuple[ToolDefinition, ...] | None = None,
    embedder: Embedder | None = None,
) -> tuple[Level0Payload, Level1Payload, int, int]:
    """Run the single catalog search round after role filtering.

    This function does not call a model. A later node may spend the one
    catalog LLM round to pick among the returned cards. Calling this twice
    with a remaining ceiling of 1 fails.

    Args:
        query: Untrusted user text.
        role: Live role.
        remaining_discovery_rounds: Remaining discovery slots.
        registry: Optional catalog.
        embedder: Optional embedding ranker.

    Returns:
        Level 0 payload, Level 1 cards, remaining discovery slots, and the
        visible searched count.

    Raises:
        ToolError: Second discovery, or a core-tool query that should not
            have entered catalog search.
    """

    remaining = consume_remaining(
        remaining_discovery_rounds, reason="discovery_exhausted"
    )
    catalog = registry if registry is not None else default_registry()
    visible = visible_tools(catalog, role=role)
    payload0 = level0_payload()
    payload1 = level1_cards(
        query,
        role=role,
        registry=catalog,
        embedder=embedder,
        top_k=L1_TOP_K,
    )
    return payload0, payload1, remaining, len(visible)


def select_from_cards(
    query: str, cards: Level1Payload, *, limit: int = 3
) -> tuple[str, ...]:
    """Deterministically pick up to ``limit`` card keys by lexical score.

    Used by the discovery comparison fixture as a stand-in for one catalog
    model round without spending OpenAI. Runtime still prefers mapping.

    Args:
        query: Untrusted user text.
        cards: Visible Level 1 cards.
        limit: Maximum keys, at most three.

    Returns:
        Selected tool keys in score order.
    """

    from smart_rag_core.tools.catalog import registry_by_key

    by_key = registry_by_key()
    scored: list[tuple[float, str]] = []
    for card in cards.cards:
        tool = by_key.get(card.tool_key)
        if tool is None:
            continue
        scored.append((lexical_score(query, tool), card.tool_key))
    scored.sort(key=lambda item: (-item[0], item[1]))
    return tuple(key for _score, key in scored[: max(0, min(limit, 3))])
