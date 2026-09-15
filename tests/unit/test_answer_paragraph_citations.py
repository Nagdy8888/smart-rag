"""Paragraph mappings, exact spans, and fail-closed company verification."""

from __future__ import annotations

from pathlib import Path

from smart_rag_agents.prompts.registry import load_prompt, prompt_text
from smart_rag_agents.query.nodes import verify as verify_mod
from smart_rag_core.query_answer.deterministic import deterministic_check_answer
from smart_rag_core.query_answer.generate import mock_answer_payload
from smart_rag_core.query_answer.models import (
    AnswerCitation,
    AnswerParagraph,
    AnswerPayload,
    AtomicLink,
    VerifierLinkVerdict,
    VerifierPayload,
)
from smart_rag_core.query_answer.schemas import (
    answer_json_schema,
    general_chat_json_schema,
)
from smart_rag_core.query_answer.verifier import (
    apply_verifier_payload,
    run_verifier_batch,
)
from smart_rag_core.query_answer.versions import (
    ANSWER_PROMPT_SHA256,
    ANSWER_PROMPT_VERSION,
    MAX_ANSWER_CITATIONS,
    MAX_VERIFIER_LINKS,
)
from smart_rag_core.query_routing.knowledge_scope import KnowledgeScope

from tests.support.answer_verifier import (
    verifier_fusion,
    verifier_passage,
    verifier_prompt_digest,
    verifier_table,
)

VERIFY_SOURCE = (
    Path(__file__).resolve().parents[2]
    / "apps"
    / "agents"
    / "src"
    / "smart_rag_agents"
    / "query"
    / "nodes"
    / "verify.py"
)


def _mapped_payload() -> tuple[AnswerPayload, object, tuple[object, ...]]:
    """Return two grounded paragraphs citing two different chunks.

    Returns:
        Payload, fusion, and empty tables.
    """

    fusion = verifier_fusion(
        verifier_passage(1, text="Atlas Controller ships in Q3."),
        verifier_passage(2, text="North revenue is 10 USD."),
    )
    first = fusion.evidence[0].chunk_id
    second = fusion.evidence[1].chunk_id
    payload = AnswerPayload(
        paragraphs=(
            AnswerParagraph(
                paragraph_index=0,
                text="Atlas Controller ships in Q3.",
                link_ids=("l1",),
            ),
            AnswerParagraph(
                paragraph_index=1,
                text="North revenue is 10 USD.",
                link_ids=("l2",),
            ),
        ),
        citations=(
            AnswerCitation(
                chunk_id=first,
                span="Atlas Controller ships in Q3.",
                paragraph_index=0,
                atomic_link_id="l1",
            ),
            AnswerCitation(
                chunk_id=second,
                span="North revenue is 10 USD.",
                paragraph_index=1,
                atomic_link_id="l2",
            ),
        ),
        atomic_links=(
            AtomicLink(
                link_id="l1",
                claim="Atlas Controller ships in Q3.",
                chunk_ids=(first,),
                kind="fact",
                priority=1,
            ),
            AtomicLink(
                link_id="l2",
                claim="North revenue is 10 USD.",
                chunk_ids=(second,),
                kind="fact",
                priority=2,
            ),
        ),
        status="complete",
        answer_origin=KnowledgeScope.COMPANY_DOCUMENTS,
    )
    return payload, fusion, ()


def test_answer_v2_is_registered_and_hashed() -> None:
    """Pinned answer_v2 hash matches the immutable prompt file."""

    entry = load_prompt("answer_v2", environment="dev")
    assert ANSWER_PROMPT_VERSION == "answer_v2"
    assert entry.sha256 == ANSWER_PROMPT_SHA256
    assert ANSWER_PROMPT_SHA256 == verifier_prompt_digest("answer_v2.md")
    body = prompt_text("answer_v2")
    assert "Do not author `answer_text`" in body
    schema = answer_json_schema()
    assert "answer_text" not in schema["properties"]
    assert "paragraphs" in schema["required"]
    general = general_chat_json_schema()
    assert "paragraphs" not in general["properties"]
    assert "answer_text" in general["required"]


def test_two_paragraphs_map_to_two_chunks() -> None:
    """Each paragraph cites a distinct canonical chunk."""

    payload, fusion, tables = _mapped_payload()
    checked, failures = deterministic_check_answer(
        payload,
        fusion=fusion,
        tables=tables,
        require_paragraphs=True,
    )
    assert failures == ()
    assert checked.status == "complete"
    assert checked.answer_text == (
        "Atlas Controller ships in Q3.\n\nNorth revenue is 10 USD."
    )
    assert {item.chunk_id for item in checked.citations} == {
        fusion.evidence[0].chunk_id,
        fusion.evidence[1].chunk_id,
    }


def test_two_citations_can_attach_to_one_paragraph() -> None:
    """One paragraph may list two links with two exact spans."""

    fusion = verifier_fusion(
        verifier_passage(1, text="Alpha clause. Beta clause."),
        verifier_passage(2, text="Gamma clause remains."),
    )
    payload = AnswerPayload(
        paragraphs=(
            AnswerParagraph(
                paragraph_index=0,
                text="Alpha and Gamma are both in force.",
                link_ids=("l1", "l2"),
            ),
        ),
        citations=(
            AnswerCitation(
                chunk_id=fusion.evidence[0].chunk_id,
                span="Alpha clause.",
                paragraph_index=0,
                atomic_link_id="l1",
            ),
            AnswerCitation(
                chunk_id=fusion.evidence[1].chunk_id,
                span="Gamma clause remains.",
                paragraph_index=0,
                atomic_link_id="l2",
            ),
        ),
        atomic_links=(
            AtomicLink(
                link_id="l1",
                claim="Alpha clause.",
                chunk_ids=(fusion.evidence[0].chunk_id,),
            ),
            AtomicLink(
                link_id="l2",
                claim="Gamma clause remains.",
                chunk_ids=(fusion.evidence[1].chunk_id,),
            ),
        ),
        status="complete",
    )
    checked, failures = deterministic_check_answer(
        payload,
        fusion=fusion,
        tables=(),
        require_paragraphs=True,
    )
    assert failures == ()
    assert len(checked.citations) == 2
    assert checked.paragraphs[0].link_ids == ("l1", "l2")


def test_missing_mapping_refuses_company_answer() -> None:
    """Live company answers without paragraphs become citation-free refusals."""

    fusion = verifier_fusion(verifier_passage(1, text="Refund period is 30 days."))
    payload = AnswerPayload(
        answer_text="Refund period is 30 days.",
        citations=(AnswerCitation(chunk_id=fusion.evidence[0].chunk_id),),
        atomic_links=(
            AtomicLink(
                link_id="l1",
                claim="Refund period is 30 days.",
                chunk_ids=(fusion.evidence[0].chunk_id,),
            ),
        ),
        status="complete",
    )
    checked, failures = deterministic_check_answer(
        payload,
        fusion=fusion,
        tables=(),
        require_paragraphs=True,
    )
    assert "paragraph_unmapped" in failures
    assert checked.status == "refused"
    assert checked.paragraphs == ()
    assert checked.citations == ()
    assert checked.answer_text == "Insufficient authorized evidence."


def test_null_or_empty_span_fails_closed() -> None:
    """Null and empty spans cannot ground a company paragraph."""

    fusion = verifier_fusion(verifier_passage(1, text="Refund period is 30 days."))
    chunk_id = fusion.evidence[0].chunk_id
    payload = AnswerPayload(
        paragraphs=(
            AnswerParagraph(
                paragraph_index=0,
                text="Refund period is 30 days.",
                link_ids=("l1",),
            ),
        ),
        citations=(
            AnswerCitation(
                chunk_id=chunk_id,
                span=None,
                paragraph_index=0,
                atomic_link_id="l1",
            ),
        ),
        atomic_links=(
            AtomicLink(
                link_id="l1",
                claim="Refund period is 30 days.",
                chunk_ids=(chunk_id,),
            ),
        ),
        status="complete",
    )
    checked, failures = deterministic_check_answer(
        payload,
        fusion=fusion,
        tables=(),
        require_paragraphs=True,
    )
    assert "citation_span_required" in failures
    assert checked.status == "refused"


def test_span_chunk_mismatch_fails_closed() -> None:
    """A span that is not a substring of the cited chunk is dropped."""

    payload, fusion, tables = _mapped_payload()
    broken = payload.citations[0].model_copy(update={"span": "not in the passage"})
    payload = payload.model_copy(update={"citations": (broken, payload.citations[1])})
    checked, failures = deterministic_check_answer(
        payload,
        fusion=fusion,
        tables=tables,
        require_paragraphs=True,
    )
    assert "citation_span_mismatch" in failures
    assert checked.answer_text == "North revenue is 10 USD."
    assert len(checked.paragraphs) == 1
    assert checked.paragraphs[0].paragraph_index == 0
    assert checked.status == "partial"


def test_citation_link_paragraph_disagreement_fails_closed() -> None:
    """Citations must name a link that belongs to the cited paragraph."""

    payload, fusion, tables = _mapped_payload()
    mismatched = payload.citations[0].model_copy(update={"atomic_link_id": "l2"})
    payload = payload.model_copy(update={"citations": (mismatched,)})
    checked, failures = deterministic_check_answer(
        payload,
        fusion=fusion,
        tables=tables,
        require_paragraphs=True,
    )
    assert "citation_link_mismatch" in failures or "paragraph_unmapped" in failures
    assert checked.status == "refused"


def test_unsupported_verifier_link_drops_paragraph() -> None:
    """Verifier rejection removes the owning paragraph and citations."""

    payload, fusion, _tables = _mapped_payload()
    checked, _failures = deterministic_check_answer(
        payload,
        fusion=fusion,
        tables=(),
        require_paragraphs=True,
    )
    updated = apply_verifier_payload(
        checked,
        VerifierPayload(
            link_verdicts=(
                VerifierLinkVerdict(
                    link_id="l1", supported=False, reason="unsupported_link"
                ),
                VerifierLinkVerdict(link_id="l2", supported=True, reason="supported"),
            )
        ),
    )
    assert updated.status == "partial"
    assert updated.answer_text == "North revenue is 10 USD."
    assert tuple(item.link_id for item in updated.atomic_links) == ("l2",)
    assert "Refund" not in updated.answer_text
    assert "Atlas Controller ships in Q3." not in updated.answer_text


def test_all_paragraphs_removed_is_citation_free_refusal() -> None:
    """Dropping every paragraph replaces original prose with a refusal."""

    payload, fusion, _tables = _mapped_payload()
    checked, _failures = deterministic_check_answer(
        payload,
        fusion=fusion,
        tables=(),
        require_paragraphs=True,
    )
    updated = apply_verifier_payload(
        checked,
        VerifierPayload(
            link_verdicts=(
                VerifierLinkVerdict(
                    link_id="l1", supported=False, reason="unsupported_link"
                ),
                VerifierLinkVerdict(
                    link_id="l2", supported=False, reason="unsupported_link"
                ),
            )
        ),
    )
    assert updated.status == "refused"
    assert updated.paragraphs == ()
    assert updated.citations == ()
    assert updated.answer_text == "Insufficient authorized evidence."


def test_seventh_link_and_thirteenth_citation_fail_bounds() -> None:
    """Seven links or thirteen citations refuse the company answer."""

    fusion = verifier_fusion(verifier_passage(1, text="Bound check passage."))
    chunk_id = fusion.evidence[0].chunk_id
    links = tuple(
        AtomicLink(
            link_id=f"l{index}",
            claim="Bound check passage.",
            chunk_ids=(chunk_id,),
            priority=index,
        )
        for index in range(MAX_VERIFIER_LINKS + 1)
    )
    payload = AnswerPayload(
        paragraphs=(
            AnswerParagraph(
                paragraph_index=0,
                text="Bound check passage.",
                link_ids=("l0",),
            ),
        ),
        citations=(
            AnswerCitation(
                chunk_id=chunk_id,
                span="Bound check passage.",
                paragraph_index=0,
                atomic_link_id="l0",
            ),
        ),
        atomic_links=links,
        status="complete",
    )
    checked, failures = deterministic_check_answer(
        payload,
        fusion=fusion,
        tables=(),
        require_paragraphs=True,
    )
    assert "answer_bounds_exceeded" in failures
    assert checked.status == "refused"
    extra_citations = tuple(
        AnswerCitation(
            chunk_id=chunk_id,
            span="Bound check passage.",
            paragraph_index=0,
            atomic_link_id="l0",
        )
        for _ in range(MAX_ANSWER_CITATIONS + 1)
    )
    crowded = payload.model_copy(
        update={
            "atomic_links": links[:MAX_VERIFIER_LINKS],
            "citations": extra_citations,
        }
    )
    crowded_checked, crowded_failures = deterministic_check_answer(
        crowded,
        fusion=fusion,
        tables=(),
        require_paragraphs=True,
    )
    assert "answer_bounds_exceeded" in crowded_failures
    assert crowded_checked.status == "refused"


def test_general_and_web_payloads_remain_unaffected() -> None:
    """General and Web answers do not require company paragraph mappings."""

    fusion = verifier_fusion(verifier_passage(1, text="Company only."))
    general = AnswerPayload(
        answer_text="Hello from general knowledge.",
        status="complete",
        answer_origin=KnowledgeScope.GENERAL_KNOWLEDGE,
    )
    checked, failures = deterministic_check_answer(
        general,
        fusion=fusion,
        tables=(),
        evidence_required=False,
        require_paragraphs=False,
    )
    assert failures == ()
    assert checked.answer_text == "Hello from general knowledge."
    assert checked.paragraphs == ()


def test_mock_answer_emits_exact_spans() -> None:
    """Extractive mocks copy exact spans from canonical citation text."""

    fusion = verifier_fusion(verifier_passage(1, text="The refund period is 30 days."))
    payload = mock_answer_payload(fusion, (), user_query="refund")
    assert payload.paragraphs
    assert payload.citations[0].span == "The refund period is 30 days."
    checked, failures = deterministic_check_answer(
        payload,
        fusion=fusion,
        tables=(),
        require_paragraphs=True,
    )
    assert failures == ()
    assert checked.status == "complete"


def test_table_paragraph_uses_exact_ranges() -> None:
    """Mock table paragraphs keep sandbox source ranges."""

    fusion = verifier_fusion()
    table = verifier_table()
    payload = mock_answer_payload(fusion, (table,), user_query="revenue")
    assert payload.table_citations
    assert payload.table_citations[0].source_ranges == table.source_ranges
    checked, failures = deterministic_check_answer(
        payload,
        fusion=fusion,
        tables=(table,),
        require_paragraphs=True,
    )
    assert failures == ()
    assert checked.status == "complete"


def test_live_verify_path_does_not_backfill_fusion_citations() -> None:
    """Production verify must not cite every retrieved fusion passage."""

    source = VERIFY_SOURCE.read_text(encoding="utf-8")
    assert "ensure_fusion_source_citations" not in source
    assert not hasattr(verify_mod, "ensure_fusion_source_citations")


def test_mock_caps_links_within_verifier_batch() -> None:
    """Extractive mocks never emit a seventh atomic link."""

    fusion = verifier_fusion(
        *(
            verifier_passage(index, text=f"Fact {index} stays in the book.")
            for index in range(1, 8)
        )
    )
    payload = mock_answer_payload(fusion, (), user_query="facts")
    assert len(payload.atomic_links) <= MAX_VERIFIER_LINKS
    assert len(payload.paragraphs) <= MAX_VERIFIER_LINKS
    checked, failures = deterministic_check_answer(
        payload,
        fusion=fusion,
        tables=(),
        require_paragraphs=True,
    )
    assert failures == ()
    assert checked.status == "complete"


def test_run_verifier_batch_still_one_call() -> None:
    """Paragraph verification does not add a second verifier call."""

    payload, _fusion, _tables = _mapped_payload()
    calls = {"count": 0}

    def _caller(links: tuple[AtomicLink, ...]) -> VerifierPayload:
        """Count verifier invocations.

        Args:
            links: Selected batch.

        Returns:
            Identity-support verdicts.
        """

        calls["count"] += 1
        return VerifierPayload(
            link_verdicts=tuple(
                VerifierLinkVerdict(
                    link_id=item.link_id, supported=True, reason="supported"
                )
                for item in links
            )
        )

    updated, call_count, omitted = run_verifier_batch(
        payload,
        caller=_caller,
        already_called=0,
    )
    assert call_count == 1
    assert calls["count"] == 1
    assert omitted == ()
    assert updated.status == "complete"
