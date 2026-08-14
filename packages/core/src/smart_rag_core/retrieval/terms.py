"""Exact, alias, and trigram term retrieval over populated search terms."""

from __future__ import annotations

from uuid import UUID

import psycopg

from smart_rag_core.retrieval.profiles import (
    MAX_NORMALIZED_QUERY_CHARS,
    TERM_CANDIDATE_CAP,
)
from smart_rag_core.retrieval.session import (
    RetrievalLanguage,
    retrieval_transaction,
)
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

        An empty or cold term channel returns ``empty_channel=True`` and must
        not be used to claim alias or code recall.

        Args:
            caller: Server-derived identity.
            query_text: Raw query; normalized with ``arabic_norm_v1``.
            candidate_limit: Requested list size, clamped to 30 in SQL.
            language: Optional language filter.
            profile: HNSW profile name unused for terms; timeout still applied.

        Returns:
            Term result with the normalized query form.

        Side Effects:
            One retrieval transaction without HNSW GUCs.
        """

        query_normalized = normalize_arabic_v1(query_text)[:MAX_NORMALIZED_QUERY_CHARS]
        if query_normalized == "":
            return TermRetrievalResult(
                candidates=(),
                query_normalized=query_normalized,
                empty_channel=True,
            )
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
                      %s::text
                    )
                    """,
                    (
                        caller.rpc_user_id(),
                        caller.rpc_role(),
                        caller.rpc_authorization_version(),
                        query_normalized,
                        candidate_limit,
                        language,
                    ),
                )
                rows = cursor.fetchall()
        candidates = tuple(
            RetrievalCandidate(
                chunk_id=UUID(str(row[0])),
                document_id=UUID(str(row[1])),
                version_id=UUID(str(row[2])),
                channel_rank=index + 1,
                channel_score=float(row[4]),
                match_kind=str(row[3]),
            )
            for index, row in enumerate(rows)
        )
        return TermRetrievalResult(
            candidates=candidates,
            query_normalized=query_normalized,
            empty_channel=len(candidates) == 0,
        )
