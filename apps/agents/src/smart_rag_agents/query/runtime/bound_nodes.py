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
_RuntimeNode = Callable[[QueryGraphState, QueryGraphDeps], QueryGraphState]


@dataclass(frozen=True, slots=True)
class BoundQueryNodes:
    """Production node callables bound to one ``QueryGraphDeps`` fallback.

    Attributes:
        load_memory: Bounded memory load.
        prepare_query: Typed preparation.
        compile_plan: Deterministic route matrix (no runtime deps).
        company_scope: Company retrieval.
        general_scope: General or user-text draft.
        mixed_scope: Mixed-scope clarification.
        web_scope: Bounded Web research with fail-closed provider errors.
        invalid_scope: Fail-closed invalid plan.
        apply_correction: Single global correction.
        fuse_evidence: Combined fusion.
        compose_tables: Deterministic table composition.
        disclose_optional_tools: Optional-tool disclosure and execution.
        generate_answer: Canonical answer generation.
        verify_answer: Layered verification.
    """

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


def _runtime_node(node: _RuntimeNode, bound: QueryGraphDeps) -> QueryNode:
    """Bind one runtime-aware query node to fallback deps.

    Args:
        node: Existing node that accepts ``QueryGraphDeps``.
        bound: Fallback bindings used when runtime context omits deps.

    Returns:
        LangGraph node that reads run-scoped deps.
    """

    def wrapped(
        state: QueryGraphState, runtime: Runtime[QueryGraphContext]
    ) -> QueryGraphState:
        """Dispatch the bound node with runtime deps.

        Args:
            state: Current graph state.
            runtime: Per-invocation context.

        Returns:
            Next graph state from the wrapped node.
        """

        return node(state, deps_from_runtime(runtime, bound))

    return wrapped


def bind_query_nodes(bound: QueryGraphDeps) -> BoundQueryNodes:
    """Bind production node wrappers to one fallback deps object.

    Args:
        bound: Fallback bindings used when runtime context omits deps.

    Returns:
        Frozen callable bundle. Callables use ``deps_from_runtime``.

    Notes:
        State inputs/outputs: ``QueryGraphState`` only.
        Persistence writes: none in this owner.
        External/model calls: delegated to the wrapped node.
        Budget/deadline behavior: unchanged from the wrapped node.
        Failure/fallback route: unchanged from the wrapped node.
    """

    return BoundQueryNodes(
        load_memory=_runtime_node(load_memory_node, bound),
        prepare_query=_runtime_node(prepare_query_node, bound),
        compile_plan=compile_plan_node,
        company_scope=_runtime_node(company_scope_node, bound),
        general_scope=_runtime_node(general_scope_node, bound),
        mixed_scope=_runtime_node(mixed_scope_node, bound),
        web_scope=_runtime_node(web_scope_node, bound),
        invalid_scope=_runtime_node(invalid_scope_node, bound),
        apply_correction=_runtime_node(apply_correction_node, bound),
        fuse_evidence=_runtime_node(fuse_evidence_node, bound),
        compose_tables=_runtime_node(compose_tables_node, bound),
        disclose_optional_tools=_runtime_node(disclose_optional_tools_node, bound),
        generate_answer=_runtime_node(generate_answer_node, bound),
        verify_answer=_runtime_node(verify_answer_node, bound),
    )
