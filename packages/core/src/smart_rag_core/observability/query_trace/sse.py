"""SSE query-run LangSmith parent-span lifecycle."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from typing import Any
from uuid import UUID

from smart_rag_core.observability.langsmith_tracing import (
    estimate_traced_chat_cost_usd,
    record_current_usage_metadata,
    traceable,
    tracing_is_enabled,
)
from smart_rag_core.observability.logging import (
    current_correlation_ids,
)
from smart_rag_core.observability.query_trace.metadata import (
    QUERY_RUN_SSE_SPAN,
    assert_query_agent_eval_langsmith_gate,
    normalize_query_run_result,
    optional_trace_str,
    query_eval_tracing_scope,
)
from smart_rag_core.observability.query_trace.redaction import (
    hashed_user_id,
    optional_cost_usd,
    redact_query_run_sse_inputs,
    redact_query_run_sse_outputs,
    usage_token_counts,
)
from smart_rag_core.query_answer.versions import ANSWER_MODEL_ID
from smart_rag_core.settings import SharedSettings


def _record_query_run_usage(result: Mapping[str, object]) -> None:
    """Attach token and USD metadata from a query-run termination summary.

    Args:
        result: Thunk return mapping. Missing token fields are ignored.

    Side Effects:
        Updates the active LangSmith run when tracing is on and the summary
        reports token counts.
    """

    counts = usage_token_counts(result)
    if counts is None:
        return
    input_count, output_count = counts
    cost = optional_cost_usd(result.get("estimated_cost_usd"))
    if cost is None:
        cost = estimate_traced_chat_cost_usd(
            input_tokens=input_count,
            output_tokens=output_count,
        )
    record_current_usage_metadata(
        provider="openai",
        model=ANSWER_MODEL_ID,
        input_tokens=input_count,
        output_tokens=output_count,
        total_cost_usd=cost,
    )


async def invoke_traced_query_run_sse(
    thunk: Callable[[], Awaitable[Mapping[str, object]]],
    *,
    settings: SharedSettings,
    run_id: UUID | str,
    user_id: UUID | str,
    user_message: str | None = None,
    requested_route: str | None = None,
    effective_route: str | None = None,
    model_versions: Mapping[str, str] | None = None,
    prompt_versions: Mapping[str, str] | None = None,
) -> Mapping[str, object]:
    """Wrap complete SSE executor consumption in a redacted parent span.

    Args:
        thunk: Async consumer that drains the executor and returns the
            sanitized termination summary. May include ``assistant_message``
            and token/cost fields.
        settings: Process settings used for the export gate.
        run_id: Application run id.
        user_id: Subject hashed before export.
        user_message: Untrusted user text. Hashed unless local
            ``LANGSMITH_EXPORT_IO`` is on.
        requested_route: Envelope family reserved at admit.
        effective_route: Planner-selected family.
        model_versions: Model ids keyed by usage kind.
        prompt_versions: Prompt version ids keyed by usage kind.

    Returns:
        The thunk result.

    Raises:
        ExternalFlowBlockedError: When export is not permitted.

    Side Effects:
        Creates a LangSmith LLM run named ``query.run.sse`` when tracing
        is enabled so Usage/Cost can render. Does not suppress
        ``GeneratorExit``.
    """

    assert_query_agent_eval_langsmith_gate(settings)
    extra: dict[str, Any] = {
        "correlation": current_correlation_ids(),
        "run_id": str(run_id),
        "user_id_sha256": hashed_user_id(user_id),
        "graph_name": QUERY_RUN_SSE_SPAN,
        "ls_provider": "openai",
        "ls_model_name": ANSWER_MODEL_ID,
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
        run_type="llm",
        process_inputs=redact_query_run_sse_inputs,
        process_outputs=redact_query_run_sse_outputs,
        metadata=extra,
        project_name=settings.langsmith_project,
    )
    async def _parent(
        run_id: str,
        user_id_sha256: str,
        user_message: str | None = None,
        requested_route: str | None = None,
        effective_route: str | None = None,
        model_versions: Mapping[str, str] | None = None,
        prompt_versions: Mapping[str, str] | None = None,
    ) -> Mapping[str, object]:
        """Redacted SSE parent. Arguments are ids, hashes, and chat text.

        Args:
            run_id: Application run id.
            user_id_sha256: Hashed user id.
            user_message: User text for local I/O export; hashed otherwise.
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
            user_message,
            requested_route,
            effective_route,
            model_versions,
            prompt_versions,
        )
        result = normalize_query_run_result(await thunk())
        _record_query_run_usage(result)
        return result

    with query_eval_tracing_scope(
        enabled=True, project_name=settings.langsmith_project
    ):
        return await _parent(
            run_id=str(extra["run_id"]),
            user_id_sha256=str(extra["user_id_sha256"]),
            user_message=user_message,
            requested_route=optional_trace_str(extra.get("requested_route")),
            effective_route=optional_trace_str(extra.get("effective_route")),
            model_versions=model_versions,
            prompt_versions=prompt_versions,
        )
