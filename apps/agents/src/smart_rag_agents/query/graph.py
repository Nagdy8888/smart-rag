"""Query LangGraph: admission through optional tools, answer, and verifier.

This module compiles without sockets or OpenAI clients.
"""

from __future__ import annotations

from typing import cast

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph

# isort: off
# hybrid_run must finish before query_admission package init (ceilings cycle).
import smart_rag_core.retrieval.hybrid_run as _hybrid_run_cycle_guard  # noqa: F401  # pyright: ignore[reportUnusedImport]
from smart_rag_core.query_admission.context import AuthorizedRuntimeContext
# isort: on

from smart_rag_agents.query.deps import QueryGraphDeps
from smart_rag_agents.query.nodes import (
    apply_correction_node,
    compile_plan_node,
    compose_tables_node,
    disclose_optional_tools_node,
    execute_branches_node,
    fuse_evidence_node,
    generate_answer_node,
    load_memory_node,
    prepare_query_node,
    verify_answer_node,
)
from smart_rag_agents.query.state import (
    CompiledQueryGraph,
    QueryGraphState,
    QueryStateGraph,
    pending_query_state,
)

__all__ = [
    "CompiledQueryGraph",
    "QueryGraphState",
    "QueryStateGraph",
    "build_query_graph",
    "compile_query_graph",
    "enforce_admission",
    "graph",
    "pending_query_state",
]


def enforce_admission(state: QueryGraphState) -> QueryGraphState:
    """Require ``AuthorizedRuntimeContext`` and copy server ceilings into state.

    State inputs:
        ``authorized_runtime`` mapping produced by FastAPI/core, or null.

    State outputs:
        ``status=admitted`` with ceiling counters copied from context, or
        ``status=admission_rejected`` with no retrieval/answer claim.

    Persistence writes:
        None. Durable admit already happened in FastAPI/core.

    External/model calls:
        None.

    Budget/deadline behavior:
        Copies server-assigned deadline and remaining ceilings. Does not
        enlarge them. Client role, BM25, graph, cache, and Valkey fields in
        extra mapping keys are ignored by Pydantic ``extra=forbid``.

    Failure/fallback route:
        Missing or invalid context sets ``admission_rejected`` and later
        nodes pass through to END. This node never claims an answer.

    Args:
        state: Incoming query graph state.

    Returns:
        State with admission status and copied ceilings.
    """

    rejected: QueryGraphState = {
        **state,
        "status": "admission_rejected",
        "detail": "authorized runtime context missing or invalid",
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
    }
    raw = state.get("authorized_runtime")
    try:
        context = AuthorizedRuntimeContext.from_mapping(raw)
    except (ValueError, TypeError):
        return rejected

    dumped = cast(dict[str, object], context.model_dump(mode="json"))
    deadline = context.deadline_at.isoformat()
    return {
        **state,
        "status": "admitted",
        "detail": "admission accepted",
        "authorized_runtime": dumped,
        "route_family": context.route_family.value,
        "requested_route": context.route_family.value,
        "deadline_at": deadline,
        "recursion_limit": context.recursion_limit,
        "remaining_corrections": context.correction_ceiling,
        "remaining_subquestions": context.subquestion_ceiling,
        "remaining_model_calls": context.model_call_ceiling,
        "remaining_tool_calls": context.tool_ceiling,
        "remaining_discovery_rounds": context.discovery_ceiling,
        "remaining_manifests": context.manifest_ceiling,
        "remaining_side_effects": context.side_effect_ceiling,
        "remaining_recursion_steps": context.recursion_limit,
    }


def _route_after_studio_seed(state: QueryGraphState) -> str:
    """Continue to admission only when Studio seeding produced a context.

    Args:
        state: State after ``seed_studio_runtime``.

    Returns:
        ``enforce_admission`` or ``end``.
    """

    if state["status"] == "admission_rejected":
        return "end"
    return "enforce_admission"


def _route_after_admission(state: QueryGraphState) -> str:
    """Continue past admission only when context was valid.

    Args:
        state: State after ``enforce_admission``.

    Returns:
        ``load_memory`` or ``end``.
    """

    if state["status"] == "admission_rejected":
        return "end"
    return "load_memory"


def _route_after_prepare(state: QueryGraphState) -> str:
    """Stop on routing rejection after preparation.

    Args:
        state: State after ``prepare_query``.

    Returns:
        ``compile_plan`` or ``end``.
    """

    if state["status"] in {"admission_rejected", "routing_rejected"}:
        return "end"
    return "compile_plan"


def _route_after_correction(state: QueryGraphState) -> str:
    """Continue to fusion unless admission, routing, or evidence already failed.

    Args:
        state: State after ``apply_correction``.

    Returns:
        ``fuse_evidence`` or ``end``. Exhausted retrieval
        (``insufficient_evidence``) ends without fusion, answer, or verifier.
    """

    if state["status"] in {
        "admission_rejected",
        "routing_rejected",
        "insufficient_evidence",
    }:
        return "end"
    return "fuse_evidence"


def build_query_graph(
    deps: QueryGraphDeps | None = None,
    *,
    studio_local: bool = False,
) -> QueryStateGraph:
    """Construct the packet 2 query ``StateGraph`` (not yet compiled).

    Args:
        deps: Optional retrieve/memory bindings. Default compiles without
            sockets or OpenAI clients.
        studio_local: When true, prepend ``seed_studio_runtime`` and accept
            ``StudioQueryInput``. FastAPI must not set this. The seed does
            not admit a paid run or open Postgres.

    Returns:
        An uncompiled graph: admission → memory → prepare → plan →
        branches → one correction → fuse → tables → optional tools →
        answer → verify → END. Studio adds a local seed before admission.

    Notes:
        State inputs: ``QueryGraphState``, or ``StudioQueryInput`` when
            ``studio_local``.
        State outputs: fused evidence, one answer, and layered verification.
        Persistence writes: counted prep/answer/verifier consume when used.
        External/model calls: at most one prep, one answer, one verifier.
        Budget/deadline behavior: copies server ceilings; never enlarges.
        Failure/fallback route: ``admission_rejected`` / ``routing_rejected``
            / ``insufficient_evidence`` / ``verified_partial`` then END.
    """

    bound = deps or QueryGraphDeps()
    input_schema: type[QueryGraphState] | type[object] = QueryGraphState
    state_schema: type[QueryGraphState] | type[object] = QueryGraphState
    output_schema: type[QueryGraphState] | type[object] = QueryGraphState
    if studio_local:
        from smart_rag_agents.query.studio import StudioQueryInput, StudioQueryState

        input_schema = StudioQueryInput
        state_schema = StudioQueryState
        output_schema = StudioQueryState
    builder: QueryStateGraph = StateGraph(  # pyright: ignore[reportAssignmentType]
        state_schema,
        input_schema=input_schema,  # pyright: ignore[reportArgumentType]
        output_schema=output_schema,  # pyright: ignore[reportArgumentType]
    )

    def load_memory(state: QueryGraphState) -> QueryGraphState:
        """LangGraph wrapper for bounded memory load.

        Args:
            state: Admitted state.

        Returns:
            State with memory records.
        """

        return load_memory_node(state, bound)

    def prepare_query(state: QueryGraphState) -> QueryGraphState:
        """LangGraph wrapper for typed preparation.

        Args:
            state: State after memory load.

        Returns:
            State with preparation.
        """

        return prepare_query_node(state, bound)

    def compile_plan(state: QueryGraphState) -> QueryGraphState:
        """LangGraph wrapper for the route matrix.

        Args:
            state: Prepared state.

        Returns:
            State with a retrieval plan.
        """

        return compile_plan_node(state)

    def execute_branches(state: QueryGraphState) -> QueryGraphState:
        """LangGraph wrapper for bounded retrieve branches.

        Args:
            state: Planned state.

        Returns:
            State with branch results.
        """

        return execute_branches_node(state, bound)

    def apply_correction(state: QueryGraphState) -> QueryGraphState:
        """LangGraph wrapper for the single global correction.

        Args:
            state: State after branches.

        Returns:
            State after the single correction.
        """

        return apply_correction_node(state, bound)

    def fuse_evidence(state: QueryGraphState) -> QueryGraphState:
        """LangGraph wrapper for Combined fusion.

        Args:
            state: State after correction.

        Returns:
            State with fused canonical evidence.
        """

        return fuse_evidence_node(state, bound)

    def compose_tables(state: QueryGraphState) -> QueryGraphState:
        """LangGraph wrapper for deterministic table composition.

        Args:
            state: State after fusion.

        Returns:
            State with table provenance.
        """

        return compose_tables_node(state, bound)

    def generate_answer(state: QueryGraphState) -> QueryGraphState:
        """LangGraph wrapper for one canonical answer generation.

        Args:
            state: State after optional tools.

        Returns:
            State with one answer payload.
        """

        return generate_answer_node(state, bound)

    def disclose_optional_tools(state: QueryGraphState) -> QueryGraphState:
        """LangGraph wrapper for optional-tool disclosure and execution.

        Args:
            state: State after table composition.

        Returns:
            State with optional-tool telemetry and maybe one execution.
        """

        return disclose_optional_tools_node(state, bound)

    def verify_answer(state: QueryGraphState) -> QueryGraphState:
        """LangGraph wrapper for layered verification.

        Args:
            state: State after answer generation.

        Returns:
            Terminal verified state.
        """

        return verify_answer_node(state, bound)

    builder.add_node(  # pyright: ignore[reportUnknownMemberType]
        "enforce_admission",
        enforce_admission,
    )
    terminal_target = END
    if studio_local:
        from smart_rag_agents.query.studio import (
            emit_studio_response,
            seed_studio_runtime,
        )

        builder.add_node(  # pyright: ignore[reportUnknownMemberType]
            "seed_studio_runtime",
            seed_studio_runtime,
        )
        builder.add_node(  # pyright: ignore[reportUnknownMemberType]
            "emit_studio_response",
            emit_studio_response,
        )
        terminal_target = "emit_studio_response"
        builder.add_edge(START, "seed_studio_runtime")
        builder.add_conditional_edges(
            "seed_studio_runtime",
            _route_after_studio_seed,
            {"enforce_admission": "enforce_admission", "end": terminal_target},
        )
    else:
        builder.add_edge(START, "enforce_admission")
    builder.add_node(  # pyright: ignore[reportUnknownMemberType]
        "load_memory",
        load_memory,
    )
    builder.add_node(  # pyright: ignore[reportUnknownMemberType]
        "prepare_query",
        prepare_query,
    )
    builder.add_node(  # pyright: ignore[reportUnknownMemberType]
        "compile_plan",
        compile_plan,
    )
    builder.add_node(  # pyright: ignore[reportUnknownMemberType]
        "execute_branches",
        execute_branches,
    )
    builder.add_node(  # pyright: ignore[reportUnknownMemberType]
        "apply_correction",
        apply_correction,
    )
    builder.add_node(  # pyright: ignore[reportUnknownMemberType]
        "fuse_evidence",
        fuse_evidence,
    )
    builder.add_node(  # pyright: ignore[reportUnknownMemberType]
        "compose_tables",
        compose_tables,
    )
    builder.add_node(  # pyright: ignore[reportUnknownMemberType]
        "disclose_optional_tools",
        disclose_optional_tools,
    )
    builder.add_node(  # pyright: ignore[reportUnknownMemberType]
        "generate_answer",
        generate_answer,
    )
    builder.add_node(  # pyright: ignore[reportUnknownMemberType]
        "verify_answer",
        verify_answer,
    )
    builder.add_conditional_edges(
        "enforce_admission",
        _route_after_admission,
        {"load_memory": "load_memory", "end": terminal_target},
    )
    builder.add_edge("load_memory", "prepare_query")
    builder.add_conditional_edges(
        "prepare_query",
        _route_after_prepare,
        {"compile_plan": "compile_plan", "end": terminal_target},
    )
    builder.add_edge("compile_plan", "execute_branches")
    builder.add_edge("execute_branches", "apply_correction")
    builder.add_conditional_edges(
        "apply_correction",
        _route_after_correction,
        {"fuse_evidence": "fuse_evidence", "end": terminal_target},
    )
    builder.add_edge("fuse_evidence", "compose_tables")
    builder.add_edge("compose_tables", "disclose_optional_tools")
    builder.add_edge("disclose_optional_tools", "generate_answer")
    builder.add_edge("generate_answer", "verify_answer")
    builder.add_edge("verify_answer", terminal_target)
    if studio_local:
        builder.add_edge("emit_studio_response", END)
    return builder


def compile_query_graph(
    deps: QueryGraphDeps | None = None,
    *,
    checkpointer: BaseCheckpointSaver[str] | None = None,
) -> CompiledQueryGraph:
    """Compile the query graph for runtime, optionally with a checkpointer.

    Args:
        deps: Optional retrieve/memory/store bindings.
        checkpointer: Optional Postgres (or test) checkpointer. ``thread_id``
            must be ``str(conversation_id)``. Module-level ``graph`` stays
            checkpointer-free for Studio.

    Returns:
        Compiled graph. Runtime never calls ``PostgresSaver.setup()``.
    """

    builder = build_query_graph(deps)
    return builder.compile(  # pyright: ignore[reportUnknownMemberType]
        checkpointer=checkpointer
    )


graph: CompiledQueryGraph = build_query_graph().compile()  # pyright: ignore[reportUnknownMemberType]
"""Compiled query graph for ``langgraph.json`` registration. Checkpointer-free."""
