"""Hard budgets rejected before optional-tool prompt construction."""

from __future__ import annotations

from smart_rag_core.tools.constants import (
    L1_CARD_MAX_BYTES,
    L2_MANIFEST_MAX_BYTES,
    L2_MANIFEST_MAX_TOKENS,
    L3_GUIDANCE_MAX_BYTES,
    L3_GUIDANCE_MAX_TOKENS,
    MAX_CONVERSATION_SUMMARY_TOKENS,
    MAX_MODEL_INPUT_TOKENS,
    MAX_PARENT_EXPANSION_IN_TOOL_PROMPT,
    MAX_RETRIEVAL_CHUNKS_IN_TOOL_PROMPT,
)
from smart_rag_core.tools.exceptions import ToolError
from smart_rag_core.tools.models import Level1Card, Level2Manifest, ToolDefinition


def count_tokens(text: str) -> int:
    """Count cl100k_base tokens for budget enforcement.

    Args:
        text: Candidate prompt or guidance.

    Returns:
        Token count.
    """

    import tiktoken

    encoding = tiktoken.get_encoding("cl100k_base")
    return len(encoding.encode(text))


def utf8_bytes(text: str) -> int:
    """Return UTF-8 byte length.

    Args:
        text: Candidate text.

    Returns:
        Byte count.
    """

    return len(text.encode("utf-8"))


def assert_card_budget(card: Level1Card) -> None:
    """Reject an oversized Level 1 card before prompt construction.

    Args:
        card: Visible card.

    Raises:
        ToolError: When the card exceeds ``L1_CARD_MAX_BYTES``.
    """

    payload = (
        f"{card.tool_key}|{card.short_name}|{card.one_line_purpose}|"
        f"{card.risk_class.value}|{card.required_role.value}"
    )
    if utf8_bytes(payload) > L1_CARD_MAX_BYTES:
        raise ToolError("oversized_card")


def assert_manifest_budget(manifest: Level2Manifest) -> None:
    """Reject an oversized Level 2 manifest before prompt construction.

    Args:
        manifest: Selected manifest.

    Raises:
        ToolError: When bytes or tokens exceed the Level 2 caps.
    """

    import json

    blob = json.dumps(manifest.model_dump(mode="json"), separators=(",", ":"))
    if utf8_bytes(blob) > L2_MANIFEST_MAX_BYTES:
        raise ToolError("oversized_manifest")
    if count_tokens(blob) > L2_MANIFEST_MAX_TOKENS:
        raise ToolError("oversized_manifest")


def assert_guidance_budget(tool: ToolDefinition) -> str:
    """Return bounded Level 3 guidance or reject it.

    Args:
        tool: Selected definition whose execution needs guidance.

    Returns:
        Guidance section that fits the Level 3 caps.

    Raises:
        ToolError: When guidance exceeds byte or token caps.
    """

    section = tool.long_guidance
    if utf8_bytes(section) > L3_GUIDANCE_MAX_BYTES:
        raise ToolError("oversized_guidance")
    if count_tokens(section) > L3_GUIDANCE_MAX_TOKENS:
        raise ToolError("oversized_guidance")
    return section


def assert_context_budgets(
    *,
    retrieval_chunks: int,
    parent_expansion: int,
    conversation_summary: str,
) -> None:
    """Reject over-limit retrieval, parent, or summary context.

    Args:
        retrieval_chunks: Chunk IDs proposed for the optional-tool prompt.
        parent_expansion: Parent passages proposed for the prompt.
        conversation_summary: Summary text proposed for the prompt.

    Raises:
        ToolError: When a context budget is exceeded.
    """

    if retrieval_chunks > MAX_RETRIEVAL_CHUNKS_IN_TOOL_PROMPT:
        raise ToolError("over_budget_model_input")
    if parent_expansion > MAX_PARENT_EXPANSION_IN_TOOL_PROMPT:
        raise ToolError("over_budget_model_input")
    if count_tokens(conversation_summary) > MAX_CONVERSATION_SUMMARY_TOKENS:
        raise ToolError("over_budget_model_input")


def assert_model_input_budget(prompt: str) -> None:
    """Reject a prompt that exceeds the total model-input token cap.

    Args:
        prompt: Fully assembled optional-tool prompt.

    Raises:
        ToolError: When token count exceeds ``MAX_MODEL_INPUT_TOKENS``.
    """

    if count_tokens(prompt) > MAX_MODEL_INPUT_TOKENS:
        raise ToolError("over_budget_model_input")
