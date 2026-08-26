"""Graph branch execution, bounds, and path snapshots."""

from __future__ import annotations

from smart_rag_core.query_admission.context import AuthorizedRuntimeContext
from smart_rag_core.query_fusion.models import GraphPassage, GraphPathInput
from smart_rag_core.query_profile.phase6_map import Phase6RouteFamily
from smart_rag_core.query_routing.acl_blindness import disclose_acl_blindness
from smart_rag_core.query_routing.branch_channels.hybrid import load_chunk_contexts
from smart_rag_core.query_routing.branch_results import (
    limitation_codes as codes_from_outcome,
)
from smart_rag_core.query_routing.constants import (
    FALLBACK_EMPTY_KEYWORDS,
    FALLBACK_GRAPH_UNAVAILABLE,
    FALLBACK_RETRIEVERS_UNBOUND,
    MAX_GRAPH_EXPANSIONS,
)
from smart_rag_core.query_routing.exceptions import QueryRoutingError
from smart_rag_core.query_routing.models import BranchKind, BranchResult, BranchSpec
from smart_rag_core.query_routing.protocols import GraphRetrieveLike
from smart_rag_core.retrieval.context import ContextFn
from smart_rag_core.runtime.async_bridge import run_coro_blocking
from smart_rag_core.security.identity import CallerContext


def run_graph(
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
    bounds = graph_bounds(remaining)
    method_name = {
        BranchKind.GRAPH_LOCAL: "retrieve_local",
        BranchKind.GRAPH_HYBRID: "retrieve_hybrid",
        BranchKind.GRAPH_GLOBAL_STEERING: "retrieve_global_steering",
    }[spec.kind]
    method = getattr(graph_retriever, method_name)
    lead_set = run_async(
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
    limitation_codes = codes_from_outcome(lead_set)
    timeout = (
        "graph_deadline" in limitation_codes or "graph_cancelled" in limitation_codes
    )
    fallback_reason = None
    if timeout:
        fallback_reason = "graph_deadline"
    paths, passages = graph_snapshots(lead_set, chunk_loader=chunk_loader)
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


def graph_bounds(remaining: float) -> object:
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


def run_async(coro: object) -> object:
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


def graph_snapshots(
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
    by_id = load_chunk_contexts(locator_ids, chunk_loader)
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
