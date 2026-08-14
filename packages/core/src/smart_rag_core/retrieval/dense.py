"""Dense pgvector adapter over ``app.retrieve_dense_candidates``."""

from __future__ import annotations

from uuid import UUID

import psycopg

from smart_rag_core.ingestion.embeddings.policy import EMBEDDING_DIMENSIONS
from smart_rag_core.retrieval.profiles import (
    DENSE_CANDIDATE_CAP,
    DenseMode,
    HnswProfileId,
    RetrievalFallbackReason,
    admit_exact_fallback,
)
from smart_rag_core.retrieval.session import (
    RetrievalLanguage,
    retrieval_transaction,
)
from smart_rag_core.retrieval.types import DenseRetrievalResult, RetrievalCandidate
from smart_rag_core.security.identity import CallerContext


class DenseRetriever:
    """Filtered HNSW dense retrieval with bounded exact fallback."""

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
        query_embedding: list[float],
        profile: HnswProfileId | str = HnswProfileId.LOW,
        mode: DenseMode = DenseMode.ANN,
        candidate_limit: int = DENSE_CANDIDATE_CAP,
        language: RetrievalLanguage | None = None,
    ) -> DenseRetrievalResult:
        """Return authorized dense candidates.

        Authorization and metadata filters run inside the security-invoker RPC
        before ranking and ``LIMIT``. Outer post-filters are not applied.

        Args:
            caller: Server-derived identity.
            query_embedding: 1024-d contextual query vector.
            profile: Allow-listed HNSW profile.
            mode: ``ann`` or ``exact``. Exact is admitted only at or below the
                10,000 authorized-row ceiling.
            candidate_limit: Requested list size, clamped to 100 in SQL.
            language: Optional ``document_versions.language`` filter.

        Returns:
            Dense result. ``weak_evidence`` when exact admission fails.

        Raises:
            ValueError: If the embedding dimension is wrong or the mode is invalid.

        Side Effects:
            One retrieval transaction with transaction-local HNSW GUCs.
        """

        if len(query_embedding) != EMBEDDING_DIMENSIONS:
            raise ValueError("embedding_dimension_mismatch")
        if mode is DenseMode.WEAK_EVIDENCE:
            raise ValueError("unknown_retrieval_mode")

        vector_literal = _vector_literal(query_embedding)
        with retrieval_transaction(
            self._connection,
            caller=caller,
            profile=profile,
            apply_hnsw=True,
        ):
            authorized_count = _count_authorized(
                self._connection,
                caller=caller,
                language=language,
            )
            selected_mode = mode
            fallback = RetrievalFallbackReason.NONE
            if mode is DenseMode.EXACT:
                selected_mode = admit_exact_fallback(authorized_count)
                if selected_mode is DenseMode.WEAK_EVIDENCE:
                    return DenseRetrievalResult(
                        mode=DenseMode.WEAK_EVIDENCE,
                        candidates=(),
                        authorized_count=authorized_count,
                        fallback_reason=RetrievalFallbackReason.WEAK_EVIDENCE,
                    )
            candidates = _fetch_dense(
                self._connection,
                caller=caller,
                vector_literal=vector_literal,
                profile=str(profile),
                mode=selected_mode.value,
                candidate_limit=candidate_limit,
                language=language,
            )
        return DenseRetrievalResult(
            mode=selected_mode,
            candidates=candidates,
            authorized_count=authorized_count,
            fallback_reason=fallback,
        )


def _vector_literal(values: list[float]) -> str:
    """Format one pgvector literal from a Python float list.

    Args:
        values: Embedding components.

    Returns:
        Square-bracket vector literal.
    """

    return "[" + ",".join(f"{value:.8f}" for value in values) + "]"


def _count_authorized(
    connection: psycopg.Connection,
    *,
    caller: CallerContext,
    language: RetrievalLanguage | None,
) -> int:
    """Count authorized retrievable chunks for exact-fallback admission.

    Args:
        connection: Open ``app_api`` transaction.
        caller: Server-derived identity.
        language: Optional language filter.

    Returns:
        Authorized row count.
    """

    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT app.count_authorized_retrievable_chunks(
              %s::uuid,
              %s::text,
              %s::bigint,
              %s::text
            )
            """,
            (
                caller.rpc_user_id(),
                caller.rpc_role(),
                caller.rpc_authorization_version(),
                language,
            ),
        )
        row = cursor.fetchone()
    return int(row[0]) if row is not None else 0


def _fetch_dense(
    connection: psycopg.Connection,
    *,
    caller: CallerContext,
    vector_literal: str,
    profile: str,
    mode: str,
    candidate_limit: int,
    language: RetrievalLanguage | None,
) -> tuple[RetrievalCandidate, ...]:
    """Execute the dense RPC and map rows to candidates.

    Args:
        connection: Open ``app_api`` transaction.
        caller: Server-derived identity.
        vector_literal: pgvector literal.
        profile: Allow-listed profile name.
        mode: ``ann`` or ``exact``.
        candidate_limit: Requested cap.
        language: Optional language filter.

    Returns:
        Ordered candidates.
    """

    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT chunk_id, document_id, version_id, distance
            FROM app.retrieve_dense_candidates(
              %s::uuid,
              %s::text,
              %s::bigint,
              %s::extensions.vector,
              %s::text,
              %s::text,
              %s::integer,
              %s::text
            )
            """,
            (
                caller.rpc_user_id(),
                caller.rpc_role(),
                caller.rpc_authorization_version(),
                vector_literal,
                profile,
                mode,
                candidate_limit,
                language,
            ),
        )
        rows = cursor.fetchall()
    return tuple(
        RetrievalCandidate(
            chunk_id=UUID(str(row[0])),
            document_id=UUID(str(row[1])),
            version_id=UUID(str(row[2])),
            channel_rank=index + 1,
            channel_score=float(row[3]),
        )
        for index, row in enumerate(rows)
    )
