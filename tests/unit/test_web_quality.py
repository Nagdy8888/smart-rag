"""Web quality regressions, provider-free and explicitly accounted."""

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest
from smart_rag_agents.query.deps import QueryGraphDeps
from smart_rag_agents.query.gateway.web_answer import (
    _parse_web_answer_payload,  # pyright: ignore[reportPrivateUsage]
)
from smart_rag_agents.query.gateway.web_verifier import verify_web_answer
from smart_rag_agents.query.state import pending_query_state
from smart_rag_core.gateways.exa_search import ExaSearchCandidate
from smart_rag_core.gateways.model import VerifierModelRequest
from smart_rag_core.query_admission.exceptions import (
    QueryBudgetError,
    TimeoutAfterSendError,
)
from smart_rag_core.query_admission.service import ReservationConsumeResult
from smart_rag_core.query_answer.exceptions import AnswerError
from smart_rag_core.query_answer.models import AnswerPayload
from smart_rag_core.query_routing.knowledge_scope import KnowledgeScope
from smart_rag_core.web_research.models import WebCitation, WebSourceRecord
from smart_rag_core.web_research.selection import evidence_follow_ups, rank_candidates

from tests.support.query_runtime import authorized_runtime


def test_web_refusal_keeps_the_attempted_verifier_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Refusing a failed verifier must not erase the attempt from graph state."""
    from smart_rag_agents.query.nodes.verify import verify_answer_node
    from smart_rag_agents.query.state import QueryGraphState

    record = source()
    state = pending_query_state(user_query="Can HTTP 429 be cached?")
    state["status"] = "answered"
    state["remaining_model_calls"] = 5
    state["web_sources"] = [record.model_dump(mode="json")]
    state["answer"] = AnswerPayload(
        answer_text="No. [[cite:0]]",
        answer_origin=KnowledgeScope.WEB,
        web_citations=(
            WebCitation(web_source_id=record.web_source_id, span=record.excerpt),
        ),
    ).model_dump(mode="json")

    def failed_attempt(
        current: QueryGraphState,
        deps: QueryGraphDeps,
        answer: AnswerPayload,
        sources: tuple[WebSourceRecord, ...],
    ) -> AnswerPayload:
        """Simulate one consumed provider attempt before release refusal."""
        del deps, answer, sources
        current["remaining_model_calls"] = 4
        current["verifier_call_count"] = 1
        raise AnswerError("web_verifier_unavailable")

    monkeypatch.setattr(
        "smart_rag_agents.query.nodes.verify.verify_web_answer", failed_attempt
    )
    result = verify_answer_node(state, QueryGraphDeps())
    assert result["status"] == "refused"
    assert result["verifier_call_count"] == 1
    assert result["remaining_model_calls"] == 4
    assert result["verification"] is not None
    assert result["verification"]["verifier_call_count"] == 1


def test_source_selection_rejects_obsolete_or_wrong_versions() -> None:
    """Old or incompatible docs cannot win by provider ordering."""
    candidates = tuple(
        ExaSearchCandidate(url=url, title="Python official tutorial")
        for url in (
            "https://docs.python.org/3.1/tutorial/",
            "https://docs.python.org/3/tutorial/",
            "https://example.org/python/",
        )
    )
    ranked = rank_candidates("official Python tutorial", candidates)
    assert ranked[0].url == "https://docs.python.org/3/tutorial/"
    assert all("/3.1/" not in item.url for item in ranked)
    assert not rank_candidates("Python 3.12 tutorial", candidates[:1])


def test_critique_uses_missing_evidence_not_result_titles() -> None:
    """Complete evidence skips follow-up; a missing criterion triggers it."""
    query = "Compare WCAG criteria 2.5.8 and 2.5.5 conformance levels"
    assert evidence_follow_ups(query, ("2.5.8 Level AA. 2.5.5 Level AAA.",)) == ()
    followups = evidence_follow_ups(query, ("2.5.8 Level AA.",))
    assert len(followups) == 1 and "2.5.5" in followups[0]


def source() -> WebSourceRecord:
    """Build one immutable fixture excerpt."""
    return WebSourceRecord(
        web_source_id=str(uuid4()),
        source_index=0,
        url="https://example.org/spec",
        title="Specification",
        excerpt="429 MUST NOT be stored by a cache.",
        content_hash="a" * 64,
    )


def test_structured_citation_indices_survive_without_reindexing() -> None:
    """Invalid markers and dropped citations never shift another reference."""
    record = source()
    raw = {
        "answer_text": "No. [[cite:0]]",
        "status": "complete",
        "atomic_links": [],
        "web_citations": [
            {"web_source_id": record.web_source_id, "span": record.excerpt}
        ],
    }
    assert (
        _parse_web_answer_payload(raw, sources=(record,)).answer_text
        == "No. [[cite:0]]"
    )
    raw["answer_text"] = "No. [[cite:1]]"
    with pytest.raises(AnswerError):
        _parse_web_answer_payload(raw, sources=(record,))
    raw["answer_text"] = "No. [[cite:0]]"
    raw["web_citations"] = [{"web_source_id": record.web_source_id, "span": "invented"}]
    with pytest.raises(AnswerError):
        _parse_web_answer_payload(raw, sources=(record,))


@pytest.mark.parametrize(
    "failure",
    [
        None,
        "support",
        "language",
        "references",
        "limitations",
        "coverage",
        "coverage_partial",
        "provider",
        "schema",
        "budget",
    ],
)
def test_web_verifier_release_and_accounting(
    monkeypatch: pytest.MonkeyPatch, failure: str | None
) -> None:
    """Each semantic gate fails closed and accounts exactly one attempt."""
    runtime = authorized_runtime()
    state = pending_query_state(
        runtime.model_dump(mode="json"), user_query="Can HTTP 429 be cached?"
    )
    state["remaining_model_calls"] = 4
    record = source()
    answer = AnswerPayload(
        answer_text="No. [[cite:0]]",
        web_citations=(
            WebCitation(web_source_id=record.web_source_id, span=record.excerpt),
        ),
    )
    if failure == "coverage_partial":
        answer = answer.model_copy(update={"status": "partial"})
    consume = Mock(
        return_value=ReservationConsumeResult(
            runtime.reservation_id, 2, Decimal("1"), 1000, 1000
        )
    )
    if failure == "budget":
        consume.side_effect = QueryBudgetError("budget_exhausted")
    usage = Mock(return_value=uuid4())
    monkeypatch.setattr(
        "smart_rag_core.query_admission.usage.consume_query_reservation", consume
    )
    monkeypatch.setattr(
        "smart_rag_core.query_admission.usage.record_query_llm_usage", usage
    )
    sends: list[VerifierModelRequest] = []

    class Gateway:
        """Deterministic provider boundary."""

        async def generate_verifier(
            self, request: VerifierModelRequest
        ) -> SimpleNamespace:
            """Return configured semantic verdicts with measured fixture tokens."""
            sends.append(request)
            assert "Can HTTP 429" in request.source_records
            assert record.excerpt in request.source_records
            if failure == "provider":
                raise RuntimeError("provider failed")
            checks = ("support", "coverage", "language", "references", "limitations")
            return SimpleNamespace(
                payload={
                    "link_verdicts": [
                        {
                            "link_id": check,
                            "supported": check
                            != (
                                "coverage" if failure == "coverage_partial" else failure
                            ),
                            "reason": "fixture",
                        }
                        for check in checks
                        if not (failure == "schema" and check == "language")
                    ]
                },
                input_tokens=100,
                output_tokens=20,
            )

    deps = QueryGraphDeps(connection=Mock(), model_gateway=Gateway())
    if failure and failure != "coverage_partial":
        with pytest.raises((AnswerError, TimeoutAfterSendError, QueryBudgetError)):
            verify_web_answer(state, deps, answer, (record,))
    else:
        assert verify_web_answer(state, deps, answer, (record,)).status == (
            "partial" if failure == "coverage_partial" else "complete"
        )
    if failure == "budget":
        assert sends == []
        usage.assert_not_called()
    else:
        assert len(sends) == 1
        usage.assert_called_once()
        assert state["remaining_model_calls"] == 3
        assert state["verifier_call_count"] == 1
        assert state["authorized_runtime"] is not None
        assert state["authorized_runtime"]["optimistic_version"] == 2
        if failure == "provider":
            assert usage.call_args.kwargs["timeout_after_send"]


def test_research_reads_before_critique_and_reserves_answer_time() -> None:
    """Critique receives contents, and optional calls cannot spend answer headroom."""
    from smart_rag_core.web_research.executor import run_web_research

    from tests.unit.test_web_research_graph import FakeSearch, FakeStore

    search = FakeSearch()
    seen: list[tuple[str, ...]] = []

    def critique(query: str, excerpts: tuple[str, ...]) -> tuple[str, ...]:
        """Inspect the evidence handed to the only critique."""
        del query
        seen.append(excerpts)
        return ("regional rainfall detail",)

    result = run_web_research(
        user_query="rainfall",
        search=search,
        store=FakeStore(),
        remaining_deadline_seconds=lambda: 21.0,
        critique=critique,
        allow_mock=True,
    )
    assert seen and "rainfall totals" in seen[0][0]
    assert result.search_count == result.contents_count == 1
    assert len(result.sources) <= 6


def test_executor_requires_explicit_mock_opt_in() -> None:
    """Missing synthesis cannot silently create a successful extractive answer."""
    from smart_rag_core.web_research.exceptions import WebResearchError
    from smart_rag_core.web_research.executor import run_web_research

    from tests.unit.test_web_research_graph import FakeSearch, FakeStore

    search = FakeSearch()
    with pytest.raises(WebResearchError):
        run_web_research(
            user_query="rainfall",
            search=search,
            store=FakeStore(),
            remaining_deadline_seconds=lambda: 40.0,
        )
    assert not search.queries


def test_multilingual_prompt_fitting_uses_discovery_anchors() -> None:
    """Arabic presentation keeps the decisive English evidence window."""
    from smart_rag_agents.query.gateway.web_answer import gateway_web_answer
    from smart_rag_core.gateways.model import (
        WebAnswerModelRequest,
        WebAnswerModelResponse,
    )

    rule = "429 MUST NOT be stored by a cache."
    record = source().model_copy(
        update={"excerpt": "Navigation links. " * 300 + rule + " cache 429" * 60}
    )

    class Gateway:
        """Inspect fitted request without a network call."""

        async def generate_web_answer(
            self, request: WebAnswerModelRequest
        ) -> WebAnswerModelResponse:
            """Return one contained structured reference."""
            assert rule in request.source_records
            return WebAnswerModelResponse(
                mode="mock",
                payload={
                    "answer_text": "No. [[cite:0]]",
                    "status": "complete",
                    "web_citations": [
                        {"web_source_id": record.web_source_id, "span": rule}
                    ],
                    "atomic_links": [],
                },
                request_id="fixture",
                input_tokens=100,
                output_tokens=10,
            )

    answer, _, _ = gateway_web_answer(
        QueryGraphDeps(
            model_gateway=Gateway(),
            web_answer_prompt_text="fixture",
            model_input_max_chars=2000,
        ),
        query="???? ????????",
        search_query="Can 429 responses be stored by a cache?",
        sources=(record,),
        context=None,
    )
    assert answer.answer_text == "No. [[cite:0]]"
    assert record.excerpt.startswith("Navigation")


def test_exa_timeout_cancels_child_coroutine() -> None:
    """The synchronous bridge stops child work at the supplied smaller deadline."""
    import asyncio

    from smart_rag_agents.query.nodes.web_scope import (
        _await_exa,  # pyright: ignore[reportPrivateUsage]
    )
    from smart_rag_core.web_research.exceptions import WebResearchError

    stopped: list[bool] = []

    async def slow() -> None:
        """Model a slow injected Exa operation."""
        try:
            await asyncio.sleep(5)
        finally:
            stopped.append(True)

    with pytest.raises(WebResearchError, match="web_search_timeout"):
        _await_exa(slow, cancel_check=None, timeout_seconds=0.1)
    assert stopped == [True]
