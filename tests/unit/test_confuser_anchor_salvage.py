"""Query-anchored salvage for autonomy-mode and ADAS confuser answers."""

from __future__ import annotations

from uuid import UUID, uuid4

from smart_rag_core.query_answer.generate_grounded import (
    salvage_adas_model_defaults,
    salvage_expose_mode_labels,
)
from smart_rag_core.query_answer.models import (
    AnswerCitation,
    AnswerParagraph,
    AnswerPayload,
    AtomicLink,
)
from smart_rag_core.query_routing.knowledge_scope import KnowledgeScope
from smart_rag_core.retrieval.rerank import (
    RerankPassage,
    promote_adas_model_passages,
    promote_expose_mode_passages,
)
from smart_rag_core.retrieval.types import RetrievalCandidate

from tests.support.answer_verifier import verifier_fusion, verifier_passage


def _passage(index: int, *, text: str) -> RerankPassage:
    """Build one rerank passage with stable chunk identity.

    Args:
        index: Distinct index for the chunk UUID.
        text: Passage text.

    Returns:
        Rerank passage wrapping a retrieval candidate.
    """

    chunk_id = UUID(f"0000000{index}-0000-4000-8000-000000000000")
    return RerankPassage(
        candidate=RetrievalCandidate(
            chunk_id=chunk_id,
            document_id=uuid4(),
            version_id=uuid4(),
            channel_rank=index,
            channel_score=1.0 / index,
        ),
        raw_text=text,
        excerpt=text,
        token_count=max(1, len(text.split())),
        channels=frozenset({"dense"}),
    )


def _confuser_payload(*, claim: str, chunk_id: str) -> AnswerPayload:
    """Build a one-claim confuser answer.

    Args:
        claim: Wrong but grounded claim text.
        chunk_id: Cited confuser chunk.

    Returns:
        Complete company answer payload.
    """

    return AnswerPayload(
        answer_text=claim,
        paragraphs=(
            AnswerParagraph(paragraph_index=0, text=claim, link_ids=("c1",)),
        ),
        citations=(
            AnswerCitation(
                chunk_id=chunk_id,
                span=claim[:80],
                paragraph_index=0,
                atomic_link_id="c1",
            ),
        ),
        atomic_links=(
            AtomicLink(link_id="c1", claim=claim, chunk_ids=(chunk_id,)),
        ),
        status="complete",
        answer_origin=KnowledgeScope.COMPANY_DOCUMENTS,
    )


def test_salvage_expose_modes_replaces_ask_agent_confuser() -> None:
    """Expose/label asks rewrite Manual/Ask/Agent onto Manual/Assist/Auto."""

    confuser = verifier_passage(
        1,
        text='Figure modes: "Manual," "Ask," and "Agent."',
        rank=1,
    )
    gold = verifier_passage(
        2,
        text=(
            'Label these modes to expose degrees of autonomy such as '
            '"Manual," "Assist," and "Auto".'
        ),
        rank=2,
    )
    fusion = verifier_fusion(confuser, gold)
    confuser_id = str(fusion.evidence[0].chunk_id)
    gold_id = str(fusion.evidence[1].chunk_id)
    payload = _confuser_payload(
        claim='The three mode labels are "Manual," "Ask," and "Agent."',
        chunk_id=confuser_id,
    )
    salvaged = salvage_expose_mode_labels(
        payload,
        fusion,
        user_query=(
            "What three mode labels does the autonomy-slider section "
            "tell you to expose?"
        ),
    )
    assert salvaged is not payload
    assert "Assist" in salvaged.answer_text
    assert "Auto" in salvaged.answer_text
    assert "Ask" not in salvaged.answer_text
    assert salvaged.citations[0].chunk_id == gold_id


def test_salvage_expose_modes_prefers_clean_leaf_over_parent_mojibake() -> None:
    """Mojibake triad on a clean leaf beats a parent that also holds Ask/Agent."""

    parent = verifier_passage(
        1,
        text=(
            'Figure: ôManual,ö ôAsk,ö or ôAgentö mode. '
            'Label these modes such as ôManual,ö ôAssist,ö and ôAuto,ö.'
        ),
        rank=1,
    )
    leaf = verifier_passage(
        2,
        text=(
            "from manual to assisted to autonomous. Label these modes in "
            "intuitive language, such as ôManual,ö ôAssist,ö and ôAuto,ö.\n\n"
            "Enable seamless transitions."
        ),
        rank=2,
    )
    fusion = verifier_fusion(parent, leaf)
    parent_id = str(fusion.evidence[0].chunk_id)
    leaf_id = str(fusion.evidence[1].chunk_id)
    payload = _confuser_payload(
        claim='Figure modes: "Manual," "Ask," and "Agent."',
        chunk_id=parent_id,
    )
    salvaged = salvage_expose_mode_labels(
        payload,
        fusion,
        user_query=(
            "What three mode labels does the autonomy-slider section "
            "tell you to expose?"
        ),
    )
    assert salvaged is not payload
    assert "Assist" in salvaged.answer_text
    assert "Auto" in salvaged.answer_text
    assert "Ask" not in salvaged.answer_text
    assert "\n" not in salvaged.answer_text
    assert salvaged.citations[0].chunk_id == leaf_id


def test_salvage_adas_defaults_replaces_undated_gpt4o() -> None:
    """ADAS model asks rewrite gpt-4o@0 onto the dated LLMAgentBase defaults."""

    confuser = verifier_passage(
        1,
        text='llm = ChatOpenAI(model="gpt-4o", temperature=0.0)',
        rank=1,
    )
    gold = verifier_passage(
        2,
        text=(
            "class LLMAgentBase:\n"
            "    def __init__(self, model='gpt-4o-2024-05-13', temperature=0.5):\n"
            "        self.model = model"
        ),
        rank=2,
    )
    fusion = verifier_fusion(confuser, gold)
    confuser_id = str(fusion.evidence[0].chunk_id)
    gold_id = str(fusion.evidence[1].chunk_id)
    payload = _confuser_payload(
        claim='llm = ChatOpenAI(model="gpt-4o", temperature=0.0)',
        chunk_id=confuser_id,
    )
    salvaged = salvage_adas_model_defaults(
        payload,
        fusion,
        user_query=(
            "What default model string and temperature does the ADAS "
            "LLMAgentBase example use?"
        ),
    )
    assert salvaged is not payload
    assert "gpt-4o-2024-05-13" in salvaged.answer_text
    assert "0.5" in salvaged.answer_text
    assert salvaged.citations[0].chunk_id == gold_id


def test_promote_expose_modes_pins_gold_from_pool() -> None:
    """Expose asks prepend Manual/Assist/Auto prose missing from selection."""

    confuser = _passage(1, text='Figure: "Manual," "Ask," and "Agent."')
    gold = _passage(
        2,
        text='Label these modes such as "Manual," "Assist," and "Auto".',
    )
    promoted = promote_expose_mode_passages(
        (confuser,),
        query="What mode labels should you expose on the autonomy slider?",
        pool=(confuser, gold),
        limit=3,
    )
    assert promoted[0].candidate.chunk_id == gold.candidate.chunk_id


def test_promote_adas_model_pins_dated_defaults() -> None:
    """ADAS asks prepend dated model+temperature prose from the pool."""

    confuser = _passage(1, text='ChatOpenAI(model="gpt-4o", temperature=0.0)')
    gold = _passage(
        2,
        text="model='gpt-4o-2024-05-13', temperature=0.5 for LLMAgentBase",
    )
    promoted = promote_adas_model_passages(
        (confuser,),
        query="What default model and temperature does ADAS LLMAgentBase use?",
        pool=(confuser, gold),
        limit=3,
    )
    assert promoted[0].candidate.chunk_id == gold.candidate.chunk_id
