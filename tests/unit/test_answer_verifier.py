"""Deterministic verifier rules, citation spans, and provenance."""

from __future__ import annotations

import pytest
from pydantic import ValidationError
from smart_rag_agents.query.deps import QueryGraphDeps
from smart_rag_agents.query.gateway.answer import gateway_answer
from smart_rag_agents.query.nodes.verify import verify_answer_node
from smart_rag_agents.query.state import pending_query_state
from smart_rag_core.gateways.model import AnswerModelResponse
from smart_rag_core.query_answer.citations import citation_provenance_payload
from smart_rag_core.query_answer.deterministic import deterministic_check_answer
from smart_rag_core.query_answer.exceptions import AnswerError
from smart_rag_core.query_answer.generate import mock_answer_payload
from smart_rag_core.query_answer.models import (
    AnswerCitation,
    AnswerParagraph,
    AnswerPayload,
    AtomicLink,
    ComposedConclusion,
    VerifierLinkVerdict,
    VerifierPayload,
)
from smart_rag_core.query_answer.release import (
    bind_company_atomic_links,
    company_release_applies,
    render_verified_company_answer,
)
from smart_rag_core.query_answer.verifier import (
    mock_verifier_payload,
    run_verifier_batch,
    select_material_links,
)
from smart_rag_core.query_answer.versions import (
    ANSWER_PROMPT_SHA256,
    ANSWER_PROMPT_VERSION,
    CONVERSATION_TITLE_PROMPT_SHA256,
    GENERAL_CHAT_PROMPT_SHA256,
    GENERAL_CHAT_PROMPT_VERSION,
    MAX_VERIFIER_LINKS,
    VERIFIER_PROMPT_SHA256,
    VERIFIER_PROMPT_VERSION,
)
from smart_rag_core.query_fusion import fusion_config_hash
from smart_rag_core.query_fusion.models import (
    FusionAlgorithm,
    FusionResult,
    PassageOrigin,
    ScoredPassage,
)
from smart_rag_core.query_routing.knowledge_scope import KnowledgeScope

from tests.support.answer_verifier import (
    verifier_fusion,
    verifier_passage,
    verifier_prompt_digest,
    verifier_table,
    verifier_uid,
)
from tests.support.query_runtime import RefusingHybridRetriever


def test_answer_and_verifier_prompt_hashes() -> None:
    """Pinned hashes match LF-normalized prompt files."""

    assert ANSWER_PROMPT_VERSION == "answer_v3"
    assert VERIFIER_PROMPT_VERSION == "verifier_v2"
    assert GENERAL_CHAT_PROMPT_VERSION == "general_chat_v1"
    assert ANSWER_PROMPT_SHA256 == verifier_prompt_digest("answer_v3.md")
    assert VERIFIER_PROMPT_SHA256 == verifier_prompt_digest("verifier_v2.md")
    assert verifier_prompt_digest("answer_v2.md") == (
        "20d55af652815a9829e477ed9d791d49386923da3c11d5dbdf1faa8081a37765"
    )
    assert verifier_prompt_digest("verifier_v1.md") == (
        "626d240ef39dc54825bb704d1812e0960539dee21449ffbe2713e8421f506962"
    )
    assert GENERAL_CHAT_PROMPT_SHA256 == verifier_prompt_digest("general_chat_v1.md")
    assert CONVERSATION_TITLE_PROMPT_SHA256 == verifier_prompt_digest(
        "conversation_title_v1.md"
    )


def test_unsupported_link_is_removed_not_softened() -> None:
    """Unsupported links are omitted or refused, never left as uncited claims."""

    fusion = verifier_fusion(
        verifier_passage(1, text="Atlas Controller is a Project Atlas product.")
    )
    payload = AnswerPayload(
        answer_text="Supplier Z funds Atlas.",
        citations=(AnswerCitation(chunk_id=verifier_uid(1)),),
        atomic_links=(
            AtomicLink(
                link_id="ok",
                claim="Atlas Controller is a Project Atlas product.",
                chunk_ids=(verifier_uid(1),),
                kind="inference_link",
                priority=1,
            ),
            AtomicLink(
                link_id="bad",
                claim="Supplier Z funds Atlas.",
                chunk_ids=(verifier_uid(999),),
                kind="inference_link",
                priority=2,
            ),
        ),
        composed_conclusion=ComposedConclusion(
            text="Supplier Z funds Project Atlas.",
            link_ids=("ok", "bad"),
        ),
        status="complete",
    )
    checked, failures = deterministic_check_answer(payload, fusion=fusion, tables=())
    assert "unsupported_link" in failures
    assert "unsupported_chain" in failures
    assert "bad" in checked.refused_links
    assert all(item.link_id != "bad" for item in checked.atomic_links)
    assert checked.composed_conclusion is None
    assert checked.status == "partial"


def test_composed_inference_need_not_appear_verbatim() -> None:
    """A fully supported chain stays a labeled inference without verbatim overlap."""

    fusion = verifier_fusion(
        verifier_passage(1, text="Atlas Controller is a Project Atlas product."),
        verifier_passage(2, text="Supplier A manufactures the Atlas Controller."),
    )
    payload = AnswerPayload(
        answer_text="Supplier A supplies a Project Atlas product.",
        citations=(
            AnswerCitation(
                chunk_id=verifier_uid(1), atomic_link_id="l1", inference=True
            ),
            AnswerCitation(
                chunk_id=verifier_uid(2), atomic_link_id="l2", inference=True
            ),
        ),
        atomic_links=(
            AtomicLink(
                link_id="l1",
                claim="Atlas Controller is a Project Atlas product.",
                chunk_ids=(verifier_uid(1),),
                kind="inference_link",
                priority=1,
            ),
            AtomicLink(
                link_id="l2",
                claim="Supplier A manufactures the Atlas Controller.",
                chunk_ids=(verifier_uid(2),),
                kind="inference_link",
                priority=2,
            ),
        ),
        composed_conclusion=ComposedConclusion(
            text="Supplier A supplies a Project Atlas product.",
            link_ids=("l1", "l2"),
        ),
        status="complete",
    )
    checked, failures = deterministic_check_answer(payload, fusion=fusion, tables=())
    assert "unsupported_chain" not in failures
    assert checked.composed_conclusion is not None
    assert checked.composed_conclusion.kind == "inference"
    assert (
        "Supplier A supplies a Project Atlas product."
        not in fusion.evidence[0].citation_text
    )
    assert (
        "Supplier A supplies a Project Atlas product."
        not in fusion.evidence[1].citation_text
    )


def test_seventh_verifier_link_does_not_trigger_another_call() -> None:
    """At most six material links; a seventh is omitted without a second call."""

    links = tuple(
        AtomicLink(
            link_id=f"link-{index}",
            claim=f"claim {index}",
            chunk_ids=(verifier_uid(1),),
            kind="inference_link" if index <= 6 else "fact",
            priority=index,
        )
        for index in range(1, 8)
    )
    selected, omitted = select_material_links(links)
    assert len(selected) == MAX_VERIFIER_LINKS == 6
    assert omitted == ("link-7",)
    calls: list[int] = []

    def _caller(batch: tuple[AtomicLink, ...]) -> VerifierPayload:
        """Count verifier invocations.

        Args:
            batch: Selected links.

        Returns:
            Identity-support verdicts.
        """

        calls.append(len(batch))
        return mock_verifier_payload(batch)

    payload = AnswerPayload(
        answer_text="links",
        atomic_links=links,
        status="complete",
    )
    updated, call_count, omitted_ids = run_verifier_batch(
        payload,
        caller=_caller,
        already_called=0,
    )
    assert call_count == 1
    assert calls == [6]
    assert omitted_ids == ("link-7",)
    assert updated.status == "partial"
    with pytest.raises(AnswerError, match="verifier_loop"):
        run_verifier_batch(updated, caller=_caller, already_called=1)
    with pytest.raises(ValidationError):
        VerifierPayload(
            link_verdicts=tuple(
                VerifierLinkVerdict(link_id=f"l{index}", supported=True, reason="ok")
                for index in range(7)
            )
        )


def test_verifier_omits_unsupported_verdicts() -> None:
    """Verifier unsupported marks are refusals, not softened claims."""

    payload = AnswerPayload(
        answer_text="two links",
        atomic_links=(
            AtomicLink(
                link_id="keep",
                claim="supported",
                chunk_ids=(verifier_uid(1),),
                priority=1,
            ),
            AtomicLink(
                link_id="drop",
                claim="unsupported",
                chunk_ids=(verifier_uid(1),),
                priority=2,
            ),
        ),
        status="complete",
    )

    def _caller(batch: tuple[AtomicLink, ...]) -> VerifierPayload:
        """Mark the second link unsupported.

        Args:
            batch: Selected links.

        Returns:
            Mixed verdicts.
        """

        return VerifierPayload(
            link_verdicts=tuple(
                VerifierLinkVerdict(
                    link_id=item.link_id,
                    supported=item.link_id == "keep",
                    reason="supported"
                    if item.link_id == "keep"
                    else "unsupported_link",
                )
                for item in batch
            )
        )

    updated, call_count, _omitted = run_verifier_batch(
        payload, caller=_caller, already_called=0
    )
    assert call_count == 1
    assert [item.link_id for item in updated.atomic_links] == ["keep"]
    assert "drop" in updated.refused_links
    assert updated.status == "partial"


def test_citation_span_and_table_range_mismatch_fail() -> None:
    """Deterministic checks require span/range alignment with canonical sources."""

    fusion = verifier_fusion(verifier_passage(1, text="The refund period is 30 days."))
    table = verifier_table()
    payload = AnswerPayload(
        answer_text="bad spans",
        citations=(AnswerCitation(chunk_id=verifier_uid(1), span="90-day refund"),),
        table_citations=(
            AnswerCitation(table_id=table.table_id, source_ranges=("Sheet9!Z9",)),
        ),
        status="complete",
    )
    checked, failures = deterministic_check_answer(
        payload, fusion=fusion, tables=(table,)
    )
    assert "citation_span_mismatch" in failures
    assert "table_range_mismatch" in failures
    assert checked.citations == ()
    assert checked.table_citations == ()


def test_empty_graph_citation_text_cannot_pass_complete() -> None:
    """Graph-derived empty citation_text cannot stay deterministic complete."""

    fusion = FusionResult(
        algorithm=FusionAlgorithm.RESOLVED_PATH_FUSION,
        config_hash=fusion_config_hash(FusionAlgorithm.RESOLVED_PATH_FUSION),
        requested_route="combined",
        effective_route="combined",
        evidence=(
            ScoredPassage(
                chunk_id=verifier_uid(1),
                document_id=verifier_uid(10_001),
                version_id=verifier_uid(20_001),
                citation_text="",
                hybrid_rank=None,
                graph_rank=1,
                combined_score=1.0 / 61,
                origin=PassageOrigin.GRAPH_RESOLVED,
                graph_discovered_only=True,
            ),
        ),
        graph_discovered_only_ratio=1.0,
    )
    payload = AnswerPayload(
        answer_text="Atlas is a product.",
        citations=(AnswerCitation(chunk_id=verifier_uid(1), span=""),),
        status="complete",
    )
    checked, failures = deterministic_check_answer(payload, fusion=fusion, tables=())
    assert "empty_citation_text" in failures
    assert checked.citations == ()
    assert checked.status != "complete"


def test_citation_provenance_uses_existing_jsonb() -> None:
    """Fusion scores land in ``app.citations.provenance`` without a new table."""

    fusion = verifier_fusion(
        verifier_passage(1, text="The refund period is 30 days.").model_copy(
            update={
                "page_number": 129,
                "section_path": ("Tools", "Parallel Tool Execution"),
            }
        )
    )
    answer = mock_answer_payload(fusion, (), user_query="refund")
    payload = citation_provenance_payload(
        fusion=fusion,
        answer=answer,
        chunk_id=verifier_uid(1),
        table_id=None,
        atomic_link_id="link-1",
        inference=False,
    )
    assert payload["algorithm"] == "resolved_path_fusion"
    assert payload["config_hash"] == fusion.config_hash
    assert payload["keyword_extract_count"] == 0
    assert payload["lightrag_answer_generate_count"] == 0
    assert payload["page_number"] == 129
    assert payload["section_path"] == ["Tools", "Parallel Tool Execution"]
    assert payload["document_id"] == verifier_uid(10_001)
    assert "citation_text" not in payload
    assert "snippet" not in payload


def _mcp_fusion() -> FusionResult:
    """Return a source that spells MCP as Model Context Protocol.

    Returns:
        Hybrid-effective fusion with one passage.
    """

    return verifier_fusion(
        verifier_passage(
            1,
            text="MCP (Model Context Protocol) lets models call tools.",
        )
    )


def _supporting_mock_verifier(
    batch: tuple[AtomicLink, ...],
) -> VerifierPayload:
    """Mark every cited link supported, matching the untrusted mock verifier.

    Args:
        batch: Selected links.

    Returns:
        All-supported verdicts.
    """

    return VerifierPayload(
        link_verdicts=tuple(
            VerifierLinkVerdict(
                link_id=item.link_id, supported=True, reason="supported"
            )
            for item in batch
        )
    )


def test_wrong_mcp_expansion_in_link_is_rejected_despite_mock_verifier() -> None:
    """A wrong MCP expansion is dropped even when the mock verifier agrees."""

    fusion = _mcp_fusion()
    chunk_id = fusion.evidence[0].chunk_id
    payload = AnswerPayload(
        answer_text="MCP is the Method Call Protocol.",
        paragraphs=(
            AnswerParagraph(
                paragraph_index=0,
                text="MCP is the Method Call Protocol.",
                link_ids=("l1",),
            ),
        ),
        citations=(
            AnswerCitation(
                chunk_id=chunk_id,
                span="MCP (Model Context Protocol)",
                paragraph_index=0,
                atomic_link_id="l1",
            ),
        ),
        atomic_links=(
            AtomicLink(
                link_id="l1",
                claim="MCP is the Method Call Protocol.",
                chunk_ids=(chunk_id,),
                kind="fact",
                priority=1,
            ),
        ),
        status="complete",
        answer_origin=KnowledgeScope.COMPANY_DOCUMENTS,
    )
    updated, call_count, _omitted = run_verifier_batch(
        payload, caller=_supporting_mock_verifier, already_called=0
    )
    assert call_count == 1
    released = render_verified_company_answer(updated, fusion=fusion, tables=())
    assert "Method Call Protocol" not in released.answer_text
    assert released.status == "refused"
    assert released.citations == ()


def test_correct_mcp_expansion_passes() -> None:
    """The source-spelled MCP expansion remains in the released company answer."""

    fusion = _mcp_fusion()
    chunk_id = fusion.evidence[0].chunk_id
    claim = "MCP (Model Context Protocol) lets models call tools."
    payload = AnswerPayload(
        answer_text=claim,
        paragraphs=(AnswerParagraph(paragraph_index=0, text=claim, link_ids=("l1",)),),
        citations=(
            AnswerCitation(
                chunk_id=chunk_id,
                span="MCP (Model Context Protocol)",
                paragraph_index=0,
                atomic_link_id="l1",
            ),
        ),
        atomic_links=(
            AtomicLink(
                link_id="l1",
                claim=claim,
                chunk_ids=(chunk_id,),
                kind="fact",
                priority=1,
            ),
        ),
        status="complete",
        answer_origin=KnowledgeScope.COMPANY_DOCUMENTS,
    )
    released = render_verified_company_answer(payload, fusion=fusion, tables=())
    assert "Model Context Protocol" in released.answer_text
    assert "Method Call Protocol" not in released.answer_text
    assert released.status == "complete"
    assert released.citations[0].atomic_link_id == "l1"


def test_mcp_stands_for_passes_when_source_spells_expansion_without_parens() -> None:
    """A stands-for claim survives when the source spells the expansion.

    The cited passage may use the expansion as a heading or sentence
    without ``MCP (Model Context Protocol)`` parentheses.
    """

    fusion = verifier_fusion(
        verifier_passage(
            1,
            text="Model Context Protocol lets models call tools via MCP.",
        )
    )
    chunk_id = fusion.evidence[0].chunk_id
    claim = "MCP stands for Model Context Protocol."
    payload = AnswerPayload(
        answer_text=claim,
        paragraphs=(AnswerParagraph(paragraph_index=0, text=claim, link_ids=("l1",)),),
        citations=(
            AnswerCitation(
                chunk_id=chunk_id,
                span="Model Context Protocol",
                paragraph_index=0,
                atomic_link_id="l1",
            ),
        ),
        atomic_links=(
            AtomicLink(
                link_id="l1",
                claim=claim,
                chunk_ids=(chunk_id,),
                kind="fact",
                priority=1,
            ),
        ),
        status="complete",
        answer_origin=KnowledgeScope.COMPANY_DOCUMENTS,
    )
    released = render_verified_company_answer(payload, fusion=fusion, tables=())
    assert "Model Context Protocol" in released.answer_text
    assert "Method Call Protocol" not in released.answer_text
    assert released.status == "complete"
    assert released.citations


def test_paragraphs_without_atomic_links_still_release_grounded_mcp() -> None:
    """Paragraph-grounded PDF answers synthesize links when the model omitted them."""

    fusion = _mcp_fusion()
    chunk_id = fusion.evidence[0].chunk_id
    claim = "MCP (Model Context Protocol) lets models call tools."
    payload = AnswerPayload(
        answer_text=claim,
        paragraphs=(AnswerParagraph(paragraph_index=0, text=claim, link_ids=("l1",)),),
        citations=(
            AnswerCitation(
                chunk_id=chunk_id,
                span="MCP (Model Context Protocol)",
                paragraph_index=0,
            ),
        ),
        atomic_links=(),
        status="complete",
        answer_origin=KnowledgeScope.COMPANY_DOCUMENTS,
    )
    released = render_verified_company_answer(payload, fusion=fusion, tables=())
    assert "Model Context Protocol" in released.answer_text
    assert released.citations
    assert released.atomic_links
    paraphrased = payload.model_copy(
        update={
            "citations": (
                payload.citations[0].model_copy(
                    update={"span": "MCP is a made-up paraphrased span."}
                ),
            )
        }
    )
    checked, failures = deterministic_check_answer(
        bind_company_atomic_links(paraphrased, fusion=fusion),
        fusion=fusion,
        tables=(),
        require_paragraphs=True,
    )
    assert checked.atomic_links
    assert "paragraph_unmapped" not in failures
    assert "citation_span_mismatch" not in failures
    assert checked.citations
    assert "Model Context Protocol" in (checked.citations[0].span or "")


def test_atomic_links_without_paragraphs_still_release_grounded_mcp() -> None:
    """Link-only live payloads synthesize paragraphs before verification."""

    fusion = _mcp_fusion()
    chunk_id = fusion.evidence[0].chunk_id
    payload = AnswerPayload(
        answer_text="",
        paragraphs=(),
        citations=(),
        atomic_links=(
            AtomicLink(
                link_id="0001",
                claim="MCP (Model Context Protocol) lets models call tools.",
                chunk_ids=(chunk_id,),
            ),
        ),
        status="complete",
        answer_origin=KnowledgeScope.COMPANY_DOCUMENTS,
    )
    bound = bind_company_atomic_links(payload, fusion=fusion)
    assert bound.paragraphs
    assert bound.citations
    checked, failures = deterministic_check_answer(
        bound,
        fusion=fusion,
        tables=(),
        require_paragraphs=True,
    )
    assert checked.atomic_links
    assert "paragraph_unmapped" not in failures
    released = render_verified_company_answer(checked, fusion=fusion, tables=())
    assert "Model Context Protocol" in released.answer_text
    invented = payload.model_copy(
        update={
            "atomic_links": (
                AtomicLink(
                    link_id="0001",
                    claim="MCP stands for Multi-Channel Protocol.",
                    chunk_ids=(chunk_id,),
                ),
            )
        }
    )
    released_wrong = render_verified_company_answer(
        bind_company_atomic_links(invented, fusion=fusion),
        fusion=fusion,
        tables=(),
    )
    assert released_wrong.status == "refused"
    assert "Multi-Channel Protocol" not in released_wrong.answer_text


def test_link_only_multiline_pdf_passage_still_maps_mcp_span() -> None:
    """Link-only payloads citing a blank-line PDF passage stay grounded."""

    fusion = verifier_fusion(
        verifier_passage(
            1,
            text=(
                "Model Context Protocol\n\n"
                "MCP lets models call tools through a shared protocol."
            ),
        )
    )
    chunk_id = fusion.evidence[0].chunk_id
    payload = AnswerPayload(
        answer_text="",
        paragraphs=(),
        citations=(),
        atomic_links=(
            AtomicLink(
                link_id="mcp_definition",
                claim="MCP stands for Model Context Protocol.",
                chunk_ids=(chunk_id,),
            ),
        ),
        status="complete",
        answer_origin=KnowledgeScope.COMPANY_DOCUMENTS,
    )
    bound = bind_company_atomic_links(payload, fusion=fusion)
    assert bound.citations
    assert bound.citations[0].span in fusion.evidence[0].citation_text
    checked, failures = deterministic_check_answer(
        bound,
        fusion=fusion,
        tables=(),
        require_paragraphs=True,
    )
    assert "citation_span_mismatch" not in failures
    assert "paragraph_unmapped" not in failures
    assert checked.atomic_links
    released = render_verified_company_answer(checked, fusion=fusion, tables=())
    assert "Model Context Protocol" in released.answer_text


def test_gateway_answer_binds_omitted_paragraphs_from_live_links() -> None:
    """The live answer gateway binds link-only payloads before verify."""

    fusion = verifier_fusion(
        verifier_passage(
            1,
            text=(
                "Model Context Protocol\n\n"
                "MCP lets models call tools through a shared protocol."
            ),
        )
    )
    chunk_id = fusion.evidence[0].chunk_id

    class _LinkOnlyGateway:
        """Return a complete answer with atomic links and no paragraphs."""

        async def generate_answer(self, request: object) -> AnswerModelResponse:
            """Return the live omitted-paragraph shape.

            Args:
                request: Unused structured answer request.

            Returns:
                Fixture payload matching live ``answer_v3`` omissions.
            """

            del request
            return AnswerModelResponse(
                mode="mock",
                payload={
                    "answer_text": "",
                    "paragraphs": [],
                    "citations": [],
                    "atomic_links": [
                        {
                            "link_id": "mcp_definition",
                            "claim": "MCP stands for Model Context Protocol.",
                            "chunk_ids": [chunk_id],
                        }
                    ],
                    "status": "complete",
                },
                request_id="gateway-bind-1",
                input_tokens=12,
                output_tokens=8,
            )

    payload, prompt_tokens, completion_tokens = gateway_answer(
        QueryGraphDeps(
            model_gateway=_LinkOnlyGateway(),
            answer_prompt_text="answer",
        ),
        query="In the Model Context Protocol section, what does MCP stand for?",
        fusion=fusion,
        tables=(),
        context=None,
    )
    assert prompt_tokens == 12
    assert completion_tokens == 8
    assert payload.paragraphs
    assert payload.citations
    assert payload.citations[0].span in fusion.evidence[0].citation_text
    assert "Model Context Protocol" in (payload.citations[0].span or "")


def test_free_prose_mcp_expansion_cannot_stay_verified() -> None:
    """Unsupported Method Call Protocol prose cannot remain in a verified answer."""

    fusion = _mcp_fusion()
    chunk_id = fusion.evidence[0].chunk_id
    claim = "MCP lets models call tools."
    payload = AnswerPayload(
        answer_text="MCP is the Method Call Protocol used for tools.",
        paragraphs=(
            AnswerParagraph(
                paragraph_index=0,
                text="MCP is the Method Call Protocol used for tools.",
                link_ids=("l1",),
            ),
        ),
        citations=(
            AnswerCitation(
                chunk_id=chunk_id,
                span="MCP (Model Context Protocol) lets models call tools.",
                paragraph_index=0,
                atomic_link_id="l1",
            ),
        ),
        atomic_links=(
            AtomicLink(
                link_id="l1",
                claim=claim,
                chunk_ids=(chunk_id,),
                kind="fact",
                priority=1,
            ),
        ),
        status="complete",
        answer_origin=KnowledgeScope.COMPANY_DOCUMENTS,
    )
    released = render_verified_company_answer(payload, fusion=fusion, tables=())
    assert "Method Call Protocol" not in released.answer_text
    assert claim in released.answer_text
    assert released.status != "complete"


def test_one_supported_link_produces_one_citation() -> None:
    """Released citations come from surviving links, not every fusion passage."""

    fusion = verifier_fusion(
        verifier_passage(1, text="The refund period is 30 days."),
        verifier_passage(2, text="Unused later passage stays uncited."),
    )
    first = fusion.evidence[0].chunk_id
    payload = AnswerPayload(
        answer_text="The refund period is 30 days.",
        paragraphs=(
            AnswerParagraph(
                paragraph_index=0,
                text="The refund period is 30 days.",
                link_ids=("keep",),
            ),
        ),
        citations=(
            AnswerCitation(
                chunk_id=first,
                span="The refund period is 30 days.",
                paragraph_index=0,
                atomic_link_id="keep",
            ),
        ),
        atomic_links=(
            AtomicLink(
                link_id="keep",
                claim="The refund period is 30 days.",
                chunk_ids=(first,),
                kind="fact",
                priority=1,
            ),
            AtomicLink(
                link_id="drop",
                claim="Unused later passage stays uncited.",
                chunk_ids=(fusion.evidence[1].chunk_id,),
                kind="fact",
                priority=2,
            ),
        ),
        status="complete",
        answer_origin=KnowledgeScope.COMPANY_DOCUMENTS,
    )
    updated, _, _ = run_verifier_batch(
        payload,
        caller=lambda batch: VerifierPayload(
            link_verdicts=tuple(
                VerifierLinkVerdict(
                    link_id=item.link_id,
                    supported=item.link_id == "keep",
                    reason="supported"
                    if item.link_id == "keep"
                    else "unsupported_link",
                )
                for item in batch
            )
        ),
        already_called=0,
    )
    released = render_verified_company_answer(updated, fusion=fusion, tables=())
    assert [item.atomic_link_id for item in released.citations] == ["keep"]
    assert fusion.evidence[1].chunk_id not in {
        item.chunk_id for item in released.citations
    }
    assert "drop" not in {item.link_id for item in released.atomic_links}


def test_composed_inference_is_appended_when_chain_survives() -> None:
    """A fully supported inference conclusion is released after unique claims."""

    fusion = verifier_fusion(
        verifier_passage(1, text="Atlas Controller is a Project Atlas product."),
        verifier_passage(2, text="Supplier A manufactures the Atlas Controller."),
    )
    payload = AnswerPayload(
        answer_text="Supplier A supplies a Project Atlas product.",
        atomic_links=(
            AtomicLink(
                link_id="l1",
                claim="Atlas Controller is a Project Atlas product.",
                chunk_ids=(verifier_uid(1),),
                kind="inference_link",
                priority=1,
            ),
            AtomicLink(
                link_id="l2",
                claim="Supplier A manufactures the Atlas Controller.",
                chunk_ids=(verifier_uid(2),),
                kind="inference_link",
                priority=2,
            ),
        ),
        composed_conclusion=ComposedConclusion(
            text="Supplier A supplies a Project Atlas product.",
            link_ids=("l1", "l2"),
        ),
        status="complete",
        answer_origin=KnowledgeScope.COMPANY_DOCUMENTS,
    )
    released = render_verified_company_answer(payload, fusion=fusion, tables=())
    assert released.composed_conclusion is not None
    assert "Supplier A supplies a Project Atlas product." in released.answer_text
    assert released.citations[0].atomic_link_id == "l1"
    assert released.citations[1].atomic_link_id == "l2"


def test_general_answers_are_not_rewritten_by_company_release() -> None:
    """General-knowledge prose is unchanged and receives no company citations."""

    payload = AnswerPayload(
        answer_text="Hello from general knowledge.",
        status="complete",
        answer_origin=KnowledgeScope.GENERAL_KNOWLEDGE,
    )
    assert company_release_applies(payload, is_web=False) is False
    assert payload.citations == ()
    assert payload.answer_text == "Hello from general knowledge."


def test_verify_node_rejects_ungrounded_mcp_expansion() -> None:
    """SSE terminal cannot stay verified when Method Call Protocol was invented."""

    fusion = _mcp_fusion()
    chunk_id = fusion.evidence[0].chunk_id
    state = pending_query_state(user_query="What is MCP?")
    state["status"] = "answered"
    state["remaining_model_calls"] = 8
    state["fusion"] = fusion.model_dump(mode="json")
    state["answer"] = AnswerPayload(
        answer_text="MCP is the Method Call Protocol.",
        paragraphs=(
            AnswerParagraph(
                paragraph_index=0,
                text="MCP is the Method Call Protocol.",
                link_ids=("l1",),
            ),
        ),
        citations=(
            AnswerCitation(
                chunk_id=chunk_id,
                span="MCP (Model Context Protocol)",
                paragraph_index=0,
                atomic_link_id="l1",
            ),
        ),
        atomic_links=(
            AtomicLink(
                link_id="l1",
                claim="MCP is the Method Call Protocol.",
                chunk_ids=(chunk_id,),
                kind="fact",
                priority=1,
            ),
        ),
        status="complete",
        answer_origin=KnowledgeScope.COMPANY_DOCUMENTS,
    ).model_dump(mode="json")
    verified = verify_answer_node(
        state, QueryGraphDeps(hybrid_retriever=RefusingHybridRetriever())
    )
    payload = AnswerPayload.model_validate(verified["answer"])
    assert verified["status"] != "verified"
    assert "Method Call Protocol" not in payload.answer_text
