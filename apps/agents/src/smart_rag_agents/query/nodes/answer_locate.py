"""Optional locate-quote call that runs before the company answer call."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from smart_rag_core.query_admission.context import AuthorizedRuntimeContext
from smart_rag_core.query_admission.exceptions import (
    QueryBudgetError,
    QueryCeilingError,
)
from smart_rag_core.query_admission.usage import execute_counted_model_call
from smart_rag_core.query_answer.locate import LocatedQuote
from smart_rag_core.query_answer.versions import (
    ANSWER_MODEL_ID,
    LOCATE_CALL_RESERVE,
    LOCATE_MIN_SECONDS,
)
from smart_rag_core.query_fusion.models import FusionResult
from smart_rag_core.query_routing.preparation import caller_from_runtime

from smart_rag_agents.query.deps import QueryGraphDeps
from smart_rag_agents.query.gateway.answer import LocateResult, gateway_locate
from smart_rag_agents.query.nodes.shared import runtime_after_consume


@dataclass(frozen=True, slots=True)
class LocateOutcome:
    """Result of the optional locate step.

    Attributes:
        quotes: Validated quotes for the answer call.
        remaining_model_calls: Remaining call ceiling after the step.
        context: Runtime context carrying the latest reservation version.
        prompt_tokens: Provider prompt tokens to add to the run total.
        completion_tokens: Provider completion tokens to add.
        diagnostics: ID-only ``answer_locate`` state value.
    """

    quotes: tuple[LocatedQuote, ...]
    remaining_model_calls: int
    context: AuthorizedRuntimeContext | None
    prompt_tokens: int
    completion_tokens: int
    diagnostics: dict[str, object]


def run_locate_step(
    deps: QueryGraphDeps,
    *,
    query: str,
    fusion: FusionResult,
    tables: tuple[object, ...],
    context: AuthorizedRuntimeContext | None,
    remaining_model_calls: int,
) -> LocateOutcome:
    """Run the locate call when prompt, call reserve, and deadline allow.

    Skips without a model call when the locate prompt or gateway is
    unbound, when fewer than ``LOCATE_CALL_RESERVE`` calls remain (the
    verifier call must stay available), or when fewer than
    ``LOCATE_MIN_SECONDS`` remain before the run deadline. A live run
    records the call as ``usage_kind = "answer"`` through the run-local
    reservation; isolated tests without a connection call the gateway
    directly, like the answer node does.

    Args:
        deps: Bound gateway, locate prompt, connection, and clock.
        query: Original user query. Untrusted.
        fusion: Fitted canonical evidence.
        tables: Fitted table records.
        context: Admitted runtime context, or None in isolated tests.
        remaining_model_calls: Remaining ceiling after the answer call was
            reserved.

    Returns:
        Quotes, updated ceiling and context, tokens, and diagnostics.

    Side Effects:
        At most one provider call and one ``app.llm_usage`` row.
    """

    def _skipped(reason: str) -> LocateOutcome:
        """Return an outcome that made no model call.

        Args:
            reason: Machine-readable skip reason.

        Returns:
            Outcome with the inputs unchanged.
        """

        return LocateOutcome(
            quotes=(),
            remaining_model_calls=remaining_model_calls,
            context=context,
            prompt_tokens=0,
            completion_tokens=0,
            diagnostics={"status": "skipped", "reason": reason, "quote_count": 0},
        )

    if not deps.locate_prompt_text:
        return _skipped("locate_prompt_unbound")
    if deps.model_gateway is None:
        return _skipped("model_gateway_unbound")
    if remaining_model_calls < LOCATE_CALL_RESERVE:
        return _skipped("locate_call_reserve")
    if context is not None:
        now = deps.now() if deps.now is not None else datetime.now(UTC)
        if (context.deadline_at - now).total_seconds() < LOCATE_MIN_SECONDS:
            return _skipped("locate_deadline_reserve")

    def _send() -> LocateResult:
        """Invoke the locate gateway once.

        Returns:
            Locate result; never raises ``AnswerError``.
        """

        return gateway_locate(
            deps, query=query, fusion=fusion, tables=tables, context=context
        )

    def _usage(result: LocateResult) -> tuple[int | None, int | None, Decimal | None]:
        """Read provider tokens from a locate send.

        Args:
            result: Locate result.

        Returns:
            Prompt tokens, completion tokens, and no measured USD.
        """

        return result.prompt_tokens, result.completion_tokens, None

    next_context = context
    try:
        if deps.connection is not None and context is not None:
            result, consumed, _usage_id = execute_counted_model_call(
                deps.connection,
                caller=caller_from_runtime(context),
                run_id=context.run_id,
                reservation_id=context.reservation_id,
                expected_version=context.optimistic_version,
                usage_kind="answer",
                model_id=ANSWER_MODEL_ID,
                provider_attempt_id=str(uuid4()),
                send=_send,
                usage_from_result=_usage,
            )
            next_context = runtime_after_consume(context, consumed)
        else:
            result = _send()
    except (QueryBudgetError, QueryCeilingError) as exc:
        return _skipped(str(exc.reason)[:64])
    return LocateOutcome(
        quotes=result.quotes,
        remaining_model_calls=remaining_model_calls - 1,
        context=next_context,
        prompt_tokens=result.prompt_tokens or 0,
        completion_tokens=result.completion_tokens or 0,
        diagnostics={
            "status": "ran" if result.error is None else "failed",
            "reason": result.error,
            "quote_count": len(result.quotes),
            "chunk_ids": sorted({quote.chunk_id for quote in result.quotes}),
        },
    )
