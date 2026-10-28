"""Metadata checks prevent a verified answer from denying its own native image."""

from __future__ import annotations

import pytest
from smart_rag_core.query_answer.deterministic import deterministic_check_answer
from smart_rag_core.query_answer.models import (
    AnswerCitation,
    AnswerParagraph,
    AnswerPayload,
    AtomicLink,
)

from tests.support.answer_verifier import verifier_fusion, verifier_passage


@pytest.mark.parametrize("available", [True, False])
def test_image_unavailable_claim_is_checked_against_its_own_source(
    available: bool,
) -> None:
    """Only an authorized cited image can invalidate an availability disclaimer."""
    caption = "Figure 3-4. The autonomy slider."
    passage = verifier_passage(71, text=caption).model_copy(
        update={"content_kind": "figure", "figure_id": "a" * 32 if available else None}
    )
    claim = "I can\u2019t include the original image because only a textual description was supplied."
    payload = AnswerPayload(
        answer_text=claim,
        paragraphs=(
            AnswerParagraph(paragraph_index=0, text=claim, link_ids=("availability",)),
        ),
        atomic_links=(
            AtomicLink(
                link_id="availability", claim=claim, chunk_ids=(passage.chunk_id,)
            ),
        ),
        citations=(
            AnswerCitation(
                chunk_id=passage.chunk_id,
                span=caption,
                atomic_link_id="availability",
                paragraph_index=0,
            ),
        ),
    )
    checked, failures = deterministic_check_answer(
        payload, fusion=verifier_fusion(passage), tables=(), require_paragraphs=True
    )
    assert ("figure_availability_mismatch" in failures) is available
    if available:
        assert claim not in checked.answer_text
        assert checked.status == "refused"
        assert checked.citations == ()
    else:
        assert checked.answer_text == claim
