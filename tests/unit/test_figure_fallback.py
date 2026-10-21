"""Exact source recovery for explicit numbered-diagram refusals."""

from __future__ import annotations

import pytest
from smart_rag_agents.query.nodes.verify_release import company_release_payload
from smart_rag_core.query_answer.figure_fallback import salvage_named_figure
from smart_rag_core.query_answer.models import AnswerPayload
from smart_rag_core.query_fusion.models import FusionResult
from smart_rag_core.query_routing.knowledge_scope import KnowledgeScope

from tests.support.answer_verifier import verifier_fusion, verifier_passage

QUERY = "Include Figure 7-3 and explain semantic widget retrieval."
PROSE = (
    "Semantic widget retrieval indexes every widget description as a vector. "
    "Figure 7-3 illustrates embedding widgets for retrieval from the index."
)


def fixture_evidence() -> FusionResult:
    """Create one authorized same-version paragraph and diagram."""
    source = verifier_passage(70, text=PROSE)
    figure = verifier_passage(
        71, text="Figure 7-3. Semantic widget retrieval."
    ).model_copy(
        update={
            "content_kind": "figure",
            "figure_id": "a" * 32,
            "version_id": source.version_id,
        }
    )
    return verifier_fusion(source, figure)


def test_refusal_recovers_only_exact_sources_and_stays_partial() -> None:
    """A rejected generated conclusion is replaced by literal authorized source text."""
    payload = AnswerPayload(
        answer_text="Insufficient authorized evidence.",
        status="refused",
        answer_origin=KnowledgeScope.COMPANY_DOCUMENTS,
        refused_links=("rejected",),
    )
    fusion = fixture_evidence()
    result = company_release_payload(
        payload, fusion=fusion, tables=(), user_query=QUERY
    )
    assert PROSE in result.answer_text
    assert "[[figure:" + "a" * 32 + "]]" in result.answer_text
    assert result.status == "partial"
    assert len(result.citations) == 2
    assert result.composed_conclusion is None
    for citation in result.citations:
        source = next(x for x in fusion.evidence if x.chunk_id == citation.chunk_id)
        assert citation.span is not None and citation.span in source.citation_text
    assert salvage_named_figure(result, fusion, user_query=QUERY) == result


@pytest.mark.parametrize(
    "change",
    [
        "wrong_label",
        "different_version",
        "no_prose",
        "ambiguous",
        "no_topic",
        "too_long",
    ],
)
def test_inadequate_or_ambiguous_evidence_keeps_refusal(change: str) -> None:
    """Number, version, uniqueness, topical support, and size are all required."""
    fusion = fixture_evidence()
    source, figure = fusion.evidence
    if change == "wrong_label":
        figure = figure.model_copy(update={"citation_text": "Figure 7-4. Widgets."})
    elif change == "different_version":
        source = source.model_copy(update={"version_id": "other"})
    elif change == "no_prose":
        source = source.model_copy(update={"citation_text": ""})
    elif change == "no_topic":
        source = source.model_copy(
            update={"citation_text": "Figure 7-3 shows a landscape. " * 4}
        )
    elif change == "too_long":
        figure = figure.model_copy(
            update={"citation_text": figure.citation_text + "x" * 1000}
        )
    evidence = (source, figure)
    if change == "ambiguous":
        evidence += (
            figure.model_copy(update={"chunk_id": "different", "figure_id": "b" * 32}),
        )
    fusion = fusion.model_copy(update={"evidence": evidence})
    payload = AnswerPayload(answer_text="No evidence.", status="refused")
    assert salvage_named_figure(payload, fusion, user_query=QUERY) == payload


def test_nonempty_checked_answer_is_never_replaced() -> None:
    """Recovery does not overwrite existing checked claims."""
    payload = AnswerPayload(answer_text="Existing answer.", status="complete")
    assert (
        salvage_named_figure(payload, fixture_evidence(), user_query=QUERY) == payload
    )
