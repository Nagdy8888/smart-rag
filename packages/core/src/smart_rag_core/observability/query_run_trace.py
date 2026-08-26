"""Compatibility facade for query-run LangSmith tracing."""

from smart_rag_core.observability.langsmith_tracing import (
    traceable,
    tracing_is_enabled,
)
from smart_rag_core.observability.query_trace.agent_eval import (
    emit_online_eval_root,
    invoke_traced_query_agent_eval,
)
from smart_rag_core.observability.query_trace.metadata import (
    QUERY_AGENT_EVAL_RUN,
    QUERY_RUN_SSE_SPAN,
    assert_query_agent_eval_langsmith_gate,
    query_run_trace_metadata,
)
from smart_rag_core.observability.query_trace.redaction import (
    hashed_conversation_id,
    hashed_user_id,
    redact_query_agent_eval_inputs,
    redact_query_agent_eval_outputs,
    redact_query_run_sse_inputs,
    redact_query_run_sse_outputs,
)
from smart_rag_core.observability.query_trace.sse import invoke_traced_query_run_sse

__all__ = [
    "QUERY_AGENT_EVAL_RUN",
    "QUERY_RUN_SSE_SPAN",
    "assert_query_agent_eval_langsmith_gate",
    "emit_online_eval_root",
    "hashed_conversation_id",
    "hashed_user_id",
    "invoke_traced_query_agent_eval",
    "invoke_traced_query_run_sse",
    "query_run_trace_metadata",
    "redact_query_agent_eval_inputs",
    "redact_query_agent_eval_outputs",
    "redact_query_run_sse_inputs",
    "redact_query_run_sse_outputs",
    "traceable",
    "tracing_is_enabled",
]
