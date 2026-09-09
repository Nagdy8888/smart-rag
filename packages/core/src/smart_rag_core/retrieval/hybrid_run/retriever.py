"""HybridRetriever orchestration: embed, channels, fuse, context, locators."""

from __future__ import annotations

import time
from uuid import UUID

import psycopg

from smart_rag_core.evaluation.schema import ExpectedProfile
from smart_rag_core.gateways.embedding import EmbeddingGateway
from smart_rag_core.query_admission.retrieve_budget import QueryRetrieveBudget
from smart_rag_core.query_profile.extract import extract_deterministic
from smart_rag_core.retrieval.context import ContextFn, RerankFn, select_hybrid_context
from smart_rag_core.retrieval.context_loader import (
    ChunkContext,
    fetch_authorized_chunk_context,
    fetch_authorized_heading_inventory,
    heading_inventory_from_contexts,
)
from smart_rag_core.retrieval.coverage_score import attach_numeric_coverage
from smart_rag_core.retrieval.frozen_profile import FrozenHybridProfile
from smart_rag_core.retrieval.hybrid import run_channels_parallel
from smart_rag_core.retrieval.hybrid_run.assemble import (
    call_assemble_hybrid,
    closed_result,
    compute_principal_scope_hash,
    elapsed_ms,
    fail_closed_query,
    hybrid_assemble_kwargs,
    query_texts,
)
from smart_rag_core.retrieval.hybrid_run.budget import (
    counted_rerank,
)
from smart_rag_core.retrieval.hybrid_run.channels import (
    compose_fallback,
    flatten_channel_candidates,
    identity_rerank,
    restrict_channel_candidates,
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
from smart_rag_core.retrieval.rerank import RerankFallbackReason, rerank_preload_ids
from smart_rag_core.retrieval.types import Bm25RetrievalResult
from smart_rag_core.security.identity import CallerContext
from smart_rag_core.text.arabic_normalize import normalize_arabic_v1


class HybridRetriever(HybridChannelJobsMixin):
    """Compose profile, channels, recheck, RRF, rerank, locators, and timing.

    This is the single retrieve entrypoint. BM25 snippets never become
    citation text. Holdout scoring is out of scope.

    External/model calls:
        One batched embedding gateway call over the original query plus at
        most three variants.
        At most one rerank call through the injected ``rerank`` callback.

    Deadline:
        ``RETRIEVAL_SLICE_SECONDS`` (8s statement-timeout bound) covers
        parallel channels plus rerank. The 25s ``HYBRID_DEADLINE_SECONDS``
        value is the Phase 6 full-run budget and is not used here.

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
    ) -> HybridRunResult:
        """Run one Hybrid retrieve and return ranked IDs plus locators.

        Args:
            query: Original user query. Empty or over-long forms fail closed.
            caller: Server-derived identity. Disabled callers are rejected.
            profile: Typed query profile. Optional variants are taken from it.
            principal_scope_hash: Cache principal hash. Derived when omitted.
            visibility_generation: ACL/visibility generation for the cache key.
            deadline_seconds: Retrieval+rerank slice. Defaults to 8.0 seconds.
            channel_jobs: Per-call job override for tests.
            restrict_version_id: When set, drop authorized candidates whose
                ``version_id`` does not match. Mapping uses this to keep one
                document version in a single retrieve.

        Returns:
            Ranked authorized IDs, ≤12 evidence units, coverage, fallback,
            ``first_evidence_ms``, and call counts.

        Side Effects:
            At most one embedding batch and one rerank call. When
            ``query_budget`` is bound, each gateway call consumes the
            run-local reservation or fails closed. Channel jobs may
            read ParadeDB and Supabase. No holdout access. No answer tokens.
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

        texts = query_texts(query, profile)
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
            )
        completed, timed_out, exhausted = run_channels_parallel(
            jobs,
            deadline_seconds=slice_seconds,
        )
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
        required_terms = (
            str_list_field(profile, "codes")
            + str_list_field(profile, "exact_terms")
            + str_list_field(profile, "quoted_phrases")
            + str_list_field(profile, "entities")
            + str_list_field(profile, "approved_aliases")
        )
        subquestions = str_list_field(profile, "subquestions")[:3]
        subquestion_count = len(subquestions)
        temporal_records = self._load_temporal_records(
            flatten_channel_candidates(dense_lists, bm25_result.candidates, term_lists)
        )
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
            query_normalized=normalize_arabic_v1(query)[:MAX_NORMALIZED_QUERY_CHARS],
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
        context_cache: dict[UUID, ChunkContext] = {}
        loader = self._bound_loader(caller, context_cache)
        remaining = max(0.0, slice_seconds - (time.perf_counter() - started))
        if self._retrieval_profile is not None:
            pool_size = self._retrieval_profile.rerank_pool_size
            max_per_document = self._retrieval_profile.rerank_max_per_document
        else:
            pool_size = RERANK_POOL_SIZE
            max_per_document = RERANK_MAX_PER_DOCUMENT
        preload_ids = rerank_preload_ids(
            assembled.fused,
            pool_size=pool_size,
            max_per_document=max_per_document,
        )
        contexts = loader(preload_ids) if preload_ids else ()
        rerank_fn: RerankFn = counted_rerank(
            self._rerank or identity_rerank,
            self.query_budget,
            count_gateway=self._rerank is not None,
        )
        rerank_calls = 0
        evidence: tuple[EvidenceUnit, ...] = ()
        selected_ids: tuple[UUID, ...] = ()
        rerank_order: tuple[UUID, ...] = fused_ids
        rerank_fallback = ""
        rerank_top_support: float | None = None
        profile_id = HYBRID_DEFAULT_PROFILE_ID
        if self._retrieval_profile is not None:
            profile_id = self._retrieval_profile.profile_id
        selection_profile = self._retrieval_profile
        coverage = assembled.coverage
        if assembled.fused:
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
            )
            if selection.usage is not None:
                rerank_calls = selection.usage.model_calls
            selected_ids = tuple(item.candidate.chunk_id for item in selection.passages)
            rerank_order = selection.rerank_order
            rerank_fallback = selection.fallback_reason.value
            locator_rows = loader(selected_ids) if selected_ids else ()
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
                subquestion_count=subquestion_count,
                supported_subquestions=supported,
                rerank_top_support=rerank_top_support,
            )
        if fallback is RetrievalFallbackReason.NONE:
            fallback = assembled.fallback_reason
        ranked = selected_ids or fused_ids
        return HybridRunResult(
            ranked_ids=ranked,
            evidence=evidence[:FINAL_EVIDENCE_MAX],
            coverage=coverage,
            fallback_reason=fallback,
            deadline_exhausted=assembled.deadline_exhausted,
            first_evidence_ms=elapsed_ms(started),
            embedding_call_count=1,
            rerank_call_count=rerank_calls,
            cache_key=assembled.cache_key,
            fused_ids=fused_ids,
            selected_ids=selected_ids,
            rerank_order=rerank_order,
            retrieval_profile_id=profile_id,
            rerank_fallback=rerank_fallback,
            rerank_top_support=rerank_top_support,
        )

    def authorized_chunk_loader(self, caller: CallerContext) -> ContextFn:
        """Return the ACL-rechecking context loader for canonical citation text.

        Args:
            caller: Server-derived identity.

        Returns:
            Loader that fetches authorized ``ChunkContext`` rows, including
            parents. Empty raw_text rows stay in the result so callers can
            drop them.

        Side Effects:
            May issue ``fetch_authorized_chunk_context`` RPCs when no
            injected loader is bound.
        """

        cache: dict[UUID, ChunkContext] = {}
        return self._bound_loader(caller, cache)

    def _bound_loader(
        self,
        caller: CallerContext,
        cache: dict[UUID, ChunkContext],
    ) -> ContextFn:
        """Return a context loader that rechecks parents through one cache.

        Args:
            caller: Server-derived identity for the RPC.
            cache: Mutable ID-to-row map shared across parent expansion.

        Returns:
            Loader used by ``select_hybrid_context``.
        """

        def load(chunk_ids: tuple[UUID, ...]) -> tuple[ChunkContext, ...]:
            """Load missing IDs then return authorized rows in request order.

            Args:
                chunk_ids: Requested canonical IDs.

            Returns:
                Cached authorized rows. Unauthorized IDs are omitted.
            """

            missing = tuple(item for item in chunk_ids if item not in cache)
            if missing:
                fetched = self._fetch_context(caller, missing)
                for row in fetched:
                    cache[row.chunk_id] = row
            return tuple(cache[item] for item in chunk_ids if item in cache)

        return load

    def _fetch_context(
        self,
        caller: CallerContext,
        chunk_ids: tuple[UUID, ...],
    ) -> tuple[ChunkContext, ...]:
        """Fetch authorized context via injection or the canonical RPC.

        Args:
            caller: Server-derived identity.
            chunk_ids: Canonical IDs. Batched at 75 per RPC.

        Returns:
            Authorized rows. Empty when no loader/connection is bound.
        """

        if self._load_context is not None:
            return self._load_context(chunk_ids)
        if self._supabase is None:
            return ()
        return fetch_authorized_chunk_context(
            self._supabase,
            caller=caller,
            chunk_ids=chunk_ids,
        )

    def _heading_inventory(
        self,
        caller: CallerContext,
        version_id: UUID | None,
    ) -> tuple[str, ...]:
        """Load authorized major headings for one current version.

        Args:
            caller: Server-derived identity.
            version_id: Resolved current version, when known.

        Returns:
            Stable section paths. Empty when the version is missing, the
            loader is injected, or the caller is unauthorized.
        """

        if version_id is None or self._load_context is not None:
            return ()
        if self._supabase is None:
            return ()
        return fetch_authorized_heading_inventory(
            self._supabase,
            caller=caller,
            version_id=version_id,
        )
