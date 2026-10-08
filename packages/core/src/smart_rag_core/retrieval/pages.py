"""Page-scoped Hybrid candidates when the query cites numeric pages."""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

import psycopg

from smart_rag_core.retrieval.profiles import TERM_CANDIDATE_CAP
from smart_rag_core.retrieval.recheck import recheck_retrieval_candidates
from smart_rag_core.retrieval.session import retrieval_transaction
from smart_rag_core.retrieval.types import RetrievalCandidate
from smart_rag_core.security.identity import CallerContext

_PAGE_FETCH_SCAN_CAP = 60
"""Pre-recheck scan bound for current-version chunks on cited pages."""


def load_chunk_page_numbers(
    connection: psycopg.Connection,
    *,
    chunk_ids: Sequence[UUID],
) -> dict[UUID, int | None]:
    """Load ``page_number`` for fused chunk IDs under ``app_api``.

    Used to build page head-pins for the rerank pool without loading full
    citation text. Missing rows map to ``None``.

    Args:
        connection: Login role that can ``SET ROLE app_api``.
        chunk_ids: Fused candidate IDs.

    Returns:
        Mapping of chunk id to page number (or None when unknown).

    Side Effects:
        Sets ``app_api`` on the connection and runs one SELECT.
    """

    unique = tuple(dict.fromkeys(chunk_ids))
    if not unique:
        return {}
    connection.execute("SET ROLE app_api")
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT id, page_number
            FROM app.document_chunks
            WHERE id = ANY(%s::uuid[])
            """,
            (list(unique),),
        )
        rows = cursor.fetchall()
    found: dict[UUID, int | None] = {}
    for row in rows:
        chunk_id = UUID(str(row[0]))
        raw = row[1]
        if raw is None:
            found[chunk_id] = None
        else:
            found[chunk_id] = int(str(raw))
    return found


def retrieve_page_candidates(
    connection: psycopg.Connection,
    *,
    caller: CallerContext,
    pages: Sequence[int],
    version_id: UUID | None = None,
    candidate_limit: int = TERM_CANDIDATE_CAP,
    profile: str = "low",
) -> tuple[RetrievalCandidate, ...]:
    """Return authorized current-version chunks on explicitly cited pages.

    The query must already name numeric pages. Chunks are loaded under
    ``app_api`` then passed through ``recheck_retrieval_candidates`` so ACL,
    deletion, and current-version checks still apply. This does not invent
    pages from gold or document-side metadata.

    Args:
        connection: Login role that can become ``app_api``.
        caller: Server-derived identity.
        pages: Explicit page numbers from the user query.
        version_id: Optional document version scope when Hybrid already
            resolved one current version.
        candidate_limit: Post-recheck cap (clamped to the term channel cap).
        profile: Timeout profile for the retrieval transaction.

    Returns:
        Ordered authorized candidates. Empty when ``pages`` is empty or no
        authorized chunk survives recheck.

    Side Effects:
        One retrieval transaction selecting candidate IDs, then one recheck.
    """

    unique_pages = tuple(dict.fromkeys(int(page) for page in pages if int(page) >= 1))
    if not unique_pages:
        return ()
    limit = max(1, min(int(candidate_limit), TERM_CANDIDATE_CAP))
    scan_cap = min(_PAGE_FETCH_SCAN_CAP, limit * 2)
    with retrieval_transaction(
        connection,
        caller=caller,
        profile=profile,
        apply_hnsw=False,
    ):
        with connection.cursor() as cursor:
            if version_id is None:
                cursor.execute(
                    """
                    SELECT c.id
                    FROM app.document_chunks AS c
                    INNER JOIN app.documents AS d
                      ON d.id = c.document_id
                     AND d.current_version_id = c.version_id
                     AND d.deleted_at IS NULL
                    WHERE c.deleted_at IS NULL
                      AND c.page_number = ANY(%s::integer[])
                    ORDER BY c.page_number ASC, c.chunk_index ASC
                    LIMIT %s
                    """,
                    (list(unique_pages), scan_cap),
                )
            else:
                cursor.execute(
                    """
                    SELECT c.id
                    FROM app.document_chunks AS c
                    INNER JOIN app.documents AS d
                      ON d.id = c.document_id
                     AND d.current_version_id = c.version_id
                     AND d.deleted_at IS NULL
                    WHERE c.deleted_at IS NULL
                      AND c.version_id = %s::uuid
                      AND c.page_number = ANY(%s::integer[])
                    ORDER BY c.page_number ASC, c.chunk_index ASC
                    LIMIT %s
                    """,
                    (version_id, list(unique_pages), scan_cap),
                )
            rows = cursor.fetchall()
    chunk_ids = tuple(UUID(str(row[0])) for row in rows)
    if not chunk_ids:
        return ()
    survivors = recheck_retrieval_candidates(
        connection,
        caller=caller,
        chunk_ids=chunk_ids,
        scores_by_id={chunk_id: 1.0 for chunk_id in chunk_ids},
        profile=profile,
    )
    return survivors[:limit]
