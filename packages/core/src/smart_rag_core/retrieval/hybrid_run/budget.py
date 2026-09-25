"""Counted retrieve-time embedding and rerank sends."""

from __future__ import annotations

import time
from collections.abc import Callable
from decimal import Decimal
from typing import Any, cast
from uuid import UUID, uuid4

import psycopg

from smart_rag_core.gateways.embedding import EmbeddingResponse
from smart_rag_core.query_admission.exceptions import (
    QueryBudgetError,
    QueryCeilingError,
)
from smart_rag_core.query_admission.retrieve_budget import (
    QueryRetrieveBudget,
    add_recorded_tokens,
)
from smart_rag_core.retrieval.context import RerankFn
from smart_rag_core.retrieval.profiles import RERANK_MODEL_ID
from smart_rag_core.retrieval.rerank import (
    RerankFallbackReason,
    RerankPassage,
    RerankRanking,
    RerankUsage,
)
from smart_rag_core.security.identity import CallerContext


def tokens_from_retrieve_result(
    result: object,
) -> tuple[int | None, int | None, Decimal | None]:
    """Read provider tokens from one retrieve-time send result.

    Args:
        result: An ``EmbeddingResponse`` or a rerank
            ``(rankings, usage, fallback)`` triple.

    Returns:
        Prompt tokens, completion tokens, and optional USD. Unknown
        shapes return ``(None, None, None)`` so durable consume keeps
        the kind cap instead of recording 0.
    """

    if isinstance(result, EmbeddingResponse):
        cost = result.estimated_cost_usd
        recorded_cost = cost if cost > 0 else None
        return result.prompt_tokens, 0, recorded_cost
    if isinstance(result, tuple):
        ranked_result = cast(tuple[object, ...], result)
        if len(ranked_result) >= 2:
            usage = ranked_result[1]
            if isinstance(usage, RerankUsage):
                from smart_rag_core.gateways.openai_pricing import (
                    estimate_chat_cost_usd,
                )

                cost = estimate_chat_cost_usd(
                    prompt_tokens=usage.input_tokens,
                    completion_tokens=usage.output_tokens,
                )
                return usage.input_tokens, usage.output_tokens, cost
    return None, None, None


def _accumulate_retrieve_tokens(budget: QueryRetrieveBudget, result: object) -> None:
    """Add provider tokens from ``result`` onto the retrieve ledger.

    Args:
        budget: Mutable retrieve ledger.
        result: Send result from embedding or rerank.
    """

    prompt, completion, _cost = tokens_from_retrieve_result(result)
    if prompt is None:
        return
    add_recorded_tokens(budget, prompt, completion or 0)


def counted_retrieve_send(
    budget: QueryRetrieveBudget | None,
    *,
    usage_kind: str,
    model_id: str,
    send: Callable[[], object],
) -> object:
    """Consume the run-local reservation for one retrieve-time gateway call.

    Args:
        budget: Retrieve ledger. ``None`` leaves the call uncounted so
            existing unit tests without a reservation keep working.
        usage_kind: ``embedding`` or ``rerank``.
        model_id: Provider model identifier recorded on usage.
        send: Provider invocation.

    Returns:
        ``send`` result.

    Raises:
        QueryCeilingError: When remaining model calls cannot cover the kind.
        QueryBudgetError: When remaining USD cannot cover the kind cap, or
            durable consume is rejected.

    Side Effects:
        Debits ``budget`` remaining and records provider tokens on the
        ledger. When connection and reservation ids are present, consumes
        via ``execute_counted_model_call`` so reserved USD cannot be
        silently exceeded. A bound run/reservation without a connection
        raises ``retrieve_accounting_connection_missing`` instead of
        skipping durable writes. Token totals still accumulate when the
        durable path is unbound so Ask Run Details can match provider traces.
    """

    if budget is None:
        return send()
    from smart_rag_core.query_admission.ceilings import (
        assert_retrieve_kind_available,
        debit_retrieve_budget,
    )
    from smart_rag_core.query_admission.usage import execute_counted_model_call

    connection = budget.connection
    caller = budget.caller
    run_id = budget.run_id
    reservation_id = budget.reservation_id
    durable_required = isinstance(run_id, UUID) and isinstance(reservation_id, UUID)
    if durable_required and not isinstance(connection, psycopg.Connection):
        raise QueryBudgetError("retrieve_accounting_connection_missing")
    if (
        isinstance(connection, psycopg.Connection)
        and isinstance(caller, CallerContext)
        and durable_required
    ):
        assert_retrieve_kind_available(
            remaining_model_calls=budget.remaining_model_calls,
            remaining_usd=budget.remaining_usd,
            usage_kind=usage_kind,
        )
        result, consumed, _usage_id = execute_counted_model_call(
            cast("psycopg.Connection[tuple[Any, ...]]", connection),
            caller=caller,
            run_id=cast(UUID, run_id),
            reservation_id=cast(UUID, reservation_id),
            expected_version=budget.expected_version,
            usage_kind=usage_kind,
            model_id=model_id,
            provider_attempt_id=str(uuid4()),
            send=send,
            usage_from_result=tokens_from_retrieve_result,
        )
        budget.expected_version = consumed.optimistic_version
        debit_retrieve_budget(budget, usage_kind, remaining_usd=consumed.remaining_usd)
        _accumulate_retrieve_tokens(budget, result)
        return result
    debit_retrieve_budget(budget, usage_kind)
    result = send()
    _accumulate_retrieve_tokens(budget, result)
    return result


def counted_rerank(
    inner: RerankFn,
    budget: QueryRetrieveBudget | None,
    *,
    count_gateway: bool,
) -> RerankFn:
    """Wrap one rerank callback so it consumes remaining before the provider.

    Args:
        inner: Injected rerank callback or identity fallback.
        budget: Retrieve ledger.
        count_gateway: True when ``inner`` is a real gateway callback.

    Returns:
        Rerank callback. Identity rerank is not a counted gateway call.
        Insufficient remaining returns ``rerank_budget_denied`` without
        calling the provider.
    """

    if not count_gateway or budget is None:
        return inner

    def _wrapped(
        query: str,
        pool: tuple[RerankPassage, ...],
        remaining_deadline_seconds: float,
    ) -> tuple[tuple[RerankRanking, ...], RerankUsage | None, RerankFallbackReason]:
        """Fail closed when remaining cannot cover rerank, else debit and call.

        Args:
            query: Original user query.
            pool: Authorized rerank pool.
            remaining_deadline_seconds: Remaining Hybrid deadline share.

        Returns:
            Rankings, usage, and fallback reason from ``inner``, or empty
            rankings with ``rerank_budget_denied``.
        """

        from smart_rag_core.query_admission.ceilings import (
            assert_retrieve_kind_available,
        )

        try:
            assert_retrieve_kind_available(
                remaining_model_calls=budget.remaining_model_calls,
                remaining_usd=budget.remaining_usd,
                usage_kind="rerank",
            )
        except (QueryBudgetError, QueryCeilingError):
            return (), None, RerankFallbackReason.BUDGET_DENIED

        def _send() -> object:
            """Invoke the inner reranker.

            Returns:
                Inner rerank triple.
            """

            return inner(query, pool, remaining_deadline_seconds)

        counted = counted_retrieve_send(
            budget,
            usage_kind="rerank",
            model_id=RERANK_MODEL_ID,
            send=_send,
        )
        return cast(
            tuple[tuple[RerankRanking, ...], RerankUsage | None, RerankFallbackReason],
            counted,
        )

    return _wrapped


def timed_rerank(inner: RerankFn, sink: list[int]) -> RerankFn:
    """Wrap a rerank callback and record its wall time.

    Args:
        inner: Rerank callback, usually the ``counted_rerank`` wrapper.
        sink: List that receives one non-negative integer millisecond
            value per invocation, including invocations that raise.

    Returns:
        Callback with the same contract as ``inner``.

    Side Effects:
        Appends to ``sink``. Adds no model call, retry, or budget debit.
    """

    def _timed(
        query: str,
        pool: tuple[RerankPassage, ...],
        remaining_deadline_seconds: float,
    ) -> tuple[tuple[RerankRanking, ...], RerankUsage | None, RerankFallbackReason]:
        """Invoke ``inner`` once and record its duration.

        Args:
            query: Original user query.
            pool: Authorized rerank pool.
            remaining_deadline_seconds: Remaining Hybrid deadline share.

        Returns:
            The unchanged ``inner`` triple.
        """

        started = time.perf_counter()
        try:
            return inner(query, pool, remaining_deadline_seconds)
        finally:
            sink.append(int(max(0.0, time.perf_counter() - started) * 1000.0))

    return _timed
