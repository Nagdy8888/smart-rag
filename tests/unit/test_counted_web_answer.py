"""Live Web synthesis must use durable accounting and fit its model input."""

from decimal import Decimal
from unittest.mock import Mock
from uuid import uuid4

import pytest
from smart_rag_agents.query.deps import QueryGraphDeps
from smart_rag_agents.query.gateway.counted_web_answer import counted_web_answer
from smart_rag_agents.query.gateway.web_answer import gateway_web_answer
from smart_rag_agents.query.state import pending_query_state
from smart_rag_core.gateways.model import WebAnswerModelRequest, WebAnswerModelResponse
from smart_rag_core.query_admission.exceptions import (
    QueryBudgetError,
    TimeoutAfterSendError,
)
from smart_rag_core.query_admission.service import ReservationConsumeResult
from smart_rag_core.query_answer.exceptions import AnswerError
from smart_rag_core.query_answer.models import AnswerPayload
from smart_rag_core.web_research.models import WebSourceRecord

from tests.support.query_runtime import authorized_runtime


@pytest.mark.parametrize("failure", [False, True, "input_bound"])
def test_web_send_records_usage_and_keeps_consumed_state(
    monkeypatch: pytest.MonkeyPatch, failure: bool | str
) -> None:
    """Success and missing-response failure both debit exactly one model slot."""
    runtime = authorized_runtime()
    state = pending_query_state(
        runtime.model_dump(mode="json"), user_query="Web question"
    )
    state["remaining_model_calls"] = 5
    before = state["remaining_model_calls"]
    consumed = ReservationConsumeResult(
        runtime.reservation_id, 2, Decimal("1"), 1000, 1000
    )
    consume = Mock(return_value=consumed)
    record = Mock(return_value=uuid4())
    send = Mock(return_value=(AnswerPayload(answer_text="Evidence"), 100, 10))
    if failure == "input_bound":
        send.side_effect = AnswerError("input_bound_exceeded")
    elif failure:
        send.side_effect = AnswerError("web_answer_provider_error")
    monkeypatch.setattr(
        "smart_rag_core.query_admission.usage.consume_query_reservation", consume
    )
    monkeypatch.setattr(
        "smart_rag_core.query_admission.usage.record_query_llm_usage", record
    )
    monkeypatch.setattr(
        "smart_rag_agents.query.gateway.counted_web_answer.gateway_web_answer", send
    )
    if failure == "input_bound":
        with pytest.raises(AnswerError):
            counted_web_answer(
                state,
                QueryGraphDeps(connection=Mock()),
                query="Web question",
                sources=(),
            )
        record.assert_not_called()
    elif failure:
        with pytest.raises(TimeoutAfterSendError):
            counted_web_answer(
                state,
                QueryGraphDeps(connection=Mock()),
                query="Web question",
                sources=(),
            )
        assert record.call_args.kwargs["timeout_after_send"] is True
    else:
        counted_web_answer(
            state, QueryGraphDeps(connection=Mock()), query="Web question", sources=()
        )
        assert record.call_args.kwargs["prompt_tokens"] == 100
        assert state["prompt_tokens"] == 100
    assert state["remaining_model_calls"] == before - 1
    assert state["authorized_runtime"] is not None
    assert state["authorized_runtime"]["optimistic_version"] == 2
    consume.assert_called_once()
    if failure != "input_bound":
        record.assert_called_once()
    send.assert_called_once()


def test_web_budget_denial_never_sends(monkeypatch: pytest.MonkeyPatch) -> None:
    """An exhausted admitted reservation cannot call the Web model."""
    state = pending_query_state(
        authorized_runtime().model_dump(mode="json"), user_query="Web question"
    )
    state["remaining_model_calls"] = 5
    monkeypatch.setattr(
        "smart_rag_core.query_admission.usage.consume_query_reservation",
        Mock(side_effect=QueryBudgetError("budget_exhausted")),
    )
    send = Mock()
    monkeypatch.setattr(
        "smart_rag_agents.query.gateway.counted_web_answer.gateway_web_answer", send
    )
    with pytest.raises(QueryBudgetError):
        counted_web_answer(
            state, QueryGraphDeps(connection=Mock()), query="Web question", sources=()
        )
    send.assert_not_called()


def test_large_web_source_set_is_fitted_without_mutating_canonical_sources() -> None:
    """The permitted 40K source set must fit the smaller model input limit."""
    sources = tuple(
        WebSourceRecord(
            web_source_id=str(uuid4()),
            source_index=i,
            url=f"https://example.org/{i}",
            title="Source",
            excerpt="Evidence " * 800,
            content_hash="a" * 64,
        )
        for i in range(5)
    )

    class Gateway:
        """Observe bounded input and return one contained citation."""

        async def generate_web_answer(
            self, request: WebAnswerModelRequest
        ) -> WebAnswerModelResponse:
            """Validate the actual model input rather than a pre-fit estimate."""
            assert len(request.source_records) + len(request.query) <= 16000
            assert request.web_source_ids == tuple(s.web_source_id for s in sources)
            return WebAnswerModelResponse(
                mode="mock",
                payload={
                    "status": "complete",
                    "answer_text": "Evidence",
                    "web_citations": [
                        {"web_source_id": sources[0].web_source_id, "span": "Evidence"}
                    ],
                },
                request_id="fit-test",
                input_tokens=100,
                output_tokens=10,
            )

    payload, _, _ = gateway_web_answer(
        QueryGraphDeps(
            model_gateway=Gateway(),
            web_answer_prompt_text="Evidence only",
            model_input_max_chars=16000,
        ),
        query="What is the evidence?",
        sources=sources,
        context=None,
    )
    assert payload.web_citations[0].web_source_id == sources[0].web_source_id
    assert all(len(source.excerpt) == 7200 for source in sources)
