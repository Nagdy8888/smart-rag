"""Select final Hybrid evidence: rerank, MMR, quotas, and parent expansion."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from uuid import UUID

from smart_rag_core.evaluation.schema import ExpectedProfile
from smart_rag_core.retrieval.context_loader import ChunkContext
from smart_rag_core.retrieval.frozen_profile import FrozenHybridProfile
from smart_rag_core.retrieval.profiles import FINAL_EVIDENCE_MAX, FINAL_TOKEN_BUDGET
from smart_rag_core.retrieval.rerank import (
    ContextSelection,
    RerankFallbackReason,
    RerankPassage,
    RerankRanking,
    RerankUsage,
    apply_mmr,
    build_rerank_pool,
    literal_anchor_ask,
    literal_gold_already_loaded,
    promote_adas_model_passages,
    promote_chunking_window_passages,
    promote_expose_mode_passages,
    promote_helper_naming_passages,
    promote_host_literal_passages,
    promote_ide_product_passages,
    promote_method_label_passages,
    promote_listed_literal_passages,
    promote_named_code_definition_passages,
    promote_named_table_passages,
    promote_protocol_aspire_passages,
    promote_tool_description_passages,
    should_skip_trivial_exact,
    trim_token_budget,
)
from smart_rag_core.retrieval.types import RetrievalCandidate

RerankFn = Callable[
    [str, tuple[RerankPassage, ...], float],
    tuple[tuple[RerankRanking, ...], RerankUsage | None, RerankFallbackReason],
]
ContextFn = Callable[[tuple[UUID, ...]], tuple[ChunkContext, ...]]


def _promote_query_anchor_passages(
    trimmed: tuple[RerankPassage, ...],
    *,
    query: str,
    pool: tuple[RerankPassage, ...],
    limit: int,
    fused: tuple[RerankPassage, ...] | None = None,
) -> tuple[RerankPassage, ...]:
    """Pin helper-name, expose-mode, ADAS, and literal-label passages.

    Args:
        trimmed: Final evidence after MMR and token trim.
        query: Original user query. Untrusted.
        pool: Rerank pool passages.
        limit: Maximum passages to retain.
        fused: Optional full fused passage list. When set, literal anchors
            may promote a fused chunk that missed the rerank pool.

    Returns:
        Trimmed passages after additive query-anchor promotions.
    """

    search = fused if fused is not None else pool
    promoted = promote_helper_naming_passages(
        trimmed, query=query, pool=pool, limit=limit
    )
    promoted = promote_expose_mode_passages(
        promoted, query=query, pool=pool, limit=limit
    )
    promoted = promote_adas_model_passages(
        promoted, query=query, pool=pool, limit=limit
    )
    promoted = promote_chunking_window_passages(
        promoted, query=query, pool=search, limit=limit
    )
    promoted = promote_tool_description_passages(
        promoted, query=query, pool=search, limit=limit
    )
    promoted = promote_method_label_passages(
        promoted, query=query, pool=search, limit=limit
    )
    promoted = promote_host_literal_passages(
        promoted, query=query, pool=search, limit=limit
    )
    promoted = promote_ide_product_passages(
        promoted, query=query, pool=search, limit=limit
    )
    promoted = promote_protocol_aspire_passages(
        promoted, query=query, pool=search, limit=limit
    )
    promoted = promote_named_code_definition_passages(
        promoted, query=query, pool=search, limit=limit
    )
    promoted = promote_named_table_passages(
        promoted, query=query, pool=search, limit=limit
    )
    return promote_listed_literal_passages(
        promoted, query=query, pool=search, limit=limit
    )


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


def load_literal_fused_passages(
    *,
    query: str,
    fused: tuple[RetrievalCandidate, ...],
    passages: tuple[RerankPassage, ...],
    channel_hits: dict[UUID, frozenset[str]],
    load_context: ContextFn,
) -> tuple[RerankPassage, ...]:
    """Load fused-outside-pool contexts when a literal-anchor ask needs them.

    Pool preload deliberately skips most fused IDs. Literal promote then
    cannot see ``window_size`` / tool-description gold that ranked outside
    the rerank pool. For those rare asks, load the missing fused contexts
    once so promote can pin them into final evidence. When a matching gold
    span is already present in the pool passages, skip the extra load so
    deadline budget is preserved.

    Args:
        query: Original user query. Untrusted.
        fused: Authorized fused candidates in rank order.
        passages: Passages already built from pool preload contexts.
        channel_hits: Per-ID channel membership.
        load_context: ACL-rechecking context loader.

    Returns:
        Fused-order passages including any newly loaded literal holders.
        Unchanged when the ask is not literal-shaped, gold is already
        loaded, or nothing is missing.
    """

    if not literal_anchor_ask(query) or not fused:
        return passages
    if literal_gold_already_loaded(query, passages):
        return passages
    have = {item.candidate.chunk_id for item in passages}
    missing = tuple(
        item.chunk_id for item in fused if item.chunk_id not in have
    )
    if not missing:
        return passages
    extra = load_context(missing)
    if not extra:
        return passages
    by_id = {item.candidate.chunk_id: item for item in passages}
    for item in passages_from_context(fused, extra, channel_hits):
        by_id.setdefault(item.candidate.chunk_id, item)
    return tuple(
        by_id[item.chunk_id] for item in fused if item.chunk_id in by_id
    )


def expand_parents(
    selected: tuple[RerankPassage, ...],
    load_context: ContextFn,
    *,
    pool: tuple[RerankPassage, ...] = (),
) -> tuple[tuple[RerankPassage, ...], tuple[UUID, ...]]:
    """Load strongest authorized parents and adjacent siblings.

    Adjacent passages are taken from the already-authorized fused passage
    list (or pool) when they share a version and sit at ``chunk_index ± 1``.
    Using the full fused list matters for table asks: the titled row body
    often sits on the next chunk after a prose intro that ranked into the
    rerank pool.

    Args:
        selected: MMR-selected child passages.
        load_context: Authoritative context loader (rechecks ACL).
        pool: Authorized fused passages used to discover adjacent IDs.

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


def fallback_pool_order(
    pool: tuple[RerankPassage, ...],
    *,
    retrieval_profile: FrozenHybridProfile | None,
    dense_ids: Sequence[UUID],
) -> tuple[RerankPassage, ...]:
    """Order the pool used when rerank did not complete.

    ``rrf`` (every profile before ``hybrid_long_document_v3`` and the
    default constants) keeps fused order. ``dense_first`` moves passages
    the dense channel returned to the front in dense-rank order and keeps
    the rest in fused order. MMR, quotas, parent expansion, and token trim
    then run unchanged on the returned order.

    Args:
        pool: Passages in fused order.
        retrieval_profile: Frozen profile, or ``None`` for default constants.
        dense_ids: Dense IDs in channel-rank order. IDs outside ``pool`` are
            ignored, so this never adds a passage.

    Returns:
        The same passages, reordered. Never adds or drops a passage.
    """

    if retrieval_profile is None or retrieval_profile.fallback_order != "dense_first":
        return pool
    dense_rank: dict[UUID, int] = {}
    for index, chunk_id in enumerate(dense_ids):
        dense_rank.setdefault(chunk_id, index)
    dense = sorted(
        (item for item in pool if item.candidate.chunk_id in dense_rank),
        key=lambda item: dense_rank[item.candidate.chunk_id],
    )
    rest = [item for item in pool if item.candidate.chunk_id not in dense_rank]
    return (*dense, *rest)


def select_hybrid_context(
    *,
    query: str,
    profile: ExpectedProfile | None,
    fused: tuple[RetrievalCandidate, ...],
    contexts: tuple[ChunkContext, ...],
    channel_hits: dict[UUID, frozenset[str]],
    rerank: RerankFn,
    load_context: ContextFn,
    remaining_deadline_seconds: float,
    retrieval_profile: FrozenHybridProfile | None = None,
    pinned_ids: Sequence[UUID] = (),
    dense_ids: Sequence[UUID] = (),
) -> ContextSelection:
    """Run pool, optional one-shot rerank, MMR, quotas, and parent expansion.

    Args:
        query: Original user query.
        profile: Typed query profile. ``None`` skips the trivial-exact
            rerank skip because that path requires profile fields.
        fused: Authorized fused candidates.
        contexts: Context rows for fused IDs.
        channel_hits: Per-ID channel membership.
        rerank: One-operation reranker. Must not retry locally.
        load_context: Rechecking context loader for parents.
        remaining_deadline_seconds: Remaining Hybrid deadline share.
        retrieval_profile: Optional frozen/candidate bounds. ``None`` uses
            ``hybrid_default_v1`` constants.
        pinned_ids: Channel-head IDs that bypass the per-document pool cap.
            Must already be authorized fused IDs.
        dense_ids: Dense IDs in channel-rank order. Used only by the
            ``dense_first`` fallback order when rerank did not complete.

    Returns:
        Final evidence plus decision metadata. No answer text.

    Side Effects:
        At most one model call through ``rerank``. Parents are rechecked.
    """

    if retrieval_profile is not None:
        pool_size = retrieval_profile.rerank_pool_size
        max_per_document = retrieval_profile.rerank_max_per_document
        excerpt_chars = retrieval_profile.excerpt_chars
        excerpt_strategy = retrieval_profile.excerpt_strategy
        document_quota = retrieval_profile.document_quota
        section_quota = retrieval_profile.section_quota
        evidence_max = retrieval_profile.final_evidence_max
        token_budget = retrieval_profile.final_token_budget
        mmr_lambda = retrieval_profile.mmr_lambda
        mmr_depth = retrieval_profile.mmr_candidate_depth
    else:
        from smart_rag_core.retrieval.profiles import (
            DOCUMENT_QUOTA,
            MMR_CANDIDATE_DEPTH,
            MMR_LAMBDA,
            RERANK_EXCERPT_CHARS,
            RERANK_MAX_PER_DOCUMENT,
            RERANK_POOL_SIZE,
            SECTION_QUOTA,
        )

        pool_size = RERANK_POOL_SIZE
        max_per_document = RERANK_MAX_PER_DOCUMENT
        excerpt_chars = RERANK_EXCERPT_CHARS
        excerpt_strategy = "prefix"
        document_quota = DOCUMENT_QUOTA
        section_quota = SECTION_QUOTA
        evidence_max = FINAL_EVIDENCE_MAX
        token_budget = FINAL_TOKEN_BUDGET
        mmr_lambda = MMR_LAMBDA
        mmr_depth = MMR_CANDIDATE_DEPTH
    passages = passages_from_context(fused, contexts, channel_hits)
    passages = load_literal_fused_passages(
        query=query,
        fused=fused,
        passages=passages,
        channel_hits=channel_hits,
        load_context=load_context,
    )
    pool = build_rerank_pool(
        passages,
        pool_size=pool_size,
        max_per_document=max_per_document,
        excerpt_chars=excerpt_chars,
        query=query,
        excerpt_strategy=excerpt_strategy,
        pinned_ids=pinned_ids,
    )
    if len(pool) < 2:
        expanded, parent_ids = expand_parents(pool, load_context, pool=passages)
        trimmed = trim_token_budget(
            expanded,
            budget=token_budget,
            limit=evidence_max,
        )
        trimmed = _promote_query_anchor_passages(
            trimmed, query=query, pool=pool, limit=evidence_max, fused=passages
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
    if profile is not None and should_skip_trivial_exact(profile, pool):
        mmr_selected, dropped = apply_mmr(
            pool,
            query=query,
            lambda_mult=mmr_lambda,
            document_quota=document_quota,
            section_quota=section_quota,
            limit=evidence_max,
            candidate_depth=mmr_depth,
        )
        expanded, parent_ids = expand_parents(
            mmr_selected, load_context, pool=passages
        )
        trimmed = trim_token_budget(expanded, budget=token_budget, limit=evidence_max)
        trimmed = _promote_query_anchor_passages(
            trimmed, query=query, pool=pool, limit=evidence_max, fused=passages
        )
        return ContextSelection(
            passages=trimmed,
            rerank_order=tuple(item.candidate.chunk_id for item in pool),
            fallback_reason=RerankFallbackReason.SKIPPED_TRIVIAL_EXACT,
            mmr_dropped=dropped,
            expanded_parent_ids=parent_ids,
            usage=None,
            skipped_counterfactual=True,
        )
    from smart_rag_core.retrieval.profiles import RERANK_RESERVED_SECONDS

    if remaining_deadline_seconds < RERANK_RESERVED_SECONDS:
        fallback_pool = fallback_pool_order(
            pool, retrieval_profile=retrieval_profile, dense_ids=dense_ids
        )
        mmr_selected, dropped = apply_mmr(
            fallback_pool,
            query=query,
            lambda_mult=mmr_lambda,
            document_quota=document_quota,
            section_quota=section_quota,
            limit=evidence_max,
            candidate_depth=mmr_depth,
        )
        expanded, parent_ids = expand_parents(
            mmr_selected, load_context, pool=passages
        )
        trimmed = trim_token_budget(expanded, budget=token_budget, limit=evidence_max)
        trimmed = _promote_query_anchor_passages(
            trimmed, query=query, pool=pool, limit=evidence_max, fused=passages
        )
        return ContextSelection(
            passages=trimmed,
            rerank_order=tuple(item.candidate.chunk_id for item in fallback_pool),
            fallback_reason=RerankFallbackReason.TIMEOUT,
            mmr_dropped=dropped,
            expanded_parent_ids=parent_ids,
            usage=None,
            skipped_counterfactual=False,
        )
    rankings, usage, reason = rerank(query, pool, remaining_deadline_seconds)
    ordered = pool
    fallback = reason
    ranked_count = 0
    appended_count = 0
    if reason is RerankFallbackReason.NONE:
        ordered = apply_rankings(pool, rankings)
        appended_count = sum(1 for item in rankings if item.appended)
        ranked_count = len(rankings) - appended_count
        if appended_count:
            ordered = ordered[:ranked_count] + fallback_pool_order(
                ordered[ranked_count:],
                retrieval_profile=retrieval_profile,
                dense_ids=dense_ids,
            )
    else:
        ordered = fallback_pool_order(
            pool, retrieval_profile=retrieval_profile, dense_ids=dense_ids
        )
    mmr_selected, dropped = apply_mmr(
        ordered,
        query=query,
        lambda_mult=mmr_lambda,
        document_quota=document_quota,
        section_quota=section_quota,
        limit=evidence_max,
        candidate_depth=mmr_depth,
    )
    expanded, parent_ids = expand_parents(mmr_selected, load_context, pool=passages)
    trimmed = trim_token_budget(expanded, budget=token_budget, limit=evidence_max)
    trimmed = _promote_query_anchor_passages(
        trimmed, query=query, pool=pool, limit=evidence_max, fused=passages
    )
    top_support: float | None = None
    indices: tuple[int, ...] = ()
    if fallback is RerankFallbackReason.NONE and rankings:
        by_id = {item.chunk_id: item for item in rankings}
        if trimmed:
            winner = by_id.get(trimmed[0].candidate.chunk_id)
            if winner is not None:
                top_support = winner.support
        collected: list[int] = []
        seen_indices: set[int] = set()
        for passage in trimmed:
            row = by_id.get(passage.candidate.chunk_id)
            if row is None:
                continue
            for index in row.supported_subquestion_indices:
                if index in seen_indices:
                    continue
                seen_indices.add(index)
                collected.append(index)
        indices = tuple(collected)
    return ContextSelection(
        passages=trimmed,
        rerank_order=tuple(item.candidate.chunk_id for item in ordered),
        fallback_reason=fallback,
        mmr_dropped=dropped,
        expanded_parent_ids=parent_ids,
        usage=usage,
        skipped_counterfactual=False,
        rerank_top_support=top_support,
        supported_subquestion_indices=indices,
        rerank_ranked_count=ranked_count,
        rerank_appended_count=appended_count,
    )
