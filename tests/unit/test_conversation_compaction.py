"""Rolling memory keeps constraints, recent turns, budgets, and evidence boundaries."""

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any, cast
from uuid import uuid4

import pytest
from smart_rag_agents.query.deps import QueryGraphDeps
from smart_rag_agents.query.nodes import memory_compaction as node
from smart_rag_agents.query.state import pending_query_state
from smart_rag_core.gateways.summary_model import SummaryModelResponse
from smart_rag_core.memory.compaction import (
    MEMORY_CONTEXT_CHARS,
    bounded_memory,
    compaction_plan,
)
from smart_rag_core.query_admission.exceptions import QueryBudgetError
from smart_rag_core.query_admission.service import ReservationConsumeResult
from smart_rag_core.query_routing.models import MemoryRecord, PreparationModelPayload
from smart_rag_core.query_routing.preparation import prepare_query
from smart_rag_core.query_routing.safety import delimit_memory_record
from smart_rag_core.search_scope import RequestedSearchScope

from tests.support.query_runtime import authorized_runtime


def records(
    count: int = 8, content: str = "Discuss storage constraints."
) -> list[MemoryRecord]:
    """Create chronological user/assistant records with distinct stable timestamps."""
    return [
        delimit_memory_record(
            message_id=str(uuid4()),
            role="user" if i % 2 == 0 else "assistant",
            content=content,
            created_at=(
                datetime(2026, 10, 22, tzinfo=UTC) + timedelta(seconds=i)
            ).isoformat(),
        )
        for i in range(count)
    ]


def test_trigger_preserves_recent_turns_and_watermark_prevents_resummarizing() -> None:
    """Keep recent messages intact and acknowledge only the summarized prefix."""
    history = records()
    assert compaction_plan(history[:6], {}) is None
    plan = compaction_plan(history, {})
    assert plan is not None
    assert plan.through_id == history[3].message_id
    saved = {
        "summary": "Use project Harbor Maple and seven reviewers.",
        "through_message_id": plan.through_id,
        "through_created_at": plan.through_created_at,
    }
    assert bounded_memory(history, saved) == history[4:]
    assert compaction_plan(history, saved) is None


def test_large_context_is_bounded_even_when_summary_is_unavailable() -> None:
    """A failed summary must not overflow the next prompt."""
    history = records(12, "context " * 170)
    recent = bounded_memory(history, {})
    assert recent[-1] == history[-1]
    assert sum(len(r.delimited) for r in recent) <= MEMORY_CONTEXT_CHARS
    assert len(recent) < len(history)


def test_summary_excludes_native_source_blocks_and_respects_utf8_budget() -> None:
    """Memory stores conversation intent rather than copied native artifacts."""
    history = records(
        content="Topic.\n```python\nsecret_source()\n```\n| Item | Value |\n[[figure:abcd]]"
    )
    plan = compaction_plan(history, {}, max_message_bytes=600)
    assert plan is not None and len(plan.messages.encode()) <= 600
    assert "secret_source()" not in plan.messages and "[[figure:" not in plan.messages
    assert "| Item" not in plan.messages


@pytest.mark.parametrize(
    "query",
    [
        "Which of those is better for the same task?",
        "وماذا عن الخيار الثاني الذي ذكرته؟",
    ],
)
def test_connected_followups_share_the_profile_call(query: str) -> None:
    """Resolve English and Arabic referents without a separate model call."""
    calls: list[str] = []

    def caller(
        question: str, memory: Sequence[MemoryRecord]
    ) -> PreparationModelPayload:
        """Exercise the bounded callback using the supplied test or runtime inputs."""
        calls.append(question)
        return PreparationModelPayload()

    result = prepare_query(
        query,
        runtime=authorized_runtime(),
        memory=records(2),
        force_model=False,
        requested_search_scope=RequestedSearchScope.COMPANY_DOCUMENTS,
        model_caller=caller,
    )
    assert calls == [query] and result.model_calls == 1
    assert result.original == query


def test_standalone_arabic_gets_one_counted_translation_profile() -> None:
    """A self-contained Arabic question can search English sources without a language filter."""
    query = "\u0643\u064a\u0641 \u062a\u0639\u0645\u0644 \u0627\u0644\u0641\u0647\u0631\u0633\u0629 \u0641\u064a \u0623\u0646\u0638\u0645\u0629 \u0627\u0644\u062a\u062e\u0632\u064a\u0646\u061f"
    calls: list[str] = []

    def caller(
        question: str, memory: Sequence[MemoryRecord]
    ) -> PreparationModelPayload:
        """Return one translation without assigning any metadata filter."""
        assert not memory
        calls.append(question)
        return PreparationModelPayload(
            rewrite="How does indexing work in storage systems?"
        )

    result = prepare_query(
        query,
        runtime=authorized_runtime(),
        memory=(),
        force_model=False,
        requested_search_scope=RequestedSearchScope.COMPANY_DOCUMENTS,
        model_caller=caller,
    )
    assert calls == [query]
    assert result.model_calls == 1 and result.original == query
    assert result.metadata_filters == ()


def test_profile_failure_keeps_the_consumed_version_and_call_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failed profile attempt must not poison later retrieval with an old version."""
    from smart_rag_core.gateways.model import ModelGatewayUnavailableError
    from smart_rag_core.query_admission.exceptions import TimeoutAfterSendError

    context = authorized_runtime()
    hold = ReservationConsumeResult(
        context.reservation_id, context.optimistic_version + 1, Decimal("2"), 5000, 1000
    )
    snapshots: list[ReservationConsumeResult] = []
    failures: list[str] = []

    def fail_profile(*args: Any) -> Any:
        """Model a timeout after dispatching the profile request."""
        raise ModelGatewayUnavailableError("profile_timeout")

    def counted(*args: Any, **kwargs: Any) -> Any:
        """Consume before provider work, as the durable gateway does."""
        kwargs["on_consumed"](hold)
        try:
            return kwargs["send"]()
        except TimeoutAfterSendError:
            failures.append("timeout_after_send")
            raise

    monkeypatch.setattr(
        "smart_rag_core.query_routing.preparation.execute_counted_model_call", counted
    )
    result = prepare_query(
        "Continue that comparison",
        runtime=context,
        memory=records(2),
        model_caller=fail_profile,
        connection=cast(Any, object()),
        on_reservation_consume=snapshots.append,
    )
    assert snapshots == [hold]
    assert result.model_calls == 1
    assert result.fallback_reason == "profile_budget_denied"
    assert failures == ["timeout_after_send"]


def test_summary_consumes_once_updates_version_and_uses_creator_namespace(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A successful summary owns one reservation consume and one scoped store write."""
    context = authorized_runtime()
    state = pending_query_state(
        user_query="Continue", authorized_runtime=context.model_dump(mode="json")
    )
    state["remaining_model_calls"] = 7
    stored: list[tuple[Any, ...]] = []

    def record_store(*args: Any) -> None:
        """Exercise the bounded callback using the supplied test or runtime inputs."""
        stored.append(args)

    hold = ReservationConsumeResult(
        context.reservation_id, context.optimistic_version + 1, Decimal("2"), 5000, 1000
    )

    def counted(
        connection: Any, **kwargs: Any
    ) -> tuple[SummaryModelResponse, ReservationConsumeResult, Any]:
        """Exercise the bounded callback using the supplied test or runtime inputs."""
        kwargs["on_consumed"](hold)
        return (
            SummaryModelResponse(
                summary="Project Harbor Maple; seven reviewers.",
                input_tokens=120,
                output_tokens=20,
            ),
            hold,
            uuid4(),
        )

    monkeypatch.setattr(node, "execute_counted_model_call", counted)
    deps = QueryGraphDeps(
        connection=cast(Any, object()),
        model_gateway=object(),
        store_put=record_store,
    )
    recent, summary, updates = node.compact_loaded_memory(
        state, deps, context, records(), {}
    )
    assert updates["memory_summary_status"] == "written"
    assert updates["remaining_model_calls"] == 6
    assert (
        updates["authorized_runtime"]["optimistic_version"] == hold.optimistic_version
    )
    assert summary["summary"] == "Project Harbor Maple; seven reviewers."
    assert len(recent) == 4
    assert stored[0][0] == (
        "company",
        str(context.user_id),
        str(context.conversation_id),
    )


def test_budget_failure_preserves_previous_summary_and_does_not_claim_compaction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Denied budget preserves old memory and reports deferral honestly."""
    context = authorized_runtime()
    state = pending_query_state(
        user_query="Continue", authorized_runtime=context.model_dump(mode="json")
    )
    state["remaining_model_calls"] = 7

    def denied(*args: Any, **kwargs: Any) -> Any:
        """Exercise the bounded callback using the supplied test or runtime inputs."""
        raise QueryBudgetError("reservation_denied")

    monkeypatch.setattr(node, "execute_counted_model_call", denied)
    stored: list[tuple[Any, ...]] = []

    def record_store(*args: Any) -> None:
        """Exercise the bounded callback using the supplied test or runtime inputs."""
        stored.append(args)

    previous = {"summary": "Keep the original user constraint."}
    deps = QueryGraphDeps(
        connection=cast(Any, object()),
        model_gateway=object(),
        store_put=record_store,
    )
    _, summary, updates = node.compact_loaded_memory(
        state, deps, context, records(), previous
    )
    assert summary == previous and not stored
    assert updates["memory_summary_status"] == "deferred"
    assert "remaining_model_calls" not in updates


def test_answer_context_keeps_late_summary_constraints_and_newest_turns() -> None:
    """A user preference after character 500 survives every answering path."""
    from smart_rag_agents.query.nodes.state_codec import memory_text_from_state

    summary = "Earlier topics. " * 60 + "Harbor Maple requires seven reviewers."
    raw = [
        {"role": "system", "content": summary},
        *[{"role": "user", "content": f"Turn {i}: " + "x" * 1400} for i in range(12)],
    ]
    text = memory_text_from_state(raw)
    assert "Harbor Maple requires seven reviewers." in text
    assert "Turn 11:" in text
    assert "Turn 0:" not in text
    assert len(text) <= 8000
