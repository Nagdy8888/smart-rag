"""Authorized chunk context loader for rerank excerpts and parent expansion."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

import psycopg

from smart_rag_core.retrieval.session import retrieval_transaction
from smart_rag_core.security.identity import CallerContext


class ContextBatchError(RuntimeError):
    """Raised when a context fetch exceeds the 75-ID bound."""


@dataclass(frozen=True, slots=True)
class ChunkContext:
    """One authorized current chunk used as citation text.

    Attributes:
        chunk_id: Canonical chunk.
        document_id: Document.
        version_id: Current version.
        parent_chunk_id: Parent passage when present.
        chunk_index: Order within the version.
        page_number: Optional page locator.
        section_path: Heading path.
        token_count: Stored token count.
        raw_text: Canonical citation text.
        is_search_representative: Whether the row is a search child.
    """

    chunk_id: UUID
    document_id: UUID
    version_id: UUID
    parent_chunk_id: UUID | None
    chunk_index: int
    page_number: int | None
    section_path: tuple[str, ...]
    token_count: int | None
    raw_text: str
    is_search_representative: bool


def fetch_authorized_chunk_context(
    connection: psycopg.Connection,
    *,
    caller: CallerContext,
    chunk_ids: tuple[UUID, ...],
) -> tuple[ChunkContext, ...]:
    """Load ACL-visible current rows including non-representative parents.

    Args:
        connection: Login role that can become ``app_api``.
        caller: Server-derived identity.
        chunk_ids: At most 75 IDs.

    Returns:
        Authorized rows in request order. Missing/unauthorized IDs are omitted.

    Raises:
        ContextBatchError: If more than 75 IDs are supplied.

    Side Effects:
        One retrieval transaction. Unauthorized IDs never leave the RPC.
    """

    unique: list[UUID] = []
    seen: set[UUID] = set()
    for chunk_id in chunk_ids:
        if chunk_id in seen:
            continue
        seen.add(chunk_id)
        unique.append(chunk_id)
    if len(unique) > 75:
        raise ContextBatchError("context_batch_exceeds_limit")
    if not unique:
        return ()
    with retrieval_transaction(
        connection,
        caller=caller,
        profile="low",
        apply_hnsw=False,
    ):
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                  chunk_id,
                  document_id,
                  version_id,
                  parent_chunk_id,
                  chunk_index,
                  page_number,
                  section_path,
                  token_count,
                  raw_text,
                  is_search_representative
                FROM app.fetch_authorized_chunk_context(
                  %s::uuid,
                  %s::text,
                  %s::bigint,
                  %s::uuid[]
                )
                """,
                (
                    caller.rpc_user_id(),
                    caller.rpc_role(),
                    caller.rpc_authorization_version(),
                    unique,
                ),
            )
            rows = cursor.fetchall()
    results: list[ChunkContext] = []
    for row in rows:
        section = row[6]
        path = tuple(str(item) for item in section) if section else ()
        results.append(
            ChunkContext(
                chunk_id=UUID(str(row[0])),
                document_id=UUID(str(row[1])),
                version_id=UUID(str(row[2])),
                parent_chunk_id=UUID(str(row[3])) if row[3] is not None else None,
                chunk_index=int(row[4]),
                page_number=int(row[5]) if row[5] is not None else None,
                section_path=path,
                token_count=int(row[7]) if row[7] is not None else None,
                raw_text=str(row[8]),
                is_search_representative=bool(row[9]),
            )
        )
    return tuple(results)
