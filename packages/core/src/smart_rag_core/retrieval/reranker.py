"""One-operation Hybrid rerank adapter. Never retries locally."""

from __future__ import annotations

import asyncio

from smart_rag_core.gateways.model import ModelGateway, RerankModelRequest
from smart_rag_core.gateways.openai_rerank import OpenAIRerankError
from smart_rag_core.retrieval.profiles import RERANK_MODEL_ID
from smart_rag_core.retrieval.rerank import (
    RerankFallbackReason,
    RerankPassage,
    RerankRanking,
    RerankUsage,
    rerank_input_hash,
    validate_rerank_payload,
)
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
    """Run exactly one rerank operation, then validate set equality.

    Args:
        query: Original user query.
        pool: Authorized top-20 pool.
        remaining_deadline_seconds: Remaining Hybrid deadline share.
        gateway: Shared model gateway. Hidden retries are forbidden.
        prompt_text: Pinned ``rerank_v1`` body.

    Returns:
        Validated rankings, usage, and fallback reason. On failure the
        rankings tuple is empty so the caller keeps fused RRF order.

    Side Effects:
        At most one ``generate_rerank`` call. Timeouts after provider success
        may still bill; ``request_id`` and usage stay observable.
    """

    if remaining_deadline_seconds <= 0:
        return (), None, RerankFallbackReason.BUDGET_DENIED
    if len(pool) < 2:
        return (), None, RerankFallbackReason.INSUFFICIENT_CANDIDATES
    candidate_ids = tuple(str(item.candidate.chunk_id) for item in pool)
    excerpts = tuple(item.excerpt or item.raw_text for item in pool)
    request = RerankModelRequest(
        query=query,
        prompt_version=RERANK_PROMPT_VERSION,
        prompt_sha256=RERANK_PROMPT_SHA256,
        prompt_text=prompt_text,
        model_id=RERANK_MODEL_ID,
        candidate_ids=list(candidate_ids),
        excerpts=list(excerpts),
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
    digest = rerank_input_hash(
        query=query,
        candidate_ids=candidate_ids,
        excerpts=excerpts,
        prompt_sha256=RERANK_PROMPT_SHA256,
    )
    try:
        rankings = validate_rerank_payload(
            response.payload,
            candidate_ids=tuple(item.candidate.chunk_id for item in pool),
            input_hash=digest,
        )
    except ValueError:
        return (
            (),
            RerankUsage(
                request_id=response.request_id,
                model=RERANK_MODEL_ID,
                input_tokens=response.input_tokens,
                output_tokens=response.output_tokens,
                model_calls=response.model_calls,
            ),
            RerankFallbackReason.SCHEMA_INVALID,
        )
    usage = RerankUsage(
        request_id=response.request_id,
        model=RERANK_MODEL_ID,
        input_tokens=response.input_tokens,
        output_tokens=response.output_tokens,
        model_calls=response.model_calls,
    )
    return rankings, usage, RerankFallbackReason.NONE
