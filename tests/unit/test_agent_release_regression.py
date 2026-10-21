"""Question-based release regression: exact content, provenance, and no extra AI."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from pydantic import BaseModel, ConfigDict, Field
from smart_rag_agents.query.deps import QueryGraphDeps
from smart_rag_agents.query.nodes.organize import organize_answer_node
from smart_rag_agents.query.nodes.verify import verify_answer_node
from smart_rag_agents.query.state import pending_query_state
from smart_rag_api.services.query_sse_mapping import QuerySseMapper
from smart_rag_core.gateways.model import VerifierModelRequest, VerifierModelResponse
from smart_rag_core.query_answer.citations import CitationPersistResult
from smart_rag_core.query_answer.models import (
    AnswerCitation,
    AnswerParagraph,
    AnswerPayload,
    AtomicLink,
)
from smart_rag_core.query_routing.knowledge_scope import KnowledgeScope

from tests.support.answer_verifier import (
    verifier_fusion,
    verifier_passage,
    verifier_uid,
)
from tests.support.query_runtime import RefusingHybridRetriever


class ReleaseCase(BaseModel):
    """One synthetic question, checked answer, and unsafe rewrite attempt."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    id: str
    question: str
    paragraphs: tuple[str, ...] = Field(min_length=1, max_length=6)
    attack: str


class ReleaseDataset(BaseModel):
    """Versioned development set; not a sealed or live-model holdout."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    version: str
    purpose: str
    cases: tuple[ReleaseCase, ...]


DATASET = ReleaseDataset.model_validate(
    json.loads(
        (Path(__file__).parents[1] / "fixtures" / "agent_release_v1.json").read_text(
            encoding="utf-8"
        )
    )
)


class RewriteTrap:
    """Offer a plausible but unsafe model rewrite if presentation calls AI."""

    def __init__(self, attack: str) -> None:
        """Keep a candidate response and a provider-send count."""
        self.attack = attack
        self.calls = 0

    async def generate_answer(self, _request: object) -> SimpleNamespace:
        """Return synthetic model output without network access."""
        self.calls += 1
        return SimpleNamespace(
            payload={"claims": [{"text": self.attack}], "status": "complete"},
            input_tokens=4,
            output_tokens=5,
        )


class SupportingVerifier:
    """Known-answer provider double; proves the real release path still works."""

    async def generate_verifier(
        self, request: VerifierModelRequest
    ) -> VerifierModelResponse:
        """Support the supplied synthetic source-exact claims, without network."""
        return VerifierModelResponse(
            mode="mock",
            request_id="release-regression",
            payload={
                "link_verdicts": [
                    {"link_id": link["link_id"], "supported": True, "reason": "exact"}
                    for link in request.links
                ]
            },
            input_tokens=17,
            output_tokens=9,
        )


@pytest.mark.parametrize("case", DATASET.cases, ids=lambda case: case.id)
def test_source_exact_answers_survive_verification_and_persistence(
    case: ReleaseCase, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Healthy questions keep source facts and persist the same released payload."""
    fusion = verifier_fusion(
        *(verifier_passage(i + 1, text=text) for i, text in enumerate(case.paragraphs))
    )
    paragraphs = tuple(
        AnswerParagraph(paragraph_index=i, text=text, link_ids=(f"claim-{i}",))
        for i, text in enumerate(case.paragraphs)
    )
    answer = AnswerPayload(
        answer_text="\n\n".join(p.text for p in paragraphs),
        paragraphs=paragraphs,
        citations=tuple(
            AnswerCitation(
                chunk_id=verifier_uid(i + 1),
                span=p.text[:1000],
                atomic_link_id=f"claim-{i}",
                paragraph_index=i,
            )
            for i, p in enumerate(paragraphs)
        ),
        atomic_links=tuple(
            AtomicLink(
                link_id=f"claim-{i}",
                claim=p.text[:2000],
                chunk_ids=(verifier_uid(i + 1),),
            )
            for i, p in enumerate(paragraphs)
        ),
        answer_origin=KnowledgeScope.COMPANY_DOCUMENTS,
        status="complete",
    )
    state = pending_query_state(user_query=case.question)
    state.update(
        status="answered",
        answer=answer.model_dump(mode="json"),
        fusion=fusion.model_dump(mode="json"),
        remaining_model_calls=2,
    )
    persist = MagicMock(return_value=CitationPersistResult(ids=(uuid4(),)))
    monkeypatch.setattr(
        "smart_rag_agents.query.nodes.verify.maybe_persist_verified_citations", persist
    )
    result = verify_answer_node(
        state,
        QueryGraphDeps(
            model_gateway=SupportingVerifier(),
            verifier_prompt_text="fixture",
            hybrid_retriever=RefusingHybridRetriever(),
        ),
    )
    assert result["status"] == "verified", result["detail"]
    released = AnswerPayload.model_validate(result["answer"])
    for paragraph in paragraphs:
        assert paragraph.text in released.answer_text
    persisted = persist.call_args.kwargs["answer"]
    assert persisted.model_dump(mode="json") == result["answer"]
    final = organize_answer_node(result, QueryGraphDeps())
    assert final["answer"] == result["answer"]
    assert len(released.citations) == len(paragraphs)
    for citation in released.citations:
        assert citation.paragraph_index is not None
        assert citation.chunk_id == verifier_uid(citation.paragraph_index + 1)


@pytest.mark.parametrize("case", DATASET.cases, ids=lambda case: case.id)
def test_checked_answer_survives_release_exactly(case: ReleaseCase) -> None:
    """Final presentation cannot change meaning, map sources, or drop blocks."""
    paragraphs = tuple(
        AnswerParagraph(paragraph_index=i, text=text, link_ids=(f"claim-{i}",))
        for i, text in enumerate(case.paragraphs)
    )
    payload = AnswerPayload(
        answer_text="\n\n".join(p.text for p in paragraphs),
        paragraphs=paragraphs,
        citations=tuple(
            AnswerCitation(
                chunk_id=verifier_uid(i + 1),
                span=p.text[:1000],
                atomic_link_id=f"claim-{i}",
                paragraph_index=i,
            )
            for i, p in enumerate(paragraphs)
        ),
        atomic_links=tuple(
            AtomicLink(
                link_id=f"claim-{i}",
                claim=p.text[:2000],
                chunk_ids=(verifier_uid(i + 1),),
            )
            for i, p in enumerate(paragraphs)
        ),
        answer_origin=KnowledgeScope.COMPANY_DOCUMENTS,
        status="complete",
    )
    state = pending_query_state(user_query=case.question)
    state.update(
        status="verified",
        answer=payload.model_dump(mode="json"),
        verification={"answer": payload.model_dump(mode="json"), "status": "verified"},
        remaining_model_calls=2,
        prompt_tokens=10,
        completion_tokens=20,
    )
    gateway = RewriteTrap(case.attack)
    result = organize_answer_node(
        state, QueryGraphDeps(model_gateway=gateway, organize_prompt_text="legacy")
    )
    assert result["answer"] == payload.model_dump(mode="json")
    assert result["verification"] == state["verification"]
    assert gateway.calls == 0
    assert result["remaining_model_calls"] == 2
    assert result["prompt_tokens"] == 10
    assert result["completion_tokens"] == 20

    mapper = QuerySseMapper()
    assert not any(
        kind == "token_delta"
        for kind, _ in mapper.consume_chunk({"verify_answer": dict(state)})
    )
    events = mapper.consume_chunk({"organize_answer": dict(result)})
    streamed = "".join(
        str(body["delta"]) for kind, body in events if kind == "token_delta"
    )
    assert streamed == payload.answer_text
    assert mapper.verified_text == payload.answer_text
    assert [kind for kind, _ in events].count("completed") == 1
    assert mapper.finish() == []
