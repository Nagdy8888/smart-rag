"""Private ParadeDB BM25 retriever returning canonical IDs only.

``Bm25Retriever`` receives opaque server-derived scope and allow-listed
filters. Every ID is batch-rechecked in Supabase before it can leave this
adapter. BM25 snippets are never selected or returned.
"""

from __future__ import annotations

from uuid import UUID

import psycopg
from psycopg import sql

from smart_rag_core.retrieval.bm25_indexer import Bm25Indexer
from smart_rag_core.retrieval.bm25_query import (
    Bm25QueryError,
    Bm25StructuredQuery,
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
from smart_rag_core.retrieval.types import Bm25RetrievalResult
from smart_rag_core.security.identity import CallerContext

_FIELD_TIER = {
    Bm25Field.TITLE: 0,
    Bm25Field.HEADING: 1,
    Bm25Field.ALIAS: 1,
    Bm25Field.BODY: 2,
}


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

        One bounded top-N query per allow-listed field is issued. Relevance
        keyset pagination is not used because it is not qualified for this pin.

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

        survivors = recheck_retrieval_candidates(
            supabase,
            caller=caller,
            chunk_ids=ordered_ids,
            scores_by_id=scores,
        )
        capped = survivors[:BM25_AUTHORIZED_SURVIVOR_CAP]
        return Bm25RetrievalResult(
            scanned_ids=tuple(ordered_ids),
            candidates=capped,
            fallback_reason=RetrievalFallbackReason.NONE,
        )

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
