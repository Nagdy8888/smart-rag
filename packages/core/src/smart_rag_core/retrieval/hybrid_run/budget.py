"""Counted retrieve-time embedding and rerank sends."""

from __future__ import annotations

from collections.abc import Callable
from typing import cast
from uuid import UUID, uuid4

import psycopg

from smart_rag_core.query_admission.exceptions import (
    QueryBudgetError,
    QueryCeilingError,
)
from smart_rag_core.query_admission.retrieve_budget import QueryRetrieveBudget
from smart_rag_core.retrieval.context import RerankFn
from smart_rag_core.retrieval.profiles import RERANK_MODEL_ID
from smart_rag_core.retrieval.rerank import (
    RerankFallbackReason,
    RerankPassage,
    RerankRanking,
    RerankUsage,
)
from smart_rag_core.security.identity import CallerContext


def _counted_retrieve_send(
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
        Debits ``budget`` remaining. When connection and reservation ids are
        present, consumes via ``execute_counted_model_call`` so reserved USD
        cannot be silently exceeded.
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
    if (
        isinstance(connection, psycopg.Connection)
        and isinstance(caller, CallerContext)
        and isinstance(run_id, UUID)
        and isinstance(reservation_id, UUID)
    ):
        assert_retrieve_kind_available(
            remaining_model_calls=budget.remaining_model_calls,
            remaining_usd=budget.remaining_usd,
            usage_kind=usage_kind,
        )
        result, consumed, _usage_id = execute_counted_model_call(
            connection,
            caller=caller,
            run_id=run_id,
            reservation_id=reservation_id,
            expected_version=budget.expected_version,
            usage_kind=usage_kind,
            model_id=model_id,
            provider_attempt_id=str(uuid4()),
            send=send,
        )
        budget.expected_version = consumed.optimistic_version
        debit_retrieve_budget(budget, usage_kind, remaining_usd=consumed.remaining_usd)
        return result
    debit_retrieve_budget(budget, usage_kind)
    return send()


def _counted_rerank(
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

        counted = _counted_retrieve_send(
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
