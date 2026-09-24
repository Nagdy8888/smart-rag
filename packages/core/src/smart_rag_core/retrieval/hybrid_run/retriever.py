"""HybridRetriever orchestration: embed, channels, fuse, context, locators."""

from __future__ import annotations

import time
from uuid import UUID

import psycopg

from smart_rag_core.evaluation.schema import ExpectedProfile
from smart_rag_core.gateways.embedding import EmbeddingGateway
from smart_rag_core.query_admission.retrieve_budget import QueryRetrieveBudget
from smart_rag_core.query_profile.extract import extract_deterministic
from smart_rag_core.retrieval.cache_store import (
    RetrievalCacheMode,
    RetrievalCacheStore,
)
from smart_rag_core.retrieval.context import ContextFn, RerankFn, select_hybrid_context
from smart_rag_core.retrieval.context_loader import (
    ChunkContext,
    heading_inventory_from_contexts,
)
from smart_rag_core.retrieval.coverage_score import (
    attach_numeric_coverage,
    exclude_source_selector_terms,
)
from smart_rag_core.retrieval.frozen_profile import FrozenHybridProfile
from smart_rag_core.retrieval.hybrid import run_channels_parallel
from smart_rag_core.retrieval.hybrid_run.assemble import (
    call_assemble_hybrid,
    closed_result,
    compute_principal_scope_hash,
    elapsed_ms,
    fail_closed_query,
    fused_first_evidence_ms,
    hybrid_assemble_kwargs,
    query_texts,
    remaining_slice_seconds,
)
from smart_rag_core.retrieval.hybrid_run.budget import (
    counted_rerank,
    timed_rerank,
)
from smart_rag_core.retrieval.hybrid_run.cache_lookup import HybridCacheLookupMixin
from smart_rag_core.retrieval.hybrid_run.channels import (
    compose_fallback,
    flatten_channel_candidates,
    identity_rerank,
    restrict_channel_candidates,
    unique_chunk_ids,
    unpack_bm25,
    unpack_dense,
    unpack_term,
)
from smart_rag_core.retrieval.hybrid_run.embed import embed_query_texts
from smart_rag_core.retrieval.hybrid_run.evidence import (
    evidence_units,
)
from smart_rag_core.retrieval.hybrid_run.jobs import HybridChannelJobsMixin
from smart_rag_core.retrieval.hybrid_run.profile_fields import (
    bool_field,
    query_type_field,
    str_field,
    str_list_field,
    target_date_field,
    temporal_intent_field,
)
from smart_rag_core.retrieval.hybrid_run.terms import (
    matched_terms_from_units,
    supported_subquestion_count,
)
from smart_rag_core.retrieval.hybrid_run.types import (
    FUSION_LIST_CAP,
    ChannelJob,
    EvidenceUnit,
    HybridRunResult,
)
from smart_rag_core.retrieval.profiles import (
    FINAL_EVIDENCE_MAX,
    HYBRID_DEFAULT_PROFILE_ID,
    MAX_NORMALIZED_QUERY_CHARS,
    RERANK_MAX_PER_DOCUMENT,
    RERANK_POOL_SIZE,
    RETRIEVAL_SLICE_SECONDS,
    RetrievalFallbackReason,
)
from smart_rag_core.retrieval.rerank import (
    RerankFallbackReason,
    channel_head_pins,
    rerank_preload_ids,
)
from smart_rag_core.retrieval.types import Bm25RetrievalResult
from smart_rag_core.security.identity import CallerContext
from smart_rag_core.text.arabic_normalize import normalize_arabic_v1


class HybridRetriever(HybridCacheLookupMixin, HybridChannelJobsMixin):
    """Compose profile, channels, recheck, RRF, rerank, locators, and timing.

    This is the single retrieve entrypoint. BM25 snippets never become
    citation text. Holdout scoring is out of scope.

    External/model calls:
        One batched embedding gateway call over the original query plus at
        most three variants.
        At most one rerank call through the injected ``rerank`` callback.

    Deadline:
        ``RETRIEVAL_SLICE_SECONDS`` (10s) covers parallel channels plus
        rerank after the embedding batch. The 8000 ms statement timeout
        stays the per-SQL bound. Embedding time is not subtracted from
        that slice. The 25s
        ``HYBRID_DEADLINE_SECONDS`` value is the Phase 6 full-run budget
        and is not used here.

    Failure/fallback:
        Empty or over-long queries fail closed with ``retrieval_empty``.
        Channel timeouts set ``deadline_exhausted`` and a named reason.
        Disabled callers return ``auth_context_invalid``.
    """

    def __init__(
        self,
        *,
        embedding_gateway: EmbeddingGateway,
        supabase: psycopg.Connection | None = None,
        paradedb: psycopg.Connection | None = None,
        dense: object | None = None,
        bm25: object | None = None,
        term: object | None = None,
        load_context: ContextFn | None = None,
        rerank: RerankFn | None = None,
        channel_jobs: dict[str, ChannelJob] | None = None,
        supabase_dsn: str | None = None,
        retrieval_profile: FrozenHybridProfile | None = None,
        retrieval_cache: RetrievalCacheStore | None = None,
    ) -> None:
        """Bind gateways, optional retrievers, and test doubles.

        Args:
            embedding_gateway: Shared embedding boundary. No bypass client.
            supabase: Canonical Postgres for context RPC and term/dense.
            paradedb: Private BM25 connection when the live retriever is used.
            dense: Object with sync ``retrieve`` matching ``DenseRetriever``.
            bm25: Object with sync ``retrieve`` matching ``Bm25Retriever``.
            term: Object with sync ``retrieve`` matching ``TermRetriever``.
            load_context: Optional context loader. Defaults to the RPC.
            rerank: Optional one-shot rerank callback.
            channel_jobs: Optional zero-arg jobs replacing retriever calls.
            supabase_dsn: Full Postgres URL used to open one idle connection
                per parallel channel. Dense, term, and BM25-recheck each need
                their own transaction; ``psycopg`` connections are not safe to
                share across those threads. ``Connection.info.dsn`` omits the
                password, so callers must pass the complete URL.
            retrieval_profile: Optional selection bounds. Runtime uses the
                frozen default; evaluation may inject the long-document
                candidate. Unfrozen ids stay rejected by
                ``load_frozen_profile``.
            retrieval_cache: Optional ID/rank cache. Hits still recheck ACL.
        """

        self._embedding_gateway = embedding_gateway
        self._supabase = supabase
        self._paradedb = paradedb
        self._supabase_dsn = supabase_dsn
        self._dense = dense
        self._bm25 = bm25
        self._term = term
        self._load_context = load_context
        self._rerank = rerank
        self._channel_jobs = channel_jobs
        self._retrieval_profile = retrieval_profile
        self._retrieval_cache = retrieval_cache
        self.query_budget: QueryRetrieveBudget | None = None

    def retrieve(
        self,
        *,
        query: str,
        caller: CallerContext,
        profile: ExpectedProfile | None = None,
        principal_scope_hash: str | None = None,
        visibility_generation: int = 1,
        deadline_seconds: float | None = None,
        channel_jobs: dict[str, ChannelJob] | None = None,
        restrict_version_id: UUID | None = None,
        cache_mode: RetrievalCacheMode = RetrievalCacheMode.NORMAL,
        source_selectors: tuple[str, ...] = (),
    ) -> HybridRunResult:
        """Run one Hybrid retrieve and return ranked IDs plus locators.

        Args:
            query: Original user query. Empty or over-long forms fail closed.
            caller: Server-derived identity. Disabled callers are rejected.
            profile: Typed query profile. Optional variants are taken from it.
            principal_scope_hash: Cache principal hash. Derived when omitted.
            visibility_generation: ACL/visibility generation for the cache key.
            deadline_seconds: Channel+rerank slice after embedding.
                Defaults to 8.0 seconds.
            channel_jobs: Per-call job override for tests.
            restrict_version_id: When set, drop authorized candidates whose
                ``version_id`` does not match. Mapping uses this to keep one
                document version in a single retrieve.
            cache_mode: ``cold_bypass`` skips ID/rank cache get/put without
                changing ranking. Exam retrieve must pass ``cold_bypass``.
            source_selectors: Authorized titles excluded from coverage
                required terms.

        Returns:
            Ranked authorized IDs, ?12 evidence units, coverage, fallback,
            ``first_evidence_ms``, and call counts.

        Side Effects:
            At most one embedding batch and one rerank call. When
            ``query_budget`` is bound, each gateway call consumes the
            run-local reservation or fails closed. Channel jobs may
            read ParadeDB and Supabase. No holdout access. No answer tokens.
            Records ID-free per-stage wall times in ``stage_timings_ms``.
        """

        started = time.perf_counter()
        slice_seconds = (
            RETRIEVAL_SLICE_SECONDS if deadline_seconds is None else deadline_seconds
        )
        scope_hash = principal_scope_hash or compute_principal_scope_hash(caller)
        if not caller.is_active():
            return closed_result(
                RetrievalFallbackReason.AUTH_CONTEXT_INVALID,
                started=started,
            )
        query_check = fail_closed_query(query)
        if query_check is not None:
            return closed_result(query_check, started=started)
        query_normalized = normalize_arabic_v1(query)[:MAX_NORMALIZED_QUERY_CHARS]
        profile_id = HYBRID_DEFAULT_PROFILE_ID
        if self._retrieval_profile is not None:
            profile_id = self._retrieval_profile.profile_id
        bypass_cache = cache_mode is RetrievalCacheMode.COLD_BYPASS
        if not bypass_cache:
            cached = self._cached_result(
                caller=caller,
                query_normalized=query_normalized,
                visibility_generation=visibility_generation,
                started=started,
                profile_id=profile_id,
                scope_hash=scope_hash,
            )
            if cached is not None:
                return cached

        texts = query_texts(query, profile)
        embed_started = time.perf_counter()
        embed_response, embed_error = embed_query_texts(
            self._embedding_gateway, texts, budget=self.query_budget
        )
        if embed_error is not None or embed_response is None:
            return closed_result(
                embed_error or RetrievalFallbackReason.DENSE_UNAVAILABLE,
                started=started,
                embedding_call_count=1,
            )
        vectors = embed_response.vectors
        timings: dict[str, int] = {"embed_ms": int(elapsed_ms(embed_started))}
        jobs: dict[str, ChannelJob] | None = (
            channel_jobs if channel_jobs is not None else self._channel_jobs
        )
        if jobs is None:
            jobs = self._build_channel_jobs(
                caller=caller,
                query=query,
                texts=texts[:FUSION_LIST_CAP],
                vectors=vectors[:FUSION_LIST_CAP],
                version_id=restrict_version_id,
                remaining_slice_seconds=slice_seconds,
            )
        channel_started = time.perf_counter()
        channel_ms: dict[str, int] = {}
        completed, timed_out, exhausted = run_channels_parallel(
            jobs,
            deadline_seconds=slice_seconds,
            durations_ms=channel_ms,
        )
        post_channel_started = time.perf_counter()
        timings["channels_ms"] = int(elapsed_ms(channel_started))
        for name in ("dense", "bm25", "term"):
            if name in channel_ms:
                timings[f"channel_{name}_ms"] = channel_ms[name]
        dense_lists, dense_reason = unpack_dense(completed.get("dense"))
        bm25_result = unpack_bm25(completed.get("bm25"))
        term_lists, term_reason = unpack_term(completed.get("term"))
        timed = frozenset(timed_out)
        if "dense" in timed:
            dense_lists = ()
            dense_reason = RetrievalFallbackReason.DENSE_UNAVAILABLE
        if "term" in timed:
            term_lists = ()
            term_reason = RetrievalFallbackReason.TERM_UNAVAILABLE
        bm25_fallback = bm25_result.fallback_reason
        if "bm25" in timed:
            bm25_result = Bm25RetrievalResult(
                scanned_ids=(),
                candidates=(),
                fallback_reason=RetrievalFallbackReason.TIMEOUT,
            )
            bm25_fallback = RetrievalFallbackReason.TIMEOUT
        dense_lists, bm25_result, term_lists = restrict_channel_candidates(
            dense_lists,
            bm25_result,
            term_lists,
            restrict_version_id,
        )
        dense_ids = unique_chunk_ids(
            tuple(item for variant in dense_lists for item in variant)
        )
        bm25_ids = unique_chunk_ids(bm25_result.candidates)
        term_ids = unique_chunk_ids(
            tuple(item for variant in term_lists for item in variant)
        )
        fallback = compose_fallback(
            dense_reason=dense_reason,
            term_reason=term_reason,
            bm25_fallback=bm25_fallback,
            deadline_exhausted=exhausted,
        )
        resolved_profile = profile
        media_dependence = bool_field(profile, "media_dependence")
        historical = bool_field(profile, "historical_relationship")
        negation_scope = str_field(profile, "negation_scope") or "none"
        query_type = query_type_field(profile)
        # Imported here so HybridRetriever load cannot cycle through query_routing.
        from smart_rag_core.query_routing.signals import is_whole_document_summary

        extract = extract_deterministic(query)
        scope_raw = str_field(profile, "document_scope") or extract.document_scope
        want_full_summary = is_whole_document_summary(
            query, extract
        ) and scope_raw not in {
            "section",
            "page",
            "range",
            "sheet",
        }
        temporal_intent = temporal_intent_field(profile)
        target = target_date_field(profile)
        required_terms = exclude_source_selector_terms(
            str_list_field(profile, "codes")
            + str_list_field(profile, "exact_terms")
            + str_list_field(profile, "quoted_phrases")
            + str_list_field(profile, "entities")
            + str_list_field(profile, "approved_aliases"),
            (
                *source_selectors,
                *str_list_field(profile, "requested_sources"),
            ),
        )
        subquestions = str_list_field(profile, "subquestions")[:3]
        subquestion_count = len(subquestions)
        temporal_started = time.perf_counter()
        temporal_records = self._load_temporal_records(
            flatten_channel_candidates(dense_lists, bm25_result.candidates, term_lists)
        )
        timings["temporal_load_ms"] = int(elapsed_ms(temporal_started))
        assemble_kwargs = hybrid_assemble_kwargs(
            dense_variants=dense_lists,
            bm25_variants=(
                bm25_result.variant_lists
                if bm25_result.variant_lists
                else ((bm25_result.candidates,) if bm25_result.candidates else ())
            ),
            term_variants=term_lists,
            bm25_fallback=bm25_fallback,
            temporal_intent=temporal_intent,
            target_date=target,
            temporal_records=temporal_records,
            want_full_summary=want_full_summary,
            media_dependence=media_dependence,
            negation_scope=negation_scope,
            historical_relationship=historical,
            principal_scope_hash=scope_hash,
            query_normalized=query_normalized,
            visibility_generation=visibility_generation,
            scanned_bm25=bm25_result.scanned_ids,
            query_type=query_type,
            required_terms=required_terms,
            matched_terms=(),
            subquestion_count=subquestion_count,
            deadline_exhausted=exhausted,
        )
        assembled = call_assemble_hybrid(
            heading_inventory=(),
            covered_headings=(),
            kwargs=assemble_kwargs,
        )
        if fallback is RetrievalFallbackReason.NONE and not assembled.fused:
            fallback = RetrievalFallbackReason.RETRIEVAL_EMPTY
        fused_ids = tuple(item.chunk_id for item in assembled.fused)
        fused_at = time.perf_counter() if fused_ids else None
        timings["assemble_ms"] = max(
            0, int(elapsed_ms(post_channel_started)) - timings["temporal_load_ms"]
        )
        context_cache: dict[UUID, ChunkContext] = {}
        loader = self._bound_loader(caller, context_cache)
        remaining = remaining_slice_seconds(
            slice_seconds=slice_seconds,
            slice_started=channel_started,
        )
        timings["rerank_gate_remaining_ms"] = int(remaining * 1000)
        preload_started = time.perf_counter()
        if self._retrieval_profile is not None:
            pool_size = self._retrieval_profile.rerank_pool_size
            max_per_document = self._retrieval_profile.rerank_max_per_document
        else:
            pool_size = RERANK_POOL_SIZE
            max_per_document = RERANK_MAX_PER_DOCUMENT
        pinned_ids = channel_head_pins(
            dense_ids=dense_ids,
            bm25_ids=bm25_ids,
            fused_ids=fused_ids,
        )
        preload_ids = rerank_preload_ids(
            assembled.fused,
            pool_size=pool_size,
            max_per_document=max_per_document,
            pinned_ids=pinned_ids,
        )
        contexts = loader(preload_ids) if preload_ids else ()
        timings["pool_preload_ms"] = int(elapsed_ms(preload_started))
        rerank_call_ms: list[int] = []
        rerank_fn: RerankFn = timed_rerank(
            counted_rerank(
                self._rerank or identity_rerank,
                self.query_budget,
                count_gateway=self._rerank is not None,
            ),
            rerank_call_ms,
        )
        rerank_calls = 0
        evidence: tuple[EvidenceUnit, ...] = ()
        selected_ids: tuple[UUID, ...] = ()
        rerank_order: tuple[UUID, ...] = fused_ids
        rerank_fallback = ""
        rerank_invalid_subcode = ""
        rerank_ranked_count = 0
        rerank_appended_count = 0
        rerank_top_support: float | None = None
        selection_profile = self._retrieval_profile
        coverage = assembled.coverage
        if assembled.fused:
            selection_started = time.perf_counter()
            selection = select_hybrid_context(
                query=query,
                profile=resolved_profile,
                fused=assembled.fused,
                contexts=contexts,
                channel_hits=assembled.channel_hits or {},
                rerank=rerank_fn,
                load_context=loader,
                remaining_deadline_seconds=remaining,
                retrieval_profile=selection_profile,
                pinned_ids=pinned_ids,
            )
            timings["selection_ms"] = int(elapsed_ms(selection_started))
            if rerank_call_ms:
                timings["rerank_call_ms"] = rerank_call_ms[0]
            if selection.usage is not None:
                rerank_calls = selection.usage.model_calls
                rerank_invalid_subcode = selection.usage.invalid_subcode
            selected_ids = tuple(item.candidate.chunk_id for item in selection.passages)
            rerank_order = selection.rerank_order
            rerank_fallback = selection.fallback_reason.value
            rerank_ranked_count = selection.rerank_ranked_count
            rerank_appended_count = selection.rerank_appended_count
            locator_started = time.perf_counter()
            locator_rows = loader(selected_ids) if selected_ids else ()
            timings["locator_reload_ms"] = int(elapsed_ms(locator_started))
            evidence = evidence_units(selection.passages, locator_rows)
            unique_docs = {item.candidate.document_id for item in selection.passages}
            unique_versions = {item.candidate.version_id for item in selection.passages}
            if want_full_summary and len(unique_docs) != 1:
                want_full_summary = False
            inventory_version = restrict_version_id
            if inventory_version is None and len(unique_versions) == 1:
                inventory_version = next(iter(unique_versions))
            rpc_inventory = self._heading_inventory(caller, inventory_version)
            covered = heading_inventory_from_contexts(locator_rows)
            inventory = rpc_inventory or covered
            matched_terms = matched_terms_from_units(required_terms, evidence)
            real_rerank = (
                selection.fallback_reason is RerankFallbackReason.NONE
                and rerank_calls == 1
            )
            rerank_top_support = selection.rerank_top_support if real_rerank else None
            supported = supported_subquestion_count(
                subquestions=subquestions,
                evidence=evidence,
                matched_terms=matched_terms,
                rerank_indices=(
                    selection.supported_subquestion_indices if real_rerank else ()
                ),
            )
            assemble_kwargs["matched_terms"] = matched_terms
            assemble_kwargs["want_full_summary"] = want_full_summary
            assembled = call_assemble_hybrid(
                heading_inventory=inventory,
                covered_headings=covered,
                kwargs=assemble_kwargs,
            )
            selected_cands = tuple(item.candidate for item in selection.passages)
            coverage = attach_numeric_coverage(
                assembled.coverage,
                fused=selected_cands,
                channel_hits=assembled.channel_hits or {},
                query_type=query_type,
                required_terms=required_terms,
                matched_terms=matched_terms,
                source_selectors=(
                    *source_selectors,
                    *str_list_field(resolved_profile, "requested_sources"),
                ),
                subquestion_count=subquestion_count,
                supported_subquestions=supported,
                rerank_top_support=rerank_top_support,
            )
        if fallback is RetrievalFallbackReason.NONE:
            fallback = assembled.fallback_reason
        ranked = selected_ids or fused_ids
        if (
            not bypass_cache
            and self._retrieval_cache is not None
            and fallback is RetrievalFallbackReason.NONE
            and ranked
        ):
            self._retrieval_cache.put_results(
                principal_scope_hash=scope_hash,
                query_normalized=query_normalized,
                visibility_generation=visibility_generation,
                chunk_ids=ranked,
                ranks=tuple(range(1, len(ranked) + 1)),
                retrieval_profile_id=profile_id,
            )
        return HybridRunResult(
            ranked_ids=ranked,
            evidence=evidence[:FINAL_EVIDENCE_MAX],
            coverage=coverage,
            fallback_reason=fallback,
            deadline_exhausted=assembled.deadline_exhausted,
            first_evidence_ms=fused_first_evidence_ms(
                started=started,
                fused_at=fused_at,
            ),
            embedding_call_count=1,
            rerank_call_count=rerank_calls,
            cache_key=assembled.cache_key,
            fused_ids=fused_ids,
            selected_ids=selected_ids,
            rerank_order=rerank_order,
            retrieval_profile_id=profile_id,
            rerank_fallback=rerank_fallback,
            rerank_top_support=rerank_top_support,
            dense_ids=dense_ids,
            bm25_ids=bm25_ids,
            term_ids=term_ids,
            stage_timings_ms={
                **timings,
                "retrieve_total_ms": int(elapsed_ms(started)),
            },
            rerank_invalid_subcode=rerank_invalid_subcode,
            rerank_ranked_count=rerank_ranked_count,
            rerank_appended_count=rerank_appended_count,
        )
