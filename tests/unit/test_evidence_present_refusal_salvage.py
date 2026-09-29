"""Refusal salvage when selected evidence already holds answer literals."""

from __future__ import annotations

from smart_rag_core.query_answer.generate_grounded import (
    distinctive_query_literals,
    generate_grounded_answer,
    salvage_refused_literal_claims,
    significant_query_terms,
)
from smart_rag_core.query_answer.models import AnswerPayload
from smart_rag_core.query_answer.release import render_verified_company_answer
from smart_rag_core.query_routing.knowledge_scope import KnowledgeScope

from tests.support.answer_verifier import verifier_fusion, verifier_passage

H23_QUERY = (
    "In the company document Building Applications with AI Agents, "
    "How many tokens do Gemini 2.5 and GPT-4.1 support in the dynamic-graph "
    "section, and about how many words is that?"
)
H23_EVIDENCE = (
    "Gemini 2.5 and GPT-4.1 support one million tokens in the dynamic-graph "
    "section, about 750,000 words of context."
)
H35_QUERY = (
    "What Redis port and stream name does the supervisor publish tasks to?"
)
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


def test_salvage_refused_when_gold_phrases_are_in_selected_evidence() -> None:
    """Model refusal with gold phrases in fusion becomes a grounded answer."""

    fusion = verifier_fusion(verifier_passage(1, text=H23_EVIDENCE))
    salvaged = salvage_refused_literal_claims(fusion, user_query=H23_QUERY)
    assert salvaged is not None
    assert salvaged.status == "complete"
    assert salvaged.atomic_links
    assert "one million tokens" in salvaged.answer_text
    released = render_verified_company_answer(
        salvaged, fusion=fusion, tables=()
    )
    assert released.status != "refused"
    assert released.answer_text != "Insufficient authorized evidence."
    assert released.citations


def test_generate_grounded_salvages_empty_model_refusal() -> None:
    """generate_grounded_answer replaces an empty refused payload from the caller."""

    fusion = verifier_fusion(verifier_passage(1, text=H35_EVIDENCE))

    def _refuse(
        _records: str,
        _fusion: object,
        _tables: object,
    ) -> AnswerPayload:
        """Return a citation-free model refusal.

        Args:
            _records: Unused assembled records.
            _fusion: Unused fusion.
            _tables: Unused tables.

        Returns:
            Refused payload with no claims.
        """

        return AnswerPayload(
            answer_text="Insufficient authorized evidence.",
            status="refused",
            answer_origin=KnowledgeScope.COMPANY_DOCUMENTS,
        )

    payload = generate_grounded_answer(
        fusion=fusion,
        tables=(),
        user_query=H35_QUERY,
        caller=_refuse,
    )
    assert payload.status == "complete"
    assert payload.atomic_links
    assert "6379" in payload.answer_text or "supply-chain-tasks" in payload.answer_text
    released = render_verified_company_answer(payload, fusion=fusion, tables=())
    assert released.status != "refused"
    assert "Insufficient authorized evidence." not in released.answer_text
