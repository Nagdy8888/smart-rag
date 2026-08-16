"""Optional-tool discovery/selection/execute wrappers. Core defines no nodes."""

from __future__ import annotations

from smart_rag_core.query_answer.models import TableComposition
from smart_rag_core.query_routing.models import TableEvidenceRecord
from smart_rag_core.query_routing.preparation import caller_from_runtime
from smart_rag_core.tools.exceptions import ToolError
from smart_rag_core.tools.models import SelectionPolicy
from smart_rag_core.tools.service import resolve_optional_tools

from smart_rag_agents.query.deps import QueryGraphDeps
from smart_rag_agents.query.nodes.binding import (
    bind_selected_tools_next_call,
    bound_tool_names,
    selected_tool_schemas,
)
from smart_rag_agents.query.nodes.pipeline import runtime_from_state, skip_closed_nodes
from smart_rag_agents.query.state import QueryGraphState


def _table_ids(state: QueryGraphState) -> tuple[str, ...]:
    """Collect composed StructuredTable IDs for executor recheck.

    Args:
        state: Graph state after ``compose_tables``.

    Returns:
        Authorized table UUID strings.
    """

    raw = state.get("table_composition")
    if raw is None:
        return ()
    try:
        composition = TableComposition.model_validate(raw)
    except (TypeError, ValueError):
        return ()
    records: tuple[TableEvidenceRecord, ...] = composition.records
    return tuple(item.table_id for item in records)


def disclose_optional_tools_node(
    state: QueryGraphState, deps: QueryGraphDeps
) -> QueryGraphState:
    """Disclose and maybe execute optional tools after deterministic tables.

    State inputs:
        ``user_query``, ``authorized_runtime``, ``table_composition``,
        remaining tool/discovery/manifest/side-effect/model ceilings.

    State outputs:
        ``optional_selection_mode``, prompt capture, bound tool names,
        optional result, telemetry, updated ceilings. Core retrieve/answer
        nodes are not invoked.

    Persistence writes:
        None in v1. Catalog LLM consume is not used because runtime mapping
        spends zero catalog model rounds.

    External/model calls:
        Zero on the deterministic mapping path. At most one catalog round
        when ``force_discovery`` is set for tests.

    Budget/deadline behavior:
        Shares ``remaining_tool_calls`` with packet 1. Enforces one
        discovery round, three manifests, one side-effecting tool, and
        prompt/chunk/summary budgets before prompt construction.

    Failure/fallback route:
        Missing optional intent skips with ``catalog_llm_call_count``
        unchanged (core path stays 0). Executor/auth/MCP failures set
        ``detail`` and do not bind unselected schemas.

    Args:
        state: State after ``compose_tables``.
        deps: Optional policy, chat model, and live-role override.

    Returns:
        State with optional-tool fields. Never a fake success.
    """

    if skip_closed_nodes(state):
        return state
    if state["status"] in {
        "insufficient_evidence",
        "refused",
        "verified_partial",
        "verified",
    }:
        return state
    context = runtime_from_state(state)
    if context is None:
        return {**state, "status": "admission_rejected"}
    caller = caller_from_runtime(context)
    live = caller
    if deps.live_role_override is not None:
        live = caller.model_copy(update={"role": deps.live_role_override})
    catalog_count = int(state.get("catalog_llm_call_count") or 0)
    try:
        (
            mode,
            prompt,
            selected_keys,
            result,
            telemetry,
            remaining_tools,
            remaining_discovery,
            remaining_manifests,
            remaining_side,
            remaining_models,
            llm_count,
        ) = resolve_optional_tools(
            query=str(state.get("user_query") or ""),
            caller=caller,
            remaining_tool_calls=state["remaining_tool_calls"],
            remaining_discovery_rounds=state["remaining_discovery_rounds"],
            remaining_manifests=state["remaining_manifests"],
            remaining_side_effects=state["remaining_side_effects"],
            remaining_model_calls=state["remaining_model_calls"],
            authorized_table_ids=_table_ids(state),
            retrieval_chunks=len(state.get("branch_results") or []),
            parent_expansion=0,
            conversation_summary="",
            catalog_llm_call_count=catalog_count,
            policy=deps.optional_policy,
            force_discovery=deps.force_discovery,
            current_caller=live,
            idempotency_key=str(context.run_id),
        )
    except ToolError as exc:
        return {
            **state,
            "status": "optional_tools_resolved",
            "detail": exc.reason,
            "optional_selection_mode": SelectionPolicy.SKIPPED.value,
            "optional_prompt_capture": "",
            "optional_bound_tool_names": [],
            "optional_selected_keys": [],
            "optional_result": None,
            "optional_telemetry": None,
            "catalog_llm_call_count": catalog_count,
        }
    bound_names: list[str] = list(selected_keys)
    if deps.chat_model is not None and selected_keys:
        from langchain_core.language_models.chat_models import BaseChatModel

        schemas = selected_tool_schemas(
            [
                {
                    "type": "function",
                    "function": {
                        "name": key,
                        "description": key,
                        "parameters": {"type": "object", "properties": {}},
                    },
                }
                for key in selected_keys
            ]
        )
        if isinstance(deps.chat_model, BaseChatModel):
            bound = bind_selected_tools_next_call(deps.chat_model, schemas)
            bound_names = list(bound_tool_names(bound))
            deps.last_bound_runnable = bound
            deps.unbound_model = deps.chat_model
    return {
        **state,
        "status": "optional_tools_resolved",
        "detail": (
            "optional tools skipped"
            if mode is SelectionPolicy.SKIPPED
            else "optional tools resolved"
        ),
        "optional_selection_mode": mode.value,
        "optional_prompt_capture": prompt,
        "optional_bound_tool_names": bound_names,
        "optional_selected_keys": list(selected_keys),
        "optional_result": None if result is None else result.model_dump(mode="json"),
        "optional_telemetry": telemetry.model_dump(mode="json"),
        "remaining_tool_calls": remaining_tools,
        "remaining_discovery_rounds": remaining_discovery,
        "remaining_manifests": remaining_manifests,
        "remaining_side_effects": remaining_side,
        "remaining_model_calls": remaining_models,
        "catalog_llm_call_count": llm_count,
        "keyword_extract_count": 0,
    }
