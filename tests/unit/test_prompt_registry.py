"""Unknown prompt ids fail closed; every prompt has a version."""

from __future__ import annotations

import pytest
from smart_rag_agents.prompts.registry import (
    PROMPT_REGISTRY,
    PromptRegistryError,
    load_prompt,
    prompt_text,
)


def test_unknown_prompt_id_fails_closed() -> None:
    """Loading an unknown prompt id does not fall back to an unversioned body."""

    with pytest.raises(PromptRegistryError, match="unknown_prompt_id"):
        load_prompt("not_a_real_prompt_v9")
    with pytest.raises(PromptRegistryError, match="prompt_without_version"):
        load_prompt("")


def test_summary_v1_is_versioned_and_hashed() -> None:
    """The compact summary prompt is registered with sha256 and promotion."""

    entry = load_prompt("summary_v1", environment="dev")
    assert entry.prompt_id == "summary_v1"
    assert len(entry.sha256) == 64
    assert "source" in prompt_text("summary_v1")
    assert "passage" in prompt_text("summary_v1")
    assert frozenset(
        {
            "query_profile_v1",
            "summary_v1",
            "general_chat_v1",
            "conversation_title_v1",
            "eval_pdf_judge_v1",
        }
    ) <= frozenset(PROMPT_REGISTRY)
