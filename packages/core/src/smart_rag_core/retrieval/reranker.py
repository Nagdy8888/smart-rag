"""One-operation Hybrid rerank adapter. Never retries locally."""

from __future__ import annotations

import asyncio
from dataclasses import replace

from smart_rag_core.gateways.model import ModelGateway, RerankModelRequest
from smart_rag_core.gateways.openai_rerank import OpenAIRerankError
from smart_rag_core.retrieval.profiles import RERANK_MODEL_ID
from smart_rag_core.retrieval.rerank import (
    RerankFallbackReason,
    RerankPassage,
    RerankPayloadError,
    RerankRanking,
    RerankUsage,
)
from smart_rag_core.retrieval.rerank_labels import validate_rerank_label_payload
from smart_rag_core.retrieval.rerank_versions import (
    RERANK_PROMPT_SHA256,
    RERANK_PROMPT_VERSION,
)


def rerank_pool(
    query: str,
    pool: tuple[RerankPassage, ...],
    remaining_deadline_seconds: float,
    *,
    gateway: ModelGateway,
    prompt_text: str,
) -> tuple[tuple[RerankRanking, ...], RerankUsage | None, RerankFallbackReason]:
    """Run exactly one rerank operation, then map labels back to IDs.

    Args:
        query: Original user query.
        pool: Authorized top-20 pool.
        remaining_deadline_seconds: Remaining Hybrid deadline share.
        gateway: Shared model gateway. Hidden retries are forbidden.
        prompt_text: Pinned ``rerank_v2`` body.

    Returns:
        Rankings that cover the whole pool, usage, and fallback reason. A
        partial model ranking is completed with the unranked candidates in
        pool order (``RerankRanking.appended``) and still returns ``none``.
        On failure the rankings tuple is empty so the caller keeps fused
        RRF order. Schema-invalid usage carries ``invalid_subcode``.

    Side Effects:
        At most one ``generate_rerank`` call. Timeouts after provider success
        may still bill; ``request_id`` and usage stay observable.
    """

    if remaining_deadline_seconds <= 0:
        return (), None, RerankFallbackReason.BUDGET_DENIED
    if len(pool) < 2:
        return (), None, RerankFallbackReason.INSUFFICIENT_CANDIDATES
    request = RerankModelRequest(
        query=query,
        prompt_version=RERANK_PROMPT_VERSION,
        prompt_sha256=RERANK_PROMPT_SHA256,
        prompt_text=prompt_text,
        model_id=RERANK_MODEL_ID,
        candidate_ids=[str(item.candidate.chunk_id) for item in pool],
        excerpts=[item.excerpt or item.raw_text for item in pool],
        remaining_deadline_seconds=min(remaining_deadline_seconds, 25.0),
    )
    try:
        response = asyncio.run(gateway.generate_rerank(request))
    except OpenAIRerankError as error:
        try:
            return (), None, RerankFallbackReason(error.reason)
        except ValueError:
            return (), None, RerankFallbackReason.PROVIDER_ERROR
    except ValueError as error:
        message = str(error)
        if "version" in message:
            return (), None, RerankFallbackReason.VERSION_MISMATCH
        return (), None, RerankFallbackReason.SCHEMA_INVALID
    usage = RerankUsage(
        request_id=response.request_id,
        model=RERANK_MODEL_ID,
        input_tokens=response.input_tokens,
        output_tokens=response.output_tokens,
        model_calls=response.model_calls,
    )
    try:
        rankings = validate_rerank_label_payload(
            response.payload,
            candidate_ids=tuple(item.candidate.chunk_id for item in pool),
        )
    except ValueError as error:
        subcode = error.subcode if isinstance(error, RerankPayloadError) else "json"
        return (
            (),
            replace(usage, invalid_subcode=subcode),
            RerankFallbackReason.SCHEMA_INVALID,
        )
    return rankings, usage, RerankFallbackReason.NONE
