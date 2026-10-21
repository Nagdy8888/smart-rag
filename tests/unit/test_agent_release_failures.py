"""Fault injection across the actual verifier-to-SSE release boundary."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from smart_rag_agents.query.deps import QueryGraphDeps
from smart_rag_agents.query.nodes.organize import organize_answer_node
from smart_rag_agents.query.nodes.verify import verify_answer_node
from smart_rag_api.services.query_sse_mapping import QuerySseMapper
from smart_rag_core.query_admission.exceptions import QueryAdmissionError
from smart_rag_core.query_answer.citations import CitationPersistResult
from smart_rag_core.query_answer.exceptions import AnswerError
from smart_rag_core.query_answer.models import (
    AnswerPayload,
    VerifierLinkVerdict,
    VerifierPayload,
)
from smart_rag_core.query_answer.verifier import run_verifier_batch

from tests.support.answer_verifier import verified_answer_state

FAULT_STAGES = (
    "bind_company_atomic_links",
    "deterministic_check_answer",
    "run_verifier_batch",
    "company_release_payload",
    "maybe_persist_verified_citations",
)


@pytest.mark.parametrize("stage", FAULT_STAGES)
@pytest.mark.parametrize("error_type", [ValueError, RuntimeError, AnswerError])
def test_checker_failure_never_releases_draft(
    monkeypatch: pytest.MonkeyPatch, stage: str, error_type: type[Exception]
) -> None:
    """Every failed trust boundary emits a safe refusal, not source claims."""
    state = verified_answer_state()
    original = AnswerPayload.model_validate(state["answer"])
    monkeypatch.setattr(
        "smart_rag_agents.query.nodes.verify.maybe_persist_verified_citations",
        MagicMock(return_value=CitationPersistResult()),
    )
    monkeypatch.setattr(
        f"smart_rag_agents.query.nodes.verify.{stage}",
        MagicMock(side_effect=error_type("synthetic_internal_secret")),
    )
    result = verify_answer_node(state, QueryGraphDeps())
    answer = AnswerPayload.model_validate(result["answer"])
    assert result["status"] == "refused"
    assert answer.status == "refused"
    assert answer.answer_text != original.answer_text
    assert "synthetic_internal_secret" not in answer.answer_text
    assert not answer.citations
    assert not answer.table_citations
    assert not answer.web_citations
    assert not answer.atomic_links
    assert not answer.paragraphs
    assert answer.composed_conclusion is None
    verification = result["verification"]
    assert isinstance(verification, dict)
    assert verification["answer"] == result["answer"]

    mapper = QuerySseMapper()
    mapper.consume_chunk({"generate_answer": dict(state)})
    mapper.consume_chunk({"verify_answer": dict(result)})
    final = organize_answer_node(result, QueryGraphDeps())
    events = mapper.consume_chunk({"organize_answer": dict(final)})
    emitted = "".join(
        str(body["delta"]) for kind, body in events if kind == "token_delta"
    )
    assert original.answer_text not in emitted
    assert "synthetic_internal_secret" not in emitted
    assert [kind for kind, _ in events].count("partial") == 1
    assert not any(kind == "citations" for kind, _ in events)


def test_storage_rejection_never_releases_checked_prose(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A denied database write cannot become a verified uncited answer."""
    monkeypatch.setattr(
        "smart_rag_agents.query.nodes.verify.maybe_persist_verified_citations",
        MagicMock(side_effect=QueryAdmissionError("authorization_rejected")),
    )
    result = verify_answer_node(verified_answer_state(), QueryGraphDeps())
    assert result["status"] == "refused"
    assert result["detail"] == "verification_unavailable:citation_persist_failed"
    assert not AnswerPayload.model_validate(result["answer"]).citations


def test_mapper_does_not_resurrect_a_draft_after_invalid_verification() -> None:
    """Malformed verifier output cannot fall back to an earlier model draft."""
    state = verified_answer_state()
    mapper = QuerySseMapper()
    mapper.consume_chunk({"generate_answer": dict(state)})
    mapper.consume_chunk(
        {"verify_answer": {"status": "verified", "answer": {"bad": 1}}}
    )
    events = mapper.consume_chunk({"organize_answer": dict(state)})
    assert not any(kind == "token_delta" for kind, _ in events)
    assert any(kind == "error" for kind, _ in events)


def test_mapper_releases_only_the_verifiers_frozen_payload() -> None:
    """A later node cannot substitute a different answer at the release gate."""
    state = verified_answer_state()
    mapper = QuerySseMapper()
    mapper.consume_chunk({"verify_answer": dict(state)})
    altered = {**state, "answer": {"answer_text": "unsafe replacement"}}
    events = mapper.consume_chunk({"organize_answer": altered})
    emitted = "".join(
        str(body["delta"]) for kind, body in events if kind == "token_delta"
    )
    assert emitted == "Refund period is 30 days."


@pytest.mark.parametrize(
    "verdict_ids", [(), ("foreign",), ("l1", "l1"), ("l1", "foreign")]
)
def test_verifier_verdicts_must_match_the_selected_claims(
    verdict_ids: tuple[str, ...],
) -> None:
    """Missing, duplicate, and invented verdict IDs cannot imply support."""
    payload = AnswerPayload.model_validate(verified_answer_state()["answer"])

    def verdicts(_links: object) -> VerifierPayload:
        return VerifierPayload(
            link_verdicts=tuple(
                VerifierLinkVerdict(link_id=key, supported=True, reason="ok")
                for key in verdict_ids
            )
        )

    with pytest.raises(AnswerError, match="verifier_verdict_mismatch"):
        run_verifier_batch(payload, caller=verdicts, already_called=0)
