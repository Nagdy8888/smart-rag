"""Deterministic verifier rules, citation spans, and provenance."""

from __future__ import annotations

import pytest
from pydantic import ValidationError
from smart_rag_core.query_answer.citations import citation_provenance_payload
from smart_rag_core.query_answer.deterministic import deterministic_check_answer
from smart_rag_core.query_answer.exceptions import AnswerError
from smart_rag_core.query_answer.generate import mock_answer_payload
from smart_rag_core.query_answer.models import (
    AnswerCitation,
    AnswerPayload,
    AtomicLink,
    ComposedConclusion,
    VerifierLinkVerdict,
    VerifierPayload,
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

from tests.support.answer_verifier import (
    verifier_fusion,
    verifier_passage,
    verifier_prompt_digest,
    verifier_table,
    verifier_uid,
)


def test_answer_and_verifier_prompt_hashes() -> None:
    """Pinned hashes match LF-normalized prompt files."""

    assert ANSWER_PROMPT_VERSION == "answer_v1"
    assert VERIFIER_PROMPT_VERSION == "verifier_v1"
    assert GENERAL_CHAT_PROMPT_VERSION == "general_chat_v1"
    assert ANSWER_PROMPT_SHA256 == verifier_prompt_digest("answer_v1.md")
    assert VERIFIER_PROMPT_SHA256 == verifier_prompt_digest("verifier_v1.md")
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
