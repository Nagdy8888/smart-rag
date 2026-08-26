"""Single Hybrid retrieve composition: embed, channels, fuse, context, locators."""

from __future__ import annotations

import hashlib
import time
from collections.abc import Callable, Generator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime
from typing import TYPE_CHECKING, Protocol, TypedDict, TypeGuard, cast
from uuid import UUID, uuid4

import psycopg

from smart_rag_core.evaluation.schema import ExpectedProfile, ProfileField, QueryType
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
from smart_rag_core.retrieval.context import ContextFn, RerankFn, select_hybrid_context
from smart_rag_core.retrieval.context_loader import (
    ChunkContext,
    fetch_authorized_chunk_context,
    heading_inventory_from_contexts,
)
from smart_rag_core.retrieval.coverage import CoverageSignal, HybridCoverage
from smart_rag_core.retrieval.hybrid import (
    HybridRetrievalResult,
    assemble_hybrid,
    run_channels_parallel,
)
from smart_rag_core.retrieval.profiles import (
    FINAL_EVIDENCE_MAX,
    MAX_NORMALIZED_QUERY_CHARS,
    RERANK_MODEL_ID,
    RETRIEVAL_SLICE_SECONDS,
    RetrievalFallbackReason,
)
from smart_rag_core.retrieval.rerank import (
    RerankFallbackReason,
    RerankPassage,
    RerankRanking,
    RerankUsage,
)
from smart_rag_core.retrieval.temporal import TemporalDocument, TemporalIntent
from smart_rag_core.retrieval.types import (
    Bm25RetrievalResult,
    DenseRetrievalResult,
    RetrievalCandidate,
    TermRetrievalResult,
)
from smart_rag_core.runtime.async_bridge import run_coro_blocking
from smart_rag_core.security.identity import CallerContext
from smart_rag_core.text.arabic_normalize import normalize_arabic_v1

if TYPE_CHECKING:
    from smart_rag_core.query_admission.ceilings import QueryRetrieveBudget

# Fusion rejects a fourth per-channel list. Embeddings still batch original
# plus at most three variants (at most four unique strings) as one call.
_FUSION_LIST_CAP = 3
_EMBED_TEXT_CAP = 4

_CandidateList = tuple[RetrievalCandidate, ...]
_VariantLists = tuple[_CandidateList, ...]
_DenseRetrieveCall = Callable[..., DenseRetrievalResult | _CandidateList]
_TermRetrieveCall = Callable[..., TermRetrievalResult | _CandidateList]
_Bm25RetrieveCall = Callable[..., object]
_ChannelJob = Callable[[], object]


def _counted_retrieve_send(
    budget: QueryRetrieveBudget | None,
    *,
    usage_kind: str,
    model_id: str,
    send: Callable[[], object],
) -> object:
    """Consume the run-local reservation for one retrieve-time gateway call.

    Args:
        budget: Retrieve ledger. ``None`` leaves the call uncounted so
            existing unit tests without a reservation keep working.
        usage_kind: ``embedding`` or ``rerank``.
        model_id: Provider model identifier recorded on usage.
        send: Provider invocation.

    Returns:
        ``send`` result.

    Raises:
        QueryCeilingError: When remaining model calls cannot cover the kind.
        QueryBudgetError: When remaining USD cannot cover the kind cap, or
            durable consume is rejected.

    Side Effects:
        Debits ``budget`` remaining. When connection and reservation ids are
        present, consumes via ``execute_counted_model_call`` so reserved USD
        cannot be silently exceeded.
    """

    if budget is None:
        return send()
    from smart_rag_core.query_admission.ceilings import (
        assert_retrieve_kind_available,
        debit_retrieve_budget,
    )
    from smart_rag_core.query_admission.usage import execute_counted_model_call

    connection = budget.connection
    caller = budget.caller
    run_id = budget.run_id
    reservation_id = budget.reservation_id
    if (
        isinstance(connection, psycopg.Connection)
        and isinstance(caller, CallerContext)
        and isinstance(run_id, UUID)
        and isinstance(reservation_id, UUID)
    ):
        assert_retrieve_kind_available(
            remaining_model_calls=budget.remaining_model_calls,
            remaining_usd=budget.remaining_usd,
            usage_kind=usage_kind,
        )
        result, consumed, _usage_id = execute_counted_model_call(
            connection,
            caller=caller,
            run_id=run_id,
            reservation_id=reservation_id,
            expected_version=budget.expected_version,
            usage_kind=usage_kind,
            model_id=model_id,
            provider_attempt_id=str(uuid4()),
            send=send,
        )
        budget.expected_version = consumed.optimistic_version
        debit_retrieve_budget(budget, usage_kind, remaining_usd=consumed.remaining_usd)
        return result
    debit_retrieve_budget(budget, usage_kind)
    return send()


def _counted_rerank(
    inner: RerankFn,
    budget: QueryRetrieveBudget | None,
    *,
    count_gateway: bool,
) -> RerankFn:
    """Wrap one rerank callback so it consumes remaining before the provider.

    Args:
        inner: Injected rerank callback or identity fallback.
        budget: Retrieve ledger.
        count_gateway: True when ``inner`` is a real gateway callback.

    Returns:
        Rerank callback. Identity rerank is not a counted gateway call.
        Insufficient remaining returns ``rerank_budget_denied`` without
        calling the provider.
    """

    if not count_gateway or budget is None:
        return inner

    def _wrapped(
        query: str,
        pool: tuple[RerankPassage, ...],
        remaining_deadline_seconds: float,
    ) -> tuple[tuple[RerankRanking, ...], RerankUsage | None, RerankFallbackReason]:
        """Fail closed when remaining cannot cover rerank, else debit and call.

        Args:
            query: Original user query.
            pool: Authorized rerank pool.
            remaining_deadline_seconds: Remaining Hybrid deadline share.

        Returns:
            Rankings, usage, and fallback reason from ``inner``, or empty
            rankings with ``rerank_budget_denied``.
        """

        from smart_rag_core.query_admission.ceilings import (
            assert_retrieve_kind_available,
        )

        try:
            assert_retrieve_kind_available(
                remaining_model_calls=budget.remaining_model_calls,
                remaining_usd=budget.remaining_usd,
                usage_kind="rerank",
            )
        except (QueryBudgetError, QueryCeilingError):
            return (), None, RerankFallbackReason.BUDGET_DENIED

        def _send() -> object:
            """Invoke the inner reranker.

            Returns:
                Inner rerank triple.
            """

            return inner(query, pool, remaining_deadline_seconds)

        counted = _counted_retrieve_send(
            budget,
            usage_kind="rerank",
            model_id=RERANK_MODEL_ID,
            send=_send,
        )
        return cast(
            tuple[tuple[RerankRanking, ...], RerankUsage | None, RerankFallbackReason],
            counted,
        )

    return _wrapped


class _DenseRetrieverLike(Protocol):
    """Object with a dense ``retrieve`` method used by Hybrid channel jobs.

    Attributes:
        retrieve: Bound dense retrieve callable or test double.
    """

    retrieve: _DenseRetrieveCall


class _Bm25RetrieverLike(Protocol):
    """Object with a BM25 ``retrieve`` method used by Hybrid channel jobs.

    Attributes:
        retrieve: Bound BM25 retrieve callable or test double.
    """

    retrieve: _Bm25RetrieveCall


class _TermRetrieverLike(Protocol):
    """Object with a term ``retrieve`` method used by Hybrid channel jobs.

    Attributes:
        retrieve: Bound term retrieve callable or test double.
    """

    retrieve: _TermRetrieveCall


class _AssembleHybridKwargs(TypedDict):
    """Keyword arguments shared by both Hybrid assemble calls in one retrieve.

    Attributes:
        dense_variants: Per-variant dense lists.
        bm25_variants: Authorized BM25 lists.
        term_variants: Per-variant term lists.
        bm25_fallback: BM25 outage, timeout, or none.
        temporal_intent: UTC temporal policy.
        target_date: ``as_of`` target.
        temporal_records: Effective timestamps by chunk.
        want_full_summary: Whole-document request.
        media_dependence: Figure-only required evidence.
        negation_scope: Profile negation enum.
        historical_relationship: Profile historical-relationship flag.
        principal_scope_hash: Cache principal hash.
        query_normalized: Normalized query used in the cache key.
        visibility_generation: ACL/visibility generation.
        scanned_bm25: BM25 IDs scanned before recheck.
        query_type: Profile query type.
        required_terms: Codes and exact terms.
        matched_terms: Terms already matched; Hybrid retrieve passes empty.
        deadline_exhausted: True when a parallel channel missed the slice.
    """

    dense_variants: _VariantLists
    bm25_variants: _VariantLists
    term_variants: _VariantLists
    bm25_fallback: RetrievalFallbackReason
    temporal_intent: TemporalIntent
    target_date: date | None
    temporal_records: dict[UUID, TemporalDocument]
    want_full_summary: bool
    media_dependence: bool
    negation_scope: str
    historical_relationship: bool
    principal_scope_hash: str
    query_normalized: str
    visibility_generation: int
    scanned_bm25: tuple[UUID, ...]
    query_type: QueryType
    required_terms: tuple[str, ...]
    matched_terms: tuple[str, ...]
    deadline_exhausted: bool


@dataclass(frozen=True, slots=True)
class EvidenceLocator:
    """Citation coordinates from canonical rows, never BM25 snippets.

    Attributes:
        page_number: Page index from ``document_chunks.page_number``.
        section_path: Heading ancestry from ``section_path``.
        sheet_name: Spreadsheet sheet from provenance locators.
        range_ref: Cell or range from provenance locators.
        source_url: HTML/crawl URL from provenance locators.
    """

    page_number: int | None = None
    section_path: tuple[str, ...] = ()
    sheet_name: str | None = None
    range_ref: str | None = None
    source_url: str | None = None


@dataclass(frozen=True, slots=True)
class EvidenceUnit:
    """One authorized Hybrid evidence unit with canonical citation text.

    Attributes:
        chunk_id: Canonical chunk UUID.
        document_id: Document UUID.
        version_id: Current version UUID.
        citation_text: ``ChunkContext.raw_text`` only.
        locator: Page/section/sheet/range/URL from canonical provenance.
    """

    chunk_id: UUID
    document_id: UUID
    version_id: UUID
    citation_text: str
    locator: EvidenceLocator


@dataclass(frozen=True, slots=True)
class HybridRunResult:
    """Typed Hybrid retrieve outcome. No answer text.

    Attributes:
        ranked_ids: Authorized fused IDs in rank order (Recall@K input).
        evidence: At most 12 citation units with locators.
        coverage: Coverage/refusal diagnostics.
        fallback_reason: Named retrieve fallback, or ``none``.
        deadline_exhausted: True when a channel missed the retrieval slice.
        first_evidence_ms: Wall milliseconds until evidence or fail-closed
            status on this retrieve path (QT-LAT-001), not first answer token.
        embedding_call_count: ``0`` or ``1``. Variants share one batch.
        rerank_call_count: ``0`` or ``1`` from the one-shot reranker.
        cache_key: Versioned ID-only cache key when assembly ran.
    """

    ranked_ids: tuple[UUID, ...]
    evidence: tuple[EvidenceUnit, ...]
    coverage: HybridCoverage
    fallback_reason: RetrievalFallbackReason
    deadline_exhausted: bool
    first_evidence_ms: float
    embedding_call_count: int
    rerank_call_count: int
    cache_key: str = ""


class HybridRetriever:
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
        channel_jobs: dict[str, _ChannelJob] | None = None,
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
        channel_jobs: dict[str, _ChannelJob] | None = None,
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
        scope_hash = principal_scope_hash or _principal_scope_hash(caller)
        if not caller.is_active():
            return _closed_result(
                RetrievalFallbackReason.AUTH_CONTEXT_INVALID,
                started=started,
            )
        query_check = _fail_closed_query(query)
        if query_check is not None:
            return _closed_result(query_check, started=started)

        texts = _query_texts(query, profile)
        embed_response, embed_error = self._embed_query_texts(
            texts, budget=self.query_budget
        )
        if embed_error is not None or embed_response is None:
            return _closed_result(
                embed_error or RetrievalFallbackReason.DENSE_UNAVAILABLE,
                started=started,
                embedding_call_count=1,
            )
        vectors = embed_response.vectors
        jobs: dict[str, _ChannelJob] | None = (
            channel_jobs if channel_jobs is not None else self._channel_jobs
        )
        if jobs is None:
            jobs = self._build_channel_jobs(
                caller=caller,
                query=query,
                texts=texts[:_FUSION_LIST_CAP],
                vectors=vectors[:_FUSION_LIST_CAP],
            )
        completed, timed_out, exhausted = run_channels_parallel(
            jobs,
            deadline_seconds=slice_seconds,
        )
        dense_lists, dense_reason = _unpack_dense(completed.get("dense"))
        bm25_result = _unpack_bm25(completed.get("bm25"))
        term_lists, term_reason = _unpack_term(completed.get("term"))
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
        dense_lists, bm25_result, term_lists = _restrict_channel_candidates(
            dense_lists,
            bm25_result,
            term_lists,
            restrict_version_id,
        )
        fallback = _compose_fallback(
            dense_reason=dense_reason,
            term_reason=term_reason,
            bm25_fallback=bm25_fallback,
            deadline_exhausted=exhausted,
        )
        resolved_profile = profile
        media_dependence = _bool_field(profile, "media_dependence")
        historical = _bool_field(profile, "historical_relationship")
        negation_scope = _str_field(profile, "negation_scope") or "none"
        want_full_summary = False
        query_type = _query_type(profile)
        temporal_intent = _temporal_intent(profile)
        target = _target_date(profile)
        required_terms = _str_list_field(profile, "codes") + _str_list_field(
            profile, "exact_terms"
        )
        temporal_records = self._load_temporal_records(
            _flatten_channel_candidates(dense_lists, bm25_result.candidates, term_lists)
        )
        assemble_kwargs = _hybrid_assemble_kwargs(
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
        assembled = _call_assemble_hybrid(
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
        assembled = _call_assemble_hybrid(
            heading_inventory=inventory,
            covered_headings=covered,
            kwargs=assemble_kwargs,
        )
        remaining = max(0.0, slice_seconds - (time.perf_counter() - started))
        rerank_fn: RerankFn = _counted_rerank(
            self._rerank or _identity_rerank,
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
            evidence = _evidence_units(selection.passages, locator_rows)
        elif assembled.fused:
            evidence = _evidence_units_from_context(
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
            first_evidence_ms=_elapsed_ms(started),
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
                _counted_retrieve_send(
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

    def _build_channel_jobs(
        self,
        *,
        caller: CallerContext,
        query: str,
        texts: tuple[str, ...],
        vectors: tuple[tuple[float, ...], ...],
    ) -> dict[str, _ChannelJob]:
        """Build parallel dense/BM25/term jobs from bound retrievers.

        Args:
            caller: Server-derived identity.
            query: Original query used for the single BM25 scan.
            texts: At most three query forms for dense/term lists.
            vectors: Embeddings aligned with ``texts``.

        Returns:
            Zero-argument jobs for ``run_channels_parallel``.
        """

        jobs: dict[str, _ChannelJob] = {}
        dense = self._dense
        if dense is not None:
            dense_retriever = cast(_DenseRetrieverLike, dense)

            def _dense_job() -> _VariantLists:
                """Run dense retrieve per fused query text.

                Returns:
                    Per-variant dense candidate lists.
                """

                if self._supabase_dsn:
                    from smart_rag_core.retrieval.dense import DenseRetriever

                    with self._channel_supabase() as connection:
                        return _collect_dense_lists(
                            DenseRetriever(connection).retrieve,
                            caller=caller,
                            texts=texts,
                            vectors=vectors,
                        )
                return _collect_dense_lists(
                    dense_retriever.retrieve,
                    caller=caller,
                    texts=texts,
                    vectors=vectors,
                )

            jobs["dense"] = _dense_job
        bm25 = self._bm25
        if bm25 is not None:
            bm25_retriever = cast(_Bm25RetrieverLike, bm25)

            def _bm25_job() -> Bm25RetrievalResult:
                """Run one BM25 scan over the original query.

                Returns:
                    Authorized BM25 survivors or a named outage fallback.
                """

                try:
                    if self._supabase_dsn:
                        with self._channel_supabase() as supabase_conn:
                            result = bm25_retriever.retrieve(
                                supabase=supabase_conn,
                                caller=caller,
                                query_text=query,
                            )
                    else:
                        result = bm25_retriever.retrieve(
                            supabase=self._supabase,
                            caller=caller,
                            query_text=query,
                        )
                except Exception:
                    return Bm25RetrievalResult(
                        scanned_ids=(),
                        candidates=(),
                        fallback_reason=RetrievalFallbackReason.BM25_UNAVAILABLE,
                    )
                if isinstance(result, Bm25RetrievalResult):
                    return result
                return Bm25RetrievalResult(scanned_ids=(), candidates=())

            jobs["bm25"] = _bm25_job
        elif self._paradedb is None and self._bm25 is None:
            jobs["bm25"] = lambda: Bm25RetrievalResult(
                scanned_ids=(),
                candidates=(),
                fallback_reason=RetrievalFallbackReason.BM25_UNAVAILABLE,
            )
        term = self._term
        if term is not None:
            term_retriever = cast(_TermRetrieverLike, term)

            def _term_job() -> _VariantLists:
                """Run term retrieve per fused query text.

                Returns:
                    Per-variant term candidate lists.
                """

                if self._supabase_dsn:
                    from smart_rag_core.retrieval.terms import TermRetriever

                    with self._channel_supabase() as connection:
                        return _collect_term_lists(
                            TermRetriever(connection).retrieve,
                            caller=caller,
                            texts=texts,
                        )
                return _collect_term_lists(
                    term_retriever.retrieve,
                    caller=caller,
                    texts=texts,
                )

            jobs["term"] = _term_job
        return jobs

    @contextmanager
    def _channel_supabase(self) -> Generator[psycopg.Connection, None, None]:
        """Open one idle canonical Postgres connection for a channel thread.

        Yields:
            A new ``psycopg`` connection created from ``supabase_dsn``.

        Raises:
            RuntimeError: If ``supabase_dsn`` is missing.

        Side Effects:
            Opens and closes one connection. Does not use the bound
            ``supabase`` connection, which stays idle for context RPC.
        """

        dsn = self._supabase_dsn
        if not dsn:
            raise RuntimeError("hybrid_channel_requires_supabase_dsn")
        connection = psycopg.connect(dsn)
        try:
            yield connection
        finally:
            connection.close()

    def _load_temporal_records(
        self,
        candidates: tuple[RetrievalCandidate, ...],
    ) -> dict[UUID, TemporalDocument]:
        """Load UTC ``effective_at`` values for fused channel candidates.

        ``as_of`` / ``latest`` policies skip undated rows. Eval compact sources
        must stamp ``document_versions.effective_at`` or those classes empty
        the fused list. Uses ``app_api`` because hosted transaction-pooler
        logins cannot ``SET ROLE postgres``.

        Args:
            candidates: Dense, BM25, and term candidates before fusion.

        Returns:
            Per-chunk temporal records. Empty when no DSN/candidates exist.
        """

        version_ids = tuple({item.version_id for item in candidates})
        if not version_ids or not self._supabase_dsn:
            return {}
        by_version: dict[UUID, datetime | None] = {}
        with self._channel_supabase() as connection:
            connection.execute("SET ROLE app_api")
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT id, effective_at
                    FROM app.document_versions
                    WHERE id = ANY(%s)
                    """,
                    (list(version_ids),),
                )
                for row in cursor.fetchall():
                    version_id = UUID(str(row[0]))
                    stamp = row[1]
                    by_version[version_id] = (
                        stamp if isinstance(stamp, datetime) else None
                    )
        records: dict[UUID, TemporalDocument] = {}
        for item in candidates:
            records[item.chunk_id] = TemporalDocument(
                item.chunk_id,
                effective_at=by_version.get(item.version_id),
            )
        return records

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


def _hybrid_assemble_kwargs(
    *,
    dense_variants: _VariantLists,
    bm25_variants: _VariantLists,
    term_variants: _VariantLists,
    bm25_fallback: RetrievalFallbackReason,
    temporal_intent: TemporalIntent,
    target_date: date | None,
    temporal_records: dict[UUID, TemporalDocument],
    want_full_summary: bool,
    media_dependence: bool,
    negation_scope: str,
    historical_relationship: bool,
    principal_scope_hash: str,
    query_normalized: str,
    visibility_generation: int,
    scanned_bm25: tuple[UUID, ...],
    query_type: QueryType,
    required_terms: tuple[str, ...],
    matched_terms: tuple[str, ...],
    deadline_exhausted: bool,
) -> _AssembleHybridKwargs:
    """Pack the shared ``assemble_hybrid`` kwargs for one retrieve.

    Args:
        dense_variants: Per-variant dense lists.
        bm25_variants: Authorized BM25 lists.
        term_variants: Per-variant term lists.
        bm25_fallback: BM25 outage, timeout, or none.
        temporal_intent: UTC temporal policy.
        target_date: ``as_of`` target.
        temporal_records: Effective timestamps by chunk.
        want_full_summary: Whole-document request.
        media_dependence: Figure-only required evidence.
        negation_scope: Profile negation enum.
        historical_relationship: Profile historical-relationship flag.
        principal_scope_hash: Cache principal hash.
        query_normalized: Normalized query used in the cache key.
        visibility_generation: ACL/visibility generation.
        scanned_bm25: BM25 IDs scanned before recheck.
        query_type: Profile query type.
        required_terms: Codes and exact terms.
        matched_terms: Terms already matched; Hybrid retrieve passes empty.
        deadline_exhausted: True when a parallel channel missed the slice.

    Returns:
        Typed kwargs unpacked into both ``assemble_hybrid`` calls.
    """

    return {
        "dense_variants": dense_variants,
        "bm25_variants": bm25_variants,
        "term_variants": term_variants,
        "bm25_fallback": bm25_fallback,
        "temporal_intent": temporal_intent,
        "target_date": target_date,
        "temporal_records": temporal_records,
        "want_full_summary": want_full_summary,
        "media_dependence": media_dependence,
        "negation_scope": negation_scope,
        "historical_relationship": historical_relationship,
        "principal_scope_hash": principal_scope_hash,
        "query_normalized": query_normalized,
        "visibility_generation": visibility_generation,
        "scanned_bm25": scanned_bm25,
        "query_type": query_type,
        "required_terms": required_terms,
        "matched_terms": matched_terms,
        "deadline_exhausted": deadline_exhausted,
    }


def _call_assemble_hybrid(
    *,
    heading_inventory: tuple[str, ...],
    covered_headings: tuple[str, ...],
    kwargs: _AssembleHybridKwargs,
) -> HybridRetrievalResult:
    """Call ``assemble_hybrid`` with the same heading and channel arguments.

    Args:
        heading_inventory: Current major headings.
        covered_headings: Headings present in fused evidence.
        kwargs: Shared channel, temporal, and coverage arguments.

    Returns:
        The ``assemble_hybrid`` result for this heading snapshot.
    """

    return assemble_hybrid(
        heading_inventory=heading_inventory,
        covered_headings=covered_headings,
        **kwargs,
    )


def _is_candidate_tuple(value: object) -> TypeGuard[_CandidateList]:
    """Return whether ``value`` is a tuple of retrieval candidates.

    Args:
        value: Channel job payload or an inner list.

    Returns:
        True when ``value`` is a tuple whose first item is a candidate, or
        empty. Matches the existing unpack ``isinstance`` checks.
    """

    if not isinstance(value, tuple):
        return False
    items = cast(tuple[object, ...], value)
    return not items or isinstance(items[0], RetrievalCandidate)


def _is_variant_tuple(value: object) -> TypeGuard[_VariantLists]:
    """Return whether ``value`` is a tuple of per-variant candidate lists.

    Args:
        value: Channel job payload.

    Returns:
        True when ``value`` is a non-empty tuple whose first item is a tuple.
    """

    if not isinstance(value, tuple) or not value:
        return False
    items = cast(tuple[object, ...], value)
    return isinstance(items[0], tuple)


def _fail_closed_query(query: str) -> RetrievalFallbackReason | None:
    """Return a named fallback when the query must not retrieve.

    Args:
        query: Raw user query.

    Returns:
        ``retrieval_empty`` when blank or over ``MAX_NORMALIZED_QUERY_CHARS``.
    """

    normalized = normalize_arabic_v1(query)
    if normalized == "" or len(normalized) > MAX_NORMALIZED_QUERY_CHARS:
        return RetrievalFallbackReason.RETRIEVAL_EMPTY
    return None


def _query_texts(query: str, profile: ExpectedProfile | None) -> tuple[str, ...]:
    """Build unique embed texts: original plus at most three variants.

    Args:
        query: Original query.
        profile: Optional profile whose ``variants`` field is a string list.

    Returns:
        At most four unique strings, original first.
    """

    ordered = [query]
    seen = {query.strip()}
    for variant in _str_list_field(profile, "variants"):
        key = variant.strip()
        if key == "" or key in seen:
            continue
        seen.add(key)
        ordered.append(variant)
        if len(ordered) >= _EMBED_TEXT_CAP:
            break
    return tuple(ordered)


def _principal_scope_hash(caller: CallerContext) -> str:
    """Hash caller identity for the ID-only cache key.

    Args:
        caller: Server-derived identity.

    Returns:
        SHA-256 hex digest. Raw user IDs are not logged here.
    """

    payload = (
        f"{caller.user_id}:{caller.rpc_role()}:{caller.rpc_authorization_version()}"
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _closed_result(
    reason: RetrievalFallbackReason,
    *,
    started: float,
    embedding_call_count: int = 0,
) -> HybridRunResult:
    """Build a fail-closed retrieve result with no evidence.

    Args:
        reason: Named fallback.
        started: ``perf_counter`` timestamp from retrieve start.
        embedding_call_count: ``1`` when a gateway call was attempted.

    Returns:
        Empty ranked/evidence result with measured ``first_evidence_ms``.
    """

    return HybridRunResult(
        ranked_ids=(),
        evidence=(),
        coverage=HybridCoverage(
            signal=CoverageSignal.WEAK_EVIDENCE,
            notes=(reason.value,),
        ),
        fallback_reason=reason,
        deadline_exhausted=reason is RetrievalFallbackReason.TIMEOUT,
        first_evidence_ms=_elapsed_ms(started),
        embedding_call_count=embedding_call_count,
        rerank_call_count=0,
    )


def _elapsed_ms(started: float) -> float:
    """Return milliseconds since ``started``.

    Args:
        started: ``time.perf_counter`` value.

    Returns:
        Non-negative milliseconds.
    """

    return max(0.0, (time.perf_counter() - started) * 1000.0)


def _collect_dense_lists(
    retrieve: Callable[..., object],
    *,
    caller: CallerContext,
    texts: tuple[str, ...],
    vectors: tuple[tuple[float, ...], ...],
) -> _VariantLists:
    """Run dense retrieve once per fused query vector.

    Args:
        retrieve: Bound ``DenseRetriever.retrieve`` or a test double.
        caller: Server-derived identity.
        texts: Query forms aligned with ``vectors``.
        vectors: Query embeddings.

    Returns:
        Per-variant dense candidate lists.
    """

    lists: list[_CandidateList] = []
    for _text, vector in zip(texts, vectors, strict=False):
        result = retrieve(caller=caller, query_embedding=list(vector))
        if isinstance(result, DenseRetrievalResult):
            lists.append(result.candidates)
        elif isinstance(result, tuple):
            lists.append(cast(_CandidateList, result))
    return tuple(lists)


def _collect_term_lists(
    retrieve: Callable[..., object],
    *,
    caller: CallerContext,
    texts: tuple[str, ...],
) -> _VariantLists:
    """Run term retrieve once per fused query text.

    Args:
        retrieve: Bound ``TermRetriever.retrieve`` or a test double.
        caller: Server-derived identity.
        texts: Query forms.

    Returns:
        Per-variant term candidate lists.
    """

    lists: list[_CandidateList] = []
    for text in texts:
        result = retrieve(caller=caller, query_text=text)
        if isinstance(result, TermRetrievalResult):
            lists.append(result.candidates)
        elif isinstance(result, tuple):
            lists.append(cast(_CandidateList, result))
    return tuple(lists)


def _restrict_channel_candidates(
    dense_lists: tuple[tuple[RetrievalCandidate, ...], ...],
    bm25_result: Bm25RetrievalResult,
    term_lists: tuple[tuple[RetrievalCandidate, ...], ...],
    version_id: UUID | None,
) -> tuple[
    tuple[tuple[RetrievalCandidate, ...], ...],
    Bm25RetrievalResult,
    tuple[tuple[RetrievalCandidate, ...], ...],
]:
    """Keep only candidates whose version matches the caller filter.

    Args:
        dense_lists: Per-variant dense lists.
        bm25_result: Authorized BM25 survivors.
        term_lists: Per-variant term lists.
        version_id: Version filter, or ``None`` to keep every candidate.

    Returns:
        Filtered dense lists, BM25 result, and term lists.
    """

    if version_id is None:
        return dense_lists, bm25_result, term_lists

    def _keep(
        candidates: tuple[RetrievalCandidate, ...],
    ) -> tuple[RetrievalCandidate, ...]:
        """Filter one candidate list to ``version_id``.

        Args:
            candidates: Authorized candidates.

        Returns:
            Candidates for the requested version only.
        """

        return tuple(item for item in candidates if item.version_id == version_id)

    filtered_dense = tuple(_keep(variant) for variant in dense_lists)
    filtered_bm25_candidates = _keep(bm25_result.candidates)
    filtered_bm25 = Bm25RetrievalResult(
        scanned_ids=tuple(item.chunk_id for item in filtered_bm25_candidates),
        candidates=filtered_bm25_candidates,
        fallback_reason=bm25_result.fallback_reason,
    )
    filtered_term = tuple(_keep(variant) for variant in term_lists)
    return filtered_dense, filtered_bm25, filtered_term


def _flatten_channel_candidates(
    dense_lists: tuple[tuple[RetrievalCandidate, ...], ...],
    bm25_candidates: tuple[RetrievalCandidate, ...],
    term_lists: tuple[tuple[RetrievalCandidate, ...], ...],
) -> tuple[RetrievalCandidate, ...]:
    """Flatten dense, BM25, and term candidates for temporal lookup.

    Args:
        dense_lists: Per-variant dense lists.
        bm25_candidates: Authorized BM25 survivors.
        term_lists: Per-variant term lists.

    Returns:
        Deduplicated candidates in first-seen order.
    """

    seen: set[UUID] = set()
    ordered: list[RetrievalCandidate] = []
    for variant in dense_lists:
        for item in variant:
            if item.chunk_id in seen:
                continue
            seen.add(item.chunk_id)
            ordered.append(item)
    for item in bm25_candidates:
        if item.chunk_id in seen:
            continue
        seen.add(item.chunk_id)
        ordered.append(item)
    for variant in term_lists:
        for item in variant:
            if item.chunk_id in seen:
                continue
            seen.add(item.chunk_id)
            ordered.append(item)
    return tuple(ordered)


def _unpack_dense(
    value: object,
) -> tuple[_VariantLists, RetrievalFallbackReason]:
    """Normalize a dense channel job result.

    Args:
        value: Job return value or ``None`` when the job was absent.

    Returns:
        Variant lists and a named dense fallback when the channel failed.
    """

    if value is None:
        return (), RetrievalFallbackReason.NONE
    if isinstance(value, DenseRetrievalResult):
        return (value.candidates,), value.fallback_reason
    if _is_candidate_tuple(value):
        if not value:
            return (), RetrievalFallbackReason.NONE
        return (value,), RetrievalFallbackReason.NONE
    if _is_variant_tuple(value):
        return value, RetrievalFallbackReason.NONE
    return (), RetrievalFallbackReason.DENSE_UNAVAILABLE


def _unpack_term(
    value: object,
) -> tuple[_VariantLists, RetrievalFallbackReason]:
    """Normalize a term channel job result.

    Args:
        value: Job return value or ``None`` when the job was absent.

    Returns:
        Variant lists and a named term fallback when the channel failed.
    """

    if value is None:
        return (), RetrievalFallbackReason.NONE
    if isinstance(value, TermRetrievalResult):
        return (value.candidates,), RetrievalFallbackReason.NONE
    if _is_candidate_tuple(value):
        if not value:
            return (), RetrievalFallbackReason.NONE
        return (value,), RetrievalFallbackReason.NONE
    if _is_variant_tuple(value):
        return value, RetrievalFallbackReason.NONE
    return (), RetrievalFallbackReason.TERM_UNAVAILABLE


def _unpack_bm25(value: object) -> Bm25RetrievalResult:
    """Normalize a BM25 channel job result.

    Args:
        value: Job return value or ``None``.

    Returns:
        ID-only BM25 result. Missing jobs are empty with ``none``.
    """

    if isinstance(value, Bm25RetrievalResult):
        return value
    if _is_candidate_tuple(value) and value:
        return Bm25RetrievalResult(scanned_ids=(), candidates=value)
    if _is_variant_tuple(value) and value[0] and _is_candidate_tuple(value[0]):
        return Bm25RetrievalResult(scanned_ids=(), candidates=value[0])
    return Bm25RetrievalResult(scanned_ids=(), candidates=())


def _compose_fallback(
    *,
    dense_reason: RetrievalFallbackReason,
    term_reason: RetrievalFallbackReason,
    bm25_fallback: RetrievalFallbackReason,
    deadline_exhausted: bool,
) -> RetrievalFallbackReason:
    """Choose the retrieve-level named fallback.

    Args:
        dense_reason: Dense channel outcome.
        term_reason: Term channel outcome.
        bm25_fallback: BM25 outage, version mismatch, timeout, or none.
        deadline_exhausted: True when any parallel job timed out.

    Returns:
        Highest-priority named reason. ``none`` when channels completed.
    """

    if dense_reason is RetrievalFallbackReason.DENSE_UNAVAILABLE:
        return RetrievalFallbackReason.DENSE_UNAVAILABLE
    if term_reason is RetrievalFallbackReason.TERM_UNAVAILABLE:
        return RetrievalFallbackReason.TERM_UNAVAILABLE
    if bm25_fallback is not RetrievalFallbackReason.NONE:
        return bm25_fallback
    if deadline_exhausted:
        return RetrievalFallbackReason.TIMEOUT
    return RetrievalFallbackReason.NONE


def _identity_rerank(
    _query: str,
    pool: tuple[RerankPassage, ...],
    _deadline: float,
) -> tuple[tuple[RerankRanking, ...], None, RerankFallbackReason]:
    """Keep fused pool order without a model call.

    Args:
        _query: Unused original query.
        pool: Authorized rerank pool.
        _deadline: Unused remaining slice.

    Returns:
        Identity rankings, no usage, and ``none`` fallback.
    """

    rankings = tuple(
        RerankRanking(
            chunk_id=item.candidate.chunk_id,
            rank=index + 1,
            support=1.0,
        )
        for index, item in enumerate(pool)
    )
    return rankings, None, RerankFallbackReason.NONE


def _evidence_units(
    passages: tuple[RerankPassage, ...],
    contexts: tuple[ChunkContext, ...],
) -> tuple[EvidenceUnit, ...]:
    """Join selected passages to canonical locator rows.

    Args:
        passages: MMR-trimmed passages. Citation text is canonical raw_text.
        contexts: Authorized rows for those IDs, including parents.

    Returns:
        Evidence units capped by selection order. BM25 text is unused.
    """

    by_id = {item.chunk_id: item for item in contexts}
    units: list[EvidenceUnit] = []
    for passage in passages:
        candidate = passage.candidate
        record = by_id.get(candidate.chunk_id)
        citation = record.raw_text if record is not None else passage.raw_text
        locator = _locator_from_context(record, passage)
        units.append(
            EvidenceUnit(
                chunk_id=candidate.chunk_id,
                document_id=candidate.document_id,
                version_id=candidate.version_id,
                citation_text=citation,
                locator=locator,
            )
        )
        if len(units) >= FINAL_EVIDENCE_MAX:
            break
    return tuple(units)


def _evidence_units_from_context(
    fused: tuple[RetrievalCandidate, ...],
    contexts: tuple[ChunkContext, ...],
) -> tuple[EvidenceUnit, ...]:
    """Build evidence from fused IDs when no profile/rerank ran.

    Args:
        fused: Fused authorized candidates, already trimmed.
        contexts: Authorized canonical rows.

    Returns:
        Evidence units using ``ChunkContext.raw_text`` only.
    """

    by_id = {item.chunk_id: item for item in contexts}
    units: list[EvidenceUnit] = []
    for candidate in fused:
        record = by_id.get(candidate.chunk_id)
        if record is None:
            continue
        units.append(
            EvidenceUnit(
                chunk_id=record.chunk_id,
                document_id=record.document_id,
                version_id=record.version_id,
                citation_text=record.raw_text,
                locator=_locator_from_context(record, None),
            )
        )
        if len(units) >= FINAL_EVIDENCE_MAX:
            break
    return tuple(units)


def _locator_from_context(
    record: ChunkContext | None,
    passage: RerankPassage | None,
) -> EvidenceLocator:
    """Copy locator fields from canonical context, then passage page/section.

    Args:
        record: Authorized chunk row when present.
        passage: Selected passage used only for page/section fallback.

    Returns:
        Locator with canonical sheet/range/URL when the row exists.
    """

    if record is not None:
        return EvidenceLocator(
            page_number=record.page_number,
            section_path=record.section_path,
            sheet_name=record.sheet_name,
            range_ref=record.range_ref,
            source_url=record.source_url,
        )
    if passage is None:
        return EvidenceLocator()
    return EvidenceLocator(
        page_number=passage.page_number,
        section_path=passage.section_path,
    )


def _str_list_field(profile: ExpectedProfile | None, name: str) -> tuple[str, ...]:
    """Read a list-or-string profile field.

    Args:
        profile: Optional typed profile.
        name: Attribute name on ``ExpectedProfile``.

    Returns:
        String values, or empty when missing.
    """

    field = _profile_field(profile, name)
    if field is None:
        return ()
    value = field.value
    if isinstance(value, list):
        return tuple(str(item) for item in value if str(item).strip())
    if isinstance(value, str) and value.strip():
        return (value,)
    return ()


def _str_field(profile: ExpectedProfile | None, name: str) -> str | None:
    """Read a string profile field.

    Args:
        profile: Optional typed profile.
        name: Attribute name.

    Returns:
        String value or ``None``.
    """

    field = _profile_field(profile, name)
    if field is None:
        return None
    value = field.value
    if isinstance(value, str):
        return value
    return None


def _bool_field(profile: ExpectedProfile | None, name: str) -> bool:
    """Read a boolean profile field.

    Args:
        profile: Optional typed profile.
        name: Attribute name.

    Returns:
        The boolean value, or ``False`` when missing.
    """

    field = _profile_field(profile, name)
    if field is None:
        return False
    value = field.value
    return bool(value) if isinstance(value, bool) else False


def _profile_field(profile: ExpectedProfile | None, name: str) -> ProfileField | None:
    """Return a named ``ProfileField`` from the typed profile.

    Args:
        profile: Optional typed profile.
        name: Attribute name on ``ExpectedProfile``.

    Returns:
        The field when present, otherwise ``None``.
    """

    if profile is None:
        return None
    raw: object = getattr(profile, name, None)
    if isinstance(raw, ProfileField):
        return raw
    return None


def _query_type(profile: ExpectedProfile | None) -> QueryType:
    """Parse an existing ``QueryType`` enum value without adding a map.

    Wave 1C owns QueryType mapping. This only accepts values already on
    ``QueryType``.

    Args:
        profile: Optional typed profile.

    Returns:
        Profile query type when it is a ``QueryType`` member, else ``factual``.
    """

    raw = _str_field(profile, "query_type")
    if raw is None:
        return QueryType.FACTUAL
    try:
        return QueryType(raw)
    except ValueError:
        return QueryType.FACTUAL


def _temporal_intent(profile: ExpectedProfile | None) -> TemporalIntent:
    """Parse an allow-listed temporal intent from the profile.

    Args:
        profile: Optional typed profile.

    Returns:
        Matching ``TemporalIntent``, or ``none``.
    """

    raw = _str_field(profile, "temporal_intent")
    if raw is None:
        return TemporalIntent.NONE
    try:
        return TemporalIntent(raw)
    except ValueError:
        return TemporalIntent.NONE


def _target_date(profile: ExpectedProfile | None) -> date | None:
    """Parse an ISO ``YYYY-MM-DD`` target date when present.

    Args:
        profile: Optional typed profile.

    Returns:
        UTC calendar date, or ``None``.
    """

    raw = _str_field(profile, "target_date")
    if raw is None:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None
