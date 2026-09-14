"""ACL-rechecking Hybrid cache hits and authorized chunk loaders."""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

import psycopg

from smart_rag_core.retrieval.cache_store import RetrievalCacheStore
from smart_rag_core.retrieval.context import ContextFn
from smart_rag_core.retrieval.context_loader import (
    ChunkContext,
    fetch_authorized_chunk_context,
    fetch_authorized_heading_inventory,
)
from smart_rag_core.retrieval.coverage import CoverageSignal, HybridCoverage
from smart_rag_core.retrieval.hybrid_run.assemble import elapsed_ms
from smart_rag_core.retrieval.hybrid_run.evidence import evidence_units_from_context
from smart_rag_core.retrieval.hybrid_run.types import HybridRunResult
from smart_rag_core.retrieval.profiles import (
    FINAL_EVIDENCE_MAX,
    RetrievalFallbackReason,
)
from smart_rag_core.retrieval.recheck import recheck_retrieval_candidates
from smart_rag_core.retrieval.types import RetrievalCandidate
from smart_rag_core.security.identity import CallerContext


class HybridCacheLookupMixin:
    """Mixin: cache hit assembly and authorized context loaders.

    Attributes:
        _retrieval_cache: Optional ID/rank cache. Hits still recheck ACL.
        _supabase: Canonical Postgres for context RPC and recheck.
        _supabase_dsn: Full URL used to open a recheck connection.
        _load_context: Optional injected context loader.
    """

    _retrieval_cache: RetrievalCacheStore | None
    _supabase: psycopg.Connection | None
    _supabase_dsn: str | None
    _load_context: ContextFn | None

    def _cached_result(
        self,
        *,
        caller: CallerContext,
        query_normalized: str,
        visibility_generation: int,
        started: float,
        profile_id: str,
        scope_hash: str,
    ) -> HybridRunResult | None:
        """Return a rechecked cache hit, or None on miss/outage.

        Args:
            caller: Server-derived identity.
            query_normalized: Normalized query used in the cache key.
            visibility_generation: ACL/visibility generation.
            started: Retrieve start timestamp.
            profile_id: Profile id used in the cache key.
            scope_hash: Principal ACL-scope hash.

        Returns:
            Cached Hybrid result after recheck, or None.

        Side Effects:
            Rechecks cached IDs through Postgres or the injected loader.
            Unauthorized IDs invalidate the key and become a miss.
        """

        store = self._retrieval_cache
        if store is None:
            return None

        def recheck(chunk_ids: Sequence[UUID]) -> tuple[RetrievalCandidate, ...]:
            """Recheck cached IDs before they become evidence.

            Args:
                chunk_ids: Cached IDs. Never trusted.

            Returns:
                Authorized current-version candidates.
            """

            return self._recheck_cached_ids(caller, chunk_ids)

        cached = store.get_results(
            principal_scope_hash=scope_hash,
            query_normalized=query_normalized,
            visibility_generation=visibility_generation,
            recheck=recheck,
            retrieval_profile_id=profile_id,
        )
        if cached is None:
            return None
        loader = self._bound_loader(caller, {})
        contexts = loader(cached.chunk_ids)
        fused = tuple(
            RetrievalCandidate(
                chunk_id=row.chunk_id,
                document_id=row.document_id,
                version_id=row.version_id,
                channel_rank=index + 1,
                channel_score=0.0,
            )
            for index, row in enumerate(contexts)
        )
        evidence = evidence_units_from_context(fused, contexts)
        signal = CoverageSignal.NONE if evidence else CoverageSignal.WEAK_EVIDENCE
        return HybridRunResult(
            ranked_ids=cached.chunk_ids,
            evidence=evidence[:FINAL_EVIDENCE_MAX],
            coverage=HybridCoverage(signal=signal, notes=("cache_hit",)),
            fallback_reason=RetrievalFallbackReason.NONE,
            deadline_exhausted=False,
            first_evidence_ms=elapsed_ms(started),
            embedding_call_count=0,
            rerank_call_count=0,
            selected_ids=cached.chunk_ids,
            retrieval_profile_id=profile_id,
        )

    def _recheck_cached_ids(
        self,
        caller: CallerContext,
        chunk_ids: Sequence[UUID],
    ) -> tuple[RetrievalCandidate, ...]:
        """Recheck cached IDs through Postgres or the injected loader.

        Args:
            caller: Server-derived identity.
            chunk_ids: Cached IDs.

        Returns:
            Authorized survivors in scan order. Empty on connection failure.
        """

        if self._supabase is not None:
            return recheck_retrieval_candidates(
                self._supabase,
                caller=caller,
                chunk_ids=chunk_ids,
            )
        if self._supabase_dsn:
            try:
                with psycopg.connect(self._supabase_dsn) as connection:
                    return recheck_retrieval_candidates(
                        connection,
                        caller=caller,
                        chunk_ids=chunk_ids,
                    )
            except (psycopg.Error, OSError):
                return ()
        rows = self._fetch_context(caller, tuple(chunk_ids))
        found = {row.chunk_id: row for row in rows}
        survivors: list[RetrievalCandidate] = []
        for index, chunk_id in enumerate(chunk_ids):
            row = found.get(chunk_id)
            if row is None:
                continue
            survivors.append(
                RetrievalCandidate(
                    chunk_id=row.chunk_id,
                    document_id=row.document_id,
                    version_id=row.version_id,
                    channel_rank=index + 1,
                    channel_score=0.0,
                )
            )
        return tuple(survivors)

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
