"""Query LangGraph topology: admission through optional tools, answer, and verifier.

This module compiles without sockets or OpenAI clients. Node callables live
in ``runtime.bound_nodes``; this file owns edges and compile only.
"""

from __future__ import annotations

from collections.abc import Callable

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph

from smart_rag_agents.query.deps import QueryGraphContext, QueryGraphDeps
from smart_rag_agents.query.nodes import enforce_admission
from smart_rag_agents.query.nodes.topology import (
    route_after_admission,
    route_after_correction,
    route_after_plan,
    route_after_prepare,
    route_after_studio_seed,
)
from smart_rag_agents.query.runtime.bound_nodes import bind_query_nodes
from smart_rag_agents.query.state import (
    CompiledQueryGraph,
    QueryGraphState,
    QueryStateGraph,
    pending_query_state,
)
from smart_rag_agents.query.streaming.progress import (
    register_production_progress_nodes,
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

_route_after_studio_seed = route_after_studio_seed
_route_after_admission = route_after_admission
_route_after_plan = route_after_plan
_route_after_prepare = route_after_prepare
_route_after_correction = route_after_correction

_PRODUCTION_STAGE_NAMES: tuple[str, ...] = (
    "enforce_admission",
    "load_memory",
    "prepare_query",
    "compile_plan",
    "company_scope",
    "general_scope",
    "mixed_scope",
    "invalid_scope",
    "apply_correction",
    "fuse_evidence",
    "compose_tables",
    "disclose_optional_tools",
    "generate_answer",
    "verify_answer",
)


def build_query_graph(
    deps: QueryGraphDeps | None = None,
    *,
    studio_local: bool = False,
    studio_live: bool = False,
    studio_live_seed: Callable[..., QueryGraphState] | None = None,
) -> QueryStateGraph:
    """Construct the packet 2 query ``StateGraph`` (not yet compiled).

    Args:
        deps: Optional retrieve/memory bindings. Default compiles without
            sockets or OpenAI clients.
        studio_local: When true, prepend ``seed_studio_runtime`` and accept
            ``StudioQueryInput``. FastAPI must not set this. The seed does
            not admit a paid run or open Postgres.
        studio_live: When true, prepend the authenticated live seed and
            accept ``StudioQueryInput``. Mutually exclusive with
            ``studio_local``. FastAPI must not set this.
        studio_live_seed: Optional live seed closure. The unbound default
            rejects and never mints ``studio_local``.

    Returns:
        An uncompiled graph: admission → memory → prepare → plan →
        one of company/general/mixed/invalid scope → verify → END.
        Company scope still runs branches, one correction, fusion,
        tables, optional tools, and grounded answer. Studio adds a seed
        before admission.

    Notes:
        State inputs: ``QueryGraphState``, or ``StudioQueryInput`` when
            ``studio_local`` or ``studio_live``.
        State outputs: fused evidence, one answer, and layered verification.
        Persistence writes: counted prep/answer/verifier consume when used.
        External/model calls: at most one prep, one answer, one verifier.
        Budget/deadline behavior: copies server ceilings; never enlarges.
        Failure/fallback route: ``admission_rejected`` / ``routing_rejected``
            / ``insufficient_evidence`` / ``verified_partial`` then END.
    """

    if studio_local and studio_live:
        raise ValueError("studio_local and studio_live are mutually exclusive")
    bound = deps or QueryGraphDeps()
    nodes = bind_query_nodes(bound)
    input_schema: type[QueryGraphState] | type[object] = QueryGraphState
    state_schema: type[QueryGraphState] | type[object] = QueryGraphState
    output_schema: type[QueryGraphState] | type[object] = QueryGraphState
    if studio_local or studio_live:
        from smart_rag_agents.query.studio.input import (
            StudioQueryInput,
            StudioQueryState,
        )

        input_schema = StudioQueryInput
        state_schema = StudioQueryState
        output_schema = StudioQueryState
    builder: QueryStateGraph = StateGraph(  # pyright: ignore[reportAssignmentType]
        state_schema,
        context_schema=QueryGraphContext,
        input_schema=input_schema,  # pyright: ignore[reportArgumentType]
        output_schema=output_schema,  # pyright: ignore[reportArgumentType]
    )

    register_production_progress_nodes(
        builder,
        enforce_admission=enforce_admission,
        nodes=nodes,
    )
    terminal_target = END
    if studio_local or studio_live:
        from smart_rag_agents.query.studio.local import emit_studio_response

        if studio_local:
            from smart_rag_agents.query.studio.local import seed_studio_runtime

            seed_node = seed_studio_runtime
            seed_name = "seed_studio_runtime"
        else:
            from smart_rag_agents.query.studio_live import seed_studio_live_unbound

            seed_node = studio_live_seed or seed_studio_live_unbound
            seed_name = "seed_studio_live_runtime"

        builder.add_node(  # pyright: ignore[reportUnknownMemberType]
            seed_name,
            seed_node,
        )
        builder.add_node(  # pyright: ignore[reportUnknownMemberType]
            "emit_studio_response",
            emit_studio_response,
        )
        terminal_target = "emit_studio_response"
        builder.add_edge(START, seed_name)
        builder.add_conditional_edges(
            seed_name,
            _route_after_studio_seed,
            {"enforce_admission": "enforce_admission", "end": terminal_target},
        )
    else:
        builder.add_edge(START, "enforce_admission")
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
    builder.add_conditional_edges(
        "compile_plan",
        _route_after_plan,
        {
            "company_scope": "company_scope",
            "general_scope": "general_scope",
            "mixed_scope": "mixed_scope",
            "invalid_scope": "invalid_scope",
            "end": terminal_target,
        },
    )
    builder.add_edge("company_scope", "apply_correction")
    builder.add_edge("general_scope", "verify_answer")
    builder.add_edge("mixed_scope", "verify_answer")
    builder.add_edge("invalid_scope", terminal_target)
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
    if studio_local or studio_live:
        builder.add_edge("emit_studio_response", END)
    return builder


def compile_query_graph(
    deps: QueryGraphDeps | None = None,
    *,
    checkpointer: BaseCheckpointSaver[str] | None = None,
) -> CompiledQueryGraph:
    """Compile the static query topology, optionally with a checkpointer.

    Args:
        deps: Optional fallback bindings used only when an invocation
            omits ``context=QueryGraphContext(...)``. Process caches must
            pass ``None`` so a prior run's connection cannot leak.
        checkpointer: Optional Postgres (or test) checkpointer. ``thread_id``
            must be ``str(conversation_id)``. Module-level ``graph`` stays
            checkpointer-free for Studio.

    Returns:
        Compiled graph. Runtime never calls ``PostgresSaver.setup()``.
        Per-run adapters are injected through ``QueryGraphContext``.
    """

    builder = build_query_graph(deps)
    return builder.compile(  # pyright: ignore[reportUnknownMemberType]
        checkpointer=checkpointer
    )


graph: CompiledQueryGraph = build_query_graph().compile()  # pyright: ignore[reportUnknownMemberType]
"""Compiled query graph for ``langgraph.json`` registration. Checkpointer-free."""


def production_stage_names() -> tuple[str, ...]:
    """Return the exact production ``add_node`` stage names.

    Returns:
        Stable stage keys registered by ``build_query_graph``.
    """

    return _PRODUCTION_STAGE_NAMES
