"""DSN-backed Hybrid retrieve adapters used by the query runtime."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, replace
from uuid import UUID

import psycopg
from smart_rag_core.evaluation.schema import ExpectedProfile
from smart_rag_core.gateways.embedding import EmbeddingGateway
from smart_rag_core.gateways.model import ModelGateway
from smart_rag_core.query_routing.profile_fields import profile_strings
from smart_rag_core.retrieval.bm25 import Bm25Retriever
from smart_rag_core.retrieval.cache_store import RetrievalCacheMode, RetrievalCacheStore
from smart_rag_core.retrieval.context_loader import (
    ChunkContext,
    fetch_authorized_chunk_context,
)
from smart_rag_core.retrieval.frozen_profile import load_frozen_profile
from smart_rag_core.retrieval.hybrid_run import HybridRetriever
from smart_rag_core.retrieval.profiles import HYBRID_DEFAULT_PROFILE_ID
from smart_rag_core.retrieval.reranker import rerank_pool
from smart_rag_core.retrieval.source_scope import (
    ResolvedRetrievalScope,
    SourceResolution,
    high_confidence_source_names,
    resolve_retrieval_scope,
    strip_source_selectors,
)
from smart_rag_core.security.identity import CallerContext
from smart_rag_core.settings.postgres_connect import connect_postgres


class _DsnChannelMarker:
    """Truthy Hybrid channel flag. Per-channel jobs open their own DSN connections.

    Attributes:
        retrieve: Unused placeholder. ``HybridRetriever`` reconstructs dense
            and term adapters when ``supabase_dsn`` is set.
    """

    retrieve = None


class DsnBm25Retriever:
    """ParadeDB BM25 adapter that opens one connection per retrieve.

    Concurrent Hybrid channel threads must not share a ``psycopg`` connection.
    """

    def __init__(self, parade_dsn: str) -> None:
        """Store the unpublished ParadeDB URL.

        Args:
            parade_dsn: ``PARADEDB_URL`` secret value.
        """

        self._parade_dsn = parade_dsn

    def retrieve(
        self,
        *,
        supabase: psycopg.Connection,
        caller: CallerContext,
        query_text: str,
    ) -> object:
        """Scan BM25 IDs on a fresh ParadeDB connection.

        Args:
            supabase: Canonical connection used only for ACL recheck.
            caller: Server-derived caller.
            query_text: Raw query.

        Returns:
            ``Bm25RetrievalResult``. Hybrid catches connection failures and
            degrades to dense plus term.

        Side Effects:
            Opens and closes one ParadeDB connection.
        """

        return self.retrieve_variants(
            supabase=supabase,
            caller=caller,
            texts=(query_text,),
        )

    def retrieve_variants(
        self,
        *,
        supabase: psycopg.Connection,
        caller: CallerContext,
        texts: tuple[str, ...],
        version_id: UUID | None = None,
    ) -> object:
        """Scan original plus bounded variants on a fresh ParadeDB connection.

        Args:
            supabase: Canonical connection used only for ACL recheck.
            caller: Server-derived caller.
            texts: Original query first, then at most three variants.
            version_id: Optional current-version filter inside ranking.

        Returns:
            ``Bm25RetrievalResult`` with per-variant lists. Never snippets.

        Side Effects:
            Opens and closes one ParadeDB connection.
        """

        with connect_postgres(self._parade_dsn, connect_timeout=8) as parade:
            return Bm25Retriever(parade).retrieve_variants(
                supabase=supabase,
                caller=caller,
                texts=texts,
                version_id=version_id,
            )


class ProcessHybridRetriever:
    """Hybrid retrieve that reuses the embedding gateway and opens per-call DB connections.

    ``HybridRetriever`` context loading captures the retrieve caller, so each
    ``retrieve`` builds an inner retriever. Dense/term/BM25-recheck threads
    still use ``supabase_dsn``.
    """

    def __init__(
        self,
        *,
        embedding_gateway: EmbeddingGateway,
        supabase_dsn: str,
        bm25: DsnBm25Retriever | None,
        model_gateway: ModelGateway | None = None,
        rerank_prompt_text: str | None = None,
        retrieval_cache: RetrievalCacheStore | None = None,
    ) -> None:
        """Bind the process embedding gateway and DSNs.

        Args:
            embedding_gateway: Shared ``EmbeddingGateway``.
            supabase_dsn: Full canonical Postgres URL including password.
            bm25: Optional per-retrieve ParadeDB adapter. ``None`` degrades
                BM25 (approved dense+term Hybrid).
            model_gateway: Shared model gateway for the one-shot reranker.
            rerank_prompt_text: Pinned ``rerank_v1`` body. Missing prompt
                leaves identity fallback.
            retrieval_cache: Optional ID/rank cache. Hits still recheck ACL.
        """

        self._embedding_gateway = embedding_gateway
        self._supabase_dsn = supabase_dsn
        self._bm25 = bm25
        self._model_gateway = model_gateway
        self._rerank_prompt = rerank_prompt_text
        self._retrieval_cache = retrieval_cache
        self.query_budget: object | None = None

    def retrieve(
        self,
        *,
        query: str,
        caller: CallerContext,
        profile: object | None = None,
        deadline_seconds: float | None = None,
        query_budget: object | None = None,
        cache_mode: RetrievalCacheMode = RetrievalCacheMode.NORMAL,
    ) -> object:
        """Run one Hybrid retrieve with per-channel connections.

        Args:
            query: Branch query text.
            caller: Server-derived caller.
            profile: Typed query profile when present.
            deadline_seconds: Remaining retrieval slice.
            query_budget: Optional per-run retrieve ledger. Copied onto the
                inner retriever so concurrent SSE runs do not share it.
            cache_mode: Exam retrieve passes ``cold_bypass`` so ranking
                still uses this production path without a warm cache hit.

        Returns:
            ``HybridRunResult`` with ranked IDs. BM25 snippets are never evidence.

        Side Effects:
            Embedding gateway call, per-channel Postgres (and optional
            ParadeDB) connections, and one shared context connection for
            preload, parent expansion, and locator reload.
            Adds ``scope_ms`` (scope resolution plus frozen-profile load) to ``stage_timings_ms``.
        """

        typed_profile = profile if isinstance(profile, ExpectedProfile) else None
        scope_started = time.perf_counter()
        scope = self._resolve_scope(caller, typed_profile, query=query)
        restrict_version_id = scope.version_id if scope is not None else None
        ranking_query = query
        if (
            scope is not None
            and scope.resolution is SourceResolution.EXACT_ONE
            and scope.selector_texts
        ):
            ranking_query = strip_source_selectors(query, scope.selector_texts)
            typed_profile = _profile_without_source_selectors(
                typed_profile, scope.selector_texts
            )
        profile_id = HYBRID_DEFAULT_PROFILE_ID
        if scope is not None:
            profile_id = scope.candidate_profile_id
        retrieval_profile = load_frozen_profile(profile_id)
        scope_ms = int(max(0.0, time.perf_counter() - scope_started) * 1000.0)
        gateway = self._model_gateway
        prompt = self._rerank_prompt
        rerank_fn = None
        if gateway is not None and prompt:

            def _rerank(
                query_text: str,
                pool: object,
                remaining: float,
            ) -> object:
                """Run one process-local rerank closure.

                Args:
                    query_text: User query.
                    pool: Authorized rerank pool.
                    remaining: Remaining deadline seconds.

                Returns:
                    Rankings, usage, and fallback from ``rerank_pool``.
                """

                return rerank_pool(
                    query_text,
                    pool,  # type: ignore[arg-type]
                    remaining,
                    gateway=gateway,
                    prompt_text=prompt,
                )

            rerank_fn = _rerank
        with connect_postgres(self._supabase_dsn) as context_connection:
            inner = HybridRetriever(
                embedding_gateway=self._embedding_gateway,
                supabase=None,
                paradedb=None,
                supabase_dsn=self._supabase_dsn,
                dense=_DsnChannelMarker(),
                bm25=self._bm25,
                term=_DsnChannelMarker(),
                load_context=context_loader_for_connection(context_connection, caller),
                rerank=rerank_fn,  # type: ignore[arg-type]
                retrieval_profile=retrieval_profile,
                retrieval_cache=self._retrieval_cache,
            )
            budget = query_budget if query_budget is not None else self.query_budget
            inner.query_budget = budget  # type: ignore[assignment]
            result = inner.retrieve(
                query=ranking_query,
                caller=caller,
                profile=typed_profile,
                deadline_seconds=deadline_seconds,
                restrict_version_id=restrict_version_id,
                cache_mode=cache_mode,
                source_selectors=scope.selector_texts if scope is not None else (),
            )
        resolution = (
            scope.resolution.value
            if scope is not None
            else SourceResolution.UNSCOPED.value
        )
        return replace(
            result,
            source_resolution=resolution,
            stage_timings_ms={**result.stage_timings_ms, "scope_ms": scope_ms},
        )

    def _resolve_version_id(
        self,
        caller: CallerContext,
        profile: ExpectedProfile | None,
    ) -> UUID | None:
        """Resolve textual requested sources to at most one authorized version.

        Low-confidence names stay unscoped. UUID-shaped strings are treated as
        text. Missing or unauthorized titles are indistinguishable.

        Args:
            caller: Server-derived identity.
            profile: Typed query profile.

        Returns:
            One current version id, or ``None`` when unscoped or ambiguous.
        """

        scope = self._resolve_scope(caller, profile, query="")
        return None if scope is None else scope.version_id

    def _resolve_scope(
        self,
        caller: CallerContext,
        profile: ExpectedProfile | None,
        *,
        query: str,
    ) -> ResolvedRetrievalScope | None:
        """Resolve source scope and the frozen Hybrid profile.

        Low-confidence requested names are ignored. Authorized titles that
        appear inside ``query`` can still uniquely scope retrieve. Missing
        and unauthorized titles stay indistinguishable.

        Args:
            caller: Server-derived identity.
            profile: Typed query profile.
            query: Original branch query used for contained-title matching.

        Returns:
            Resolved scope, or None when names are absent and no title is
            contained in the query.
        """

        names: tuple[str, ...] = ()
        if profile is not None:
            names = high_confidence_source_names(
                profile_strings(profile.requested_sources),
                profile.requested_sources.confidence,
            )
        if profile is None and not query.strip():
            return None
        raw_class = None if profile is None else profile.query_type.value
        query_class = raw_class if isinstance(raw_class, str) else None
        try:
            with connect_postgres(self._supabase_dsn) as connection:
                connection.execute("SET ROLE app_api")
                return resolve_retrieval_scope(
                    caller=caller,
                    requested_sources=names,
                    whole_document=False,
                    query_class=query_class,
                    connection=connection,
                    query_text=query,
                )
        except psycopg.Error:
            return None

    def authorized_chunk_loader(self, caller: CallerContext) -> object:
        """Return the ACL-rechecking canonical context loader.

        Args:
            caller: Server-derived identity.

        Returns:
            Loader used by citations and parent expansion.
        """

        return context_loader(self._supabase_dsn, caller)


@dataclass(slots=True)
class RunScopedHybrid:
    """Per-run Hybrid facade. ``query_budget`` must not live on the process adapter.

    Attributes:
        inner: Process DSN-based Hybrid.
        query_budget: Set by ``execute_branches`` for this compiled run only.
    """

    inner: ProcessHybridRetriever
    query_budget: object | None = None

    def retrieve(
        self,
        *,
        query: str,
        caller: CallerContext,
        profile: object | None = None,
        deadline_seconds: float | None = None,
        cache_mode: RetrievalCacheMode = RetrievalCacheMode.NORMAL,
    ) -> object:
        """Forward retrieve with this run's budget.

        Args:
            query: Branch query text.
            caller: Server-derived caller.
            profile: Typed query profile when present.
            deadline_seconds: Remaining retrieval slice.
            cache_mode: Forwarded to the process Hybrid retrieve.

        Returns:
            ``HybridRunResult``.
        """

        return self.inner.retrieve(
            query=query,
            caller=caller,
            profile=profile,
            deadline_seconds=deadline_seconds,
            query_budget=self.query_budget,
            cache_mode=cache_mode,
        )

    def authorized_chunk_loader(self, caller: CallerContext) -> object:
        """Forward the process Hybrid canonical context loader.

        Args:
            caller: Server-derived identity.

        Returns:
            ACL-rechecking context loader.
        """

        return self.inner.authorized_chunk_loader(caller)


def context_loader_for_connection(
    connection: psycopg.Connection,
    caller: CallerContext,
) -> Callable[[tuple[UUID, ...]], tuple[ChunkContext, ...]]:
    """Build a context loader that reuses one open connection.

    Preload, parent expansion, and locator reload share this connection
    for a single retrieve. ``_resolve_scope`` and
    ``authorized_chunk_loader`` keep their own connections.

    Args:
        connection: Open canonical Postgres connection. The loader does
            not close it.
        caller: Retrieve caller captured for ACL.

    Returns:
        ``ContextFn`` used by ``HybridRetriever``.
    """

    def load(chunk_ids: tuple[UUID, ...]) -> tuple[ChunkContext, ...]:
        """Load authorized chunk context on the retrieve connection.

        Args:
            chunk_ids: Canonical IDs.

        Returns:
            Authorized rows. Unauthorized IDs are omitted.
        """

        return fetch_authorized_chunk_context(
            connection,
            caller=caller,
            chunk_ids=chunk_ids,
        )

    return load


def context_loader(
    supabase_dsn: str, caller: CallerContext
) -> Callable[[tuple[UUID, ...]], tuple[ChunkContext, ...]]:
    """Build a context RPC loader that opens one connection per fetch.

    Args:
        supabase_dsn: Canonical Postgres URL.
        caller: Retrieve caller captured for ACL.

    Returns:
        ``ContextFn`` used by ``HybridRetriever``.
    """

    def load(chunk_ids: tuple[UUID, ...]) -> tuple[ChunkContext, ...]:
        """Load authorized chunk context on a fresh idle login connection.

        ``fetch_authorized_chunk_context`` starts ``retrieval_transaction``,
        which requires an idle connection and applies ``SET LOCAL ROLE
        app_api``. Pre-setting the role would leave the connection
        in-transaction and fail closed on hosted pooler and local Postgres.

        Args:
            chunk_ids: Canonical IDs.

        Returns:
            Authorized rows. Unauthorized IDs are omitted.
        """

        with connect_postgres(supabase_dsn) as connection:
            return fetch_authorized_chunk_context(
                connection,
                caller=caller,
                chunk_ids=chunk_ids,
            )

    return load


def _profile_without_source_selectors(
    profile: ExpectedProfile | None,
    selectors: tuple[str, ...],
) -> ExpectedProfile | None:
    """Strip source-selector phrases from profile variants used for ranking.

    Args:
        profile: Typed profile, if any.
        selectors: Authorized titles already used as scope selectors.

    Returns:
        Copied profile with stripped variants, or the original when there
        are no variants.
    """

    if profile is None or not selectors:
        return profile
    raw = profile.variants.value
    if not isinstance(raw, list):
        return profile
    stripped = [
        strip_source_selectors(str(item), selectors)
        for item in raw
        if str(item).strip()
    ]
    return profile.model_copy(
        update={
            "variants": profile.variants.model_copy(update={"value": stripped}),
        }
    )
