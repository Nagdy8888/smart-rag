"""Refusal salvage when selected evidence already holds answer literals."""

from __future__ import annotations

from smart_rag_core.query_answer.generate_grounded import (
    distinctive_query_literals,
    significant_query_terms,
)

H23_QUERY = (
    "In the company document Building Applications with AI Agents, "
    "How many tokens do Gemini 2.5 and GPT-4.1 support in the dynamic-graph "
    "section, and about how many words is that?"
)
H23_EVIDENCE = (
    "Gemini 2.5 and GPT-4.1 support one million tokens in the dynamic-graph "
    "section, about 750,000 words of context."
)
H35_QUERY = "What Redis port and stream name does the supervisor publish tasks to?"
H35_EVIDENCE = (
    "The supervisor publishes tasks to Redis on port 6379 using the "
    "supply-chain-tasks stream."
)


def test_distinctive_literals_and_terms_from_hard_asks() -> None:
    """Hard50-shaped asks expose numerals and content tokens for salvage."""

    assert "2.5" in distinctive_query_literals(H23_QUERY)
    assert "4.1" in distinctive_query_literals(H23_QUERY)
    terms = significant_query_terms(H35_QUERY)
    assert "redis" in terms
    assert "supervisor" in terms
