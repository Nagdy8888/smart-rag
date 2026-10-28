"""Offline regressions from recorded Web failures; never sends provider calls."""

from __future__ import annotations

import pytest
from smart_rag_core.query_routing.knowledge_scope import (
    KnowledgeScope,
    classify_knowledge_scope,
)
from smart_rag_core.query_routing.knowledge_scope_preference import (
    apply_requested_search_scope,
)
from smart_rag_core.search_scope import RequestedSearchScope
from smart_rag_core.web_research.excerpt_window import query_excerpt_window


@pytest.mark.parametrize(
    "question",
    [
        "Compare target-size criteria and their conformance levels. Cite the standards body.",
        "Compare phantom-read behavior under two isolation levels using the official table.",
    ],
)
def test_public_comparison_does_not_imply_company_data(question: str) -> None:
    """Explicit public comparisons honor Web instead of entering a Hybrid branch."""
    result = apply_requested_search_scope(
        question, classify_knowledge_scope(question), RequestedSearchScope.WEB
    )
    assert result.knowledge_scope is KnowledgeScope.WEB
    assert result.company_signal is False


@pytest.mark.parametrize(
    "question",
    [
        "Compare those policies using the official table.",
        "Compare our salary bands. Cite the official policy.",
        "Compare the uploaded documents using official sources.",
        "Compare this to http://127.0.0.1/private using official documentation.",
        "Compare Bearer private-credential using official documentation.",
    ],
)
def test_comparison_keeps_private_reference_guard(question: str) -> None:
    """A presentation request cannot authorize exporting company or private inputs."""
    result = apply_requested_search_scope(
        question, classify_knowledge_scope(question), RequestedSearchScope.WEB
    )
    assert result.knowledge_scope is not KnowledgeScope.WEB


def test_fitting_keeps_relevant_evidence_beyond_the_page_prefix() -> None:
    """A long page's decisive passage survives while canonical text stays exact."""
    rule = "429 responses MUST NOT be stored by a cache."
    text = "Navigation header. " * 300 + rule + " More 429 cache notes." * 100
    window = query_excerpt_window(text, "Can 429 responses be stored by a cache?", 2000)
    assert len(window) == 2000
    assert window in text
    assert rule in window
    assert rule not in text[:2000]


def test_fitting_without_query_anchors_preserves_prefix() -> None:
    """No invented relevance score changes an anchor-free excerpt."""
    assert query_excerpt_window("abcdef", "?", 3) == "abc"


def test_search_translation_does_not_replace_answer_language(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A translated discovery query cannot replace the original synthesis request."""
    from collections.abc import Callable
    from types import SimpleNamespace
    from unittest.mock import Mock

    from smart_rag_agents.query.deps import QueryGraphDeps
    from smart_rag_agents.query.nodes.web_scope import web_scope_node
    from smart_rag_agents.query.state import pending_query_state
    from smart_rag_core.gateways.exa_search import ExaSearchGateway
    from smart_rag_core.query_answer.models import AnswerPayload
    from smart_rag_core.web_research.models import WebSourceRecord

    from tests.support.query_runtime import authorized_runtime

    original = "اشرح بالعربية معنى رمز HTTP 429."
    rewrite = "Explain the meaning of HTTP 429."
    state = pending_query_state(
        authorized_runtime().model_dump(mode="json"), user_query=original
    )
    state["preparation"] = {"rewrite": rewrite}
    answer = AnswerPayload(answer_text="إجابة عربية", answer_origin=KnowledgeScope.WEB)
    counted = Mock(return_value=answer)

    def research(
        *,
        user_query: str,
        synthesize: Callable[[str, tuple[WebSourceRecord, ...]], AnswerPayload],
        **_kwargs: object,
    ) -> SimpleNamespace:
        """Keep discovery in English while exercising the real synthesis closure."""
        assert user_query == rewrite
        return SimpleNamespace(answer=synthesize(user_query, ()), sources=())

    monkeypatch.setattr(
        "smart_rag_agents.query.nodes.web_scope.run_web_research", research
    )
    monkeypatch.setattr(
        "smart_rag_agents.query.nodes.web_scope.counted_web_answer", counted
    )
    web_scope_node(
        state,
        QueryGraphDeps(
            connection=Mock(),
            model_gateway=Mock(),
            web_answer_prompt_text="Evidence only",
            web_search_enabled=True,
            web_search_configured=True,
            exa_search_gateway=Mock(spec=ExaSearchGateway),
        ),
    )
    counted.assert_called_once()
    assert counted.call_args.kwargs["query"] == original
