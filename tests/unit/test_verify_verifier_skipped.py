"""Verifier failures release the checked answer instead of a deadline."""

from __future__ import annotations

from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from smart_rag_agents.query.state import QueryGraphState
from smart_rag_core.query_admission.exceptions import QueryAdmissionError
from smart_rag_core.query_answer.citations import CitationPersistResult
from smart_rag_core.query_answer.exceptions import AnswerError
from smart_rag_core.query_answer.models import (
    AnswerCitation,
    AnswerParagraph,
    AnswerPayload,
    AtomicLink,
)
from smart_rag_core.security.identity import UserRole

from tests.support.answer_verifier import verifier_fusion, verifier_passage


def _verified_state() -> QueryGraphState:
    """Build one company answer that passes deterministic citation checks.

    Returns:
        Graph state with fusion and a cited paragraph.
    """

    from smart_rag_agents.query.state import pending_query_state

    fusion = verifier_fusion(verifier_passage(1, text="Refund period is 30 days."))
    chunk_id = fusion.evidence[0].chunk_id
    state = pending_query_state(user_query="What is the refund period?")
    state["status"] = "answered"
    state["remaining_model_calls"] = 8
    state["fusion"] = fusion.model_dump(mode="json")
    state["answer"] = AnswerPayload(
        answer_text="Refund period is 30 days.",
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
                span="Refund period is 30 days.",
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
    ).model_dump(mode="json")
    return state


def _run_skipped(
    monkeypatch: pytest.MonkeyPatch, reason: str
) -> tuple[QueryGraphState, MagicMock]:
    """Run verify with a failing verifier and a recording citation persist.

    Args:
        monkeypatch: Pytest patcher.
        reason: ``AnswerError`` reason raised by the verifier batch.

    Returns:
        Node state and the persist mock.
    """

    from smart_rag_agents.query.deps import QueryGraphDeps
    from smart_rag_agents.query.nodes.verify import verify_answer_node

    runtime = MagicMock()
    runtime.user_id = uuid4()
    runtime.role = UserRole.MEMBER
    runtime.authorization_version = 1
    runtime.session_id = None
    runtime.run_id = uuid4()

    def _runtime_from_state(_state: object) -> MagicMock:
        """Return the mocked runtime regardless of graph state."""

        return runtime

    def _keep_remaining(remaining: int) -> int:
        """Skip the model-call ceiling for this unit test.

        Args:
            remaining: Calls left on the run.

        Returns:
            The same count.
        """

        return remaining

    monkeypatch.setattr(
        "smart_rag_agents.query.nodes.verify.runtime_from_state",
        _runtime_from_state,
    )
    monkeypatch.setattr(
        "smart_rag_agents.query.nodes.verify.summarize_run_usage",
        MagicMock(side_effect=QueryAdmissionError("database_rejected")),
    )
    monkeypatch.setattr(
        "smart_rag_agents.query.nodes.verify.run_verifier_batch",
        MagicMock(side_effect=AnswerError(reason)),
    )
    monkeypatch.setattr(
        "smart_rag_agents.query.nodes.verify.assert_call_available",
        _keep_remaining,
    )
    persist = MagicMock(return_value=CitationPersistResult())
    monkeypatch.setattr(
        "smart_rag_agents.query.nodes.verify.maybe_persist_verified_citations",
        persist,
    )
    verified = verify_answer_node(
        _verified_state(),
        QueryGraphDeps(
            connection=MagicMock(),
            model_gateway=MagicMock(),
            verifier_prompt_text="verifier",
        ),
    )
    return verified, persist


def test_verifier_deadline_releases_checked_answer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A verifier deadline keeps the checked answer and persists citations."""

    verified, persist = _run_skipped(monkeypatch, "deadline_exhausted")
    assert verified["status"] == "verified_partial"
    assert verified["detail"] == "verifier_skipped:deadline_exhausted"
    verification = verified["verification"]
    assert isinstance(verification, dict)
    assert verification["verifier_skipped_reason"] == "deadline_exhausted"
    assert verification["status"] == "verified_partial"
    timings = verified["run_timings"]
    assert isinstance(timings, dict)
    assert timings["verifier_outcome"] == "skipped"
    assert timings["verifier_reason"] == "deadline_exhausted"
    assert isinstance(timings["verifier_ms"], int)
    persist.assert_called_once()


def test_verifier_success_records_ok_timing(monkeypatch: pytest.MonkeyPatch) -> None:
    """A completed verifier batch records an ok timing."""

    from smart_rag_agents.query.deps import QueryGraphDeps
    from smart_rag_agents.query.nodes.verify import verify_answer_node

    state = _verified_state()

    def _batch(
        checked: object, **_kwargs: object
    ) -> tuple[object, int, tuple[str, ...]]:
        """Return the checked answer as if the verifier agreed."""

        return checked, 1, ()

    monkeypatch.setattr(
        "smart_rag_agents.query.nodes.verify.run_verifier_batch",
        _batch,
    )
    monkeypatch.setattr(
        "smart_rag_agents.query.nodes.verify.maybe_persist_verified_citations",
        MagicMock(return_value=CitationPersistResult()),
    )
    monkeypatch.setattr(
        "smart_rag_agents.query.nodes.verify.summarize_run_usage",
        MagicMock(side_effect=QueryAdmissionError("database_rejected")),
    )
    verified = verify_answer_node(
        state,
        QueryGraphDeps(connection=None, model_gateway=None, verifier_prompt_text=""),
    )
    timings = verified["run_timings"]
    assert isinstance(timings, dict)
    assert timings["verifier_outcome"] == "ok"
    assert "verifier_reason" not in timings


def test_verifier_gateway_failure_uses_the_same_prefix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Other verifier failures use the same non-deadline detail prefix."""

    verified, _persist = _run_skipped(monkeypatch, "gateway_failed")
    assert verified["detail"] == "verifier_skipped:gateway_failed"


def test_unexpected_verifier_exception_releases_the_draft(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An unexpected verifier exception returns the generated draft."""

    from smart_rag_agents.query.deps import QueryGraphDeps
    from smart_rag_agents.query.nodes.verify import verify_answer_node

    monkeypatch.setattr(
        "smart_rag_agents.query.nodes.verify.run_verifier_batch",
        MagicMock(side_effect=RuntimeError("verifier blew up")),
    )
    monkeypatch.setattr(
        "smart_rag_agents.query.nodes.verify.summarize_run_usage",
        MagicMock(side_effect=QueryAdmissionError("database_rejected")),
    )
    persist = MagicMock(return_value=CitationPersistResult())
    monkeypatch.setattr(
        "smart_rag_agents.query.nodes.verify.maybe_persist_verified_citations",
        persist,
    )
    verified = verify_answer_node(
        _verified_state(),
        QueryGraphDeps(connection=MagicMock(), model_gateway=None),
    )
    assert verified["status"] == "verified_partial"
    assert verified["detail"] == "verifier_skipped:RuntimeError"
    answer = verified["answer"]
    assert isinstance(answer, dict)
    assert answer["answer_text"] == "Refund period is 30 days."
    persist.assert_not_called()
