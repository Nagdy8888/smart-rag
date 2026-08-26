"""Load bounded creator-only conversation memory into query-graph state."""

from __future__ import annotations

from uuid import NAMESPACE_URL, uuid5

from smart_rag_core.memory.payload import memory_store_namespace
from smart_rag_core.query_routing.constants import FALLBACK_MEMORY_UNAVAILABLE
from smart_rag_core.query_routing.exceptions import QueryRoutingError
from smart_rag_core.query_routing.memory import load_authorized_memory
from smart_rag_core.query_routing.preparation import caller_from_runtime
from smart_rag_core.query_routing.safety import delimit_memory_record

from smart_rag_agents.query.deps import QueryGraphDeps
from smart_rag_agents.query.nodes.shared import runtime_from_state, skip_closed_nodes
from smart_rag_agents.query.state import QueryGraphState


def load_memory_node(state: QueryGraphState, deps: QueryGraphDeps) -> QueryGraphState:
    """Load bounded creator-only messages as untrusted delimited records.

    State inputs:
        ``authorized_runtime``, ``status`` after ``enforce_admission``.

    State outputs:
        ``memory_records`` (possibly empty) and ``status=memory_loaded``.

    Persistence writes:
        None. Reads ``app.load_query_memory`` and optional compact store
        summaries. Source documents are never joined.

    External/model calls:
        None.

    Budget/deadline behavior:
        No reservation consume. Deleted/foreign conversations fail closed.

    Failure/fallback route:
        Without a connection, records empty memory and
        ``memory_unavailable``. Deleted conversation sets
        ``routing_rejected``. Invalid store payloads are skipped.

    Args:
        state: Admitted query graph state.
        deps: Optional database binding.

    Returns:
        State with memory records.
    """

    if skip_closed_nodes(state):
        return state
    context = runtime_from_state(state)
    if context is None:
        return {**state, "status": "admission_rejected"}
    if deps.connection is None:
        return {
            **state,
            "status": "memory_loaded",
            "memory_records": [],
            "detail": FALLBACK_MEMORY_UNAVAILABLE,
        }
    try:
        records = load_authorized_memory(
            deps.connection,
            caller=caller_from_runtime(context),
            conversation_id=context.conversation_id,
        )
    except QueryRoutingError as exc:
        return {
            **state,
            "status": "routing_rejected",
            "detail": exc.reason,
            "memory_records": [],
        }
    dumped = [item.model_dump(mode="json") for item in records]
    if deps.store_get is not None:
        namespace = memory_store_namespace(
            company_id=None,
            user_id=str(context.user_id),
            conversation_id=str(context.conversation_id),
        )
        stored = deps.store_get(namespace, "summary")
        summary_text = stored.get("summary") if stored else None
        if isinstance(summary_text, str) and summary_text:
            summary_record = delimit_memory_record(
                message_id=str(
                    uuid5(NAMESPACE_URL, f"summary:{context.conversation_id}")
                ),
                role="system",
                content=summary_text,
                created_at="1970-01-01T00:00:00+00:00",
            )
            dumped = [summary_record.model_dump(mode="json"), *dumped]
    return {
        **state,
        "status": "memory_loaded",
        "memory_records": dumped,
        "detail": "memory loaded as untrusted delimited records",
    }
