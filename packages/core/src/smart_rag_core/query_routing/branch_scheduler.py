"""Bounded parallel branch scheduling. Retrieve only; do not fuse or answer."""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, wait
from datetime import UTC, datetime

from smart_rag_core.query_admission.ceilings import (
    QueryRetrieveBudget,
    assert_deadline_open,
)
from smart_rag_core.query_admission.context import AuthorizedRuntimeContext
from smart_rag_core.query_admission.exceptions import QueryCeilingError
from smart_rag_core.query_routing.branch_channels.citation import run_citation_lookups
from smart_rag_core.query_routing.branch_channels.graph import run_graph
from smart_rag_core.query_routing.branch_channels.hybrid import chunk_loader, run_hybrid
from smart_rag_core.query_routing.branch_channels.table import table_evidence
from smart_rag_core.query_routing.branch_results import inherited_result
from smart_rag_core.query_routing.constants import (
    BRANCH_CONCURRENCY,
    FALLBACK_RETRIEVERS_UNBOUND,
    FALLBACK_TABLE_PLAN_INCOMPLETE,
)
from smart_rag_core.query_routing.exceptions import QueryRoutingError
from smart_rag_core.query_routing.models import (
    BranchKind,
    BranchResult,
    BranchSpec,
    QueryPreparation,
    RetrievalPlan,
)
from smart_rag_core.query_routing.preparation import caller_from_runtime
from smart_rag_core.query_routing.protocols import (
    GraphRetrieveLike,
    HybridRetrieveLike,
    TableExecuteLike,
)
from smart_rag_core.query_routing.retrieve_budget import attach_retrieve_budget
from smart_rag_core.retrieval.context import ContextFn
from smart_rag_core.security.identity import CallerContext


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
    attach_retrieve_budget(
        runtime=runtime,
        caller=caller,
        hybrid_retriever=hybrid_retriever,
        graph_retriever=graph_retriever,
        query_budget=query_budget,
    )
    loader = chunk_loader(hybrid_retriever, caller)
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
                    run_spec(
                        spec,
                        plan=plan,
                        prep=prep,
                        runtime=runtime,
                        caller=caller,
                        remaining=remaining,
                        hybrid_retriever=hybrid_retriever,
                        graph_retriever=graph_retriever,
                        table_executor=table_executor,
                        chunk_loader=loader,
                    )
                )
            continue
        with ThreadPoolExecutor(max_workers=branch_concurrency) as pool:
            futures = [
                pool.submit(
                    run_spec,
                    spec,
                    plan=plan,
                    prep=prep,
                    runtime=runtime,
                    caller=caller,
                    remaining=remaining,
                    hybrid_retriever=hybrid_retriever,
                    graph_retriever=graph_retriever,
                    table_executor=table_executor,
                    chunk_loader=loader,
                )
                for spec in group_specs
            ]
            done, pending = wait(futures, timeout=remaining)
            for item in pending:
                item.cancel()
            for item in done:
                results.append(item.result())
    run_citation_lookups(lookups, results, runtime)
    return tuple(results)


def run_spec(
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
        return inherited_result(
            spec, runtime, status="ok", fallback_reason="no_retrieval"
        )
    if spec.kind is BranchKind.SCOPED_REFUSAL:
        return inherited_result(
            spec,
            runtime,
            status="refused",
            fallback_reason=(
                plan.limitations[0] if plan.limitations else "scoped_refusal"
            ),
        )
    if spec.kind is BranchKind.HYBRID:
        return run_hybrid(
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
        return run_graph(
            spec,
            runtime=runtime,
            remaining=remaining,
            graph_retriever=graph_retriever,
            caller=caller,
            chunk_loader=chunk_loader,
        )
    if spec.kind is BranchKind.STRUCTURED_TABLE:
        if spec.table_plan is None and table_executor is None:
            return inherited_result(
                spec,
                runtime,
                status="degraded",
                fallback_reason=FALLBACK_TABLE_PLAN_INCOMPLETE,
            )
        if table_executor is None:
            return inherited_result(
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
            table_evidence=table_evidence(table_result),
        )
    return inherited_result(spec, runtime, status="ok")
