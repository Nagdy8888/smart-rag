"""Authoritative Supabase recheck for BM25 and other derived-index IDs."""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

import psycopg

from smart_rag_core.retrieval.profiles import BM25_SCAN_ID_CAP
from smart_rag_core.retrieval.session import retrieval_transaction
from smart_rag_core.retrieval.types import RetrievalCandidate
from smart_rag_core.security.identity import CallerContext


class RecheckRejectedError(RuntimeError):
    """Raised when a recheck batch exceeds the scan bound."""


def recheck_retrieval_candidates(
    connection: psycopg.Connection,
    *,
    caller: CallerContext,
    chunk_ids: Sequence[UUID],
    scores_by_id: dict[UUID, float] | None = None,
    profile: str = "low",
) -> tuple[RetrievalCandidate, ...]:
    """Drop unauthorized, stale, deleted, or version-mismatched candidate IDs.

    Args:
        connection: Login role that can become ``app_api``.
        caller: Server-derived identity.
        chunk_ids: Derived-index IDs in scan order. At most 300.
        scores_by_id: Optional channel scores retained only for survivors.
        profile: Timeout profile for the retrieval transaction.

    Returns:
        At most 75 authorized candidates in original scan order.

    Raises:
        RecheckRejectedError: If more than 300 IDs are supplied.

    Side Effects:
        One retrieval transaction. Unauthorized IDs never leave the RPC.
    """

    unique_ordered = _bounded_unique(chunk_ids)
    if not unique_ordered:
        return ()
    scores = scores_by_id or {}
    with retrieval_transaction(
        connection,
        caller=caller,
        profile=profile,
        apply_hnsw=False,
    ):
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT chunk_id, document_id, version_id
                FROM app.recheck_retrieval_candidates(
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
                    unique_ordered,
                ),
            )
            rows = cursor.fetchall()
    return tuple(
        RetrievalCandidate(
            chunk_id=UUID(str(row[0])),
            document_id=UUID(str(row[1])),
            version_id=UUID(str(row[2])),
            channel_rank=index + 1,
            channel_score=float(scores.get(UUID(str(row[0])), 0.0)),
        )
        for index, row in enumerate(rows)
    )


def _bounded_unique(chunk_ids: Sequence[UUID]) -> list[UUID]:
    """Dedupe IDs while preserving scan order and enforcing the 300 cap.

    Args:
        chunk_ids: Input IDs.

    Returns:
        Ordered unique IDs.

    Raises:
        RecheckRejectedError: If the input exceeds 300 IDs.
    """

    if len(chunk_ids) > BM25_SCAN_ID_CAP:
        raise RecheckRejectedError("recheck_batch_exceeds_limit")
    seen: set[UUID] = set()
    ordered: list[UUID] = []
    for chunk_id in chunk_ids:
        if chunk_id in seen:
            continue
        seen.add(chunk_id)
        ordered.append(chunk_id)
    return ordered
