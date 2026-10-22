"""Regressions for figures lost when all six prose slots are occupied."""

from __future__ import annotations

import pytest
from smart_rag_core.query_answer.figure_placement import (
    figure_caption_text,
    place_owned_figures,
)
from smart_rag_core.query_answer.models import (
    AnswerCitation,
    AnswerParagraph,
    AnswerPayload,
    AtomicLink,
)
from smart_rag_core.query_answer.native_blocks import attach_native_evidence
from smart_rag_core.query_fusion.models import FusionResult

from tests.support.answer_verifier import verifier_fusion, verifier_passage


def test_figure_caption_excludes_a_preceding_pdf_code_comment() -> None:
    """An exact caption suffix survives without unrelated page contents."""
    caption = "Figure 3-2. Agent control.\nA labeled diagram."
    assert figure_caption_text("# helper for completions\n" + caption) == caption
    assert figure_caption_text(caption) == caption


def fixture_answer() -> tuple[AnswerPayload, FusionResult]:
    """Build six checked claims, including one claim owning a diagram."""
    figure = verifier_passage(42, text="Figure 3-4. Component diagram.").model_copy(
        update={"content_kind": "figure", "figure_id": "a" * 32}
    )
    paragraphs = tuple(
        AnswerParagraph(
            paragraph_index=i, text=f"Checked claim {i}.", link_ids=(f"c{i}",)
        )
        for i in range(6)
    )
    payload = AnswerPayload(
        answer_text="\n\n".join(p.text for p in paragraphs),
        paragraphs=paragraphs,
        atomic_links=tuple(
            AtomicLink(link_id=f"c{i}", claim=p.text, chunk_ids=(figure.chunk_id,))
            for i, p in enumerate(paragraphs)
        ),
        citations=(
            AnswerCitation(
                chunk_id=figure.chunk_id,
                span=figure.citation_text,
                paragraph_index=2,
                atomic_link_id="c2",
            ),
        ),
        status="complete",
    )
    return payload, verifier_fusion(figure)


def test_six_claims_keep_owned_figure_without_eviction() -> None:
    """A diagram keeps its actual owner and all six existing prose claims."""
    payload, fusion = fixture_answer()
    result = attach_native_evidence(payload, fusion, user_query="Include Figure 3-4.")
    assert len(result.paragraphs) == 6
    assert all(p.text in result.answer_text for p in payload.paragraphs)
    assert result.paragraphs[2].text.endswith("[[figure:" + "a" * 32 + "]]")
    assert result.citations == payload.citations
    assert result.atomic_links == payload.atomic_links
    assert result.status == "complete"
    assert (
        attach_native_evidence(result, fusion, user_query="Include Figure 3-4.")
        == result
    )


@pytest.mark.parametrize("missing", ["citation", "link", "wrong_paragraph"])
def test_no_placement_without_both_owners(missing: str) -> None:
    """Neither a citation nor a link alone establishes paragraph ownership."""
    payload, fusion = fixture_answer()
    if missing == "citation":
        payload = payload.model_copy(update={"citations": ()})
    elif missing == "link":
        payload = payload.model_copy(update={"atomic_links": ()})
    else:
        payload = payload.model_copy(
            update={
                "citations": (
                    payload.citations[0].model_copy(update={"paragraph_index": 1}),
                )
            }
        )
    assert place_owned_figures(payload, fusion) == payload


def test_explicit_other_figure_is_not_placed() -> None:
    """A numbered request cannot display a different cited diagram."""
    payload, fusion = fixture_answer()
    result = attach_native_evidence(payload, fusion, user_query="Include Figure 3-5.")
    assert "[[figure:" not in result.answer_text


def test_paragraph_character_ceiling_is_preserved() -> None:
    """A full paragraph stays bounded even when its figure is requested."""
    payload, fusion = fixture_answer()
    paragraphs = list(payload.paragraphs)
    paragraphs[2] = paragraphs[2].model_copy(update={"text": "x" * 4000})
    payload = payload.model_copy(
        update={
            "paragraphs": tuple(paragraphs),
            "answer_text": "\n\n".join(p.text for p in paragraphs),
        }
    )
    assert place_owned_figures(payload, fusion) == payload


def test_terse_prose_keeps_full_source_description_and_exact_citation() -> None:
    """A short generated claim cannot hide the component names in the diagram."""
    payload, fusion = fixture_answer()
    caption = "Figure 3-4. Components: Controller, Model, Memory, Tools."
    figure = fusion.evidence[0].model_copy(update={"citation_text": caption})
    fusion = fusion.model_copy(update={"evidence": (figure,)})
    payload = payload.model_copy(
        update={
            "citations": (
                payload.citations[0].model_copy(update={"span": "Figure 3-4."}),
            )
        }
    )
    result = attach_native_evidence(payload, fusion, user_query="Include Figure 3-4.")
    assert caption in result.paragraphs[2].text
    assert len(result.citations) == 2
    assert result.citations[-1].span == caption
    assert result.citations[-1].atomic_link_id == "c2"
    assert result.citations[-1].paragraph_index == 2


def test_full_citation_capacity_does_not_add_uncited_description() -> None:
    """A diagram description cannot exceed the existing citation ceiling."""
    payload, fusion = fixture_answer()
    citations = tuple(
        payload.citations[0].model_copy(update={"span": f"short-{i}"})
        for i in range(12)
    )
    payload = payload.model_copy(update={"citations": citations})
    assert place_owned_figures(payload, fusion) == payload
