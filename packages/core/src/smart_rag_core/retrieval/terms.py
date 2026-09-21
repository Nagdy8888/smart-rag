"""Exact, alias, and trigram term retrieval over populated search terms."""

from __future__ import annotations

from uuid import UUID

import psycopg

from smart_rag_core.retrieval.profiles import (
    MAX_NORMALIZED_QUERY_CHARS,
    TERM_CANDIDATE_CAP,
    RetrievalFallbackReason,
)
from smart_rag_core.retrieval.recheck import recheck_retrieval_candidates
from smart_rag_core.retrieval.session import (
    RetrievalLanguage,
    retrieval_transaction,
)
from smart_rag_core.retrieval.term_needles import extract_term_needles
from smart_rag_core.retrieval.types import RetrievalCandidate, TermRetrievalResult
from smart_rag_core.security.identity import CallerContext
from smart_rag_core.text.arabic_normalize import normalize_arabic_v1


class TermRetriever:
    """Deterministic term channel over filenames, titles, codes, and aliases."""

    def __init__(self, connection: psycopg.Connection) -> None:
        """Bind one Postgres connection used with ``SET LOCAL ROLE app_api``.

        Args:
            connection: Login role that can become ``app_api``.
        """

        self._connection = connection

    def retrieve(
        self,
        *,
        caller: CallerContext,
        query_text: str,
        candidate_limit: int = TERM_CANDIDATE_CAP,
        language: RetrievalLanguage | None = None,
        profile: str = "low",
    ) -> TermRetrievalResult:
        """Return authorized exact/alias/trigram term candidates.

        Bounded codes, acronyms, entities, and aliases extracted from the
        ranking query are passed as extra needles in addition to the remaining
        sentence. An empty or cold term channel returns ``empty_channel=True``
        and must not be used to claim alias or code recall.

        Args:
            caller: Server-derived identity.
            query_text: Raw query; normalized with ``arabic_norm_v1``.
            candidate_limit: Requested list size, clamped to 30 in SQL.
            language: Optional language filter.
            profile: HNSW profile name unused for terms; timeout still applied.

        Returns:
            Term result with the normalized query form and extra needles.

        Side Effects:
            One retrieval transaction without HNSW GUCs, then one
            authoritative recheck of surviving IDs.
        """

        query_normalized = normalize_arabic_v1(query_text)[:MAX_NORMALIZED_QUERY_CHARS]
        extra_terms = extract_term_needles(query_text)
        if query_normalized == "":
            return TermRetrievalResult(
                candidates=(),
                query_normalized=query_normalized,
                empty_channel=True,
                extra_terms=extra_terms,
            )
        try:
            with retrieval_transaction(
                self._connection,
                caller=caller,
                profile=profile,
                apply_hnsw=False,
            ):
                with self._connection.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT chunk_id, document_id, version_id, match_kind, similarity
                        FROM app.retrieve_term_candidates(
                          %s::uuid,
                          %s::text,
                          %s::bigint,
                          %s::text,
                          %s::integer,
                          %s::text,
                          %s::text[]
                        )
                        """,
                        (
                            caller.rpc_user_id(),
                            caller.rpc_role(),
                            caller.rpc_authorization_version(),
                            query_normalized,
                            candidate_limit,
                            language,
                            list(extra_terms) or None,
                        ),
                    )
                    rows = cursor.fetchall()
        except psycopg.Error:
            return TermRetrievalResult(
                candidates=(),
                query_normalized=query_normalized,
                empty_channel=True,
                extra_terms=extra_terms,
                fallback_reason=RetrievalFallbackReason.TERM_UNAVAILABLE,
            )
        scored = {UUID(str(row[0])): float(row[4]) for row in rows}
        match_kinds = {UUID(str(row[0])): str(row[3]) for row in rows}
        survivors = recheck_retrieval_candidates(
            self._connection,
            caller=caller,
            chunk_ids=tuple(UUID(str(row[0])) for row in rows),
            scores_by_id=scored,
            profile=profile,
        )
        candidates = tuple(
            RetrievalCandidate(
                chunk_id=item.chunk_id,
                document_id=item.document_id,
                version_id=item.version_id,
                channel_rank=index + 1,
                channel_score=item.channel_score,
                match_kind=match_kinds.get(item.chunk_id),
            )
            for index, item in enumerate(survivors)
        )
        return TermRetrievalResult(
            candidates=candidates,
            query_normalized=query_normalized,
            empty_channel=len(candidates) == 0,
            extra_terms=extra_terms,
        )
