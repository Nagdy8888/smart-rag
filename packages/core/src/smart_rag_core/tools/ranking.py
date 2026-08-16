"""Lexical catalog ranking. Embedding rankers are optional and injectable."""

from __future__ import annotations

from collections.abc import Callable, Sequence

from smart_rag_core.tools.models import ToolDefinition

Embedder = Callable[[str], tuple[float, ...]]


def _tokens(text: str) -> frozenset[str]:
    """Split text into lowercase alphanumeric tokens.

    Args:
        text: Untrusted query or catalog field.

    Returns:
        Token set.
    """

    cleaned = "".join(ch.lower() if ch.isalnum() else " " for ch in text)
    return frozenset(part for part in cleaned.split() if part)


def lexical_score(query: str, tool: ToolDefinition) -> float:
    """Score one tool against a query using token overlap.

    Args:
        query: Untrusted user text.
        tool: Visible catalog definition.

    Returns:
        Non-negative overlap score. Higher is better.
    """

    query_tokens = _tokens(query)
    if not query_tokens:
        return 0.0
    haystack = _tokens(
        " ".join(
            (
                tool.tool_key,
                tool.short_name,
                tool.one_line_purpose,
                tool.description,
                " ".join(tool.tags),
                " ".join(tool.capabilities),
            )
        )
    )
    overlap = query_tokens.intersection(haystack)
    return float(len(overlap))


def _cosine(left: Sequence[float], right: Sequence[float]) -> float:
    """Return cosine similarity, or 0 when a vector is empty.

    Args:
        left: Query embedding.
        right: Tool embedding.

    Returns:
        Similarity in ``[-1, 1]``, or 0 when undefined.
    """

    if not left or not right or len(left) != len(right):
        return 0.0
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    n_left = sum(a * a for a in left) ** 0.5
    n_right = sum(b * b for b in right) ** 0.5
    if n_left == 0.0 or n_right == 0.0:
        return 0.0
    return dot / (n_left * n_right)


def rank_tools(
    query: str,
    tools: tuple[ToolDefinition, ...],
    *,
    embedder: Embedder | None = None,
    limit: int,
) -> tuple[ToolDefinition, ...]:
    """Rank visible tools by lexical score, optionally plus embeddings.

    Args:
        query: Untrusted user text.
        tools: Already permission-filtered tools.
        embedder: Optional embedding function. Must not call a catalog LLM.
        limit: Maximum tools to return.

    Returns:
        Top tools in descending score order.
    """

    query_vec = embedder(query) if embedder is not None else None
    scored: list[tuple[float, int, ToolDefinition]] = []
    for index, tool in enumerate(tools):
        score = lexical_score(query, tool)
        if query_vec is not None and embedder is not None:
            tool_text = f"{tool.tool_key} {tool.one_line_purpose} {' '.join(tool.tags)}"
            score += _cosine(query_vec, embedder(tool_text))
        scored.append((score, index, tool))
    scored.sort(key=lambda item: (-item[0], item[1]))
    return tuple(item[2] for item in scored[: max(0, limit)])
