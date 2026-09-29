"""Private ParadeDB BM25 retriever returning canonical IDs only.

``Bm25Retriever`` receives opaque server-derived scope and allow-listed
filters. Every ID is batch-rechecked in Supabase before it can leave this
adapter. BM25 snippets are never selected or returned.

Multi-token asks try conjunction (``&&&``) before disjunction (``|||``).
Flat equal scores are discarded so UUID ordering cannot poison Hybrid
fusion with query-independent heads.
"""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

import psycopg
from psycopg import sql

from smart_rag_core.retrieval.bm25_indexer import Bm25Indexer
from smart_rag_core.retrieval.bm25_query import (
    Bm25QueryError,
    Bm25StructuredQuery,
    bm25_key_scope_sql,
    bm25_match_clause,
    build_bm25_query,
)
from smart_rag_core.retrieval.profiles import (
    BM25_AUTHORIZED_SURVIVOR_CAP,
    BM25_FIELD_PRIORITY,
    BM25_INDEX_SCHEMA_VERSION,
    BM25_SCAN_ID_CAP,
    NORMALIZATION_VERSION,
    RETRIEVAL_STATEMENT_TIMEOUT_MS,
    Bm25Field,
    Bm25Operator,
    RetrievalFallbackReason,
)
from smart_rag_core.retrieval.recheck import recheck_retrieval_candidates
from smart_rag_core.retrieval.types import Bm25RetrievalResult, RetrievalCandidate
from smart_rag_core.security.identity import CallerContext
from smart_rag_core.text.arabic_normalize import normalize_arabic_v1

_FIELD_TIER = {
    Bm25Field.TITLE: 0,
    Bm25Field.HEADING: 1,
    Bm25Field.ALIAS: 1,
    Bm25Field.BODY: 2,
}
_SCORE_EQUALITY_DIGITS = 6


def bm25_query_token_count(query_text: str) -> int:
    """Return the whitespace token count after Arabic normalization.

    Args:
        query_text: Raw user or variant query.

    Returns:
        Non-negative token count. Empty or whitespace-only text is ``0``.
    """

    normalized = normalize_arabic_v1(query_text).strip()
    if not normalized:
        return 0
    return len(normalized.split())


def prefer_bm25_conjunction(query_text: str) -> bool:
    """Return whether multi-token queries should try conjunction first.

    Disjunction (``|||``) on long English asks matches nearly every chunk
    with flat scores; ``chunk_id`` then dominates the sort and unrelated
    questions share the same BM25 head. Conjunction recovers distinctive
    multi-token phrases before falling back to disjunction.

    Args:
        query_text: Raw user or variant query.

    Returns:
        True when the normalized query has two or more tokens.
    """

    return bm25_query_token_count(query_text) >= 2


def bm25_scores_discriminate(scores: Sequence[float]) -> bool:
    """Return whether BM25 scores separate the top survivors.

    When every survivor shares one rounded score, ordering collapses to
    ``chunk_id`` and pollutes Hybrid fusion with query-independent heads.

    Args:
        scores: Channel scores for authorized survivors in rank order.

    Returns:
        True when there are fewer than two scores, or at least two distinct
        values after rounding to six decimals.
    """

    if len(scores) < 2:
        return True
    distinct = {round(float(item), _SCORE_EQUALITY_DIGITS) for item in scores}
    return len(distinct) >= 2


def resolve_bm25_operators(
    query_text: str,
    *,
    requested: Bm25Operator,
) -> tuple[Bm25Operator, ...]:
    """Return operators to try, conjunction first for multi-token asks.

    Args:
        query_text: Raw query used for token counting.
        requested: Caller-selected operator. Non-disjunction requests are
            returned alone (no conjunction probe).

    Returns:
        Ordered operators. Never empty.
    """

    if requested is not Bm25Operator.MATCH_DISJUNCTION:
        return (requested,)
    if prefer_bm25_conjunction(query_text):
        return (Bm25Operator.MATCH_CONJUNCTION, Bm25Operator.MATCH_DISJUNCTION)
    return (Bm25Operator.MATCH_DISJUNCTION,)


class Bm25Retriever:
    """Read-only BM25 candidate scan over the derived ParadeDB projection."""

    def __init__(self, connection: psycopg.Connection) -> None:
        """Bind one ParadeDB connection used by the API reader DSN.

        Args:
            connection: ParadeDB login. Compose wires ``PARADEDB_URL`` to
                ``paradedb_reader``. Writer-login tests may SELECT only.
        """

        self._connection = connection
        self._indexer = Bm25Indexer(connection)

    def retrieve(
        self,
        *,
        supabase: psycopg.Connection,
        caller: CallerContext,
        query_text: str,
        operator: Bm25Operator = Bm25Operator.MATCH_DISJUNCTION,
        language: str | None = None,
        acl_scope_id: str | None = None,
        fields: tuple[Bm25Field, ...] = BM25_FIELD_PRIORITY,
    ) -> Bm25RetrievalResult:
        """Scan BM25 IDs and recheck them on canonical Supabase.

        Multi-token asks try conjunction before disjunction. Flat-score
        survivor lists are dropped so UUID-ordered noise cannot enter fusion.

        Args:
            supabase: Canonical Postgres connection for the recheck RPC.
            caller: Server-derived identity used only on the recheck path.
            query_text: Raw query; normalized with ``arabic_norm_v1``.
            operator: Allow-listed ParadeDB operator from the query profile.
            language: Optional opaque language filter.
            acl_scope_id: Optional opaque ACL scope prefilter. Not authorization.
            fields: Allow-listed fields in priority order.

        Returns:
            Scanned IDs plus authorized survivors. On ParadeDB outage or
            version mismatch, ``fallback_reason`` is set and candidates are empty.

        Side Effects:
            Reads ParadeDB as ``paradedb_reader``. Recheck writes nothing.
        """

        meta = self._indexer.fetch_meta()
        if meta.get("normalization_version") != NORMALIZATION_VERSION:
            return Bm25RetrievalResult(
                scanned_ids=(),
                candidates=(),
                fallback_reason=RetrievalFallbackReason.BM25_VERSION_MISMATCH,
            )
        if meta.get("index_schema_version") != BM25_INDEX_SCHEMA_VERSION:
            return Bm25RetrievalResult(
                scanned_ids=(),
                candidates=(),
                fallback_reason=RetrievalFallbackReason.BM25_VERSION_MISMATCH,
            )
        if not self._indexer.search_index_exists():
            return Bm25RetrievalResult(
                scanned_ids=(),
                candidates=(),
                fallback_reason=RetrievalFallbackReason.BM25_UNAVAILABLE,
            )

        last_empty = Bm25RetrievalResult(
            scanned_ids=(),
            candidates=(),
            fallback_reason=RetrievalFallbackReason.NONE,
        )
        for active in resolve_bm25_operators(query_text, requested=operator):
            result = self._retrieve_with_operator(
                supabase=supabase,
                caller=caller,
                query_text=query_text,
                operator=active,
                language=language,
                acl_scope_id=acl_scope_id,
                fields=fields,
            )
            if result.fallback_reason is not RetrievalFallbackReason.NONE:
                return result
            if result.candidates:
                return result
            last_empty = result
        return last_empty

    def _retrieve_with_operator(
        self,
        *,
        supabase: psycopg.Connection,
        caller: CallerContext,
        query_text: str,
        operator: Bm25Operator,
        language: str | None,
        acl_scope_id: str | None,
        fields: tuple[Bm25Field, ...],
    ) -> Bm25RetrievalResult:
        """Run one operator pass for :meth:`retrieve`.

        Args:
            supabase: Canonical recheck connection.
            caller: Server-derived identity.
            query_text: Raw query.
            operator: Operator for this pass.
            language: Optional language filter.
            acl_scope_id: Optional ACL scope prefilter.
            fields: Field priority.

        Returns:
            Survivors for this operator, or empty candidates when scores
            do not discriminate.
        """

        per_field_limit = BM25_SCAN_ID_CAP // max(len(fields), 1)
        scored: list[tuple[int, float, UUID]] = []
        try:
            with self._connection.transaction():
                with self._connection.cursor() as cursor:
                    cursor.execute(
                        "SELECT set_config(%s, %s, true)",
                        ("statement_timeout", str(RETRIEVAL_STATEMENT_TIMEOUT_MS)),
                    )
                for field in fields:
                    query = build_bm25_query(
                        query_text=query_text,
                        operator=operator,
                        field=field,
                    )
                    scored.extend(
                        self._scan_field(
                            query=query,
                            language=language,
                            acl_scope_id=acl_scope_id,
                            limit=per_field_limit,
                            field_tier=_FIELD_TIER[field],
                        )
                    )
        except (psycopg.Error, Bm25QueryError):
            return Bm25RetrievalResult(
                scanned_ids=(),
                candidates=(),
                fallback_reason=RetrievalFallbackReason.BM25_UNAVAILABLE,
            )

        scored.sort(key=lambda item: (item[0], -item[1], str(item[2])))
        ordered_ids: list[UUID] = []
        scores: dict[UUID, float] = {}
        seen: set[UUID] = set()
        for _tier, score, chunk_id in scored:
            if chunk_id in seen:
                continue
            seen.add(chunk_id)
            ordered_ids.append(chunk_id)
            scores[chunk_id] = score
            if len(ordered_ids) >= BM25_SCAN_ID_CAP:
                break

        scanned_ids = tuple(ordered_ids)
        survivors = recheck_retrieval_candidates(
            supabase,
            caller=caller,
            chunk_ids=ordered_ids,
            scores_by_id=scores,
        )
        capped = survivors[:BM25_AUTHORIZED_SURVIVOR_CAP]
        if not bm25_scores_discriminate(
            tuple(item.channel_score for item in capped)
        ):
            return Bm25RetrievalResult(
                scanned_ids=scanned_ids,
                candidates=(),
                fallback_reason=RetrievalFallbackReason.NONE,
                variant_count=1,
                variant_ranks=(0,),
                rechecked_count=len(ordered_ids),
                survivor_count=0,
                index_schema_version=BM25_INDEX_SCHEMA_VERSION,
                normalizer_version=NORMALIZATION_VERSION,
            )
        return Bm25RetrievalResult(
            scanned_ids=scanned_ids,
            candidates=capped,
            fallback_reason=RetrievalFallbackReason.NONE,
            variant_count=1,
            variant_ranks=(len(capped),),
            rechecked_count=len(ordered_ids),
            survivor_count=len(capped),
            index_schema_version=BM25_INDEX_SCHEMA_VERSION,
            normalizer_version=NORMALIZATION_VERSION,
            variant_lists=(capped,) if capped else (),
        )

    def retrieve_variants(
        self,
        *,
        supabase: psycopg.Connection,
        caller: CallerContext,
        texts: tuple[str, ...],
        operator: Bm25Operator = Bm25Operator.MATCH_DISJUNCTION,
        language: str | None = None,
        acl_scope_id: str | None = None,
        version_id: UUID | None = None,
        fields: tuple[Bm25Field, ...] = BM25_FIELD_PRIORITY,
    ) -> Bm25RetrievalResult:
        """Scan original plus at most three variants in one top-300 statement.

        Multi-token primary asks try conjunction before disjunction. Flat
        survivor scores are discarded so UUID-ordered noise cannot enter
        Hybrid fusion.

        Args:
            supabase: Canonical Postgres for the recheck RPC.
            caller: Server-derived identity used only on recheck.
            texts: Original query first, then at most three variants.
            operator: Allow-listed ParadeDB operator.
            language: Optional language filter pushed into ranking.
            acl_scope_id: Optional opaque scope prefilter.
            version_id: Optional current version. Applied as a btree lookup
                of ``chunk_id`` values, then ``chunk_id = ANY(...)`` on the
                BM25 key field. ``version_id`` is not a ``pg_search`` filter
                column; mixing it with ``pdb.score`` is an unsupported query
                shape on the pinned image.
            fields: Allow-listed fields.

        Returns:
            Combined scanned IDs, per-variant authorized lists, and
            globally capped unique survivors. Never returns snippets.

        Side Effects:
            One btree id lookup when ``version_id`` is set. One ParadeDB
            BM25 statement. One canonical recheck of the union.
        """

        meta = self._indexer.fetch_meta()
        if meta.get("normalization_version") != NORMALIZATION_VERSION:
            return Bm25RetrievalResult(
                scanned_ids=(),
                candidates=(),
                fallback_reason=RetrievalFallbackReason.BM25_VERSION_MISMATCH,
                index_schema_version=str(meta.get("index_schema_version") or ""),
                normalizer_version=str(meta.get("normalization_version") or ""),
            )
        if meta.get("index_schema_version") != BM25_INDEX_SCHEMA_VERSION:
            return Bm25RetrievalResult(
                scanned_ids=(),
                candidates=(),
                fallback_reason=RetrievalFallbackReason.BM25_VERSION_MISMATCH,
                index_schema_version=str(meta.get("index_schema_version") or ""),
                normalizer_version=NORMALIZATION_VERSION,
            )
        if not self._indexer.search_index_exists():
            return Bm25RetrievalResult(
                scanned_ids=(),
                candidates=(),
                fallback_reason=RetrievalFallbackReason.BM25_UNAVAILABLE,
            )

        unique_texts: list[str] = []
        seen_text: set[str] = set()
        for text in texts[:3]:
            normalized = text.strip()
            if not normalized or normalized in seen_text:
                continue
            seen_text.add(normalized)
            unique_texts.append(text)
        if not unique_texts:
            return Bm25RetrievalResult(
                scanned_ids=(),
                candidates=(),
                fallback_reason=RetrievalFallbackReason.NONE,
            )

        primary = unique_texts[0]
        last_empty = Bm25RetrievalResult(
            scanned_ids=(),
            candidates=(),
            fallback_reason=RetrievalFallbackReason.NONE,
            variant_count=len(unique_texts),
        )
        for active in resolve_bm25_operators(primary, requested=operator):
            result = self._retrieve_variants_with_operator(
                supabase=supabase,
                caller=caller,
                unique_texts=tuple(unique_texts),
                operator=active,
                language=language,
                acl_scope_id=acl_scope_id,
                version_id=version_id,
                fields=fields,
            )
            if result.fallback_reason is not RetrievalFallbackReason.NONE:
                return result
            if result.candidates:
                return result
            last_empty = result
        return last_empty

    def _retrieve_variants_with_operator(
        self,
        *,
        supabase: psycopg.Connection,
        caller: CallerContext,
        unique_texts: tuple[str, ...],
        operator: Bm25Operator,
        language: str | None,
        acl_scope_id: str | None,
        version_id: UUID | None,
        fields: tuple[Bm25Field, ...],
    ) -> Bm25RetrievalResult:
        """Run one operator pass for :meth:`retrieve_variants`.

        Args:
            supabase: Canonical recheck connection.
            caller: Server-derived identity.
            unique_texts: Deduplicated original plus variants.
            operator: Operator for every branch in this pass.
            language: Optional language filter.
            acl_scope_id: Optional ACL scope prefilter.
            version_id: Optional version scope.
            fields: Field priority.

        Returns:
            Survivors for this operator, or empty candidates when scores
            do not discriminate.
        """

        branches: list[sql.Composed] = []
        params: list[object] = []
        try:
            scope_ids: tuple[UUID, ...] | None = None
            if version_id is not None:
                scope_ids = self._current_chunk_ids_for_version(version_id)
                if not scope_ids:
                    return Bm25RetrievalResult(
                        scanned_ids=(),
                        candidates=(),
                        fallback_reason=RetrievalFallbackReason.NONE,
                    )
            scope_sql, scope_params = bm25_key_scope_sql(scope_ids)
            for ordinal, text in enumerate(unique_texts):
                for field in fields:
                    structured = build_bm25_query(
                        query_text=text,
                        operator=operator,
                        field=field,
                    )
                    branches.append(
                        sql.SQL(
                            """
                            SELECT {ordinal}::integer AS variant_ordinal,
                                   {tier}::integer AS field_tier,
                                   chunk_id,
                                   pdb.score(chunk_id) AS score
                            FROM bm25_chunks
                            WHERE {match}
                              AND is_current = true
                              AND (%s::text IS NULL OR language IS NOT DISTINCT FROM %s)
                              AND (%s::text IS NULL OR acl_scope_id = %s)
                              {scope}
                            """
                        ).format(
                            ordinal=sql.Literal(ordinal),
                            tier=sql.Literal(_FIELD_TIER[field]),
                            match=bm25_match_clause(structured),
                            scope=scope_sql,
                        )
                    )
                    params.extend(
                        [
                            structured.query_normalized,
                            language,
                            language,
                            acl_scope_id,
                            acl_scope_id,
                            *scope_params,
                        ]
                    )
            statement = sql.SQL(
                """
                SELECT variant_ordinal, field_tier, chunk_id, score
                FROM ({union}) AS unioned
                ORDER BY field_tier ASC, score DESC, chunk_id ASC
                LIMIT %s
                """
            ).format(union=sql.SQL(" UNION ALL ").join(branches))
            params.append(BM25_SCAN_ID_CAP)
            with self._connection.transaction():
                with self._connection.cursor() as cursor:
                    cursor.execute(
                        "SELECT set_config(%s, %s, true)",
                        ("statement_timeout", str(RETRIEVAL_STATEMENT_TIMEOUT_MS)),
                    )
                    cursor.execute(statement, params)
                    rows = cursor.fetchall()
        except (psycopg.Error, Bm25QueryError):
            return Bm25RetrievalResult(
                scanned_ids=(),
                candidates=(),
                fallback_reason=RetrievalFallbackReason.BM25_UNAVAILABLE,
            )

        scanned: list[UUID] = []
        scores: dict[UUID, float] = {}
        seen_ids: set[UUID] = set()
        per_variant_ids: list[list[UUID]] = [[] for _ in unique_texts]
        per_variant_scores: list[dict[UUID, float]] = [{} for _ in unique_texts]
        for row in rows:
            ordinal = int(row[0])
            score = float(row[3])
            chunk_id = UUID(str(row[2]))
            if (
                0 <= ordinal < len(per_variant_ids)
                and chunk_id not in per_variant_scores[ordinal]
            ):
                per_variant_ids[ordinal].append(chunk_id)
                per_variant_scores[ordinal][chunk_id] = score
            if chunk_id in seen_ids:
                continue
            seen_ids.add(chunk_id)
            scanned.append(chunk_id)
            scores[chunk_id] = score
            if len(scanned) >= BM25_SCAN_ID_CAP:
                break

        survivors = recheck_retrieval_candidates(
            supabase,
            caller=caller,
            chunk_ids=tuple(scanned),
            scores_by_id=scores,
        )
        survivor_by_id = {item.chunk_id: item for item in survivors}
        variant_lists: list[tuple[RetrievalCandidate, ...]] = []
        for ordinal, ids in enumerate(per_variant_ids):
            kept: list[RetrievalCandidate] = []
            for chunk_id in ids:
                item = survivor_by_id.get(chunk_id)
                if item is None:
                    continue
                kept.append(
                    RetrievalCandidate(
                        chunk_id=item.chunk_id,
                        document_id=item.document_id,
                        version_id=item.version_id,
                        channel_rank=len(kept) + 1,
                        channel_score=per_variant_scores[ordinal].get(
                            chunk_id, item.channel_score
                        ),
                    )
                )
            variant_lists.append(tuple(kept))
        from smart_rag_core.retrieval.hybrid_run.channels import (
            cap_unique_across_variants,
        )

        capped_lists = cap_unique_across_variants(
            tuple(variant_lists), BM25_AUTHORIZED_SURVIVOR_CAP
        )
        combined: list[RetrievalCandidate] = []
        seen_final: set[UUID] = set()
        for variant in capped_lists:
            for item in variant:
                if item.chunk_id in seen_final:
                    continue
                seen_final.add(item.chunk_id)
                combined.append(item)
        if not bm25_scores_discriminate(
            tuple(item.channel_score for item in combined)
        ):
            return Bm25RetrievalResult(
                scanned_ids=tuple(scanned),
                candidates=(),
                fallback_reason=RetrievalFallbackReason.NONE,
                variant_count=len(unique_texts),
                variant_ranks=tuple(0 for _ in capped_lists),
                rechecked_count=len(scanned),
                survivor_count=0,
                index_schema_version=BM25_INDEX_SCHEMA_VERSION,
                normalizer_version=NORMALIZATION_VERSION,
            )
        return Bm25RetrievalResult(
            scanned_ids=tuple(scanned),
            candidates=tuple(combined),
            fallback_reason=RetrievalFallbackReason.NONE,
            variant_count=len(unique_texts),
            variant_ranks=tuple(len(item) for item in capped_lists),
            rechecked_count=len(scanned),
            survivor_count=len(combined),
            index_schema_version=BM25_INDEX_SCHEMA_VERSION,
            normalizer_version=NORMALIZATION_VERSION,
            variant_lists=capped_lists,
        )

    def _current_chunk_ids_for_version(self, version_id: UUID) -> tuple[UUID, ...]:
        """Load current projection ids for one version via btree, not BM25.

        Args:
            version_id: Canonical document version.

        Returns:
            Chunk ids currently projected for that version.

        Side Effects:
            One ParadeDB ``SELECT`` on ``bm25_chunks_version_id_idx``.
        """

        with self._connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT chunk_id
                FROM bm25_chunks
                WHERE version_id = %s
                  AND is_current = true
                """,
                (version_id,),
            )
            return tuple(UUID(str(row[0])) for row in cursor.fetchall())

    def _scan_field(
        self,
        *,
        query: Bm25StructuredQuery,
        language: str | None,
        acl_scope_id: str | None,
        limit: int,
        field_tier: int,
    ) -> list[tuple[int, float, UUID]]:
        """Run one ID-only field query.

        Args:
            query: Structured BM25 query.
            language: Optional language filter.
            acl_scope_id: Optional opaque scope filter.
            limit: Per-field scan cap.
            field_tier: Title=0, heading/alias=1, body=2.

        Returns:
            Tuples of ``(tier, score, chunk_id)``.
        """

        structured = query
        statement = sql.SQL(
            """
            SELECT chunk_id, pdb.score(chunk_id) AS score
            FROM bm25_chunks
            WHERE {match}
              AND is_current = true
              AND (%s::text IS NULL OR language IS NOT DISTINCT FROM %s)
              AND (%s::text IS NULL OR acl_scope_id = %s)
            ORDER BY pdb.score(chunk_id) DESC, chunk_id ASC
            LIMIT %s
            """
        ).format(match=bm25_match_clause(structured))
        with self._connection.cursor() as cursor:
            cursor.execute(
                statement,
                (
                    structured.query_normalized,
                    language,
                    language,
                    acl_scope_id,
                    acl_scope_id,
                    limit,
                ),
            )
            rows = cursor.fetchall()
        return [(field_tier, float(row[1]), UUID(str(row[0]))) for row in rows]
