"""Non-negative token coercion and run-total accumulation."""

from __future__ import annotations

from smart_rag_agents.query.state import QueryGraphState


def nonneg_token_count(value: object) -> int:
    """Return a non-negative token count from a gateway field.

    Args:
        value: Untrusted attribute from a gateway response.

    Returns:
        Integer token count. Booleans and non-integers become 0.
    """

    if isinstance(value, bool) or not isinstance(value, int):
        return 0
    return max(0, value)


def tokens_from_gateway_response(response: object) -> tuple[int, int]:
    """Read provider prompt and completion tokens from a gateway response.

    Args:
        response: Gateway response with ``input_tokens`` / ``output_tokens``.

    Returns:
        Prompt tokens and completion tokens. Missing fields are 0.
    """

    return (
        nonneg_token_count(getattr(response, "input_tokens", 0)),
        nonneg_token_count(getattr(response, "output_tokens", 0)),
    )


def accumulated_tokens(
    state: QueryGraphState, prompt_tokens: int, completion_tokens: int
) -> dict[str, int]:
    """Add one model call's tokens onto the run totals.

    Args:
        state: Current graph state.
        prompt_tokens: Provider prompt tokens from this call.
        completion_tokens: Provider completion tokens from this call.

    Returns:
        Partial state update with accumulated totals.
    """

    return {
        "prompt_tokens": int(state.get("prompt_tokens") or 0) + max(0, prompt_tokens),
        "completion_tokens": int(state.get("completion_tokens") or 0)
        + max(0, completion_tokens),
    }
