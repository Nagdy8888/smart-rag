"""Hybrid channel jobs, per-thread Postgres, and temporal stamps."""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from datetime import datetime
from typing import cast
from uuid import UUID

import psycopg

from smart_rag_core.retrieval.frozen_profile import FrozenHybridProfile
from smart_rag_core.retrieval.hybrid_run.channels import (
    collect_dense_lists,
    collect_term_lists,
    dense_retrieve_mode,
)
from smart_rag_core.retrieval.hybrid_run.types import (
    Bm25RetrieverLike,
    ChannelJob,
    DenseRetrieverLike,
    TermRetrieverLike,
    VariantLists,
)
from smart_rag_core.retrieval.profiles import RetrievalFallbackReason
from smart_rag_core.retrieval.temporal import TemporalDocument
from smart_rag_core.retrieval.types import Bm25RetrievalResult, RetrievalCandidate
from smart_rag_core.security.identity import CallerContext
from smart_rag_core.settings.postgres_connect import connect_postgres


class HybridChannelJobsMixin:
    """Build parallel channel jobs and load temporal records.

    Attributes:
        _dense: Optional dense retriever double or live adapter.
        _bm25: Optional BM25 retriever double or live adapter.
        _term: Optional term retriever double or live adapter.
        _paradedb: Optional ParadeDB connection used as a BM25 presence signal.
        _supabase: Bound canonical connection used when no DSN is provided.
        _supabase_dsn: Full Postgres URL for one idle connection per thread.
        _retrieval_profile: Optional frozen or evaluation profile. Version
            scoped exact dense is read from this object.
    """

    _dense: object | None
    _bm25: object | None
    _term: object | None
    _paradedb: object | None
    _supabase: psycopg.Connection | None
    _supabase_dsn: str | None
    _retrieval_profile: FrozenHybridProfile | None

    def _build_channel_jobs(
        self,
        *,
        caller: CallerContext,
        query: str,
        texts: tuple[str, ...],
        vectors: tuple[tuple[float, ...], ...],
        version_id: UUID | None = None,
    ) -> dict[str, ChannelJob]:
        """Build parallel dense/BM25/term jobs from bound retrievers.

        Args:
            caller: Server-derived identity.
            query: Original query used for the single BM25 scan.
            texts: At most three query forms for dense/term lists.
            vectors: Embeddings aligned with ``texts``.
            version_id: Optional current-version filter pushed inside ranking.

        Returns:
            Zero-argument jobs for ``run_channels_parallel``.
        """

        jobs: dict[str, ChannelJob] = {}
        dense = self._dense
        dense_mode = dense_retrieve_mode(
            version_id=version_id,
            profile=getattr(self, "_retrieval_profile", None),
        )
        if dense is not None:
            dense_retriever = cast(DenseRetrieverLike, dense)

            def _dense_job() -> VariantLists:
                """Run dense retrieve per fused query text.

                Returns:
                    Per-variant dense candidate lists.
                """

                if self._supabase_dsn:
                    from smart_rag_core.retrieval.dense import DenseRetriever

                    with self._channel_supabase() as connection:
                        return collect_dense_lists(
                            DenseRetriever(connection).retrieve,
                            caller=caller,
                            texts=texts,
                            vectors=vectors,
                            version_id=version_id,
                            dense_mode=dense_mode,
                        )
                return collect_dense_lists(
                    dense_retriever.retrieve,
                    caller=caller,
                    texts=texts,
                    vectors=vectors,
                    version_id=version_id,
                    dense_mode=dense_mode,
                )

            jobs["dense"] = _dense_job
        bm25 = self._bm25
        if bm25 is not None:
            bm25_retriever = cast(Bm25RetrieverLike, bm25)

            def _bm25_job() -> Bm25RetrievalResult:
                """Run one BM25 scan over original plus bounded variants.

                Returns:
                    Authorized BM25 survivors or a named outage fallback.
                """

                variant_texts = texts if texts else (query,)
                try:
                    retrieve_variants = getattr(
                        bm25_retriever, "retrieve_variants", None
                    )

                    def _scan(supabase_conn: object) -> object:
                        """Call variants when present; drop unknown kwargs.

                        Args:
                            supabase_conn: Canonical recheck connection.

                        Returns:
                            Channel result from the BM25 adapter.
                        """

                        if callable(retrieve_variants):
                            try:
                                return retrieve_variants(
                                    supabase=supabase_conn,
                                    caller=caller,
                                    texts=variant_texts,
                                    version_id=version_id,
                                )
                            except TypeError:
                                return retrieve_variants(
                                    supabase=supabase_conn,
                                    caller=caller,
                                    texts=variant_texts,
                                )
                        return bm25_retriever.retrieve(
                            supabase=supabase_conn,
                            caller=caller,
                            query_text=query,
                        )

                    if self._supabase_dsn:
                        with self._channel_supabase() as supabase_conn:
                            result = _scan(supabase_conn)
                    else:
                        result = _scan(self._supabase)
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
            term_retriever = cast(TermRetrieverLike, term)

            def _term_job() -> VariantLists:
                """Run term retrieve per fused query text.

                Returns:
                    Per-variant term candidate lists.
                """

                if self._supabase_dsn:
                    from smart_rag_core.retrieval.terms import TermRetriever

                    with self._channel_supabase() as connection:
                        return collect_term_lists(
                            TermRetriever(connection).retrieve,
                            caller=caller,
                            texts=texts,
                        )
                return collect_term_lists(
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
            Opens and closes one connection with automatic prepares
            disabled so hosted transaction poolers cannot raise
            ``DuplicatePreparedStatement``. Does not use the bound
            ``supabase`` connection, which stays idle for context RPC.
        """

        dsn = self._supabase_dsn
        if not dsn:
            raise RuntimeError("hybrid_channel_requires_supabase_dsn")
        connection = connect_postgres(dsn)
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
