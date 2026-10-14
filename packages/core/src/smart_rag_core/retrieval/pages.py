"""Page-scoped Hybrid candidates when the query cites numeric pages."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from uuid import UUID

import psycopg
from psycopg.pq import TransactionStatus

from smart_rag_core.retrieval.hybrid_run.channels import cap_unique_across_variants
from smart_rag_core.retrieval.hybrid_run.types import VariantLists
from smart_rag_core.retrieval.profiles import TERM_CANDIDATE_CAP
from smart_rag_core.retrieval.session import retrieval_transaction
from smart_rag_core.retrieval.types import RetrievalCandidate
from smart_rag_core.security.identity import CallerContext

_PAGE_FETCH_SCAN_CAP = 60
"""Scan bound for current-version chunks on cited pages."""

PAGE_CANDIDATE_SQL = """
SELECT c.id, c.document_id, c.version_id
FROM app.document_chunks AS c
INNER JOIN app.documents AS d
  ON d.id = c.document_id
 AND d.current_version_id = c.version_id
 AND d.deleted_at IS NULL
INNER JOIN app.document_versions AS dv
  ON dv.id = c.version_id
 AND dv.deleted_at IS NULL
WHERE c.deleted_at IS NULL
  AND c.page_number = ANY(%s::integer[])
  AND (%s::uuid IS NULL OR c.version_id = %s::uuid)
  AND dv.status IN (
    'hybrid_ready'::app.document_status,
    'graph_pending'::app.document_status,
    'graph_ready'::app.document_status,
    'graph_ineligible'::app.document_status
  )
  AND app.caller_can_read_document(%s::uuid, %s, d.id)
ORDER BY c.page_number ASC, c.chunk_index ASC
LIMIT %s
"""
"""Authorized cited-page chunks, including ones search ranking skips.

Search ranking keeps ``is_search_representative`` chunks only. An explicit
page cite still needs the stored chunks on that page, so this statement
does not apply that flag. ACL, deletion, current version, and ready status
stay the same as ``app.recheck_retrieval_candidates``.
"""


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


def idle_page_connection(
    connection: psycopg.Connection,
    opener: Callable[[], psycopg.Connection],
) -> tuple[psycopg.Connection, bool]:
    """Return an idle connection for a cited-page fetch.

    ``retrieval_transaction`` refuses a connection that already has a
    transaction open. The term channel may still be inside one, so the page
    fetch opens a new connection instead of skipping the page.

    Args:
        connection: Connection the term channel just used.
        opener: Zero-arg callable that opens a new idle connection.

    Returns:
        The connection to use, and whether the caller must close it.
    """

    if connection.info.transaction_status == TransactionStatus.IDLE:
        return connection, False
    return opener(), True


def merge_cited_page_candidates(
    lists: VariantLists,
    page_hits: Sequence[RetrievalCandidate],
    *,
    cap: int = TERM_CANDIDATE_CAP,
) -> VariantLists:
    """Prepend cited-page hits, then apply the term-channel cap.

    Page hits stay ahead of lexical term hits so the cap cannot drop the
    cited page behind other needles.

    Args:
        lists: Per-variant lexical term candidates. Empty when term recall
            returned nothing.
        page_hits: Authorized chunks on the cited pages, in page order.
        cap: Unique chunk ceiling. Defaults to the term channel cap.

    Returns:
        Variant lists whose first entries are the cited-page hits, capped.
    """

    if not page_hits:
        return lists
    if not lists:
        merged: VariantLists = (tuple(page_hits),)
    else:
        seen = {item.chunk_id for item in page_hits}
        head = [item for item in lists[0] if item.chunk_id not in seen]
        merged = (tuple(page_hits) + tuple(head), *lists[1:])
    return cap_unique_across_variants(merged, cap)


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
    ``app_api``. ACL, deletion, current version, and ready status match
    ``app.recheck_retrieval_candidates``. Chunks that search ranking skips
    (``is_search_representative`` false) stay included, because the user
    named the page. This does not invent pages from gold or document-side
    metadata.

    Args:
        connection: Login role that can become ``app_api``. Must be idle.
        caller: Server-derived identity.
        pages: Explicit page numbers from the user query.
        version_id: Optional document version scope when Hybrid already
            resolved one current version.
        candidate_limit: Result cap (clamped to the term channel cap).
        profile: Timeout profile for the retrieval transaction.

    Returns:
        Ordered authorized candidates. Empty when ``pages`` is empty or no
        authorized chunk is on those pages.

    Side Effects:
        One retrieval transaction. Does not call the representative recheck.
    """

    unique_pages = tuple(dict.fromkeys(int(page) for page in pages if int(page) >= 1))
    if not unique_pages:
        return ()
    limit = max(1, min(int(candidate_limit), _PAGE_FETCH_SCAN_CAP, TERM_CANDIDATE_CAP))
    with retrieval_transaction(
        connection,
        caller=caller,
        profile=profile,
        apply_hnsw=False,
    ):
        with connection.cursor() as cursor:
            cursor.execute(
                PAGE_CANDIDATE_SQL,
                (
                    list(unique_pages),
                    version_id,
                    version_id,
                    caller.rpc_user_id(),
                    caller.rpc_role(),
                    limit,
                ),
            )
            rows = cursor.fetchall()
    return tuple(
        RetrievalCandidate(
            chunk_id=UUID(str(row[0])),
            document_id=UUID(str(row[1])),
            version_id=UUID(str(row[2])),
            channel_rank=index + 1,
            channel_score=1.0,
        )
        for index, row in enumerate(rows)
    )
