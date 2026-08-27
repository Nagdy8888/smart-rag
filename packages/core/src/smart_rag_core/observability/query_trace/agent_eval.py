"""Agent-eval and online-eval LangSmith parent-span lifecycle."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from contextlib import AbstractContextManager
from typing import Any, cast
from uuid import UUID

import langsmith

from smart_rag_core.evaluation.online import (
    AGENT_ONLINE_EVAL_SCHEMA_VERSION,
    ONLINE_EVAL_PROJECT,
    QUERY_AGENT_ONLINE_EVAL_RUN,
)
from smart_rag_core.evaluation.online_envelope import (
    keep_online_eval_inputs,
    keep_online_eval_outputs,
)
from smart_rag_core.observability.langsmith_tracing import (
    traceable,
    tracing_is_enabled,
)
from smart_rag_core.observability.logging import (
    correlation_context,
    current_correlation_ids,
)
from smart_rag_core.observability.query_trace.metadata import (
    QUERY_AGENT_EVAL_RUN,
    T,
    assert_query_agent_eval_langsmith_gate,
    optional_trace_str,
    query_eval_tracing_scope,
)
from smart_rag_core.observability.query_trace.redaction import (
    hashed_conversation_id,
    hashed_user_id,
    redact_query_agent_eval_inputs,
    redact_query_agent_eval_outputs,
)
from smart_rag_core.settings import SharedSettings


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

        with query_eval_tracing_scope(enabled=True):
            return _parent(
                case_id=case_id,
                graph_name=QUERY_AGENT_EVAL_RUN,
                run_id=optional_trace_str(extra.get("run_id")),
                user_id_sha256=optional_trace_str(extra.get("user_id_sha256")),
                conversation_id_sha256=optional_trace_str(
                    extra.get("conversation_id_sha256")
                ),
                requested_route=optional_trace_str(extra.get("requested_route")),
                effective_route=optional_trace_str(extra.get("effective_route")),
                corrected_route=optional_trace_str(extra.get("corrected_route")),
            )


def emit_online_eval_root(
    produce_outputs: Callable[[], Mapping[str, Any]],
    *,
    settings: SharedSettings,
    inputs: Mapping[str, Any],
) -> dict[str, Any]:
    """Emit one dedicated-project root with the bounded synthetic envelope.

    This always opens a scoped ``tracing_context`` for
    ``smart-rag-agent-eval-online``. It does not change process-global
    ``LANGSMITH_PROJECT`` for unrelated traces after the block exits.

    Args:
        produce_outputs: Runs the admitted graph and returns envelope outputs.
        settings: Process settings used for the export gate.
        inputs: Validated ``OnlineEvalInputs`` mapping.

    Returns:
        Envelope outputs actually exported to LangSmith.

    Raises:
        ExternalFlowBlockedError: When export is not permitted.

    Side Effects:
        Creates one ``query.agent.eval.online.v1`` chain run on the dedicated
        project when tracing is enabled. Child spans created inside
        ``produce_outputs`` inherit that project for the duration of the
        scoped context only.
    """

    assert_query_agent_eval_langsmith_gate(settings)
    tracing_on = bool(settings.langsmith_tracing or tracing_is_enabled())
    if not tracing_on:
        produced = produce_outputs()
        return dict(produced)

    extra: dict[str, Any] = {
        "correlation": current_correlation_ids(),
        "schema_version": AGENT_ONLINE_EVAL_SCHEMA_VERSION,
        "redaction_class": "synthetic",
        "graph_name": QUERY_AGENT_ONLINE_EVAL_RUN,
        "langsmith_project": ONLINE_EVAL_PROJECT,
    }

    @traceable(
        name=QUERY_AGENT_ONLINE_EVAL_RUN,
        run_type="chain",
        project_name=ONLINE_EVAL_PROJECT,
        process_inputs=keep_online_eval_inputs,
        process_outputs=keep_online_eval_outputs,
        metadata=extra,
    )
    def _parent(inputs: dict[str, Any]) -> dict[str, Any]:
        """Dedicated online-eval parent. Arguments are the synthetic envelope.

        Args:
            inputs: Bounded synthetic inputs.

        Returns:
            Bounded synthetic outputs plus reference.
        """

        del inputs
        produced = produce_outputs()
        return dict(produced)

    factory = cast(
        Callable[..., AbstractContextManager[object]],
        langsmith.tracing_context,  # pyright: ignore[reportUnknownMemberType]
    )
    with factory(enabled=True, project_name=ONLINE_EVAL_PROJECT):
        result = _parent(dict(inputs))
    return dict(result)
