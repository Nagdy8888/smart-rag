"""Assemble FusionInput from packet 2 branch results and run selected ranking."""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from smart_rag_core.query_fusion.config_hash import fusion_config_hash
from smart_rag_core.query_fusion.constants import (
    FALLBACK_GRAPH_ONLY_ANSWER,
    FALLBACK_HIDDEN_KEYWORD,
    FALLBACK_HIDDEN_LIGHTRAG_ANSWER,
    FALLBACK_HOLDOUT_TUNING,
)
from smart_rag_core.query_fusion.exceptions import FusionError
from smart_rag_core.query_fusion.models import (
    FusionAlgorithm,
    FusionInput,
    FusionResult,
    GraphPassage,
    GraphPathInput,
    HybridPassage,
)
from smart_rag_core.query_fusion.quotas import (
    apply_document_section_quotas,
    cap_graph_discovered_only,
    graph_only_ratio,
)
from smart_rag_core.query_fusion.ranking import (
    graph_branch_usable,
    score_resolved_path_fusion,
)
from smart_rag_core.query_fusion.union import score_naive_union
from smart_rag_core.query_routing.models.plan import BranchKind

if TYPE_CHECKING:
    from smart_rag_core.query_routing.models.results import BranchResult


def fuse_evidence(
    fusion_input: FusionInput,
    *,
    algorithm: FusionAlgorithm,
) -> FusionResult:
    """Run resolved-path fusion or naive union, then frozen quotas and the 40% cap.

    Args:
        fusion_input: Hybrid ranks and resolved graph paths.
        algorithm: Ablation-selected algorithm.

    Returns:
        Bounded canonical evidence. Combined with unusable graph becomes
        effective Hybrid and never a graph-only answer.

    Raises:
        FusionError: Hidden LightRAG calls, holdout tuning, native prose,
            BM25 snippets, or graph-only answering.
    """

    if fusion_input.tune_on_holdout:
        raise FusionError(FALLBACK_HOLDOUT_TUNING)
    if fusion_input.keyword_extract_count:
        raise FusionError(FALLBACK_HIDDEN_KEYWORD)
    if fusion_input.lightrag_answer_generate_count:
        raise FusionError(FALLBACK_HIDDEN_LIGHTRAG_ANSWER)
    graph_usable, graph_reason = graph_branch_usable(fusion_input)
    requested = fusion_input.requested_route
    effective = fusion_input.effective_route
    fallback = fusion_input.graph_fallback_reason
    if not graph_usable and requested in {"combined", "composite"}:
        effective = "hybrid"
        fallback = graph_reason or fallback
    if algorithm is FusionAlgorithm.NAIVE_UNION:
        scored, discarded = score_naive_union(fusion_input)
    else:
        scored, discarded = score_resolved_path_fusion(
            fusion_input,
            graph_usable=graph_usable,
        )
    trimmed = apply_document_section_quotas(scored)
    capped, dropped = cap_graph_discovered_only(trimmed)
    hybrid_present = any(not item.graph_discovered_only for item in capped)
    had_graph_only = any(item.graph_discovered_only for item in trimmed)
    if had_graph_only and not hybrid_present:
        raise FusionError(FALLBACK_GRAPH_ONLY_ANSWER)
    return FusionResult(
        algorithm=algorithm,
        config_hash=fusion_config_hash(algorithm),
        requested_route=requested,
        effective_route=effective,
        fallback_reason=fallback,
        evidence=capped,
        dropped_graph_only=dropped,
        discarded_paths=discarded,
        graph_discovered_only_ratio=graph_only_ratio(capped),
        keyword_extract_count=0,
        lightrag_answer_generate_count=0,
    )


def fusion_input_from_branches(
    branch_results: tuple[BranchResult, ...],
    *,
    requested_route: str,
    effective_route: str,
    tune_on_holdout: bool = False,
) -> FusionInput:
    """Build fusion input from packet 2/3 branch snapshots.

    Args:
        branch_results: Hybrid, graph, and table branch outcomes.
        requested_route: Envelope family reserved at admit.
        effective_route: Planner family after correction.
        tune_on_holdout: Forbidden. Must stay false.

    Returns:
        Typed fusion input. Graph prose and BM25 snippets cannot be marked
        as evidence on ``BranchResult``.

    Raises:
        FusionError: Hidden keyword/answer counters or holdout tuning.
    """

    if tune_on_holdout:
        raise FusionError(FALLBACK_HOLDOUT_TUNING)
    hybrid: list[HybridPassage] = []
    paths: list[GraphPathInput] = []
    passages: list[GraphPassage] = []
    steering_ids: list[str] = []
    survival: float | None = None
    fallback: str | None = None
    timeout = False
    extract_total = 0
    answer_total = 0
    for branch in branch_results:
        extract_total += int(branch.keyword_extract_count)
        answer_total += int(branch.lightrag_answer_generate_count)
        if branch.kind is BranchKind.HYBRID:
            hybrid.extend(branch.hybrid_evidence)
            if branch.fallback_reason and fallback is None:
                fallback = branch.fallback_reason
        if branch.kind in {
            BranchKind.GRAPH_LOCAL,
            BranchKind.GRAPH_HYBRID,
        }:
            paths.extend(branch.graph_paths)
            passages.extend(branch.graph_passages)
            if branch.graph_survival_ratio is not None:
                survival = branch.graph_survival_ratio
            if branch.graph_timeout:
                timeout = True
            if branch.fallback_reason:
                fallback = branch.fallback_reason
            if branch.limitations:
                if "graph_deadline" in branch.limitations:
                    timeout = True
                    fallback = fallback or "graph_deadline"
        if branch.kind is BranchKind.GRAPH_GLOBAL_STEERING:
            for path in branch.graph_paths:
                steering_ids.extend(path.canonical_chunk_ids)
            for item in branch.graph_passages:
                steering_ids.append(item.chunk_id)
    if extract_total:
        raise FusionError(FALLBACK_HIDDEN_KEYWORD)
    if answer_total:
        raise FusionError(FALLBACK_HIDDEN_LIGHTRAG_ANSWER)
    extract: Literal[0] = 0
    answer: Literal[0] = 0
    return FusionInput(
        requested_route=requested_route,
        effective_route=effective_route,
        hybrid_passages=tuple(hybrid),
        graph_paths=tuple(paths),
        graph_passages=tuple(passages),
        graph_survival_ratio=survival,
        graph_fallback_reason=fallback,
        graph_timeout=timeout,
        keyword_extract_count=extract,
        lightrag_answer_generate_count=answer,
        tune_on_holdout=False,
        global_steering_chunk_ids=tuple(dict.fromkeys(steering_ids)),
    )
