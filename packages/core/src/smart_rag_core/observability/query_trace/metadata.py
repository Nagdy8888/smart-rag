"""Query-run trace constants, gates, and normalized metadata."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from contextlib import AbstractContextManager, nullcontext
from typing import Any, TypeVar, cast
from uuid import UUID

import langsmith

from smart_rag_core.observability.governance_gate import (
    assert_langsmith_export_permitted,
)
from smart_rag_core.observability.langsmith_tracing import (
    estimate_traced_chat_cost_usd,
    langsmith_usage_metadata,
    tracing_is_enabled,
)
from smart_rag_core.observability.logging import (
    current_correlation_ids,
)
from smart_rag_core.observability.query_trace.redaction import (
    hashed_user_id,
    optional_cost_usd,
    usage_token_counts,
)
from smart_rag_core.security.external_processing import ContentClass
from smart_rag_core.settings import SharedSettings

T = TypeVar("T")

QUERY_AGENT_EVAL_RUN = "query.agent.eval"

QUERY_RUN_SSE_SPAN = "query.run.sse"


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


def optional_trace_str(value: object) -> str | None:
    """Return a string metadata value or None.

    Args:
        value: Extra parent-span field.

    Returns:
        String when ``value`` is a non-empty str; otherwise None.
    """

    if isinstance(value, str) and value:
        return value
    return None


def query_eval_tracing_scope(
    *, enabled: bool, project_name: str | None = None
) -> AbstractContextManager[object]:
    """Open ``langsmith.tracing_context`` when export is on and no scope exists.

    Args:
        enabled: Whether this process should export the eval parent run.
        project_name: LangSmith project when this function opens a new scope.

    Returns:
        An enabled tracing context when the SDK is not already tracing;
        otherwise a no-op so unit tests keep their recording client.
    """

    if not enabled or tracing_is_enabled():
        return nullcontext()
    factory = cast(
        Callable[..., AbstractContextManager[object]],
        langsmith.tracing_context,  # pyright: ignore[reportUnknownMemberType]
    )
    if project_name:
        return factory(enabled=True, project_name=project_name)
    return factory(enabled=True)


def assert_query_agent_eval_langsmith_gate(settings: SharedSettings) -> None:
    """Fail closed before opening a ``query.agent.eval`` parent run.

    Args:
        settings: Validated process settings.

    Raises:
        ExternalFlowBlockedError: When real-company export is unverified and
            the local waiver does not apply.
    """

    content_class = ContentClass.SYNTHETIC
    if not (
        settings.mock_model_mode or settings.allows_unsigned_local_live_providers()
    ):
        content_class = ContentClass.REAL_COMPANY
    assert_langsmith_export_permitted(
        tracing_enabled=settings.langsmith_tracing,
        content_class=content_class,
        provider_settings_verified=settings.subprocessor_matrix_verified,
        local_unsigned_waiver=settings.allows_unsigned_local_live_providers(),
    )


def normalize_query_run_result(result: Mapping[str, object]) -> dict[str, object]:
    """Copy token aliases onto the raw parent return for usage extraction.

    Args:
        result: Thunk termination summary.

    Returns:
        Mutable copy with ``input_tokens``, ``output_tokens``, estimated
        USD, and ``usage_metadata`` when either token count is present.
    """

    payload = dict(result)
    counts = usage_token_counts(payload)
    if counts is None:
        return payload
    input_count, output_count = counts
    payload["input_tokens"] = input_count
    payload["output_tokens"] = output_count
    cost = optional_cost_usd(payload.get("estimated_cost_usd"))
    if cost is None:
        cost = estimate_traced_chat_cost_usd(
            input_tokens=input_count,
            output_tokens=output_count,
        )
    payload["estimated_cost_usd"] = float(cost)
    payload["usage_metadata"] = langsmith_usage_metadata(
        input_tokens=input_count,
        output_tokens=output_count,
        total_cost_usd=cost,
    )
    return payload
