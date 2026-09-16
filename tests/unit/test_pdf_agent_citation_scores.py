"""PDF paragraph citation scoring uses leaves and toolbar pages, not labels."""

from __future__ import annotations

from uuid import UUID

from smart_rag_core.evaluation.private_pdf.agent_scores import (
    citation_precision,
    paragraph_completeness,
    pdf_locator_ok,
    resolved_citation_ids,
    score_agent_case,
)

_LEAF = UUID("11111111-1111-4111-8111-111111111111")
_RETRIEVED = UUID("22222222-2222-4222-8222-222222222222")
_FORBIDDEN = UUID("33333333-3333-4333-8333-333333333333")


def test_resolved_ids_ignore_retrieved_occupancy() -> None:
    """Retrieved IDs that were not cited never become citation scores."""

    cited = resolved_citation_ids((_LEAF,), (_LEAF, _RETRIEVED))
    assert cited == (_LEAF,)
    assert citation_precision((_RETRIEVED,), (_LEAF,)) == 0.0
    assert citation_precision(cited, (_LEAF,)) == 1.0


def test_pdf_locator_ok_uses_viewer_page_not_page_label() -> None:
    """Gold page_number 25 matches pdf_page_number 25 even when label is 12."""

    assert pdf_locator_ok((25,), (25,), page_labels=("12",)) is True
    assert pdf_locator_ok((12,), (25,), page_labels=("12",)) is False
    assert pdf_locator_ok((None,), (25,), page_labels=("12",)) is False


def test_paragraph_completeness_requires_surviving_citations() -> None:
    """Every factual paragraph needs at least one surviving citation."""

    assert paragraph_completeness((True, True)) == 1.0
    assert paragraph_completeness((True, False)) == 0.5
    assert paragraph_completeness(()) == 1.0


def test_forbidden_source_is_a_hard_failure() -> None:
    """ACL-forbidden ids fail the case even when locators match."""

    score = score_agent_case(
        case_id="fixture-ai-agents",
        cited_ids=(_FORBIDDEN,),
        allowed_ids=(_LEAF,),
        fact_chunk_ids=((_LEAF,),),
        forbidden_ids=(_FORBIDDEN,),
        locator_ok=True,
        route_ok=True,
        expected_refusal=False,
        refused=False,
        judge_status="complete",
        judge_faithfulness=1.0,
        paragraph_supported=(True,),
    )
    assert score.forbidden_cited is True
    assert score.citation_completeness == 1.0


def test_fixture_case_scores_viewer_page_25() -> None:
    """The deterministic AI Agents fixture is 100% when the leaf is on page 25."""

    score = score_agent_case(
        case_id="fixture-ai-agents",
        cited_ids=resolved_citation_ids((_LEAF,), (_RETRIEVED, _LEAF)),
        allowed_ids=(_LEAF,),
        fact_chunk_ids=((_LEAF,),),
        forbidden_ids=(),
        locator_ok=pdf_locator_ok((25,), (25,), page_labels=("12",)),
        route_ok=True,
        expected_refusal=False,
        refused=False,
        judge_status="complete",
        judge_faithfulness=1.0,
        paragraph_supported=(True,),
    )
    assert score.citation_precision == 1.0
    assert score.citation_completeness == 1.0
    assert score.locator_ok is True
    assert score.forbidden_cited is False
