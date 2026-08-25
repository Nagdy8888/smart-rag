"""Query-run LangSmith metadata: hashes and counts only."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping, Sequence
from contextlib import AbstractContextManager, nullcontext
from typing import Any, TypeVar, cast
from uuid import UUID

import langsmith

from smart_rag_core.observability.governance_gate import (
    assert_langsmith_export_permitted,
)
from smart_rag_core.observability.langsmith_tracing import (
    flush_langsmith_traces,
    short_content_hash,
    traceable,
    tracing_is_enabled,
)
from smart_rag_core.observability.logging import (
    correlation_context,
    current_correlation_ids,
)
from smart_rag_core.security.external_processing import ContentClass
from smart_rag_core.settings import SharedSettings

T = TypeVar("T")

QUERY_AGENT_EVAL_RUN = "query.agent.eval"
QUERY_RUN_SSE_SPAN = "query.run.sse"
_PARENT_INPUT_KEYS = frozenset(
    {
        "case_id",
        "run_id",
        "user_id_sha256",
        "conversation_id_sha256",
        "requested_route",
        "effective_route",
        "corrected_route",
        "graph_name",
    }
)


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


def hashed_conversation_id(conversation_id: UUID | str) -> str:
    """Return a truncated SHA-256 of a conversation id.

    Args:
        conversation_id: Conversation UUID.

    Returns:
        First 16 hex characters of SHA-256.
    """

    return short_content_hash(str(conversation_id))


def redact_query_agent_eval_inputs(inputs: Mapping[str, Any]) -> dict[str, Any]:
    """Keep case/run hashes and routes; drop query, answer, and secrets.

    Args:
        inputs: Traceable kwargs.

    Returns:
        Exportable parent inputs plus correlation ids.
    """

    payload: dict[str, Any] = {"correlation": current_correlation_ids()}
    for key in _PARENT_INPUT_KEYS:
        value = inputs.get(key)
        if isinstance(value, str) and value:
            payload[key] = value
    return payload


def redact_query_agent_eval_outputs(outputs: object) -> dict[str, Any]:
    """Export status, counts, and routes only. Never copy answer text.

    Args:
        outputs: Traceable return wrapper or the raw thunk result.

    Returns:
        Completed flag, route, citation count, latency, and cost when present.
    """

    raw: object = outputs
    if isinstance(outputs, Mapping):
        mapped = dict(cast(Mapping[str, object], outputs))
        raw = mapped.get("output", mapped)
    if not isinstance(raw, Mapping):
        return {"completed": True}
    payload: dict[str, Any] = {}
    typed = cast(Mapping[str, object], raw)
    completed = typed.get("completed")
    if isinstance(completed, bool):
        payload["completed"] = completed
    failure_kind = typed.get("failure_kind")
    if isinstance(failure_kind, str) and failure_kind:
        payload["failure_kind"] = failure_kind[:64]
    for key in ("effective_route", "answer_status"):
        value = typed.get(key)
        if isinstance(value, str) and value:
            payload[key] = value[:64]
    cited = typed.get("cited_chunk_ids")
    tables = typed.get("cited_table_ids")
    cited_count = 0
    if isinstance(cited, (list, tuple)):
        cited_count += len(cast(Sequence[object], cited))
    if isinstance(tables, (list, tuple)):
        cited_count += len(cast(Sequence[object], tables))
    payload["citation_count"] = cited_count
    latency = typed.get("latency_ms")
    if isinstance(latency, int):
        payload["latency_ms"] = latency
    cost = typed.get("agent_cost_usd")
    if isinstance(cost, str):
        payload["cost_usd"] = cost
    return payload or {"completed": True}


def _optional_trace_str(value: object) -> str | None:
    """Return a string metadata value or None.

    Args:
        value: Extra parent-span field.

    Returns:
        String when ``value`` is a non-empty str; otherwise None.
    """

    if isinstance(value, str) and value:
        return value
    return None


def _query_eval_tracing_scope(
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


def invoke_traced_query_agent_eval(
    thunk: Callable[[], T],
    *,
    settings: SharedSettings,
    case_id: str,
    run_id: UUID | str | None = None,
    user_id: UUID | str | None = None,
    conversation_id: UUID | str | None = None,
    requested_route: str | None = None,
    effective_route: str | None = None,
    corrected_route: str | None = None,
) -> T:
    """Wrap one admitted graph invoke in a redacted ``query.agent.eval`` parent.

    Args:
        thunk: Production graph ``invoke``. Must not log source text.
        settings: Process settings used for the export gate.
        case_id: Synthetic development case identifier.
        run_id: Application run id when admission succeeded.
        user_id: Subject hashed before export.
        conversation_id: Conversation id hashed before export.
        requested_route: Envelope family reserved at admit.
        effective_route: Planner-selected family.
        corrected_route: Family after the one correction, if any.

    Returns:
        The thunk result.

    Raises:
        ExternalFlowBlockedError: When export is not permitted.

    Side Effects:
        Sets correlation context. Creates a LangSmith chain run when tracing
        is enabled. Child gateway spans nest under this parent.
    """

    assert_query_agent_eval_langsmith_gate(settings)
    extra: dict[str, Any] = {
        "correlation": current_correlation_ids(),
        "case_id": case_id,
        "graph_name": QUERY_AGENT_EVAL_RUN,
    }
    if run_id is not None:
        extra["run_id"] = str(run_id)
    if user_id is not None:
        extra["user_id_sha256"] = hashed_user_id(user_id)
    if conversation_id is not None:
        extra["conversation_id_sha256"] = hashed_conversation_id(conversation_id)
    if requested_route:
        extra["requested_route"] = requested_route
    if effective_route:
        extra["effective_route"] = effective_route
    if corrected_route:
        extra["corrected_route"] = corrected_route
    with correlation_context(run_id=str(run_id) if run_id is not None else None):
        tracing_on = bool(settings.langsmith_tracing or tracing_is_enabled())
        if not tracing_on:
            return thunk()

        @traceable(
            name=QUERY_AGENT_EVAL_RUN,
            run_type="chain",
            process_inputs=redact_query_agent_eval_inputs,
            process_outputs=redact_query_agent_eval_outputs,
            metadata=extra,
        )
        def _parent(
            case_id: str,
            graph_name: str,
            run_id: str | None = None,
            user_id_sha256: str | None = None,
            conversation_id_sha256: str | None = None,
            requested_route: str | None = None,
            effective_route: str | None = None,
            corrected_route: str | None = None,
        ) -> T:
            """Redacted query-agent eval parent. Arguments are ids and hashes.

            Args:
                case_id: Synthetic case identifier.
                graph_name: Parent run name.
                run_id: Application run id.
                user_id_sha256: Hashed user id.
                conversation_id_sha256: Hashed conversation id.
                requested_route: Admit family.
                effective_route: Planner family.
                corrected_route: Post-correction family.

            Returns:
                Thunk result.
            """

            del (
                case_id,
                graph_name,
                run_id,
                user_id_sha256,
                conversation_id_sha256,
                requested_route,
                effective_route,
                corrected_route,
            )
            return thunk()

        with _query_eval_tracing_scope(enabled=True):
            return _parent(
                case_id=case_id,
                graph_name=QUERY_AGENT_EVAL_RUN,
                run_id=_optional_trace_str(extra.get("run_id")),
                user_id_sha256=_optional_trace_str(extra.get("user_id_sha256")),
                conversation_id_sha256=_optional_trace_str(
                    extra.get("conversation_id_sha256")
                ),
                requested_route=_optional_trace_str(extra.get("requested_route")),
                effective_route=_optional_trace_str(extra.get("effective_route")),
                corrected_route=_optional_trace_str(extra.get("corrected_route")),
            )


_SSE_PARENT_INPUT_KEYS = frozenset(
    {
        "run_id",
        "user_id_sha256",
        "requested_route",
        "effective_route",
        "model_versions",
        "prompt_versions",
    }
)
_SSE_PARENT_OUTPUT_KEYS = frozenset(
    {
        "termination_reason",
        "terminal_event_type",
        "stream_exhausted",
    }
)


def redact_query_run_sse_inputs(inputs: Mapping[str, Any]) -> dict[str, Any]:
    """Export correlation IDs, hashed user, route, and versions only.

    Args:
        inputs: Traceable kwargs. Must not contain query text or JWTs.

    Returns:
        Redacted parent inputs.
    """

    payload: dict[str, Any] = {"correlation": current_correlation_ids()}
    for key in _SSE_PARENT_INPUT_KEYS:
        value = inputs.get(key)
        if isinstance(value, str) and value:
            payload[key] = value[:64]
        elif isinstance(value, Mapping):
            mapped = cast(Mapping[object, object], value)
            payload[key] = {
                str(item_key)[:64]: str(item_value)[:64]
                for item_key, item_value in mapped.items()
            }
    return payload


def redact_query_run_sse_outputs(outputs: object) -> dict[str, Any]:
    """Export the sanitized termination summary only.

    Args:
        outputs: Traceable return wrapper or the raw summary mapping.

    Returns:
        Termination reason, terminal type, and exhausted bool. Never query
        text, messages, sources, JWTs, or citations.
    """

    raw: object = outputs
    if isinstance(outputs, Mapping):
        mapped = dict(cast(Mapping[str, object], outputs))
        raw = mapped.get("output", mapped)
    if not isinstance(raw, Mapping):
        return {"termination_reason": "unknown"}
    payload: dict[str, Any] = {}
    typed = cast(Mapping[str, object], raw)
    for key in _SSE_PARENT_OUTPUT_KEYS:
        value = typed.get(key)
        if key == "stream_exhausted" and isinstance(value, bool):
            payload[key] = value
        elif isinstance(value, str) and value:
            payload[key] = value[:64]
    return payload or {"termination_reason": "unknown"}


async def invoke_traced_query_run_sse(
    thunk: Callable[[], Awaitable[Mapping[str, object]]],
    *,
    settings: SharedSettings,
    run_id: UUID | str,
    user_id: UUID | str,
    requested_route: str | None = None,
    effective_route: str | None = None,
    model_versions: Mapping[str, str] | None = None,
    prompt_versions: Mapping[str, str] | None = None,
) -> Mapping[str, object]:
    """Wrap complete SSE executor consumption in a redacted parent span.

    Args:
        thunk: Async consumer that drains the executor and returns the
            sanitized termination summary.
        settings: Process settings used for the export gate.
        run_id: Application run id.
        user_id: Subject hashed before export.
        requested_route: Envelope family reserved at admit.
        effective_route: Planner-selected family.
        model_versions: Model ids keyed by usage kind.
        prompt_versions: Prompt version ids keyed by usage kind.

    Returns:
        The thunk result.

    Raises:
        ExternalFlowBlockedError: When export is not permitted.

    Side Effects:
        Creates a LangSmith chain run named ``query.run.sse`` when tracing
        is enabled. Does not suppress ``GeneratorExit``.
    """

    assert_query_agent_eval_langsmith_gate(settings)
    extra: dict[str, Any] = {
        "correlation": current_correlation_ids(),
        "run_id": str(run_id),
        "user_id_sha256": hashed_user_id(user_id),
        "graph_name": QUERY_RUN_SSE_SPAN,
    }
    if requested_route:
        extra["requested_route"] = requested_route
    if effective_route:
        extra["effective_route"] = effective_route
    if model_versions:
        extra["model_versions"] = dict(model_versions)
    if prompt_versions:
        extra["prompt_versions"] = dict(prompt_versions)
    tracing_on = bool(settings.langsmith_tracing or tracing_is_enabled())
    if not tracing_on:
        return await thunk()

    @traceable(
        name=QUERY_RUN_SSE_SPAN,
        run_type="chain",
        process_inputs=redact_query_run_sse_inputs,
        process_outputs=redact_query_run_sse_outputs,
        metadata=extra,
        project_name=settings.langsmith_project,
    )
    async def _parent(
        run_id: str,
        user_id_sha256: str,
        requested_route: str | None = None,
        effective_route: str | None = None,
        model_versions: Mapping[str, str] | None = None,
        prompt_versions: Mapping[str, str] | None = None,
    ) -> Mapping[str, object]:
        """Redacted SSE parent. Arguments are ids, hashes, and versions.

        Args:
            run_id: Application run id.
            user_id_sha256: Hashed user id.
            requested_route: Admit family.
            effective_route: Planner family.
            model_versions: Model ids by usage kind.
            prompt_versions: Prompt versions by usage kind.

        Returns:
            Sanitized termination summary from the thunk.
        """

        del (
            run_id,
            user_id_sha256,
            requested_route,
            effective_route,
            model_versions,
            prompt_versions,
        )
        return await thunk()

    try:
        with _query_eval_tracing_scope(
            enabled=True, project_name=settings.langsmith_project
        ):
            return await _parent(
                run_id=str(extra["run_id"]),
                user_id_sha256=str(extra["user_id_sha256"]),
                requested_route=_optional_trace_str(extra.get("requested_route")),
                effective_route=_optional_trace_str(extra.get("effective_route")),
                model_versions=model_versions,
                prompt_versions=prompt_versions,
            )
    finally:
        flush_langsmith_traces()
