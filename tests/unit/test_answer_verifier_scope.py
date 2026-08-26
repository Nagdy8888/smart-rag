"""Graph-inspection refusal versus greeting safe-chat behavior."""

from __future__ import annotations

from smart_rag_core.query_answer.deterministic import deterministic_check_answer
from smart_rag_core.query_answer.generate import generate_answer
from smart_rag_core.query_routing.knowledge_scope import KnowledgeScope

from tests.support.answer_verifier import (
    _fusion,
    _passage,
)


def test_graph_inspection_refuses_but_greeting_is_safe_chat() -> None:
    """Graph-only refuses while a greeting returns no company claim."""

    fusion = _fusion(_passage(1, text="secret"))
    graph_only = generate_answer(
        fusion=fusion,
        tables=(),
        user_query="inspect",
        caller=None,
        already_generated=0,
        company_claim_forbidden=False,
        graph_as_answer_forbidden=True,
    )
    assert graph_only.status == "refused"
    greeting = generate_answer(
        fusion=_fusion(),
        tables=(),
        user_query="hello",
        caller=None,
        already_generated=0,
        company_claim_forbidden=True,
        graph_as_answer_forbidden=False,
    )
    assert greeting.status == "complete"
    assert greeting.answer_origin is KnowledgeScope.GENERAL_KNOWLEDGE
    assert "uploaded documents" not in greeting.answer_text
    checked_greeting, greeting_failures = deterministic_check_answer(
        greeting,
        fusion=_fusion(),
        tables=(),
        evidence_required=False,
    )
    assert checked_greeting.status == "complete"
    assert greeting_failures == ()
    transform = generate_answer(
        fusion=_fusion(),
        tables=(),
        user_query="rewrite this paragraph: hello",
        caller=None,
        already_generated=0,
        company_claim_forbidden=True,
        graph_as_answer_forbidden=False,
    )
    assert transform.status == "complete"
    assert transform.citations == ()
    assert "hello" in transform.answer_text
