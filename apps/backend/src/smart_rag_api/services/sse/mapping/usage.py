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
    return ("usage", {"prompt_tokens": prompt, "completion_tokens": completion})
