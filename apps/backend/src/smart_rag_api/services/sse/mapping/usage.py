"""Usage-event mapping from accumulated graph token totals."""

from __future__ import annotations


def usage_event(
    update: dict[str, object],
) -> tuple[str, dict[str, object]] | None:
    """Build a catalog ``usage`` event from accumulated graph totals.

    Args:
        update: Node return mapping. Prompt and completion must be ints.

    Returns:
        ``usage`` event, or None when counts are missing or negative.
    """

    prompt = update.get("prompt_tokens")
    completion = update.get("completion_tokens")
    if isinstance(prompt, bool) or isinstance(completion, bool):
        return None
    if not isinstance(prompt, int) or not isinstance(completion, int):
        return None
    if prompt < 0 or completion < 0:
        return None
    payload: dict[str, object] = {
        "prompt_tokens": prompt,
        "completion_tokens": completion,
    }
    raw_cost = update.get("cost_usd")
    if isinstance(raw_cost, bool):
        raw_cost = None
    if isinstance(raw_cost, (int, float)) and raw_cost >= 0:
        payload["cost_usd"] = float(raw_cost)
    if isinstance(update.get("cost_reporting"), dict):
        payload["cost_reporting"] = update["cost_reporting"]
    return ("usage", payload)
