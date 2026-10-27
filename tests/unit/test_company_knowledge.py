"""Authority policies do not infer approval or change access permissions."""

from datetime import UTC, date, datetime, timedelta
from uuid import uuid4

import pytest
from pydantic import ValidationError
from smart_rag_core.knowledge import (
    AuthorityStatus,
    DocumentGovernance,
    UpdateDocumentGovernance,
)
from smart_rag_core.retrieval.temporal import (
    TemporalDocument,
    TemporalIntent,
    apply_temporal_policy,
)
from smart_rag_core.retrieval.types import RetrievalCandidate


def candidate(rank: int) -> RetrievalCandidate:
    """Make an already-authorized candidate for policy tests."""
    return RetrievalCandidate(uuid4(), uuid4(), uuid4(), rank, 1.0)


def test_legacy_document_has_no_inferred_authority() -> None:
    """Missing metadata remains explicitly unreviewed."""
    record = DocumentGovernance()
    assert record.authority_status is AuthorityStatus.UNREVIEWED
    assert record.effective_at is None
    assert record.warnings() == ("source_unreviewed", "source_owner_missing")


@pytest.mark.parametrize("status", ["draft", "superseded", "approved"])
def test_current_filters_draft_superseded_and_future(status: str) -> None:
    """None of these rows can establish a current policy."""
    item = candidate(1)
    now = datetime(2026, 10, 25, tzinfo=UTC)
    record = TemporalDocument(
        item.chunk_id,
        effective_at=now + timedelta(days=1),
        authority_status=status,
        reliability_enabled=True,
    )
    for intent in (TemporalIntent.NONE, TemporalIntent.CURRENT, TemporalIntent.LATEST):
        assert not apply_temporal_policy(
            (item,), {item.chunk_id: record}, intent=intent, target_date=None, now=now
        )


def test_approved_rank_and_unreviewed_fallback() -> None:
    """Approved applicable rows precede unreviewed rows without dropping them."""
    unreviewed, approved = candidate(1), candidate(2)
    now = datetime(2026, 10, 25, tzinfo=UTC)
    rows = {
        unreviewed.chunk_id: TemporalDocument(
            unreviewed.chunk_id, effective_at=None, reliability_enabled=True
        ),
        approved.chunk_id: TemporalDocument(
            approved.chunk_id,
            effective_at=now,
            authority_status=AuthorityStatus.APPROVED,
            reliability_enabled=True,
        ),
    }
    assert apply_temporal_policy(
        (unreviewed, approved),
        rows,
        intent=TemporalIntent.CURRENT,
        target_date=None,
        now=now,
    ) == (approved, unreviewed)


def test_overdue_review_warns_without_expiry() -> None:
    """Overdue review is not a fabricated supersession event."""
    record = DocumentGovernance(
        owner_user_id=uuid4(),
        authority_status=AuthorityStatus.APPROVED,
        review_due_at=date(2026, 10, 1),
    )
    assert record.warnings(today=date(2026, 10, 25)) == ("source_review_overdue",)


@pytest.mark.parametrize(
    "fields",
    [
        {"authority_status": "approved"},
        {"authority_status": "superseded"},
        {"effective_at": "2026-10-25T00:00:00"},
        {"knowledge_area": " "},
    ],
)
def test_governance_rejects_ambiguous_mutations(fields: dict[str, object]) -> None:
    """Invalid authority never reaches the persistence layer."""
    with pytest.raises(ValidationError):
        UpdateDocumentGovernance.model_validate(
            {
                "version_id": str(uuid4()),
                "expected_generation": 1,
                **fields,
            }
        )


def test_disabled_flag_preserves_existing_selection() -> None:
    """Deployment may prepare metadata before enabling behavior."""
    item = candidate(1)
    row = TemporalDocument(item.chunk_id, effective_at=None, authority_status="draft")
    assert apply_temporal_policy(
        (item,), {item.chunk_id: row}, intent=TemporalIntent.NONE, target_date=None
    ) == (item,)


def test_conflict_requires_explicit_equal_scope_and_approved_sources() -> None:
    """Different countries, unreviewed prose, and equal values never become conflicts."""
    from smart_rag_core.query_answer.knowledge_conflicts import explicit_policy_conflict
    from smart_rag_core.query_fusion.models import (
        FusionAlgorithm,
        FusionResult,
        PassageOrigin,
        ScoredPassage,
    )

    documents = [str(uuid4()), str(uuid4())]
    passages = tuple(
        ScoredPassage(
            chunk_id=str(uuid4()),
            document_id=doc,
            version_id=str(uuid4()),
            citation_text=f"Scope: Egypt employees\nAnnual leave: {20 + i * 5} days",
            combined_score=1.0,
            origin=PassageOrigin.HYBRID,
            graph_discovered_only=False,
        )
        for i, doc in enumerate(documents)
    )
    fusion = FusionResult(
        algorithm=FusionAlgorithm.RESOLVED_PATH_FUSION,
        config_hash="0" * 64,
        requested_route="Hybrid",
        effective_route="Hybrid",
        evidence=passages,
        graph_discovered_only_ratio=0,
    )
    records = {
        doc: DocumentGovernance(
            authority_status=AuthorityStatus.APPROVED, knowledge_area="HR"
        )
        for doc in documents
    }
    result = explicit_policy_conflict(fusion, records)
    assert result is not None and len(result.citations) == 2
    for citation in result.citations:
        assert citation.span is not None
        assert any(
            citation.chunk_id == p.chunk_id and citation.span in p.citation_text
            for p in passages
        )
    other = passages[1].model_copy(
        update={"citation_text": "Scope: UK employees\nAnnual leave: 25 days"}
    )
    assert (
        explicit_policy_conflict(
            fusion.model_copy(update={"evidence": (passages[0], other)}), records
        )
        is None
    )
    records[documents[1]] = DocumentGovernance(
        authority_status=AuthorityStatus.UNREVIEWED, knowledge_area="HR"
    )
    assert explicit_policy_conflict(fusion, records) is None


def test_operational_failure_is_not_a_supported_knowledge_outcome() -> None:
    """The checked outcome is absent until explicitly annotated after release."""
    from smart_rag_core.query_answer.knowledge import knowledge_result
    from smart_rag_core.query_answer.models import AnswerPayload

    answer = AnswerPayload(status="refused")
    assert answer.knowledge_result is None
    assert knowledge_result(answer).outcome == "insufficient_evidence"


def test_checked_knowledge_outcome_survives_the_sse_contract() -> None:
    """The outcome sent with the answer is the checked artifact's exact metadata."""
    from smart_rag_api.services.sse.mapping.verified import emit_verified_events
    from smart_rag_core.knowledge import KnowledgeResult
    from smart_rag_core.query_answer.models import AnswerPayload
    from smart_rag_core.query_routing.knowledge_scope import KnowledgeScope

    outcome = KnowledgeResult(
        outcome="partial",
        limitations=("source_unreviewed",),
        unanswered_parts=("Eligibility",),
    )
    payload = AnswerPayload(
        answer_text="Checked text",
        status="partial",
        answer_origin=KnowledgeScope.COMPANY_DOCUMENTS,
        knowledge_result=outcome,
    )
    events, released, final = emit_verified_events(
        payload, {"status": "verified_partial"}
    )
    origin = next(data for kind, data in events if kind == "answer_origin")
    assert released and final == payload
    assert origin["knowledge_result"] == outcome.model_dump(mode="json")
    assert (
        sum(
            kind in {"completed", "partial", "error", "cancelled"} for kind, _ in events
        )
        == 1
    )
