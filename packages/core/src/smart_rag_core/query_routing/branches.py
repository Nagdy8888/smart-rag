"""Bounded parallel branch execution. Retrieve only; do not fuse or answer."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor, wait
from datetime import UTC, datetime
from enum import Enum
from typing import Literal, Protocol
from uuid import UUID

from smart_rag_core.query_admission.ceilings import (
    QueryRetrieveBudget,
    assert_deadline_open,
)
from smart_rag_core.query_admission.context import AuthorizedRuntimeContext
from smart_rag_core.query_admission.exceptions import QueryCeilingError
from smart_rag_core.query_fusion.models import (
    GraphPassage,
    GraphPathInput,
    HybridPassage,
)
from smart_rag_core.query_profile.phase6_map import Phase6RouteFamily
from smart_rag_core.query_routing.constants import (
    BRANCH_CONCURRENCY,
    FALLBACK_EMPTY_KEYWORDS,
    FALLBACK_GRAPH_UNAVAILABLE,
    FALLBACK_RETRIEVERS_UNBOUND,
    FALLBACK_TABLE_PLAN_INCOMPLETE,
    MAX_GRAPH_EXPANSIONS,
    WHOLE_DOCUMENT_SECTION_COVERAGE,
)
from smart_rag_core.query_routing.exceptions import QueryRoutingError
from smart_rag_core.query_routing.models import (
    BranchKind,
    BranchResult,
    BranchSpec,
    QueryPreparation,
    RetrievalPlan,
    TableEvidenceRecord,
)
from smart_rag_core.query_routing.preparation import caller_from_runtime
from smart_rag_core.retrieval.context import ContextFn
from smart_rag_core.retrieval.context_loader import ChunkContext
from smart_rag_core.runtime.async_bridge import run_coro_blocking
from smart_rag_core.security.identity import CallerContext, UserRole


class HybridRetrieveLike(Protocol):
    """Minimal Hybrid retrieve surface used by packet 2 tests and runtime."""

    query_budget: QueryRetrieveBudget | None

    def retrieve(
        self,
        *,
        query: str,
        caller: CallerContext,
        profile: object | None = None,
        deadline_seconds: float | None = None,
    ) -> object:
        """Run one Hybrid retrieve.

        Args:
            query: Branch query text.
            caller: Server-derived caller.
            profile: Typed query profile.
            deadline_seconds: Remaining retrieval slice.

        Returns:
            Object with ``ranked_ids`` and ``coverage`` attributes.
        """


class GraphRetrieveLike(Protocol):
    """Minimal async GraphRetriever used by packet 2 tests and runtime."""

    query_budget: QueryRetrieveBudget | None

    async def retrieve_local(
        self,
        *,
        query: str,
        hl_keywords: tuple[str, ...],
        ll_keywords: tuple[str, ...],
        bounds: object,
    ) -> object:
        """Return local graph leads.

        Args:
            query: Original query.
            hl_keywords: Precomputed high-level keywords.
            ll_keywords: Precomputed low-level keywords.
            bounds: Adapter bounds.

        Returns:
            Structured leads. Never evidence.
        """

    async def retrieve_hybrid(
        self,
        *,
        query: str,
        hl_keywords: tuple[str, ...],
        ll_keywords: tuple[str, ...],
        bounds: object,
    ) -> object:
        """Return graph-hybrid leads.

        Args:
            query: Original query.
            hl_keywords: Precomputed high-level keywords.
            ll_keywords: Precomputed low-level keywords.
            bounds: Adapter bounds.

        Returns:
            Structured leads.
        """

    async def retrieve_global_steering(
        self,
        *,
        query: str,
        hl_keywords: tuple[str, ...],
        ll_keywords: tuple[str, ...],
        bounds: object,
    ) -> object:
        """Return at most three steering expansions.

        Args:
            query: Original query.
            hl_keywords: Precomputed high-level keywords.
            ll_keywords: Precomputed low-level keywords.
            bounds: Adapter bounds.

        Returns:
            Steering leads. Never evidence.
        """


class TableExecuteLike(Protocol):
    """Minimal structured-table executor."""

    def __call__(self, spec: BranchSpec, caller: CallerContext) -> object:
        """Execute one table branch.

        Args:
            spec: Table branch spec.
            caller: Server-derived caller.

        Returns:
            Table result or raises.
        """


def disclose_acl_blindness(
    *,
    caller: CallerContext,
    count: int,
    authorized_visibility: bool,
) -> int | None:
    """Return ACL blindness only for the authorized visibility path.

    Unauthorized callers receive silence, not a zero that reveals existence.

    Args:
        caller: Server-derived caller.
        count: Resolver count for this caller.
        authorized_visibility: True only when this caller's resolver ran.

    Returns:
        The count, or None when suppressed.
    """

    del caller
    if not authorized_visibility:
        return None
    return count


def suppress_unauthorized_blindness(
    *,
    role: UserRole,
    count: int | None,
) -> int | None:
    """Hide injected privileged blindness counts from unauthorized roles.

    Args:
        role: Live profile role.
        count: Candidate count.

    Returns:
        None for viewer when the count did not come from their resolver.
        This helper is used by negative tests that inject a privileged count.
    """

    if count is None:
        return None
    if role is UserRole.VIEWER:
        return None
    return count


def _attach_retrieve_budget(
    *,
    runtime: AuthorizedRuntimeContext,
    caller: CallerContext,
    hybrid_retriever: HybridRetrieveLike | None,
    graph_retriever: GraphRetrieveLike | None,
    query_budget: QueryRetrieveBudget | None,
) -> QueryRetrieveBudget:
    """Bind the retrieve-time remaining ledger onto Hybrid and graph adapters.

    Args:
        runtime: Packet 1 context. Used when ``query_budget`` is omitted.
        caller: Server-derived caller copied onto a newly created ledger.
        hybrid_retriever: Optional Hybrid adapter.
        graph_retriever: Optional graph adapter.
        query_budget: Remaining after earlier counted calls. ``None`` starts
            at ``runtime.model_call_ceiling`` (standalone branch tests).

    Returns:
        The ledger bound onto adapters. Retrieve mutates it in place.
    """

    retrieve_budget = query_budget or QueryRetrieveBudget(
        remaining_model_calls=runtime.model_call_ceiling,
        remaining_usd=runtime.remaining_usd,
        caller=caller,
        run_id=runtime.run_id,
        reservation_id=runtime.reservation_id,
        expected_version=runtime.optimistic_version,
    )
    if retrieve_budget.caller is None:
        retrieve_budget.caller = caller
    if retrieve_budget.run_id is None:
        retrieve_budget.run_id = runtime.run_id
    if retrieve_budget.reservation_id is None:
        retrieve_budget.reservation_id = runtime.reservation_id
    if hybrid_retriever is not None:
        supabase = getattr(hybrid_retriever, "_supabase", None)
        if supabase is not None:
            retrieve_budget.connection = supabase
        hybrid_retriever.query_budget = retrieve_budget
    if graph_retriever is not None:
        graph_retriever.query_budget = retrieve_budget
    return retrieve_budget


def execute_branches(
    plan: RetrievalPlan,
    prep: QueryPreparation,
    runtime: AuthorizedRuntimeContext,
    *,
    hybrid_retriever: HybridRetrieveLike | None = None,
    graph_retriever: GraphRetrieveLike | None = None,
    table_executor: TableExecuteLike | None = None,
    query_budget: QueryRetrieveBudget | None = None,
    now: datetime | None = None,
    branch_concurrency: int = BRANCH_CONCURRENCY,
    cancel_check: Callable[[], bool] | None = None,
) -> tuple[BranchResult, ...]:
    """Execute required branches with server-bounded parallelism.

    Hybrid, LightRAG, StructuredTable, and citation lookup are invoked
    directly. There is no catalog LLM and no LightRAG keyword extraction.
    Retrieve-time embed, rerank, and LightRAG callbacks debit
    ``QueryRetrieveBudget`` on bound adapters.

    Args:
        plan: Compiled retrieval plan.
        prep: Typed preparation with precomputed keywords.
        runtime: Packet 1 context inherited by every branch.
        hybrid_retriever: Optional Hybrid retriever. Unbound Hybrid degrades.
        graph_retriever: Optional GraphRetriever. Missing Combined degrades.
        table_executor: Optional table executor.
        query_budget: Remaining after profile (or other prior consumes).
            Omit only in standalone tests that start at the family ceiling.
        now: Clock for deadline checks. Defaults to UTC now.
        branch_concurrency: Must be 1 or 2. Larger values are fan-out.
        cancel_check: Optional cancellation probe.

    Returns:
        One result per executed spec. Fusion/answer/verifier are not run.
        ``query_budget.remaining_model_calls`` reflects retrieve consumes.

    Raises:
        QueryRoutingError: Fan-out, historical graph path, empty-keyword
            graph call, or deadline exhaustion mapped from ceilings.
    """

    if branch_concurrency > BRANCH_CONCURRENCY or branch_concurrency < 1:
        raise QueryRoutingError("branch_fan_out")
    clock = now or datetime.now(UTC)
    try:
        assert_deadline_open(now=clock, deadline_at=runtime.deadline_at)
    except QueryCeilingError as exc:
        raise QueryRoutingError("deadline_exhausted") from exc
    caller = caller_from_runtime(runtime)
    remaining = max(0.1, (runtime.deadline_at - clock).total_seconds())
    _attach_retrieve_budget(
        runtime=runtime,
        caller=caller,
        hybrid_retriever=hybrid_retriever,
        graph_retriever=graph_retriever,
        query_budget=query_budget,
    )
    chunk_loader = _chunk_loader(hybrid_retriever, caller)
    results: list[BranchResult] = []
    independent = [
        spec for spec in plan.branches if spec.kind is not BranchKind.CITATION_LOOKUP
    ]
    lookups = [
        spec for spec in plan.branches if spec.kind is BranchKind.CITATION_LOOKUP
    ]
    grouped: dict[int, list[BranchSpec]] = {}
    for spec in independent:
        grouped.setdefault(spec.parallel_group, []).append(spec)
    for group_specs in grouped.values():
        if cancel_check is not None and cancel_check():
            break
        if len(group_specs) == 1 or branch_concurrency == 1:
            for spec in group_specs:
                results.append(
                    _run_spec(
                        spec,
                        plan=plan,
                        prep=prep,
                        runtime=runtime,
                        caller=caller,
                        remaining=remaining,
                        hybrid_retriever=hybrid_retriever,
                        graph_retriever=graph_retriever,
                        table_executor=table_executor,
                        chunk_loader=chunk_loader,
                    )
                )
            continue
        with ThreadPoolExecutor(max_workers=branch_concurrency) as pool:
            futures = [
                pool.submit(
                    _run_spec,
                    spec,
                    plan=plan,
                    prep=prep,
                    runtime=runtime,
                    caller=caller,
                    remaining=remaining,
                    hybrid_retriever=hybrid_retriever,
                    graph_retriever=graph_retriever,
                    table_executor=table_executor,
                    chunk_loader=chunk_loader,
                )
                for spec in group_specs
            ]
            done, pending = wait(futures, timeout=remaining)
            for item in pending:
                item.cancel()
            for item in done:
                results.append(item.result())
    hybrid_ids = tuple(
        item.ranked_ids for item in results if item.kind is BranchKind.HYBRID
    )
    resolved = hybrid_ids[0] if hybrid_ids else ()
    for spec in lookups:
        results.append(
            BranchResult(
                branch_id=spec.branch_id,
                kind=spec.kind,
                family=spec.family,
                run_id=runtime.run_id,
                reservation_id=runtime.reservation_id,
                query_text=spec.query_text,
                ranked_ids=resolved,
                status="ok",
            )
        )
    return tuple(results)


def _run_spec(
    spec: BranchSpec,
    *,
    plan: RetrievalPlan,
    prep: QueryPreparation,
    runtime: AuthorizedRuntimeContext,
    caller: CallerContext,
    remaining: float,
    hybrid_retriever: HybridRetrieveLike | None,
    graph_retriever: GraphRetrieveLike | None,
    table_executor: TableExecuteLike | None,
    chunk_loader: ContextFn | None,
) -> BranchResult:
    """Execute one spec and inherit packet 1 run/reservation ids.

    Args:
        spec: Branch spec.
        plan: Parent plan.
        prep: Preparation.
        runtime: Authorized context.
        caller: Caller snapshot.
        remaining: Remaining seconds.
        hybrid_retriever: Optional Hybrid retriever.
        graph_retriever: Optional graph retriever.
        table_executor: Optional table executor.
        chunk_loader: Authorized canonical-text loader for graph locators
            and Hybrid ranked-ID fallbacks.

    Returns:
        Branch result. Never an answer.

    Raises:
        QueryRoutingError: Historical graph or empty keywords.
    """

    if spec.kind in {
        BranchKind.GRAPH_LOCAL,
        BranchKind.GRAPH_HYBRID,
        BranchKind.GRAPH_GLOBAL_STEERING,
    } and (plan.historical_relationship or plan.temporal_graph_limitation):
        raise QueryRoutingError("historical_graph_path")
    if spec.kind is BranchKind.NO_RETRIEVAL:
        return _inherited_result(
            spec, runtime, status="ok", fallback_reason="no_retrieval"
        )
    if spec.kind is BranchKind.SCOPED_REFUSAL:
        return _inherited_result(
            spec,
            runtime,
            status="refused",
            fallback_reason=(
                plan.limitations[0] if plan.limitations else "scoped_refusal"
            ),
        )
    if spec.kind is BranchKind.HYBRID:
        return _run_hybrid(
            spec,
            prep=prep,
            runtime=runtime,
            caller=caller,
            remaining=remaining,
            hybrid_retriever=hybrid_retriever,
            whole_document=plan.whole_document_summary,
            chunk_loader=chunk_loader,
        )
    if spec.kind in {
        BranchKind.GRAPH_LOCAL,
        BranchKind.GRAPH_HYBRID,
        BranchKind.GRAPH_GLOBAL_STEERING,
        BranchKind.GRAPH_INSPECTION,
    }:
        return _run_graph(
            spec,
            runtime=runtime,
            remaining=remaining,
            graph_retriever=graph_retriever,
            caller=caller,
            chunk_loader=chunk_loader,
        )
    if spec.kind is BranchKind.STRUCTURED_TABLE:
        if spec.table_plan is None and table_executor is None:
            return _inherited_result(
                spec,
                runtime,
                status="degraded",
                fallback_reason=FALLBACK_TABLE_PLAN_INCOMPLETE,
            )
        if table_executor is None:
            return _inherited_result(
                spec,
                runtime,
                status="degraded",
                fallback_reason=FALLBACK_RETRIEVERS_UNBOUND,
            )
        table_result = table_executor(spec, caller)
        return BranchResult(
            branch_id=spec.branch_id,
            kind=spec.kind,
            family=spec.family,
            run_id=runtime.run_id,
            reservation_id=runtime.reservation_id,
            query_text=spec.query_text,
            status="ok",
            table_evidence=_table_evidence(table_result),
        )
    return _inherited_result(spec, runtime, status="ok")


def _inherited_result(
    spec: BranchSpec,
    runtime: AuthorizedRuntimeContext,
    *,
    status: Literal["ok", "degraded", "refused", "failed"],
    fallback_reason: str | None = None,
) -> BranchResult:
    """Build a branch result that copies packet 1 run and reservation ids.

    Args:
        spec: Branch spec.
        runtime: Authorized context.
        status: Branch status. Never an answer claim.
        fallback_reason: Optional limitation or degrade reason.

    Returns:
        Typed branch result.
    """

    return BranchResult(
        branch_id=spec.branch_id,
        kind=spec.kind,
        family=spec.family,
        run_id=runtime.run_id,
        reservation_id=runtime.reservation_id,
        query_text=spec.query_text,
        status=status,
        fallback_reason=fallback_reason,
    )


def _run_hybrid(
    spec: BranchSpec,
    *,
    prep: QueryPreparation,
    runtime: AuthorizedRuntimeContext,
    caller: CallerContext,
    remaining: float,
    hybrid_retriever: HybridRetrieveLike | None,
    whole_document: bool,
    chunk_loader: ContextFn | None,
) -> BranchResult:
    """Invoke HybridRetriever when bound.

    Args:
        spec: Hybrid spec.
        prep: Preparation.
        runtime: Authorized context.
        caller: Caller snapshot.
        remaining: Remaining seconds.
        hybrid_retriever: Optional retriever.
        whole_document: Whether section coverage must be 1.0.
        chunk_loader: Canonical text loader for ranked-ID fallbacks.

    Returns:
        Hybrid branch result. BM25 snippets are never marked as evidence.
    """

    if hybrid_retriever is None:
        return BranchResult(
            branch_id=spec.branch_id,
            kind=spec.kind,
            family=spec.family,
            run_id=runtime.run_id,
            reservation_id=runtime.reservation_id,
            query_text=spec.query_text,
            status="degraded",
            fallback_reason=FALLBACK_RETRIEVERS_UNBOUND,
        )
    outcome = hybrid_retriever.retrieve(
        query=spec.query_text,
        caller=caller,
        profile=prep.profile,
        deadline_seconds=min(remaining, 8.0),
    )
    ranked = _ranked_ids(outcome)
    coverage_score, ratio, uncovered = _coverage_bits(outcome, whole_document)
    status: Literal["ok", "degraded", "refused", "failed"] = "ok"
    fallback_text = _fallback_reason_text(outcome)
    if whole_document and (ratio is None or ratio < WHOLE_DOCUMENT_SECTION_COVERAGE):
        status = "refused"
        fallback_text = "section_coverage_below_1"
    return BranchResult(
        branch_id=spec.branch_id,
        kind=spec.kind,
        family=spec.family,
        run_id=runtime.run_id,
        reservation_id=runtime.reservation_id,
        query_text=spec.query_text,
        ranked_ids=ranked,
        coverage_score=coverage_score,
        section_coverage_ratio=ratio,
        uncovered_headings=uncovered,
        fallback_reason=fallback_text,
        status=status,
        bm25_snippets_used=False,
        graph_prose_used=False,
        hybrid_evidence=_hybrid_evidence(outcome, chunk_loader=chunk_loader),
    )


def _run_graph(
    spec: BranchSpec,
    *,
    runtime: AuthorizedRuntimeContext,
    remaining: float,
    graph_retriever: GraphRetrieveLike | None,
    caller: CallerContext,
    chunk_loader: ContextFn | None,
) -> BranchResult:
    """Invoke GraphRetriever with precomputed keywords only.

    Args:
        spec: Graph spec.
        runtime: Authorized context.
        remaining: Remaining seconds.
        graph_retriever: Optional retriever.
        caller: Caller snapshot.
        chunk_loader: Canonical text loader. Empty raw_text locators drop.

    Returns:
        Graph branch result. Graph prose is never evidence.

    Raises:
        QueryRoutingError: Empty keywords (never extract).
    """

    if spec.kind is BranchKind.GRAPH_INSPECTION:
        return BranchResult(
            branch_id=spec.branch_id,
            kind=spec.kind,
            family=spec.family,
            run_id=runtime.run_id,
            reservation_id=runtime.reservation_id,
            query_text=spec.query_text,
            status="ok" if graph_retriever is not None else "degraded",
            fallback_reason=None
            if graph_retriever is not None
            else FALLBACK_RETRIEVERS_UNBOUND,
            limitations=("graph_inspection_only",),
            acl_blindness_count=disclose_acl_blindness(
                caller=caller,
                count=0,
                authorized_visibility=graph_retriever is not None,
            ),
        )
    if graph_retriever is None:
        return BranchResult(
            branch_id=spec.branch_id,
            kind=BranchKind.HYBRID,
            family=Phase6RouteFamily.HYBRID,
            run_id=runtime.run_id,
            reservation_id=runtime.reservation_id,
            query_text=spec.query_text,
            status="degraded",
            fallback_reason=FALLBACK_GRAPH_UNAVAILABLE,
            limitations=("graph_unavailable",),
        )
    if not spec.hl_keywords or not spec.ll_keywords:
        raise QueryRoutingError(FALLBACK_EMPTY_KEYWORDS)
    bounds = _graph_bounds(remaining)
    method_name = {
        BranchKind.GRAPH_LOCAL: "retrieve_local",
        BranchKind.GRAPH_HYBRID: "retrieve_hybrid",
        BranchKind.GRAPH_GLOBAL_STEERING: "retrieve_global_steering",
    }[spec.kind]
    method = getattr(graph_retriever, method_name)
    lead_set = _run_async(
        method(
            query=spec.query_text,
            hl_keywords=spec.hl_keywords,
            ll_keywords=spec.ll_keywords,
            bounds=bounds,
        )
    )
    steering = getattr(lead_set, "entities", ())
    if (
        spec.kind is BranchKind.GRAPH_GLOBAL_STEERING
        and len(steering) > MAX_GRAPH_EXPANSIONS
    ):
        raise QueryRoutingError("branch_fan_out")
    counters = getattr(lead_set, "counters", None)
    extract_count = getattr(counters, "keyword_extract", 0) if counters else 0
    answer_count = getattr(counters, "answer_generate", 0) if counters else 0
    if extract_count:
        raise QueryRoutingError("hidden_keyword_call")
    if answer_count:
        raise QueryRoutingError("hidden_lightrag_answer")
    blindness = getattr(lead_set, "acl_blindness_count", None)
    published = None
    if isinstance(blindness, int):
        published = disclose_acl_blindness(
            caller=caller,
            count=blindness,
            authorized_visibility=True,
        )
    survival = getattr(lead_set, "graph_survival_ratio", None)
    limitation_codes = _limitation_codes(lead_set)
    timeout = (
        "graph_deadline" in limitation_codes or "graph_cancelled" in limitation_codes
    )
    fallback_reason = None
    if timeout:
        fallback_reason = "graph_deadline"
    paths, passages = _graph_snapshots(lead_set, chunk_loader=chunk_loader)
    if spec.kind is BranchKind.GRAPH_GLOBAL_STEERING:
        paths = tuple(
            item.model_copy(update={"steering_only": True, "fully_mapped": False})
            for item in paths
        )
        if "global_steering_only" not in limitation_codes:
            limitation_codes = ("global_steering_only", *limitation_codes)
    return BranchResult(
        branch_id=spec.branch_id,
        kind=spec.kind,
        family=spec.family,
        run_id=runtime.run_id,
        reservation_id=runtime.reservation_id,
        query_text=spec.query_text,
        status="ok",
        keyword_extract_count=0,
        lightrag_answer_generate_count=0,
        acl_blindness_count=published,
        graph_survival_ratio=survival if isinstance(survival, float) else None,
        limitations=limitation_codes,
        graph_prose_used=False,
        graph_paths=paths,
        graph_passages=passages,
        graph_timeout=timeout,
        fallback_reason=fallback_reason,
    )


def _chunk_loader(
    hybrid_retriever: HybridRetrieveLike | None,
    caller: CallerContext,
) -> ContextFn | None:
    """Bind the Hybrid canonical-text loader when the retriever exposes it.

    Args:
        hybrid_retriever: Optional Hybrid retriever.
        caller: Server-derived caller.

    Returns:
        ``ContextFn`` or None when unbound.
    """

    if hybrid_retriever is None:
        return None
    factory = getattr(hybrid_retriever, "authorized_chunk_loader", None)
    if not callable(factory):
        return None
    loader = factory(caller)
    if not callable(loader):
        return None
    return loader


def _load_chunk_contexts(
    chunk_ids: tuple[str, ...],
    chunk_loader: ContextFn | None,
) -> dict[str, ChunkContext]:
    """Load authorized canonical rows for one ID list.

    Args:
        chunk_ids: Canonical chunk UUID strings.
        chunk_loader: Optional ACL-rechecking loader.

    Returns:
        Mapping of chunk id string to authorized context. Missing,
        unauthorized, and unparsable IDs are omitted.
    """

    if chunk_loader is None or not chunk_ids:
        return {}
    parsed: list[UUID] = []
    for item in chunk_ids:
        try:
            parsed.append(UUID(str(item)))
        except ValueError:
            continue
    if not parsed:
        return {}
    loaded = chunk_loader(tuple(parsed))
    return {str(row.chunk_id): row for row in loaded}


def _graph_bounds(remaining: float) -> object:
    """Build adapter bounds without importing LightRAG at module load.

    Args:
        remaining: Remaining seconds.

    Returns:
        ``GraphQueryBounds`` instance.
    """

    from smart_rag_core.retrieval.graph import apply_query_bounds

    return apply_query_bounds(
        top_k=12,
        chunk_top_k=12,
        max_entity_tokens=4000,
        max_relation_tokens=4000,
        max_total_tokens=12000,
        deadline_seconds=max(0.1, remaining),
    )


def _run_async(coro: object) -> object:
    """Run one async graph retrieve from the sync query graph.

    Args:
        coro: Awaitable from GraphRetriever, or a sync test double result.

    Returns:
        Retrieve result.

    Side Effects:
        Uses ``run_coro_blocking`` so SSE ``astream`` (live loop) does not
        crash with nested ``asyncio.run``.
    """

    return run_coro_blocking(coro)


def _hybrid_evidence(
    outcome: object,
    *,
    chunk_loader: ContextFn | None,
) -> tuple[HybridPassage, ...]:
    """Snapshot Hybrid evidence units with 1-based post-rerank ranks.

    When evidence units are absent, RRF ``ranked_ids`` supply the allowed
    skip/fallback ranks. Canonical ``raw_text`` is loaded when a chunk
    loader is bound. Empty text is dropped and is never treated as a
    whole-passage citation.

    Args:
        outcome: Hybrid retrieve result.
        chunk_loader: Authorized canonical-text loader.

    Returns:
        Canonical Hybrid passages. BM25 snippets are never copied.
    """

    units = getattr(outcome, "evidence", ())
    records: list[HybridPassage] = []
    if units:
        unit_ids = tuple(str(unit.chunk_id) for unit in units)
        by_id = _load_chunk_contexts(unit_ids, chunk_loader)
        for index, unit in enumerate(units, start=1):
            locator = getattr(unit, "locator", None)
            record = by_id.get(str(unit.chunk_id))
            if record is not None:
                text = record.raw_text
            elif chunk_loader is None:
                text = str(getattr(unit, "citation_text", "") or "")
            else:
                continue
            if not text.strip():
                continue
            records.append(
                HybridPassage(
                    chunk_id=str(unit.chunk_id),
                    document_id=str(
                        record.document_id if record is not None else unit.document_id
                    ),
                    version_id=str(
                        record.version_id if record is not None else unit.version_id
                    ),
                    citation_text=text,
                    hybrid_rank=index,
                    section_path=tuple(
                        record.section_path
                        if record is not None
                        else getattr(locator, "section_path", ()) or ()
                    ),
                    page_number=(
                        record.page_number
                        if record is not None
                        else getattr(locator, "page_number", None)
                    ),
                    sheet_name=(
                        record.sheet_name
                        if record is not None
                        else getattr(locator, "sheet_name", None)
                    ),
                    range_ref=(
                        record.range_ref
                        if record is not None
                        else getattr(locator, "range_ref", None)
                    ),
                    source_url=(
                        record.source_url
                        if record is not None
                        else getattr(locator, "source_url", None)
                    ),
                )
            )
        return tuple(records)
    ranked = tuple(str(item) for item in getattr(outcome, "ranked_ids", ()) or ())
    by_id = _load_chunk_contexts(ranked, chunk_loader)
    for index, chunk_id in enumerate(ranked, start=1):
        record = by_id.get(chunk_id)
        text = record.raw_text if record is not None else ""
        if not text.strip():
            continue
        records.append(
            HybridPassage(
                chunk_id=chunk_id,
                document_id=str(record.document_id),
                version_id=str(record.version_id),
                citation_text=text,
                hybrid_rank=index,
                section_path=record.section_path,
                page_number=record.page_number,
                sheet_name=record.sheet_name,
                range_ref=record.range_ref,
                source_url=record.source_url,
            )
        )
    return tuple(records)


def _limitation_codes(outcome: object) -> tuple[str, ...]:
    """Normalize graph limitation codes from a retrieve result.

    Args:
        outcome: Graph retrieve result.

    Returns:
        Limitation code strings.
    """

    raw = getattr(outcome, "limitations", ())
    codes: list[str] = []
    for item in raw or ():
        code = getattr(item, "code", item)
        value = getattr(code, "value", code)
        codes.append(str(value))
    return tuple(codes)


def _graph_snapshots(
    outcome: object,
    *,
    chunk_loader: ContextFn | None,
) -> tuple[tuple[GraphPathInput, ...], tuple[GraphPassage, ...]]:
    """Capture resolved paths and canonical locators. Never vendor prose.

    Args:
        outcome: GraphRetrievalResult-like object, or a lead set without paths.
        chunk_loader: Authorized canonical-text loader. Empty raw_text drops.

    Returns:
        Path inputs and canonical locators with loaded ``raw_text``.
    """

    candidates = getattr(outcome, "candidates", ())
    support_by_id = {
        str(getattr(item, "object_id", "")): float(getattr(item, "support", 0.0) or 0.0)
        for item in candidates or ()
        if getattr(item, "object_id", None)
    }
    chunks_by_id = {
        str(getattr(item, "object_id", "")): tuple(
            str(chunk) for chunk in getattr(item, "canonical_chunk_ids", ()) or ()
        )
        for item in candidates or ()
        if getattr(item, "object_id", None)
    }
    paths: list[GraphPathInput] = []
    for path in getattr(outcome, "paths", ()) or ():
        statement_ids = tuple(
            str(item) for item in getattr(path, "statement_ids", ()) or ()
        )
        hops = int(getattr(path, "hops", len(statement_ids) or 1))
        supports = tuple(
            support_by_id.get(statement_id, 0.0) for statement_id in statement_ids
        )
        missing = any(
            statement_id not in support_by_id or support_by_id[statement_id] <= 0.0
            for statement_id in statement_ids
        )
        edge_chunks = tuple(
            chunks_by_id.get(statement_id, ()) for statement_id in statement_ids
        )
        canonical = tuple(
            str(chunk) for chunk in getattr(path, "canonical_chunk_ids", ()) or ()
        )
        if not canonical:
            canonical = tuple(
                dict.fromkeys(chunk for group in edge_chunks for chunk in group)
            )
        paths.append(
            GraphPathInput(
                statement_ids=statement_ids,
                hops=max(1, min(hops, 3)),
                canonical_chunk_ids=canonical,
                edge_chunk_ids=edge_chunks,
                edge_supports=supports,
                fully_mapped=bool(statement_ids) and not missing,
                unmapped=not statement_ids or missing,
                missing_edge_support=missing,
                steering_only=False,
            )
        )
    locators: list[GraphPassage] = []
    raw_locators = tuple(getattr(outcome, "locators", ()) or ())
    locator_ids = tuple(str(item.chunk_id) for item in raw_locators)
    by_id = _load_chunk_contexts(locator_ids, chunk_loader)
    for locator in raw_locators:
        chunk_id = str(locator.chunk_id)
        record = by_id.get(chunk_id)
        text = record.raw_text if record is not None else ""
        if not text.strip():
            continue
        locators.append(
            GraphPassage(
                chunk_id=chunk_id,
                document_id=str(
                    record.document_id if record is not None else locator.document_id
                ),
                version_id=str(
                    record.version_id if record is not None else locator.version_id
                ),
                citation_text=text,
                section_path=tuple(
                    record.section_path
                    if record is not None
                    else getattr(locator, "section_path", ()) or ()
                ),
                page_number=(
                    record.page_number
                    if record is not None
                    else getattr(locator, "page_number", None)
                ),
                sheet_name=(
                    record.sheet_name
                    if record is not None
                    else getattr(locator, "sheet_name", None)
                ),
                range_ref=(
                    record.range_ref
                    if record is not None
                    else getattr(locator, "range_ref", None)
                ),
                source_url=(
                    record.source_url
                    if record is not None
                    else getattr(locator, "source_url", None)
                ),
            )
        )
    return tuple(paths), tuple(locators)


def _table_evidence(outcome: object) -> TableEvidenceRecord | None:
    """Snapshot a structured-table result. Prose arithmetic is forbidden.

    Args:
        outcome: ``TableQueryResult`` or None.

    Returns:
        Table evidence record, or None when the executor returned nothing.
    """

    if outcome is None:
        return None
    table_id = getattr(outcome, "table_id", None)
    if table_id is None:
        return None
    rows_raw = getattr(outcome, "rows", ()) or ()
    rows = tuple(dict(item) for item in rows_raw)
    return TableEvidenceRecord(
        table_id=str(table_id),
        version_id=str(getattr(outcome, "version_id", "") or ""),
        document_id=str(getattr(outcome, "document_id", "") or ""),
        source_ranges=tuple(
            str(item) for item in getattr(outcome, "source_ranges", ()) or ()
        ),
        operation=str(getattr(outcome, "operation", "table") or "table"),
        rows=rows,
        sheet=getattr(outcome, "sheet", None),
        workbook=getattr(outcome, "workbook", None),
        units=getattr(outcome, "units", None),
        from_prose=False,
    )


def _ranked_ids(outcome: object) -> tuple[str, ...]:
    """Extract canonical ranked IDs from a Hybrid result.

    Args:
        outcome: Hybrid retrieve result.

    Returns:
        UUID strings.
    """

    ranked = getattr(outcome, "ranked_ids", ())
    return tuple(str(item) for item in ranked)


def _coverage_bits(
    outcome: object,
    whole_document: bool,
) -> tuple[float | None, float | None, tuple[str, ...]]:
    """Read coverage_score and section ratio from Hybrid coverage.

    Args:
        outcome: Hybrid retrieve result.
        whole_document: Whether to compute section coverage.

    Returns:
        Coverage score, section ratio, and uncovered headings.
    """

    coverage = getattr(outcome, "coverage", None)
    score = getattr(coverage, "coverage_score", None) if coverage else None
    uncovered = (
        tuple(getattr(coverage, "uncovered_headings", ()) or ()) if coverage else ()
    )
    ratio: float | None = None
    if whole_document:
        inventory = getattr(coverage, "uncovered_headings", ()) if coverage else ()
        notes = getattr(coverage, "notes", ()) if coverage else ()
        signal = str(getattr(coverage, "signal", "") or "")
        if signal.endswith("full_coverage") or signal == "full_coverage":
            ratio = 1.0
        elif uncovered:
            ratio = 0.0
        elif inventory == ():
            ratio = 1.0 if not notes else 0.0
        else:
            ratio = 0.0
    typed_score = score if isinstance(score, int | float) else None
    return (
        float(typed_score) if typed_score is not None else None,
        ratio,
        tuple(str(item) for item in uncovered),
    )


def _fallback_reason_text(outcome: object) -> str | None:
    """Normalize Hybrid fallback reasons without treating them as evidence.

    Args:
        outcome: Hybrid retrieve result or test double.

    Returns:
        Enum value or string, or None when absent/none.
    """

    fallback = getattr(outcome, "fallback_reason", None)
    if fallback is None:
        return None
    if isinstance(fallback, Enum):
        text = str(fallback.value)
    else:
        text = str(fallback)
    if text in {"", "none"}:
        return None
    return text


def inherit_ids(result: BranchResult, runtime: AuthorizedRuntimeContext) -> None:
    """Assert a result copied packet 1 run and reservation ids.

    Args:
        result: Branch result.
        runtime: Authorized context.

    Raises:
        QueryRoutingError: When ids do not match.
    """

    if (
        result.run_id != runtime.run_id
        or result.reservation_id != runtime.reservation_id
    ):
        raise QueryRoutingError("branch_authorization_mismatch")


def empty_keyword_guard(hl_keywords: Sequence[str], ll_keywords: Sequence[str]) -> None:
    """Fail closed instead of calling LightRAG keyword extraction.

    Args:
        hl_keywords: High-level keywords.
        ll_keywords: Low-level keywords.

    Raises:
        QueryRoutingError: ``empty_keywords``.
    """

    if not hl_keywords or not ll_keywords:
        raise QueryRoutingError(FALLBACK_EMPTY_KEYWORDS)
