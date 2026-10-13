"""Rebind a mis-cited claim onto the fused chunk that holds its token."""

from __future__ import annotations

from smart_rag_core.query_answer.models import (
    AnswerCitation,
    AnswerParagraph,
    AnswerPayload,
    AtomicLink,
)
from smart_rag_core.query_answer.release import bind_company_atomic_links
from smart_rag_core.query_routing.knowledge_scope import KnowledgeScope

from tests.support.answer_verifier import (
    verifier_fusion,
    verifier_passage,
    verifier_uid,
)

_WRONG = (
    "Tool selection compares the model output with the available toolset "
    "and returns the highest-scoring option."
)
_GOLD = (
    "The helper persists conversation state through update_memory before "
    "the next agent turn begins."
)
_CLAIM = "The helper function name used for memory updates is update_memory."


def _payload(cited: str) -> AnswerPayload:
    """Build a one-claim answer that cited ``cited``.

    Args:
        cited: Chunk id the model attached to the claim.

    Returns:
        Company answer with one fact claim and one citation.
    """

    return AnswerPayload(
        answer_text=_CLAIM,
        paragraphs=(
            AnswerParagraph(paragraph_index=0, text=_CLAIM, link_ids=("claim-1",)),
        ),
        citations=(
            AnswerCitation(
                chunk_id=cited,
                span="Tool selection compares",
                paragraph_index=0,
                atomic_link_id="claim-1",
            ),
        ),
        atomic_links=(
            AtomicLink(
                link_id="claim-1",
                claim=_CLAIM,
                chunk_ids=(cited,),
            ),
        ),
        status="complete",
        answer_origin=KnowledgeScope.COMPANY_DOCUMENTS,
    )


def test_miscited_unique_token_rebinds_to_gold_chunk() -> None:
    """A claim citing a chunk without the token moves onto the unique holder."""

    fusion = verifier_fusion(
        verifier_passage(1, text=_WRONG, rank=1),
        verifier_passage(2, text=_GOLD, rank=2),
    )
    wrong_id = verifier_uid(1)
    gold_id = verifier_uid(2)
    bound = bind_company_atomic_links(_payload(wrong_id), fusion=fusion)
    link = bound.atomic_links[0]
    assert link.chunk_ids[0] == gold_id
    assert bound.citations[0].chunk_id == gold_id
    memory_span = bound.citations[0].span
    assert memory_span is not None
    assert "update_memory" in memory_span


def test_prose_and_def_token_holders_multicite_gold_prose() -> None:
    """Helper prose and def chunks are both cited; prose is primary."""

    prose = (
        "4. Update memory. A helper function (update_memory) reads the "
        "trial logs, invokes the LLM on the reflections, and stores them."
    )
    definition = (
        "def update_memory(trial_log_path: str, env_configs: List[Dict[str, Any]]):\n"
        "    pass\n"
    )
    call_site = (
        "reflections.append(result)\nupdate_memory(trial_log_path, env_configs)\n"
    )
    fusion = verifier_fusion(
        verifier_passage(1, text=definition, rank=1),
        verifier_passage(2, text=prose, rank=2),
        verifier_passage(3, text=call_site, rank=3),
    )
    def_id = verifier_uid(1)
    prose_id = verifier_uid(2)
    bound = bind_company_atomic_links(_payload(def_id), fusion=fusion)
    cited_ids = {item.chunk_id for item in bound.citations}
    assert prose_id in cited_ids
    assert bound.citations[0].chunk_id == prose_id
    assert prose_id in bound.atomic_links[0].chunk_ids
    assert def_id in bound.atomic_links[0].chunk_ids or def_id in cited_ids


def test_contained_claim_cites_only_the_holding_passage() -> None:
    """A claim that is one whole passage does not also cite a shared number."""

    page_a = "The rollout reached 50 engineers in the first month."
    page_b = "Later the team grew beyond 50 engineers on the same product."
    claim = "The rollout reached 50 engineers in the first month."
    fusion = verifier_fusion(
        verifier_passage(1, text=page_a, rank=2),
        verifier_passage(2, text=page_b, rank=1),
    )
    cited = verifier_uid(1)
    payload = AnswerPayload(
        answer_text=claim,
        paragraphs=(
            AnswerParagraph(paragraph_index=0, text=claim, link_ids=("claim-1",)),
        ),
        citations=(
            AnswerCitation(
                chunk_id=cited,
                span="The rollout reached",
                paragraph_index=0,
                atomic_link_id="claim-1",
            ),
        ),
        atomic_links=(
            AtomicLink(
                link_id="claim-1",
                claim=claim,
                chunk_ids=(cited,),
            ),
        ),
        status="complete",
        answer_origin=KnowledgeScope.COMPANY_DOCUMENTS,
    )
    bound = bind_company_atomic_links(payload, fusion=fusion)
    cited_ids = {item.chunk_id for item in bound.citations}
    assert cited_ids == {verifier_uid(1)}
    assert bound.atomic_links[0].chunk_ids == (verifier_uid(1),)
    assert bound.citations[0].span is not None
    assert bound.citations[0].span in page_a


def test_hyphen_model_token_rebinds_to_holder() -> None:
    """A gpt-4o claim citing a non-holder moves onto the model chunk."""

    wrong = "ChatOpenAI can bind tools after the calculator helpers load."
    gold = 'llm = ChatOpenAI(model_name="gpt-4o", temperature=0)'
    claim = 'ChatOpenAI(model_name="gpt-4o", temperature=0)'
    fusion = verifier_fusion(
        verifier_passage(1, text=wrong, rank=1),
        verifier_passage(2, text=gold, rank=2),
    )
    payload = AnswerPayload(
        answer_text=claim,
        paragraphs=(
            AnswerParagraph(paragraph_index=0, text=claim, link_ids=("claim-1",)),
        ),
        citations=(
            AnswerCitation(
                chunk_id=verifier_uid(1),
                span="ChatOpenAI can bind",
                paragraph_index=0,
                atomic_link_id="claim-1",
            ),
        ),
        atomic_links=(
            AtomicLink(
                link_id="claim-1",
                claim=claim,
                chunk_ids=(verifier_uid(1),),
            ),
        ),
        status="complete",
        answer_origin=KnowledgeScope.COMPANY_DOCUMENTS,
    )
    bound = bind_company_atomic_links(payload, fusion=fusion)
    assert bound.citations[0].chunk_id == verifier_uid(2)
    model_span = bound.citations[0].span
    assert model_span is not None
    assert "gpt-4o" in model_span


def test_host_path_token_rebinds_to_holder() -> None:
    """A localhost path claim retargets onto the fused host chunk."""

    wrong = "The weather tool runs as a remote MCP endpoint."
    gold = "Connect to the weather MCP server on localhost:8000/mcp."
    claim = "The weather MCP server runs at localhost:8000/mcp."
    fusion = verifier_fusion(
        verifier_passage(1, text=wrong, rank=1),
        verifier_passage(2, text=gold, rank=2),
    )
    payload = AnswerPayload(
        answer_text=claim,
        paragraphs=(
            AnswerParagraph(paragraph_index=0, text=claim, link_ids=("claim-1",)),
        ),
        citations=(
            AnswerCitation(
                chunk_id=verifier_uid(1),
                span="The weather tool runs",
                paragraph_index=0,
                atomic_link_id="claim-1",
            ),
        ),
        atomic_links=(
            AtomicLink(
                link_id="claim-1",
                claim=claim,
                chunk_ids=(verifier_uid(1),),
            ),
        ),
        status="complete",
        answer_origin=KnowledgeScope.COMPANY_DOCUMENTS,
    )
    bound = bind_company_atomic_links(payload, fusion=fusion)
    assert bound.citations[0].chunk_id == verifier_uid(2)
    host_span = bound.citations[0].span
    assert host_span is not None
    assert "localhost:8000/mcp" in host_span.lower()


def test_query_overlap_prefers_gold_holder_for_shared_token() -> None:
    """Multi-holder gpt-4o cites the passage that overlaps the ask most."""

    weak = (
        'Later chapters also initialize ChatOpenAI(model_name="gpt-4o") '
        "for unrelated demos."
    )
    gold = (
        "In the calculator tool-binding example, "
        'llm = ChatOpenAI(model_name="gpt-4o", temperature=0)'
    )
    claim = 'llm = ChatOpenAI(model_name="gpt-4o", temperature=0)'
    query = (
        "In the calculator tool-binding example, which ChatOpenAI "
        "model_name is initialized?"
    )
    fusion = verifier_fusion(
        verifier_passage(1, text=weak, rank=1),
        verifier_passage(2, text=gold, rank=2),
    )
    payload = AnswerPayload(
        answer_text=claim,
        paragraphs=(
            AnswerParagraph(paragraph_index=0, text=claim, link_ids=("claim-1",)),
        ),
        citations=(
            AnswerCitation(
                chunk_id=verifier_uid(1),
                span='model_name="gpt-4o"',
                paragraph_index=0,
                atomic_link_id="claim-1",
            ),
        ),
        atomic_links=(
            AtomicLink(
                link_id="claim-1",
                claim=claim,
                chunk_ids=(verifier_uid(1),),
            ),
        ),
        status="complete",
        answer_origin=KnowledgeScope.COMPANY_DOCUMENTS,
    )
    bound = bind_company_atomic_links(payload, fusion=fusion, user_query=query)
    assert bound.citations[0].chunk_id == verifier_uid(2)


def test_query_overlap_prefers_a2a_acronym_holder() -> None:
    """A2A claim prefers the HTTP-composability page over the intro page."""

    weak = (
        "The Agent-to-Agent (A2A) Protocol, introduced by Google, is an "
        "ambitious step toward enabling autonomous agents to work together."
    )
    gold = (
        "Much like HTTP enabled the composability of the web, A2A aspires "
        "to do the same for AI agents."
    )
    claim = (
        "The protocol that aspires to do for AI agents what HTTP enabled "
        "for the composability of the web is the Agent-to-Agent (A2A) Protocol."
    )
    query = (
        "What protocol does the book say aspires to do for AI agents what "
        "HTTP enabled for the composability of the web?"
    )
    fusion = verifier_fusion(
        verifier_passage(1, text=weak, rank=1),
        verifier_passage(2, text=gold, rank=2),
    )
    payload = AnswerPayload(
        answer_text=claim,
        paragraphs=(
            AnswerParagraph(paragraph_index=0, text=claim, link_ids=("claim-1",)),
        ),
        citations=(
            AnswerCitation(
                chunk_id=verifier_uid(1),
                span="The Agent-to-Agent (A2A) Protocol",
                paragraph_index=0,
                atomic_link_id="claim-1",
            ),
        ),
        atomic_links=(
            AtomicLink(
                link_id="claim-1",
                claim=claim,
                chunk_ids=(verifier_uid(1),),
            ),
        ),
        status="complete",
        answer_origin=KnowledgeScope.COMPANY_DOCUMENTS,
    )
    bound = bind_company_atomic_links(payload, fusion=fusion, user_query=query)
    assert bound.citations[0].chunk_id == verifier_uid(2)


def test_contained_claim_cites_the_passage_that_holds_it() -> None:
    """A collapsed claim leaves a short span and cites the holding passage."""

    other = "A handshake token appears only in this later sentence."
    holder = "The ledger records a final balance\nbefore any later note."
    claim = "The ledger records a final balance before any later note."
    fusion = verifier_fusion(
        verifier_passage(1, text=other, rank=1),
        verifier_passage(2, text=holder, rank=2),
    )
    payload = AnswerPayload(
        answer_text=claim,
        paragraphs=(
            AnswerParagraph(paragraph_index=0, text=claim, link_ids=("claim-1",)),
        ),
        citations=(
            AnswerCitation(
                chunk_id=verifier_uid(1),
                span="A handshake token",
                paragraph_index=0,
                atomic_link_id="claim-1",
            ),
        ),
        atomic_links=(
            AtomicLink(
                link_id="claim-1",
                claim=claim,
                chunk_ids=(verifier_uid(1),),
                kind="fact",
            ),
        ),
        status="complete",
        answer_origin=KnowledgeScope.COMPANY_DOCUMENTS,
    )
    bound = bind_company_atomic_links(payload, fusion=fusion)
    link = bound.atomic_links[0]
    citation = bound.citations[0]
    assert link.claim == claim
    assert link.chunk_ids == (verifier_uid(2),)
    assert citation.chunk_id == verifier_uid(2)
    assert citation.span is not None
    assert citation.span in holder


def test_paraphrase_still_follows_token_rebind() -> None:
    """A claim that is not contained in a passage still uses token rebind."""

    fusion = verifier_fusion(
        verifier_passage(1, text=_WRONG, rank=1),
        verifier_passage(2, text=_GOLD, rank=2),
    )
    bound = bind_company_atomic_links(_payload(verifier_uid(1)), fusion=fusion)
    assert bound.atomic_links[0].chunk_ids[0] == verifier_uid(2)
    assert bound.citations[0].chunk_id == verifier_uid(2)
