"""Select final Hybrid evidence: rerank, MMR, quotas, and parent expansion."""

from __future__ import annotations

from collections.abc import Callable
from uuid import UUID

from smart_rag_core.evaluation.schema import ExpectedProfile
from smart_rag_core.retrieval.context_loader import ChunkContext
from smart_rag_core.retrieval.profiles import FINAL_EVIDENCE_MAX, FINAL_TOKEN_BUDGET
from smart_rag_core.retrieval.rerank import (
    ContextSelection,
    RerankFallbackReason,
    RerankPassage,
    RerankRanking,
    RerankUsage,
    apply_mmr,
    build_rerank_pool,
    should_skip_trivial_exact,
    trim_token_budget,
)
from smart_rag_core.retrieval.types import RetrievalCandidate

RerankFn = Callable[
    [str, tuple[RerankPassage, ...], float],
    tuple[tuple[RerankRanking, ...], RerankUsage | None, RerankFallbackReason],
]
ContextFn = Callable[[tuple[UUID, ...]], tuple[ChunkContext, ...]]


def passages_from_context(
    fused: tuple[RetrievalCandidate, ...],
    contexts: tuple[ChunkContext, ...],
    channel_hits: dict[UUID, frozenset[str]],
) -> tuple[RerankPassage, ...]:
    """Join fused IDs to authorized canonical text.

    Args:
        fused: Fused authorized candidates.
        contexts: Rechecked context rows.
        channel_hits: Independent channel membership.

    Returns:
        Passages in fused order. IDs missing from context are dropped.
    """

    by_id = {item.chunk_id: item for item in contexts}
    passages: list[RerankPassage] = []
    for candidate in fused:
        record = by_id.get(candidate.chunk_id)
        if record is None:
            continue
        passages.append(
            RerankPassage(
                candidate=candidate,
                raw_text=record.raw_text,
                section_path=record.section_path,
                page_number=record.page_number,
                parent_chunk_id=record.parent_chunk_id,
                chunk_index=record.chunk_index,
                token_count=record.token_count or max(1, len(record.raw_text.split())),
                channels=channel_hits.get(candidate.chunk_id, frozenset()),
            )
        )
    return tuple(passages)


def expand_parents(
    selected: tuple[RerankPassage, ...],
    load_context: ContextFn,
    *,
    pool: tuple[RerankPassage, ...] = (),
) -> tuple[tuple[RerankPassage, ...], tuple[UUID, ...]]:
    """Load strongest authorized parents and adjacent siblings.

    Adjacent passages are taken from the already-authorized pool when they
    share a version and sit at ``chunk_index ± 1``. Parents are rechecked
    through ``load_context`` because they may be non-representative.

    Args:
        selected: MMR-selected child passages.
        load_context: Authoritative context loader (rechecks ACL).
        pool: Authorized fused pool used to discover adjacent IDs.

    Returns:
        Expanded list and parent IDs that survived recheck.
    """

    extra: list[UUID] = []
    for item in selected:
        if item.parent_chunk_id is not None:
            extra.append(item.parent_chunk_id)
    loaded = load_context(tuple(extra)) if extra else ()
    by_id = {item.chunk_id: item for item in loaded}
    neighbors = {(item.candidate.version_id, item.chunk_index): item for item in pool}
    expanded: list[RerankPassage] = []
    parent_ids: list[UUID] = []
    seen: set[UUID] = set()

    def _append(passage: RerankPassage) -> None:
        """Append one unseen passage.

        Args:
            passage: Candidate evidence unit.
        """

        chunk_id = passage.candidate.chunk_id
        if chunk_id in seen:
            return
        seen.add(chunk_id)
        expanded.append(passage)

    for item in selected:
        _append(item)
        parent_id = item.parent_chunk_id
        if parent_id is not None and parent_id not in seen:
            record = by_id.get(parent_id)
            if record is not None:
                seen.add(parent_id)
                parent_ids.append(parent_id)
                expanded.append(
                    RerankPassage(
                        candidate=RetrievalCandidate(
                            chunk_id=record.chunk_id,
                            document_id=record.document_id,
                            version_id=record.version_id,
                            channel_rank=item.candidate.channel_rank,
                            channel_score=item.candidate.channel_score,
                        ),
                        raw_text=record.raw_text,
                        section_path=record.section_path,
                        page_number=record.page_number,
                        parent_chunk_id=record.parent_chunk_id,
                        chunk_index=record.chunk_index,
                        token_count=record.token_count
                        or max(1, len(record.raw_text.split())),
                        channels=item.channels,
                        excerpt=record.raw_text,
                    )
                )
        for offset in (-1, 1):
            neighbor = neighbors.get(
                (item.candidate.version_id, item.chunk_index + offset)
            )
            if neighbor is not None:
                _append(neighbor)
    return tuple(expanded), tuple(parent_ids)


def apply_rankings(
    pool: tuple[RerankPassage, ...],
    rankings: tuple[RerankRanking, ...],
) -> tuple[RerankPassage, ...]:
    """Reorder the pool by validated rerank ranks.

    Args:
        pool: Pre-rerank pool.
        rankings: Validated unique rankings.

    Returns:
        Pool in rerank order.
    """

    by_id = {item.candidate.chunk_id: item for item in pool}
    return tuple(by_id[item.chunk_id] for item in rankings)


def select_hybrid_context(
    *,
    query: str,
    profile: ExpectedProfile,
    fused: tuple[RetrievalCandidate, ...],
    contexts: tuple[ChunkContext, ...],
    channel_hits: dict[UUID, frozenset[str]],
    rerank: RerankFn,
    load_context: ContextFn,
    remaining_deadline_seconds: float,
) -> ContextSelection:
    """Run pool, optional one-shot rerank, MMR, quotas, and parent expansion.

    Args:
        query: Original user query.
        profile: Typed query profile.
        fused: Authorized fused candidates.
        contexts: Context rows for fused IDs.
        channel_hits: Per-ID channel membership.
        rerank: One-operation reranker. Must not retry locally.
        load_context: Rechecking context loader for parents.
        remaining_deadline_seconds: Remaining Hybrid deadline share.

    Returns:
        Final evidence plus decision metadata. No answer text.

    Side Effects:
        At most one model call through ``rerank``. Parents are rechecked.
    """

    passages = passages_from_context(fused, contexts, channel_hits)
    pool = build_rerank_pool(passages)
    if len(pool) < 2:
        expanded, parent_ids = expand_parents(pool, load_context, pool=pool)
        trimmed = trim_token_budget(
            expanded,
            budget=FINAL_TOKEN_BUDGET,
            limit=FINAL_EVIDENCE_MAX,
        )
        return ContextSelection(
            passages=trimmed,
            rerank_order=tuple(item.candidate.chunk_id for item in pool),
            fallback_reason=RerankFallbackReason.INSUFFICIENT_CANDIDATES,
            mmr_dropped=(),
            expanded_parent_ids=parent_ids,
            usage=None,
            skipped_counterfactual=False,
        )
    if should_skip_trivial_exact(profile, pool):
        mmr_selected, dropped = apply_mmr(pool, query=query)
        expanded, parent_ids = expand_parents(mmr_selected, load_context, pool=pool)
        trimmed = trim_token_budget(expanded)
        return ContextSelection(
            passages=trimmed,
            rerank_order=tuple(item.candidate.chunk_id for item in pool),
            fallback_reason=RerankFallbackReason.SKIPPED_TRIVIAL_EXACT,
            mmr_dropped=dropped,
            expanded_parent_ids=parent_ids,
            usage=None,
            skipped_counterfactual=True,
        )
    rankings, usage, reason = rerank(query, pool, remaining_deadline_seconds)
    ordered = pool
    fallback = reason
    if reason is RerankFallbackReason.NONE:
        ordered = apply_rankings(pool, rankings)
    mmr_selected, dropped = apply_mmr(ordered, query=query)
    expanded, parent_ids = expand_parents(mmr_selected, load_context, pool=pool)
    trimmed = trim_token_budget(expanded)
    return ContextSelection(
        passages=trimmed,
        rerank_order=tuple(item.candidate.chunk_id for item in ordered),
        fallback_reason=fallback,
        mmr_dropped=dropped,
        expanded_parent_ids=parent_ids,
        usage=usage,
        skipped_counterfactual=False,
    )
