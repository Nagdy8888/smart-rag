"""Bound production query-node callables with no topology edges.

This owner wraps existing node functions with ``deps_from_runtime``. It
emits no progress events and contains no LangGraph edges.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from langgraph.runtime import Runtime

from smart_rag_agents.query.deps import (
    QueryGraphContext,
    QueryGraphDeps,
    deps_from_runtime,
)
from smart_rag_agents.query.nodes import (
    apply_correction_node,
    company_scope_node,
    compile_plan_node,
    compose_tables_node,
    disclose_optional_tools_node,
    fuse_evidence_node,
    general_scope_node,
    generate_answer_node,
    invalid_scope_node,
    load_memory_node,
    mixed_scope_node,
    prepare_query_node,
    verify_answer_node,
    web_scope_node,
)
from smart_rag_agents.query.state import QueryGraphState

QueryNode = Callable[[QueryGraphState, Runtime[QueryGraphContext]], QueryGraphState]
QueryNodeNoRuntime = Callable[[QueryGraphState], QueryGraphState]
DepsNode = Callable[[QueryGraphState, QueryGraphDeps], QueryGraphState]


@dataclass(frozen=True, slots=True)
class BoundQueryNodes:
    """Production node callables bound to one ``QueryGraphDeps`` fallback."""

    load_memory: QueryNode
    prepare_query: QueryNode
    compile_plan: QueryNodeNoRuntime
    company_scope: QueryNode
    general_scope: QueryNode
    mixed_scope: QueryNode
    web_scope: QueryNode
    invalid_scope: QueryNode
    apply_correction: QueryNode
    fuse_evidence: QueryNode
    compose_tables: QueryNode
    disclose_optional_tools: QueryNode
    generate_answer: QueryNode
    verify_answer: QueryNode


def bind_query_nodes(bound: QueryGraphDeps) -> BoundQueryNodes:
    """Bind production node wrappers to one fallback deps object.

    Args:
        bound: Fallback bindings used when runtime context omits deps.

    Returns:
        Frozen callable bundle. Callables use ``deps_from_runtime``.

    Notes:
        State, persistence, models, budgets, and failure routes stay on the
        wrapped node. This owner only injects runtime deps.
    """

    def bind(node: DepsNode) -> QueryNode:
        """Bind one deps-taking node to LangGraph runtime.

        Args:
            node: Production node callable.

        Returns:
            Runtime-aware wrapper named after ``node``.
        """

        def wrapped(
            state: QueryGraphState, runtime: Runtime[QueryGraphContext]
        ) -> QueryGraphState:
            """Invoke the bound node with runtime deps.

            Args:
                state: Graph state.
                runtime: Per-invocation deps context.

            Returns:
                Node output state.
            """

            return node(state, deps_from_runtime(runtime, bound))

        wrapped.__name__ = node.__name__
        wrapped.__qualname__ = node.__qualname__
        return wrapped

    def compile_plan(state: QueryGraphState) -> QueryGraphState:
        """LangGraph wrapper for the route matrix.

        Args:
            state: Prepared state.

        Returns:
            State with a retrieval plan.
        """

        return compile_plan_node(state)

    return BoundQueryNodes(
        load_memory=bind(load_memory_node),
        prepare_query=bind(prepare_query_node),
        compile_plan=compile_plan,
        company_scope=bind(company_scope_node),
        general_scope=bind(general_scope_node),
        mixed_scope=bind(mixed_scope_node),
        web_scope=bind(web_scope_node),
        invalid_scope=bind(invalid_scope_node),
        apply_correction=bind(apply_correction_node),
        fuse_evidence=bind(fuse_evidence_node),
        compose_tables=bind(compose_tables_node),
        disclose_optional_tools=bind(disclose_optional_tools_node),
        generate_answer=bind(generate_answer_node),
        verify_answer=bind(verify_answer_node),
    )
