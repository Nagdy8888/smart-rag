"""Extractive salvage for exact-wording paraphrases on selected evidence."""

from __future__ import annotations

from smart_rag_core.query_answer.generate_grounded import (
    distinctive_query_names,
)


def test_book_title_tokens_are_not_query_name_anchors() -> None:
    """Prompts that name the book must not treat title words as anchors."""

    names = distinctive_query_names(
        "In the company document Building Applications with AI Agents, "
        "what exact phrase pairs Tempo with its role?"
    )
    assert "Tempo" in names
    assert "Building" not in names
    assert "Applications" not in names
    assert "Agents" not in names
