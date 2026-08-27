"""HybridRetriever orchestration: embed, channels, fuse, context, locators."""

from __future__ import annotations

import time
from typing import cast
from uuid import UUID

import psycopg

from smart_rag_core.evaluation.schema import ExpectedProfile
from smart_rag_core.gateways.embedding import (
    EmbeddingGateway,
    EmbeddingRequest,
    EmbeddingResponse,
)
from smart_rag_core.ingestion.embeddings.policy import (
    EMBEDDING_DIMENSIONS,
    EMBEDDING_MODEL,
)
from smart_rag_core.query_admission.exceptions import (
    QueryBudgetError,
    QueryCeilingError,
)
from smart_rag_core.query_admission.retrieve_budget import QueryRetrieveBudget
from smart_rag_core.retrieval.context import ContextFn, RerankFn, select_hybrid_context
from smart_rag_core.retrieval.context_loader import (
    ChunkContext,
    fetch_authorized_chunk_context,
    heading_inventory_from_contexts,
)
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
    counted_retrieve_send,
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
from smart_rag_core.retrieval.hybrid_run.evidence import (
    evidence_units,
    evidence_units_from_context,
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
from smart_rag_core.retrieval.hybrid_run.types import (
    FUSION_LIST_CAP,
    ChannelJob,
    EvidenceUnit,
    HybridRunResult,
)
from smart_rag_core.retrieval.profiles import (
    FINAL_EVIDENCE_MAX,
    MAX_NORMALIZED_QUERY_CHARS,
    RETRIEVAL_SLICE_SECONDS,
    RetrievalFallbackReason,
)
from smart_rag_core.retrieval.types import Bm25RetrievalResult
from smart_rag_core.runtime.async_bridge import run_coro_blocking
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
        embed_response, embed_error = self._embed_query_texts(
            texts, budget=self.query_budget
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
        want_full_summary = False
        query_type = query_type_field(profile)
        temporal_intent = temporal_intent_field(profile)
        target = target_date_field(profile)
        required_terms = str_list_field(profile, "codes") + str_list_field(
            profile, "exact_terms"
        )
        temporal_records = self._load_temporal_records(
            flatten_channel_candidates(dense_lists, bm25_result.candidates, term_lists)
        )
        assemble_kwargs = hybrid_assemble_kwargs(
            dense_variants=dense_lists,
            bm25_variants=(bm25_result.candidates,) if bm25_result.candidates else (),
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
        contexts = loader(fused_ids) if fused_ids else ()
        inventory = heading_inventory_from_contexts(contexts)
        covered = heading_inventory_from_contexts(
            tuple(item for item in contexts if item.chunk_id in set(fused_ids))
        )
        assembled = call_assemble_hybrid(
            heading_inventory=inventory,
            covered_headings=covered,
            kwargs=assemble_kwargs,
        )
        remaining = max(0.0, slice_seconds - (time.perf_counter() - started))
        rerank_fn: RerankFn = counted_rerank(
            self._rerank or identity_rerank,
            self.query_budget,
            count_gateway=self._rerank is not None,
        )
        rerank_calls = 0
        evidence: tuple[EvidenceUnit, ...] = ()
        if assembled.fused and resolved_profile is not None:
            selection = select_hybrid_context(
                query=query,
                profile=resolved_profile,
                fused=assembled.fused,
                contexts=contexts,
                channel_hits=assembled.channel_hits or {},
                rerank=rerank_fn,
                load_context=loader,
                remaining_deadline_seconds=remaining,
            )
            if selection.usage is not None:
                rerank_calls = selection.usage.model_calls
            selected_ids = tuple(item.candidate.chunk_id for item in selection.passages)
            locator_rows = loader(selected_ids) if selected_ids else ()
            evidence = evidence_units(selection.passages, locator_rows)
        elif assembled.fused:
            evidence = evidence_units_from_context(
                assembled.fused[:FINAL_EVIDENCE_MAX],
                contexts,
            )
        if fallback is RetrievalFallbackReason.NONE:
            fallback = assembled.fallback_reason
        return HybridRunResult(
            ranked_ids=tuple(item.chunk_id for item in assembled.fused),
            evidence=evidence[:FINAL_EVIDENCE_MAX],
            coverage=assembled.coverage,
            fallback_reason=fallback,
            deadline_exhausted=assembled.deadline_exhausted,
            first_evidence_ms=elapsed_ms(started),
            embedding_call_count=1,
            rerank_call_count=rerank_calls,
            cache_key=assembled.cache_key,
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

    def _embed_query_texts(
        self,
        texts: tuple[str, ...],
        budget: QueryRetrieveBudget | None = None,
    ) -> tuple[EmbeddingResponse | None, RetrievalFallbackReason | None]:
        """Issue one batched gateway embedding call.

        Args:
            texts: Unique original plus variants, already bounded.
            budget: Optional retrieve ledger. When set, the batch consumes
                the run-local reservation before the provider call.

        Returns:
            Response and optional fallback when the gateway fails or
            remaining cannot cover the embedding kind cap.
        """

        request = EmbeddingRequest(
            operation_key="hybrid.query_embed",
            inputs=texts,
            model=EMBEDDING_MODEL,
            dimensions=EMBEDDING_DIMENSIONS,
        )

        def _send() -> EmbeddingResponse:
            """Await the embedding gateway from this sync retrieve.

            Returns:
                Embedding response.

            Raises:
                Exception: Provider or loop failures. Mapped to dense
                    unavailable by the caller.
            """

            result = run_coro_blocking(self._embedding_gateway.embed(request))
            return cast(EmbeddingResponse, result)

        try:
            response = cast(
                EmbeddingResponse,
                counted_retrieve_send(
                    budget,
                    usage_kind="embedding",
                    model_id=EMBEDDING_MODEL,
                    send=_send,
                ),
            )
        except (QueryBudgetError, QueryCeilingError):
            return None, RetrievalFallbackReason.DENSE_UNAVAILABLE
        except Exception:
            return None, RetrievalFallbackReason.DENSE_UNAVAILABLE
        if len(response.vectors) != len(texts):
            return None, RetrievalFallbackReason.DENSE_UNAVAILABLE
        return response, None

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
