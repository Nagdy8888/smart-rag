"""Structured graph query orchestration: vendor leads plus authoritative resolve.

This module must not mention mapping-table names. Resolver SQL lives under
``jobs/``. Combined answers and SSE are Phase 6.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Literal
from uuid import UUID

import psycopg

from smart_rag_core.evaluation.schema import ExpectedProfile, ProfileField
from smart_rag_core.jobs.exceptions import GraphResolverError
from smart_rag_core.jobs.graph_resolver import (
    enqueue_query_repairs,
    inspect_graph,
    limitation_for_visibility,
    load_canonical_locators,
    load_query_workspace,
    record_survival_sample,
    resolve_graph_leads,
    visibility_counts,
)
from smart_rag_core.retrieval.graph import (
    GRAPH_SURVIVAL_FALLBACK_THRESHOLD,
    GraphLeadSet,
    GraphLimitationCode,
    GraphQueryBounds,
    GraphRetriever,
    apply_query_bounds,
    clamp_global_steering,
    clamp_graph_leads,
    graph_survival_ratio,
    workspace_limitation_code,
)
from smart_rag_core.retrieval.graph_results import (
    GraphInspectResult,
    GraphLimitation,
    GraphQueryCounters,
    GraphRetrievalResult,
    GraphSteeringExpansion,
    RollingSurvivalWindow,
)
from smart_rag_core.retrieval.lightrag_callbacks import CountedLightRagCallbacks
from smart_rag_core.retrieval.lightrag_structured import LightRagQueryFailure
from smart_rag_core.retrieval.temporal import TemporalIntent
from smart_rag_core.security.identity import CallerContext

GraphMode = Literal["local", "hybrid", "global"]


class GraphQueryError(GraphResolverError):
    """Raised when structured graph query fails closed."""


async def retrieve_graph(
    *,
    retriever: GraphRetriever,
    connection: psycopg.Connection,
    caller: CallerContext,
    query: str,
    profile: ExpectedProfile,
    mode: GraphMode,
    bounds: GraphQueryBounds,
    remaining_deadline_seconds: float,
    callbacks: CountedLightRagCallbacks | None = None,
    relevant_version_ids: tuple[UUID, ...] | None = None,
) -> GraphRetrievalResult:
    """Run structured graph retrieval, resolve leads, and emit typed signals.

    Args:
        retriever: Adapter implementing ``GraphRetriever``.
        connection: Idle login connection.
        caller: Server-derived identity snapshot.
        query: Original user query text.
        profile: Frozen query profile with both keyword lists.
        mode: ``local``, graph ``hybrid``, or ``global`` steering.
        bounds: Adapter-owned candidate/token/deadline limits.
        remaining_deadline_seconds: Time left before the route deadline.
        callbacks: Optional counted callbacks for hidden-call proof.
        relevant_version_ids: Optional Hybrid-hit versions for readiness.

    Returns:
        Authoritative IDs, locators, limitations, and counters. Vendor prose
        is never evidence.

    Raises:
        GraphQueryError: Empty keywords, hidden callback, unsupported mode,
            or a cancelled/timed-out vendor query that cannot degrade.

    Side Effects:
        May call ``aquery_data``, enqueue bounded repair jobs, and record a
        survival sample. Never runs query-time Hybrid.
    """

    if mode not in {"local", "hybrid", "global"}:
        raise GraphQueryError("unsupported_graph_mode")
    hl_keywords = _keyword_tuple(profile.hl_keywords)
    ll_keywords = _keyword_tuple(profile.ll_keywords)
    if not hl_keywords or not ll_keywords:
        raise GraphQueryError("both_keyword_lists_required")

    empty_counters = GraphQueryCounters(
        keyword_extract=0,
        answer_generate=0,
        support_searches=0,
        repair_hybrid_searches=0,
    )
    limitations: list[GraphLimitation] = []
    if remaining_deadline_seconds <= 0:
        return _empty_result(
            mode=mode,
            limitations=(GraphLimitation(code=GraphLimitationCode.GRAPH_DEADLINE),),
            counters=empty_counters,
        )
    clamped = apply_query_bounds(
        top_k=bounds.top_k,
        chunk_top_k=bounds.chunk_top_k,
        max_entity_tokens=bounds.max_entity_tokens,
        max_relation_tokens=bounds.max_relation_tokens,
        max_total_tokens=bounds.max_total_tokens,
        deadline_seconds=min(bounds.deadline_seconds, remaining_deadline_seconds),
    )
    snapshot = load_query_workspace(connection)
    workspace_code = workspace_limitation_code(
        snapshot.state,
        pointer_attached=snapshot.pointer_attached,
    )
    if workspace_code is not None:
        counts = visibility_counts(
            connection,
            caller=caller,
            relevant_version_ids=relevant_version_ids,
        )
        return _empty_result(
            mode=mode,
            limitations=(
                GraphLimitation(code=workspace_code),
                *limitation_for_visibility(counts),
            ),
            counters=empty_counters,
            partial_readiness_count=counts.partial_readiness_count,
            acl_blindness_count=counts.acl_blindness_count,
        )
    if _temporal_graph_blocked(profile):
        counts = visibility_counts(
            connection,
            caller=caller,
            relevant_version_ids=relevant_version_ids,
        )
        return _empty_result(
            mode=mode,
            limitations=(
                GraphLimitation(code=GraphLimitationCode.TEMPORAL_GRAPH_LIMITATION),
                *limitation_for_visibility(counts),
            ),
            counters=empty_counters,
            partial_readiness_count=counts.partial_readiness_count,
            acl_blindness_count=counts.acl_blindness_count,
        )

    before = callbacks.counts.snapshot() if callbacks is not None else None
    try:
        leads = await asyncio.wait_for(
            _vendor_retrieve(
                retriever,
                mode=mode,
                query=query,
                hl_keywords=hl_keywords,
                ll_keywords=ll_keywords,
                bounds=clamped,
            ),
            timeout=clamped.deadline_seconds,
        )
    except TimeoutError as exc:
        raise GraphQueryError("graph_deadline") from exc
    except asyncio.CancelledError as exc:
        raise GraphQueryError("graph_cancelled") from exc
    except LightRagQueryFailure:
        counts = visibility_counts(
            connection,
            caller=caller,
            relevant_version_ids=relevant_version_ids,
        )
        return _empty_result(
            mode=mode,
            limitations=(
                GraphLimitation(code=GraphLimitationCode.GRAPH_EMPTY),
                *limitation_for_visibility(counts),
            ),
            counters=_counters_from_callbacks(
                callbacks,
                before=before,
                vendor_queries=1,
            ),
            partial_readiness_count=counts.partial_readiness_count,
            acl_blindness_count=counts.acl_blindness_count,
        )
    _assert_zero_hidden_calls(callbacks, before)

    if mode == "global":
        leads = clamp_global_steering(leads)
        counts = visibility_counts(
            connection,
            caller=caller,
            relevant_version_ids=relevant_version_ids,
        )
        return GraphRetrievalResult(
            mode="global",
            steering=tuple(
                GraphSteeringExpansion(topic=item.entity_name)
                for item in leads.entities
            ),
            limitations=(
                GraphLimitation(code=GraphLimitationCode.GLOBAL_STEERING_ONLY),
                *limitation_for_visibility(counts),
            ),
            counters=_counters_from_callbacks(
                callbacks,
                before=before,
                vendor_queries=1,
            ),
            partial_readiness_count=counts.partial_readiness_count,
            acl_blindness_count=counts.acl_blindness_count,
        )

    leads = clamp_graph_leads(leads, clamped)
    outcome = resolve_graph_leads(
        connection,
        caller=caller,
        leads=leads,
        snapshot=snapshot,
    )
    enqueue_query_repairs(connection, snapshot=snapshot, dropped=outcome.dropped)
    locators = load_canonical_locators(
        connection,
        caller=caller,
        chunk_ids=tuple(
            chunk_id
            for candidate in outcome.candidates
            for chunk_id in candidate.canonical_chunk_ids
        ),
    )
    ratio = graph_survival_ratio(
        supported=outcome.supported_candidates,
        returned=outcome.returned_candidates,
    )
    rolling = RollingSurvivalWindow(sample_count=0)
    if ratio is not None:
        rolling = record_survival_sample(connection, ratio=ratio, mode=mode)
    counts = visibility_counts(
        connection,
        caller=caller,
        relevant_version_ids=relevant_version_ids,
    )
    if ratio is None:
        limitations.append(GraphLimitation(code=GraphLimitationCode.GRAPH_EMPTY))
    elif ratio < GRAPH_SURVIVAL_FALLBACK_THRESHOLD:
        limitations.append(
            GraphLimitation(code=GraphLimitationCode.GRAPH_SURVIVAL_BELOW_THRESHOLD)
        )
    limitations.extend(limitation_for_visibility(counts))
    return GraphRetrievalResult(
        mode=mode,
        candidates=outcome.candidates,
        paths=outcome.paths,
        locators=locators,
        graph_survival_ratio=ratio,
        partial_readiness_count=counts.partial_readiness_count,
        acl_blindness_count=counts.acl_blindness_count,
        limitations=tuple(limitations),
        diagnostics=outcome.diagnostics,
        counters=_counters_from_callbacks(
            callbacks,
            before=before,
            vendor_queries=1,
            returned=outcome.returned_candidates,
            supported=outcome.supported_candidates,
        ),
        rolling_survival=rolling,
    )


def inspect_graph_authorized(
    *,
    connection: psycopg.Connection,
    caller: CallerContext,
    entity_keys: tuple[str, ...] = (),
    document_id: UUID | None = None,
    depth: int = 3,
    remaining_deadline_seconds: float = 10.0,
) -> GraphInspectResult:
    """Run bounded graph inspection through the identical resolver.

    Args:
        connection: Idle login connection.
        caller: Server-derived identity.
        entity_keys: Application entity keys, at most 12.
        document_id: Optional document seed.
        depth: Hop cap, clamped to 3.
        remaining_deadline_seconds: Inspection deadline remainder.

    Returns:
        At most 200 authorized rows. Native prose is omitted.

    Raises:
        GraphQueryError: Deadline exhausted or inspect seed overflow.
    """

    if remaining_deadline_seconds <= 0:
        return GraphInspectResult(
            limitations=(GraphLimitation(code=GraphLimitationCode.GRAPH_DEADLINE),),
            depth=max(1, min(depth, 3)),
        )
    snapshot = load_query_workspace(connection)
    workspace_code = workspace_limitation_code(
        snapshot.state,
        pointer_attached=snapshot.pointer_attached,
    )
    if workspace_code is not None:
        return GraphInspectResult(
            limitations=(GraphLimitation(code=workspace_code),),
            depth=max(1, min(depth, 3)),
        )
    try:
        result = inspect_graph(
            connection,
            caller=caller,
            snapshot=snapshot,
            entity_keys=entity_keys,
            document_id=document_id,
            depth=depth,
        )
    except GraphResolverError as exc:
        raise GraphQueryError(exc.reason) from exc
    return result


async def _vendor_retrieve(
    retriever: GraphRetriever,
    *,
    mode: GraphMode,
    query: str,
    hl_keywords: tuple[str, ...],
    ll_keywords: tuple[str, ...],
    bounds: GraphQueryBounds,
) -> GraphLeadSet:
    """Dispatch one structured vendor retrieve by mode.

    Args:
        retriever: Adapter protocol.
        mode: Query mode.
        query: User query.
        hl_keywords: Non-empty high-level keywords.
        ll_keywords: Non-empty low-level keywords.
        bounds: Clamped bounds.

    Returns:
        Structured leads.
    """

    method: Callable[..., Awaitable[GraphLeadSet]]
    if mode == "local":
        method = retriever.retrieve_local
    elif mode == "hybrid":
        method = retriever.retrieve_hybrid
    else:
        method = retriever.retrieve_global_steering
    return await method(
        query=query,
        hl_keywords=hl_keywords,
        ll_keywords=ll_keywords,
        bounds=bounds,
    )


def _keyword_tuple(field: ProfileField) -> tuple[str, ...]:
    """Extract a non-empty keyword tuple from a profile field.

    Args:
        field: High-level or low-level keyword field.

    Returns:
        Stripped keyword strings.
    """

    value = field.value
    if isinstance(value, list):
        return tuple(str(item).strip() for item in value if str(item).strip())
    if isinstance(value, str) and value.strip():
        return (value.strip(),)
    return ()


def _temporal_graph_blocked(profile: ExpectedProfile) -> bool:
    """Return whether current-only graph policy forbids this query.

    Args:
        profile: Frozen query profile.

    Returns:
        True for explicit ``as_of`` or historical relationship/multi-hop.
    """

    intent = str(profile.temporal_intent.value or "")
    historical = profile.historical_relationship.value
    if intent == TemporalIntent.AS_OF.value:
        return True
    return historical is True


def _assert_zero_hidden_calls(
    callbacks: CountedLightRagCallbacks | None,
    before: dict[str, int] | None,
) -> None:
    """Fail closed if keyword extraction or answer generation ran.

    Args:
        callbacks: Counted callbacks, if instrumented.
        before: Snapshot taken before the vendor query.

    Raises:
        GraphQueryError: A hidden keyword or answer callback occurred.
    """

    if callbacks is None or before is None:
        return
    after = callbacks.counts.snapshot()
    if after["keyword_extract"] != before["keyword_extract"]:
        raise GraphQueryError("hidden_keyword_or_answer_call")
    if after["answer_generate"] != before["answer_generate"]:
        raise GraphQueryError("hidden_keyword_or_answer_call")


def _counters_from_callbacks(
    callbacks: CountedLightRagCallbacks | None,
    *,
    before: dict[str, int] | None,
    vendor_queries: int,
    returned: int = 0,
    supported: int = 0,
) -> GraphQueryCounters:
    """Build counters that prove zero support searches and hidden LLM calls.

    Args:
        callbacks: Optional counted callbacks.
        before: Pre-query snapshot.
        vendor_queries: ``aquery_data`` invocations.
        returned: Clamped candidate count.
        supported: Surviving candidate count.

    Returns:
        Frozen counters with support searches hard-zeroed.
    """

    keyword = 0
    answer = 0
    embed = 0
    if callbacks is not None:
        snap = callbacks.counts.snapshot()
        if before is not None:
            keyword = snap["keyword_extract"] - before["keyword_extract"]
            answer = snap["answer_generate"] - before["answer_generate"]
            embed = snap["embed"] - before["embed"]
        else:
            keyword = snap["keyword_extract"]
            answer = snap["answer_generate"]
            embed = snap["embed"]
    return GraphQueryCounters(
        keyword_extract=keyword,
        answer_generate=answer,
        support_searches=0,
        repair_hybrid_searches=0,
        embed=embed,
        vendor_queries=vendor_queries,
        candidates_returned=returned,
        candidates_supported=supported,
    )


def _empty_result(
    *,
    mode: str,
    limitations: tuple[GraphLimitation, ...],
    counters: GraphQueryCounters,
    partial_readiness_count: int = 0,
    acl_blindness_count: int = 0,
) -> GraphRetrievalResult:
    """Return a fail-closed empty retrieval result.

    Args:
        mode: Query mode.
        limitations: Typed signals.
        counters: Query counters.
        partial_readiness_count: Authorized company-visible unreadiness.
        acl_blindness_count: Authorized-only restricted ineligible count.

    Returns:
        Empty result with limitations.
    """

    return GraphRetrievalResult(
        mode=mode,
        limitations=limitations,
        counters=counters,
        partial_readiness_count=partial_readiness_count,
        acl_blindness_count=acl_blindness_count,
    )
