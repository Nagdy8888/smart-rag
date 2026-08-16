"""Typed query graph state for Phase 6 packets 1-4."""

from __future__ import annotations

from typing import Literal, TypeAlias, TypedDict

from langgraph.graph import StateGraph
from langgraph.graph.state import CompiledStateGraph


class QueryGraphState(TypedDict):
    """Typed query state through admission, preparation, routing, and retrieve.

    Attributes:
        status: Pipeline status. Never an answer claim.
        detail: Safe diagnostic text.
        authorized_runtime: Server-derived context mapping, or null.
        route_family: Envelope family copied from context when admitted.
        deadline_at: ISO-8601 deadline copied from context.
        recursion_limit: Superstep cap copied from context.
        remaining_corrections: Remaining correction slots.
        remaining_subquestions: Remaining subquestion slots.
        remaining_model_calls: Remaining counted gateway calls.
        remaining_tool_calls: Remaining tool executions.
        remaining_discovery_rounds: Remaining optional discovery rounds.
        remaining_manifests: Remaining optional manifests.
        remaining_side_effects: Remaining side-effecting tools.
        remaining_recursion_steps: Remaining LangGraph supersteps.
        user_query: Original user text. Untrusted.
        routing_surface: ``production`` or ``diagnostic``.
        requested_manual_route: Diagnostic-only client route.
        memory_records: Untrusted delimited message mappings.
        preparation: ``QueryPreparation`` mapping.
        retrieval_plan: ``RetrievalPlan`` mapping.
        branch_results: ``BranchResult`` mappings.
        correction: ``CorrectionDecision`` mapping.
        requested_route: Envelope family reserved at admit.
        effective_route: Planner-selected family.
        corrected_route: Family after the one correction.
        keyword_extract_count: Must stay 0.
        catalog_llm_call_count: Must stay 0 on the core path.
        correction_applied: Guard against a second correction.
        fusion: ``FusionResult`` mapping.
        table_composition: ``TableComposition`` mapping.
        optional_selection_mode: skipped, deterministic_mapping, or catalog_discovery.
        optional_prompt_capture: Selected disclosure only.
        optional_bound_tool_names: Names bound for the next model call.
        optional_selected_keys: Loaded optional tool keys.
        optional_result: Executor payload mapping.
        optional_telemetry: Visible-set counters only.
        answer: ``AnswerPayload`` mapping.
        verification: ``VerificationResult`` mapping.
        answer_call_count: Must be 0 or 1.
        verifier_call_count: Must be 0 or 1.
        selected_algorithm: Fusion or naive union.
        fusion_config_hash: Frozen configuration digest.
    """

    status: Literal[
        "pending",
        "admitted",
        "admission_rejected",
        "memory_loaded",
        "prepared",
        "planned",
        "branches_executed",
        "correction_applied",
        "fused",
        "tables_composed",
        "optional_tools_resolved",
        "answered",
        "verified",
        "verified_partial",
        "refused",
        "routing_rejected",
        "insufficient_evidence",
    ]
    detail: str
    authorized_runtime: dict[str, object] | None
    route_family: str | None
    deadline_at: str | None
    recursion_limit: int
    remaining_corrections: int
    remaining_subquestions: int
    remaining_model_calls: int
    remaining_tool_calls: int
    remaining_discovery_rounds: int
    remaining_manifests: int
    remaining_side_effects: int
    remaining_recursion_steps: int
    user_query: str
    routing_surface: str
    requested_manual_route: str | None
    memory_records: list[dict[str, object]]
    preparation: dict[str, object] | None
    retrieval_plan: dict[str, object] | None
    branch_results: list[dict[str, object]]
    correction: dict[str, object] | None
    requested_route: str | None
    effective_route: str | None
    corrected_route: str | None
    keyword_extract_count: int
    catalog_llm_call_count: int
    correction_applied: bool
    fusion: dict[str, object] | None
    table_composition: dict[str, object] | None
    optional_selection_mode: str | None
    optional_prompt_capture: str
    optional_bound_tool_names: list[str]
    optional_selected_keys: list[str]
    optional_result: dict[str, object] | None
    optional_telemetry: dict[str, object] | None
    answer: dict[str, object] | None
    verification: dict[str, object] | None
    answer_call_count: int
    verifier_call_count: int
    selected_algorithm: str | None
    fusion_config_hash: str | None


QueryStateGraph: TypeAlias = StateGraph[
    QueryGraphState,
    None,
    QueryGraphState,
    QueryGraphState,
]
CompiledQueryGraph: TypeAlias = CompiledStateGraph[
    QueryGraphState,
    None,
    QueryGraphState,
    QueryGraphState,
]


def pending_query_state(
    authorized_runtime: dict[str, object] | None = None,
    *,
    user_query: str = "",
    routing_surface: str = "production",
    requested_manual_route: str | None = None,
) -> QueryGraphState:
    """Return a pending graph input that does not claim retrieval success.

    Args:
        authorized_runtime: Optional server-derived context mapping.
        user_query: Original user text.
        routing_surface: ``production`` or ``diagnostic``.
        requested_manual_route: Diagnostic-only route string.

    Returns:
        Minimal pending state for compile/invoke tests.
    """

    return {
        "status": "pending",
        "detail": "",
        "authorized_runtime": authorized_runtime,
        "route_family": None,
        "deadline_at": None,
        "recursion_limit": 0,
        "remaining_corrections": 0,
        "remaining_subquestions": 0,
        "remaining_model_calls": 0,
        "remaining_tool_calls": 0,
        "remaining_discovery_rounds": 0,
        "remaining_manifests": 0,
        "remaining_side_effects": 0,
        "remaining_recursion_steps": 0,
        "user_query": user_query,
        "routing_surface": routing_surface,
        "requested_manual_route": requested_manual_route,
        "memory_records": [],
        "preparation": None,
        "retrieval_plan": None,
        "branch_results": [],
        "correction": None,
        "requested_route": None,
        "effective_route": None,
        "corrected_route": None,
        "keyword_extract_count": 0,
        "catalog_llm_call_count": 0,
        "correction_applied": False,
        "fusion": None,
        "table_composition": None,
        "optional_selection_mode": None,
        "optional_prompt_capture": "",
        "optional_bound_tool_names": [],
        "optional_selected_keys": [],
        "optional_result": None,
        "optional_telemetry": None,
        "answer": None,
        "verification": None,
        "answer_call_count": 0,
        "verifier_call_count": 0,
        "selected_algorithm": None,
        "fusion_config_hash": None,
    }
