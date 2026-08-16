"""Query-run LangSmith metadata: hashes and counts only."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any
from uuid import UUID

from smart_rag_core.observability.langsmith_tracing import short_content_hash
from smart_rag_core.observability.logging import current_correlation_ids


def hashed_user_id(user_id: UUID | str) -> str:
    """Return a truncated SHA-256 of a user id. Never the raw UUID in traces.

    Args:
        user_id: Authenticated subject.

    Returns:
        First 16 hex characters of SHA-256.
    """

    return short_content_hash(str(user_id))


def query_run_trace_metadata(
    *,
    run_id: UUID | str,
    user_id: UUID | str,
    requested_route: str | None,
    effective_route: str | None,
    corrected_route: str | None,
    model_versions: Mapping[str, str] | None = None,
    prompt_versions: Mapping[str, str] | None = None,
    disclosed_tools: Sequence[str] | None = None,
    candidate_counts: Mapping[str, int] | None = None,
    bm25_index: str | None = None,
    bm25_version: str | None = None,
    bm25_lag_seconds: int | None = None,
    bm25_recheck_count: int | None = None,
    bm25_fallback: str | None = None,
    latency_ms: int | None = None,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    cache_hit: bool | None = None,
    cost_usd: str | None = None,
) -> dict[str, Any]:
    """Build a LangSmith extra payload with hashes and counts only.

    Args:
        run_id: Admitted run id (exported as the run identifier, not a secret).
        user_id: Subject hashed before export.
        requested_route: Envelope family reserved at admit.
        effective_route: Planner-selected family.
        corrected_route: Family after the one correction, if any.
        model_versions: Model ids keyed by usage kind.
        prompt_versions: Prompt version ids keyed by usage kind.
        disclosed_tools: Optional tool keys actually bound.
        candidate_counts: Per-channel candidate counts.
        bm25_index: BM25 index name/version label.
        bm25_version: Normalization/index version.
        bm25_lag_seconds: Projection lag in seconds.
        bm25_recheck_count: Supabase recheck count.
        bm25_fallback: Named fallback reason, if any.
        latency_ms: End-to-end latency.
        input_tokens: Prompt tokens.
        output_tokens: Completion tokens.
        cache_hit: Whether retrieval cache was used.
        cost_usd: Decimal string of recorded USD.

    Returns:
        Exportable metadata. Raw passages, emails, and secrets are omitted.
    """

    payload: dict[str, Any] = {
        "correlation": current_correlation_ids(),
        "run_id": str(run_id),
        "user_id_sha256": hashed_user_id(user_id),
        "requested_route": requested_route,
        "effective_route": effective_route,
        "corrected_route": corrected_route,
    }
    if model_versions:
        payload["model_versions"] = dict(model_versions)
    if prompt_versions:
        payload["prompt_versions"] = dict(prompt_versions)
    if disclosed_tools is not None:
        payload["disclosed_tool_count"] = len(tuple(disclosed_tools))
        payload["disclosed_tools"] = list(disclosed_tools)
    if candidate_counts:
        payload["candidate_counts"] = {
            str(key): int(value) for key, value in candidate_counts.items()
        }
    if bm25_index is not None:
        payload["bm25_index"] = bm25_index
    if bm25_version is not None:
        payload["bm25_version"] = bm25_version
    if bm25_lag_seconds is not None:
        payload["bm25_lag_seconds"] = bm25_lag_seconds
    if bm25_recheck_count is not None:
        payload["bm25_recheck_count"] = bm25_recheck_count
    if bm25_fallback is not None:
        payload["bm25_fallback"] = bm25_fallback
    if latency_ms is not None:
        payload["latency_ms"] = latency_ms
    if input_tokens is not None:
        payload["input_tokens"] = input_tokens
    if output_tokens is not None:
        payload["output_tokens"] = output_tokens
    if cache_hit is not None:
        payload["cache_hit"] = cache_hit
    if cost_usd is not None:
        payload["cost_usd"] = cost_usd
    return payload
