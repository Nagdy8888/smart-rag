"""Actual verifier attempt wrapper: deny-before-send and recorded outcomes."""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from typing import cast
from unittest.mock import MagicMock
from uuid import uuid4

import psycopg
import pytest
from smart_rag_agents.query.deps import QueryGraphDeps
from smart_rag_agents.query.gateway.verifier import gateway_verifier
from smart_rag_agents.query.nodes.release_safety import (
    refresh_refusal_usage,
    refuse_release,
)
from smart_rag_core.gateways.openai_answer import OpenAIAnswerError
from smart_rag_core.query_admission.exceptions import (
    QueryBudgetError,
    TimeoutAfterSendError,
)
from smart_rag_core.query_admission.repository.records import RunUsageSummary
from smart_rag_core.query_admission.service import ReservationConsumeResult
from smart_rag_core.query_answer.exceptions import AnswerError
from smart_rag_core.query_answer.models import AnswerPayload

from tests.support.answer_verifier import verified_answer_state
from tests.support.query_runtime import authorized_runtime


class VerifierStub:
    """One no-network provider with selectable reply/failure."""

    def __init__(self, outcome: str) -> None:
        """Store the desired response and invocation count."""
        self.outcome = outcome
        self.calls = 0

    async def generate_verifier(self, _request: object) -> SimpleNamespace:
        """Return measured usage, invalid output, or an uncertain failure."""
        self.calls += 1
        if self.outcome == "timeout":
            raise TimeoutError("synthetic provider timeout")
        if self.outcome.startswith("verifier_"):
            raise OpenAIAnswerError(self.outcome)
        payload = (
            {"link_verdicts": [{"link_id": "l1", "supported": True, "reason": "ok"}]}
            if self.outcome == "valid"
            else {"invalid": True}
        )
        return SimpleNamespace(payload=payload, input_tokens=17, output_tokens=9)


@pytest.mark.parametrize(
    "outcome",
    [
        "valid",
        "invalid",
        "timeout",
        "denied",
        "verifier_output_limit",
        "verifier_content_filter",
        "verifier_refusal",
        "verifier_empty_output",
    ],
)
def test_verifier_attempt_accounting(
    monkeypatch: pytest.MonkeyPatch, outcome: str
) -> None:
    """Denial sends nothing; invalid output and timeout still record work."""
    from smart_rag_core.query_fusion.models import FusionResult

    state = verified_answer_state()
    answer = AnswerPayload.model_validate(state["answer"])
    fusion = FusionResult.model_validate(state["fusion"])
    runtime = authorized_runtime()
    consumed = ReservationConsumeResult(
        reservation_id=runtime.reservation_id,
        optimistic_version=2,
        remaining_usd=Decimal("1.00"),
        remaining_prompt_tokens=2000,
        remaining_completion_tokens=1000,
    )
    consume = MagicMock(return_value=consumed)
    if outcome == "denied":
        consume.side_effect = QueryBudgetError("budget_exhausted")
    record = MagicMock(return_value=uuid4())
    monkeypatch.setattr(
        "smart_rag_core.query_admission.usage.consume_query_reservation", consume
    )
    monkeypatch.setattr(
        "smart_rag_core.query_admission.usage.record_query_llm_usage", record
    )
    provider = VerifierStub(outcome)
    callback = MagicMock()
    args = {
        "links": answer.atomic_links,
        "fusion": fusion,
        "tables": (),
        "context": runtime,
        "on_consumed": callback,
    }
    deps = QueryGraphDeps(
        connection=cast(psycopg.Connection, MagicMock()),
        model_gateway=provider,
        verifier_prompt_text="synthetic verifier",
    )
    if outcome == "denied":
        with pytest.raises(QueryBudgetError):
            gateway_verifier(deps, **args)  # type: ignore[arg-type]
        assert provider.calls == 0
        record.assert_not_called()
    else:
        if outcome == "valid":
            _, prompt, completion = gateway_verifier(deps, **args)  # type: ignore[arg-type]
            assert (prompt, completion) == (17, 9)
            callback.assert_called_once_with(consumed)
        else:
            error = AnswerError if outcome == "invalid" else TimeoutAfterSendError
            with pytest.raises(error) as failure:
                gateway_verifier(deps, **args)  # type: ignore[arg-type]
            if outcome.startswith("verifier_"):
                assert getattr(failure.value, "reason", None) == outcome
        assert provider.calls == 1
        record.assert_called_once()
        recorded = record.call_args.kwargs
        assert recorded["usage_kind"] == "verifier"
        uncertain = outcome == "timeout" or outcome.startswith("verifier_")
        assert recorded["timeout_after_send"] == uncertain
        if not uncertain:
            assert recorded["prompt_tokens"] == 17
            assert recorded["completion_tokens"] == 9
    consume.assert_called_once()


def test_live_verifier_without_accounting_cannot_send() -> None:
    """A paid runtime with no durable connection is not an offline fallback."""
    from smart_rag_core.query_fusion.models import FusionResult

    state = verified_answer_state()
    provider = VerifierStub("valid")
    with pytest.raises(AnswerError, match="verifier_accounting_unavailable"):
        gateway_verifier(
            QueryGraphDeps(model_gateway=provider),
            links=AnswerPayload.model_validate(state["answer"]).atomic_links,
            fusion=FusionResult.model_validate(state["fusion"]),
            tables=(),
            context=authorized_runtime(),
        )
    assert provider.calls == 0


def test_failed_attempt_usage_remains_visible_in_safe_refusal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Refusing a charged invalid response does not hide its durable cost."""
    state = verified_answer_state()
    state["authorized_runtime"] = authorized_runtime().model_dump(mode="json")
    safe = refuse_release(state, "verifier_schema_invalid")
    monkeypatch.setattr(
        "smart_rag_agents.query.nodes.release_safety.summarize_run_usage",
        MagicMock(
            return_value=RunUsageSummary(
                cost_usd=Decimal("0.012"),
                prompt_tokens=17,
                completion_tokens=9,
                usage_rows=1,
            )
        ),
    )
    refreshed = refresh_refusal_usage(
        safe, QueryGraphDeps(connection=cast(psycopg.Connection, MagicMock()))
    )
    assert refreshed["prompt_tokens"] == 17
    assert refreshed["completion_tokens"] == 9
    assert refreshed["cost_usd"] == 0.012
    assert refreshed["answer"] == safe["answer"]
    assert refreshed["status"] == "refused"
