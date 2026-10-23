"""Budgeted rolling summaries before the bounded recent-message window fills."""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any, cast

from smart_rag_core.gateways.summary_model import (
    SummaryModelRequest,
    SummaryModelResponse,
)
from smart_rag_core.memory.compaction import bounded_memory, compaction_plan
from smart_rag_core.memory.payload import (
    memory_store_namespace,
    validate_memory_store_payload,
)
from smart_rag_core.memory.preferences import (
    merge_preference_updates,
    stored_preferences,
)
from smart_rag_core.memory.user_notes import (
    merge_explicit_user_notes,
    stored_user_notes,
)
from smart_rag_core.memory.versions import SUMMARY_PROMPT_VERSION
from smart_rag_core.query_admission.context import AuthorizedRuntimeContext
from smart_rag_core.query_admission.exceptions import TimeoutAfterSendError
from smart_rag_core.query_admission.service import ReservationConsumeResult
from smart_rag_core.query_admission.usage import execute_counted_model_call
from smart_rag_core.query_routing.models import MemoryRecord
from smart_rag_core.query_routing.preparation import caller_from_runtime

from smart_rag_agents.prompts.registry import load_prompt
from smart_rag_agents.query.deps import QueryGraphDeps
from smart_rag_agents.query.gateway.sync_bridge import run_coro
from smart_rag_agents.query.nodes.shared import runtime_after_consume
from smart_rag_agents.query.state import QueryGraphState

LOGGER = logging.getLogger(__name__)


def compact_loaded_memory(
    state: QueryGraphState,
    deps: QueryGraphDeps,
    context: AuthorizedRuntimeContext,
    records: Sequence[MemoryRecord],
    stored: Mapping[str, object],
) -> tuple[list[MemoryRecord], Mapping[str, object], dict[str, Any]]:
    """Summarize only with reserved headroom; failure preserves bounded recent context."""
    plan = compaction_plan(records, stored)
    updates: dict[str, Any] = {"memory_summary_status": "not_needed"}
    if plan is None:
        return bounded_memory(records, stored), stored, updates
    updates["memory_summary_status"] = "deferred"
    notes = merge_explicit_user_notes(
        stored,
        records,
        through_id=plan.through_id,
        through_created_at=plan.through_created_at,
    )
    if notes != stored_user_notes(stored) and deps.store_put is not None:
        # This local write neither advances the summary watermark nor spends a
        # model call. A deferred summary must not erase explicit user setup.
        preserved = validate_memory_store_payload(
            {**stored, "explicit_user_notes": list(notes)}
        )
        try:
            deps.store_put(
                memory_store_namespace(
                    company_id=None,
                    user_id=str(context.user_id),
                    conversation_id=str(context.conversation_id),
                ),
                "summary",
                preserved,
            )
            stored = preserved
        except Exception as exc:
            LOGGER.info(
                "explicit user memory deferred",
                extra={"error_type": type(exc).__name__},
            )
    seconds = (context.deadline_at - datetime.now(UTC)).total_seconds()
    if (
        deps.connection is None
        or deps.model_gateway is None
        or deps.store_put is None
        or state["remaining_model_calls"] < 6
        or seconds < 15
    ):
        return bounded_memory(records, stored), stored, updates
    prompt = load_prompt(SUMMARY_PROMPT_VERSION)
    prompt_text = prompt.path.read_text(encoding="utf8")
    preferences_json = json.dumps(stored_preferences(stored), ensure_ascii=False)
    # UTF-8 byte count safely upper-bounds tokens without downloading a tokenizer.
    plan = compaction_plan(
        records,
        stored,
        max_message_bytes=max(
            0,
            6000
            - len(prompt_text.encode("utf8"))
            - len(plan.previous_summary.encode("utf8"))
            - len(preferences_json.encode("utf8"))
            - 512,
        ),
    )
    if plan is None:
        return bounded_memory(records, stored), stored, updates
    request = SummaryModelRequest(
        messages=plan.messages,
        previous_summary=plan.previous_summary,
        previous_preferences=preferences_json,
        prompt_text=prompt_text,
        prompt_sha256=prompt.sha256,
        remaining_deadline_seconds=min(6.0, seconds - 10),
    )
    consumed: list[ReservationConsumeResult] = []

    def send() -> SummaryModelResponse:
        """Call the summary gateway once and conservatively charge a lost response."""
        try:
            return cast(
                SummaryModelResponse,
                run_coro(
                    lambda: cast(Any, deps.model_gateway).generate_summary(request),
                    cancel_check=deps.cancel_check,
                    timeout_seconds=request.remaining_deadline_seconds,
                ),
            )
        except Exception as exc:
            raise TimeoutAfterSendError("summary_attempt_failed") from exc

    try:
        result, _hold, _usage = execute_counted_model_call(
            deps.connection,
            caller=caller_from_runtime(context),
            run_id=context.run_id,
            reservation_id=context.reservation_id,
            expected_version=context.optimistic_version,
            usage_kind="summary",
            model_id=request.model_id,
            provider_attempt_id=f"summary:{context.run_id}",
            send=send,
            usage_from_result=lambda response: (
                response.input_tokens,
                response.output_tokens,
                None,
            ),
            on_consumed=consumed.append,
        )
        updated = validate_memory_store_payload(
            {
                "summary": result.summary,
                "through_message_id": plan.through_id,
                "through_created_at": plan.through_created_at,
                "prompt_version": request.prompt_version,
                "preferences": merge_preference_updates(
                    stored,
                    result.preference_updates,
                    records,
                    through_id=plan.through_id,
                    through_created_at=plan.through_created_at,
                ),
                "explicit_user_notes": list(stored_user_notes(stored)),
            }
        )
        namespace = memory_store_namespace(
            company_id=None,
            user_id=str(context.user_id),
            conversation_id=str(context.conversation_id),
        )
        deps.store_put(namespace, "summary", updated)
        stored = updated
        updates.update(
            memory_summary_status="written",
            prompt_tokens=int(state.get("prompt_tokens") or 0) + result.input_tokens,
            completion_tokens=int(state.get("completion_tokens") or 0)
            + result.output_tokens,
        )
    except Exception as exc:
        LOGGER.info(
            "conversation summary deferred",
            extra={
                "event": "query.memory.summary_deferred",
                "error_type": type(exc).__name__,
                "cause_type": type(exc.__cause__).__name__
                if exc.__cause__ is not None
                else "none",
            },
        )
    finally:
        if consumed:
            updates["authorized_runtime"] = runtime_after_consume(
                context, consumed[-1]
            ).model_dump(mode="json")
            updates["remaining_model_calls"] = max(
                0, state["remaining_model_calls"] - 1
            )
    return bounded_memory(records, stored), stored, updates
