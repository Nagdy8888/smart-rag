"""Multi-part figure salvage when the model omits rates present in evidence."""

from __future__ import annotations

from smart_rag_core.query_answer.generate_grounded import (
    generate_grounded_answer,
    is_multipart_figure_ask,
    salvage_missing_multipart_figures,
)
from smart_rag_core.query_answer.models import (
    AnswerCitation,
    AnswerParagraph,
    AnswerPayload,
    AtomicLink,
)
from smart_rag_core.query_routing.knowledge_scope import KnowledgeScope

from tests.support.answer_verifier import verifier_fusion, verifier_passage, verifier_uid

H08_QUERY = (
    "What speaking rate, reading rate, and skimming rate does the "
    "voice-interface section give for humans?"
)
H08_EVIDENCE = (
    "Humans typically speak at 150–180 words per minute, read at "
    "250–300 words per minute, and skim at about 500 words per minute."
)
H45_QUERY = (
    "What share of AI-related data breaches does the book say Gartner "
    "predicts by 2027 will stem from cross-border generative AI misuse, "
    "and what average incident cost does that paragraph cite?"
)
H45_EVIDENCE = (
    "Gartner predicts that by 2027 over 40% of AI-related data breaches "
    "will stem from cross-border generative AI misuse, at an average "
    "incident cost of $4.8 million."
)


def test_multipart_ask_detection() -> None:
    """Speaking/reading/skimming, share+cost, and score/rate asks are multi-part."""

    assert is_multipart_figure_ask(H08_QUERY)
    assert is_multipart_figure_ask(H45_QUERY)
    assert is_multipart_figure_ask(
        "how many candidate plans are generated, and what score must the best exceed"
    )
    assert is_multipart_figure_ask(
        "pilot size, the suggestion acceptance rate, and the developer satisfaction rate"
    )
    assert is_multipart_figure_ask(
        "Which narrow tasks excel, naming FAQs and order tracking?"
    )
    assert not is_multipart_figure_ask("What is the Redis port?")


def test_salvage_appends_omitted_rate_figures() -> None:
    """Missing reading/skimming rates are appended from fused evidence."""

    fusion = verifier_fusion(verifier_passage(1, text=H08_EVIDENCE))
    speaking = "Humans typically speak at 150–180 words per minute."
    chunk = verifier_uid(1)
    partial = AnswerPayload(
        answer_text=speaking,
        paragraphs=(
            AnswerParagraph(
                paragraph_index=0, text=speaking, link_ids=("claim-1",)
            ),
        ),
        citations=(
            AnswerCitation(
                chunk_id=chunk,
                span="150–180 words per minute",
                paragraph_index=0,
                atomic_link_id="claim-1",
            ),
        ),
        atomic_links=(
            AtomicLink(
                link_id="claim-1",
                claim=speaking,
                chunk_ids=(chunk,),
            ),
        ),
        status="partial",
        answer_origin=KnowledgeScope.COMPANY_DOCUMENTS,
    )
    completed = salvage_missing_multipart_figures(
        partial, fusion, user_query=H08_QUERY
    )
    text = completed.answer_text.lower()
    assert "250–300 words per minute" in text or "250-300 words per minute" in text
    assert "500 words per minute" in text
    assert len(completed.atomic_links) > len(partial.atomic_links)


def test_generate_grounded_appends_missing_multipart_figures() -> None:
    """generate_grounded_answer adds omitted share/cost figures after the model."""

    fusion = verifier_fusion(verifier_passage(1, text=H45_EVIDENCE))
    cost_only = "The average incident cost cited is $4.8 million."
    chunk = verifier_uid(1)

    def _partial(
        _records: str,
        _fusion: object,
        _tables: object,
    ) -> AnswerPayload:
        """Return a one-figure answer that omits the share.

        Args:
            _records: Unused assembled records.
            _fusion: Unused fusion.
            _tables: Unused tables.

        Returns:
            Partial company payload with only the cost claim.
        """

        return AnswerPayload(
            answer_text=cost_only,
            paragraphs=(
                AnswerParagraph(
                    paragraph_index=0, text=cost_only, link_ids=("claim-1",)
                ),
            ),
            citations=(
                AnswerCitation(
                    chunk_id=chunk,
                    span="$4.8 million",
                    paragraph_index=0,
                    atomic_link_id="claim-1",
                ),
            ),
            atomic_links=(
                AtomicLink(
                    link_id="claim-1",
                    claim=cost_only,
                    chunk_ids=(chunk,),
                ),
            ),
            status="partial",
            answer_origin=KnowledgeScope.COMPANY_DOCUMENTS,
        )

    payload = generate_grounded_answer(
        fusion=fusion,
        tables=(),
        user_query=H45_QUERY,
        caller=_partial,
    )
    assert "$4.8 million" in payload.answer_text
    assert "over 40%" in payload.answer_text.lower()
