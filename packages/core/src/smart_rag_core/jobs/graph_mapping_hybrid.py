"""Worker-owned mapping Hybrid retrieve and support rerank callbacks.

Hash/span/overlap run first. Unresolved vendor chunks get at most one
version-scoped Hybrid retrieve and one OpenAI support rerank. Query-time
Hybrid is forbidden. Repair must not attach these callbacks.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID

import psycopg

from smart_rag_core.gateways import (
    ModelGatewayUnavailableError,
    create_embedding_gateway,
    create_model_gateway,
)
from smart_rag_core.ingestion.chunking.normalize import normalize_for_dedup
from smart_rag_core.jobs import graph_mapping_persist as persist
from smart_rag_core.jobs.limits import (
    MAPPING_HYBRID_CANDIDATE_CAP,
    MAPPING_SUPPORT_RERANK_DEADLINE_SECONDS,
)
from smart_rag_core.retrieval.context_loader import ChunkContext
from smart_rag_core.retrieval.coverage import CoverageSignal, HybridCoverage
from smart_rag_core.retrieval.graph_mapping import CanonicalPassage, SupportRerankFn
from smart_rag_core.retrieval.hybrid_run import HybridRetriever, HybridRunResult
from smart_rag_core.retrieval.profiles import RetrievalFallbackReason
from smart_rag_core.retrieval.rerank import RerankFallbackReason, RerankRanking
from smart_rag_core.retrieval.reranker import rerank_pool
from smart_rag_core.retrieval.types import Bm25RetrievalResult, RetrievalCandidate
from smart_rag_core.security.identity import CallerContext
from smart_rag_core.settings.base import SettingsValidationError, SharedSettings

_RERANK_PROMPT = (
    Path(__file__).resolve().parents[5]
    / "apps"
    / "agents"
    / "src"
    / "smart_rag_agents"
    / "prompts"
    / "rerank_v1.md"
)


@dataclass(frozen=True, slots=True)
class MappingSupportCallbacks:
    """Injected mapping Hybrid and support-rerank callables.

    Attributes:
        hybrid_retrieve: ``(query, version_id) -> HybridRunResult``.
        support_rerank: One OpenAI-only support rerank batch.
    """

    hybrid_retrieve: Callable[[str, UUID], HybridRunResult]
    support_rerank: SupportRerankFn


def bind_mapping_support(
    connection: psycopg.Connection,
    settings: SharedSettings,
) -> MappingSupportCallbacks | None:
    """Build mapping Hybrid/rerank callbacks for one worker connection.

    Args:
        connection: ``app_worker`` connection used to load the document owner
            and canonical passages.
        settings: Worker/shared settings for embedding and rerank gateways.

    Returns:
        Callbacks, or ``None`` when the gateway or pinned prompt cannot load.
        Hash/span/overlap still run; unresolved chunks then fail coverage.

    Side Effects:
        Constructs embedding and model gateways. Does not call providers until
        mapping invokes the callbacks.
    """

    try:
        embedding_gateway = create_embedding_gateway(settings)
        model_gateway = create_model_gateway(settings)
        prompt_text = _RERANK_PROMPT.read_text(encoding="utf-8")
    except (OSError, ModelGatewayUnavailableError, SettingsValidationError):
        return None

    def hybrid_retrieve(query: str, version_id: UUID) -> HybridRunResult:
        """Run one version-scoped Hybrid retrieve without Hybrid rerank.

        Args:
            query: Concatenated unresolved vendor text.
            version_id: Canonical version.

        Returns:
            Ranked canonical IDs from RRF over this version's passages.
        """

        caller = load_mapping_caller(connection, version_id=version_id)
        if caller is None or not caller.is_active():
            return _empty_hybrid_result(RetrievalFallbackReason.AUTH_CONTEXT_INVALID)
        canonicals = persist.load_canonical_passages(connection, version_id=version_id)
        capped = select_mapping_candidates(
            query,
            canonicals,
            cap=MAPPING_HYBRID_CANDIDATE_CAP,
        )
        if not capped:
            return _empty_hybrid_result(RetrievalFallbackReason.RETRIEVAL_EMPTY)
        candidates = tuple(
            RetrievalCandidate(
                chunk_id=item.chunk_id,
                document_id=item.document_id,
                version_id=item.version_id,
                channel_rank=index + 1,
                channel_score=1.0,
            )
            for index, item in enumerate(capped)
        )
        contexts = {
            item.chunk_id: ChunkContext(
                chunk_id=item.chunk_id,
                document_id=item.document_id,
                version_id=item.version_id,
                parent_chunk_id=None,
                chunk_index=item.chunk_index,
                page_number=None,
                section_path=(),
                token_count=None,
                raw_text=item.raw_text,
                is_search_representative=True,
            )
            for item in capped
        }

        def _load_context(chunk_ids: tuple[UUID, ...]) -> tuple[ChunkContext, ...]:
            """Return in-memory canonical contexts. No BM25 snippets.

            Args:
                chunk_ids: Requested chunk ids.

            Returns:
                Contexts that exist in this version cap.
            """

            return tuple(
                contexts[chunk_id] for chunk_id in chunk_ids if chunk_id in contexts
            )

        def _dense() -> tuple[tuple[RetrievalCandidate, ...], ...]:
            """Return the version-scoped dense list.

            Returns:
                One candidate list.
            """

            return (candidates,)

        def _bm25() -> Bm25RetrievalResult:
            """Return the version-scoped BM25 survivors.

            Returns:
                Authorized BM25 result for this version only.
            """

            return Bm25RetrievalResult(
                scanned_ids=tuple(item.chunk_id for item in candidates),
                candidates=candidates,
            )

        def _term() -> tuple[tuple[RetrievalCandidate, ...], ...]:
            """Return the version-scoped term list.

            Returns:
                One candidate list.
            """

            return (candidates,)

        retriever = HybridRetriever(
            embedding_gateway=embedding_gateway,
            load_context=_load_context,
            rerank=None,
        )
        return retriever.retrieve(
            query=query,
            caller=caller,
            restrict_version_id=version_id,
            channel_jobs={"dense": _dense, "bm25": _bm25, "term": _term},
        )

    def support_rerank(
        query: str, passages: tuple[Any, ...]
    ) -> tuple[RerankRanking, ...]:
        """Run one support rerank batch through the shared gateway.

        Args:
            query: Unresolved vendor/object text.
            passages: Canonical pool already capped at 20.

        Returns:
            Rankings for the supplied IDs. Provider failure returns identity
            ranks with support ``0.0`` so mapping stays fail-closed.
        """

        rankings, _usage, reason = rerank_pool(
            query,
            passages,
            MAPPING_SUPPORT_RERANK_DEADLINE_SECONDS,
            gateway=model_gateway,
            prompt_text=prompt_text,
        )
        if rankings and reason is RerankFallbackReason.NONE:
            return rankings
        return tuple(
            RerankRanking(
                chunk_id=item.candidate.chunk_id,
                rank=index + 1,
                support=0.0,
            )
            for index, item in enumerate(passages)
        )

    return MappingSupportCallbacks(
        hybrid_retrieve=hybrid_retrieve,
        support_rerank=support_rerank,
    )


def select_mapping_candidates(
    query: str,
    canonicals: tuple[CanonicalPassage, ...],
    *,
    cap: int,
) -> tuple[CanonicalPassage, ...]:
    """Select bounded version passages by deterministic query token overlap.

    Args:
        query: Balanced text sampled from every unresolved vendor chunk.
        canonicals: All canonical passages for the version.
        cap: Maximum passages exposed to the one Hybrid support call.

    Returns:
        Passages ordered by descending token overlap, then canonical chunk
        order. Zero-overlap rows fill remaining capacity deterministically.

    Raises:
        ValueError: If ``cap`` is not positive.
    """

    if cap <= 0:
        raise ValueError("mapping_candidate_cap_invalid")
    query_tokens = set(normalize_for_dedup(query).split())

    def _score(item: CanonicalPassage) -> tuple[int, float, int]:
        """Return overlap count, Jaccard score, and inverse chunk order.

        Args:
            item: Canonical passage to score.

        Returns:
            Sort tuple ordered toward stronger overlap and earlier chunks.
        """

        passage_tokens = set(normalize_for_dedup(item.raw_text).split())
        overlap = len(query_tokens & passage_tokens)
        union = len(query_tokens | passage_tokens)
        ratio = overlap / union if union else 0.0
        return overlap, ratio, -item.chunk_index

    return tuple(sorted(canonicals, key=_score, reverse=True)[:cap])


def load_mapping_caller(
    connection: psycopg.Connection,
    *,
    version_id: UUID,
) -> CallerContext | None:
    """Load the document owner's identity for a version-scoped Hybrid retrieve.

    Graph-eligible documents are company-visible. Mapping uses the uploader
    profile so Hybrid RPCs have a real ``CallerContext``. Disabled owners
    fail closed.

    Args:
        connection: ``app_worker`` connection.
        version_id: Canonical version being mapped.

    Returns:
        Active caller context, or ``None`` when the owner cannot be used.
    """

    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT
              user_id::text,
              role::text,
              authorization_version,
              disabled_at,
              upload_enabled,
              mfa_enrolled
            FROM app.load_graph_mapping_caller(%s)
            """,
            (version_id,),
        )
        row = cursor.fetchone()
    if row is None:
        return None
    try:
        caller = CallerContext.from_profile_row(
            user_id=str(row[0]),
            role=str(row[1]),
            authorization_version=int(row[2] or 1),
            disabled_at=row[3],
            upload_enabled=bool(row[4]),
            mfa_enrolled=bool(row[5]),
        )
    except ValueError:
        return None
    if not caller.is_active():
        return None
    return caller


def _empty_hybrid_result(reason: RetrievalFallbackReason) -> HybridRunResult:
    """Return an empty Hybrid result for mapping fail-closed paths.

    Args:
        reason: Named retrieve fallback.

    Returns:
        Empty ranked IDs so unresolved chunks stay unmapped.
    """

    return HybridRunResult(
        ranked_ids=(),
        evidence=(),
        coverage=HybridCoverage(
            signal=CoverageSignal.WEAK_EVIDENCE,
            notes=(reason.value,),
        ),
        fallback_reason=reason,
        deadline_exhausted=False,
        first_evidence_ms=0.0,
        embedding_call_count=0,
        rerank_call_count=0,
    )


__all__ = [
    "MappingSupportCallbacks",
    "bind_mapping_support",
    "load_mapping_caller",
]
