"""Retrieve-time budget ledger and debit helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from uuid import UUID

from smart_rag_core.query_admission.exceptions import (
    QueryBudgetError,
    QueryCeilingError,
)
from smart_rag_core.query_admission.usage_caps import (
    assert_call_available,
    usage_kind_caps,
)

RETRIEVE_USAGE_KINDS: frozenset[str] = frozenset({"embedding", "rerank", "lightrag"})
"""Gateway kinds that retrieve must debit against the run-local reservation."""


@dataclass(slots=True)
class QueryRetrieveBudget:
    """Mutable remaining that retrieve-time gateway calls must consume.

    LangGraph ``remaining_model_calls`` is the parallel call counter.
    Pipeline retrieve nodes pass remaining after profile into this ledger
    and write the post-retrieve value back. Binding this ledger on
    Hybrid/LightRAG adapters is how retrieve decrements remaining
    and reserved USD. Durable consume uses ``execute_counted_model_call``
    when ``connection`` and reservation ids are present.

    Attributes:
        remaining_model_calls: Remaining counted gateway calls.
        remaining_usd: Remaining reservation USD.
        connection: Optional ``app_api`` connection for durable consume.
        caller: Server-derived caller when ``connection`` is set.
        run_id: Admitted query run when ``connection`` is set.
        reservation_id: Run-local reservation when ``connection`` is set.
        expected_version: Optimistic reservation version.
        usage_kinds: Debited kinds in call order (tests and audit).
        prompt_tokens: Provider prompt tokens recorded on this ledger.
        completion_tokens: Provider completion tokens recorded on this
            ledger.
    """

    remaining_model_calls: int
    remaining_usd: Decimal
    connection: object | None = None
    caller: object | None = None
    run_id: UUID | None = None
    reservation_id: UUID | None = None
    expected_version: int = 1
    usage_kinds: list[str] = field(default_factory=lambda: list[str]())
    prompt_tokens: int = 0
    completion_tokens: int = 0


def assert_retrieve_kind_available(
    *,
    remaining_model_calls: int,
    remaining_usd: Decimal,
    usage_kind: str,
) -> tuple[Decimal, int, int]:
    """Fail closed when remaining cannot cover one retrieve-time gateway kind.

    Args:
        remaining_model_calls: Remaining counted gateway calls.
        remaining_usd: Remaining reservation USD.
        usage_kind: Allow-listed kind. Retrieve uses embedding, rerank, or
            lightrag.

    Returns:
        ``(usd_cap, prompt_token_cap, completion_token_cap)``.

    Raises:
        QueryCeilingError: When the call ceiling is exhausted or the kind
            is unknown.
        QueryBudgetError: When remaining USD cannot cover the kind cap.
    """

    usd_cap, prompt_cap, completion_cap = usage_kind_caps(usage_kind)
    if remaining_model_calls < 1:
        raise QueryCeilingError("model_call_exhausted")
    if remaining_usd < usd_cap:
        raise QueryBudgetError("reservation_exhausted")
    return usd_cap, prompt_cap, completion_cap


def debit_retrieve_budget(
    budget: QueryRetrieveBudget,
    usage_kind: str,
    *,
    remaining_usd: Decimal | None = None,
) -> None:
    """Record one retrieve-time kind against the in-memory remaining counters.

    Args:
        budget: Mutable retrieve ledger.
        usage_kind: Allow-listed kind that was consumed.
        remaining_usd: Durable remaining after ``execute_counted_model_call``.
            When omitted, subtract the kind USD cap locally.

    Raises:
        QueryCeilingError: When remaining calls cannot cover this kind.
        QueryBudgetError: When local remaining USD cannot cover the cap
            and ``remaining_usd`` was omitted.
    """

    usd_cap, _, _ = assert_retrieve_kind_available(
        remaining_model_calls=budget.remaining_model_calls,
        remaining_usd=budget.remaining_usd,
        usage_kind=usage_kind,
    )
    budget.remaining_model_calls = assert_call_available(budget.remaining_model_calls)
    budget.remaining_usd = (
        remaining_usd if remaining_usd is not None else budget.remaining_usd - usd_cap
    )
    budget.usage_kinds.append(usage_kind)


def add_recorded_tokens(
    budget: QueryRetrieveBudget, prompt_tokens: int, completion_tokens: int
) -> None:
    """Add provider-reported tokens onto the retrieve ledger.

    Args:
        budget: Mutable retrieve ledger.
        prompt_tokens: Provider prompt tokens from one gateway call.
        completion_tokens: Provider completion tokens from one gateway
            call. Embeddings typically report 0.

    Side Effects:
        Increments ``budget.prompt_tokens`` and ``budget.completion_tokens``.
        Negative values are stored as 0 so a malformed adapter cannot
        shrink the run total.
    """

    budget.prompt_tokens += max(0, prompt_tokens)
    budget.completion_tokens += max(0, completion_tokens)
