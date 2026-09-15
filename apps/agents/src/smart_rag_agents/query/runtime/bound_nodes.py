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

    def load_memory(
        state: QueryGraphState, runtime: Runtime[QueryGraphContext]
    ) -> QueryGraphState:
        """LangGraph wrapper for bounded memory load.

        Args:
            state: Admitted state.
            runtime: Per-invocation deps context.

        Returns:
            State with memory records.
        """

        return load_memory_node(state, deps_from_runtime(runtime, bound))

    def prepare_query(
        state: QueryGraphState, runtime: Runtime[QueryGraphContext]
    ) -> QueryGraphState:
        """LangGraph wrapper for typed preparation.

        Args:
            state: State after memory load.
            runtime: Per-invocation deps context.

        Returns:
            State with preparation.
        """

        return prepare_query_node(state, deps_from_runtime(runtime, bound))

    def compile_plan(state: QueryGraphState) -> QueryGraphState:
        """LangGraph wrapper for the route matrix.

        Args:
            state: Prepared state.

        Returns:
            State with a retrieval plan.
        """

        return compile_plan_node(state)

    def company_scope(
        state: QueryGraphState, runtime: Runtime[QueryGraphContext]
    ) -> QueryGraphState:
        """LangGraph wrapper for company retrieval after plan compilation.

        Args:
            state: Planned company-document state.
            runtime: Per-invocation deps context.

        Returns:
            State with branch results.
        """

        return company_scope_node(state, deps_from_runtime(runtime, bound))

    def general_scope(
        state: QueryGraphState, runtime: Runtime[QueryGraphContext]
    ) -> QueryGraphState:
        """LangGraph wrapper for direct general/user-text answers.

        Args:
            state: Planned NoRetrieval general state.
            runtime: Per-invocation deps context.

        Returns:
            State with one general or user-text draft.
        """

        return general_scope_node(state, deps_from_runtime(runtime, bound))

    def mixed_scope(
        state: QueryGraphState, runtime: Runtime[QueryGraphContext]
    ) -> QueryGraphState:
        """LangGraph wrapper for mixed-scope clarification.

        Args:
            state: Planned NoRetrieval clarification state.
            runtime: Per-invocation deps context.

        Returns:
            State with a deterministic clarification draft.
        """

        return mixed_scope_node(state, deps_from_runtime(runtime, bound))

    def web_scope(
        state: QueryGraphState, runtime: Runtime[QueryGraphContext]
    ) -> QueryGraphState:
        """LangGraph wrapper for bounded Web research.

        Args:
            state: Planned Web-research state.
            runtime: Per-invocation deps context.

        Returns:
            Answered draft for ``verify_answer``, or a typed fail-closed
            terminal. Never emits ``token_delta``.
        """

        return web_scope_node(state, deps_from_runtime(runtime, bound))

    def invalid_scope(
        state: QueryGraphState, runtime: Runtime[QueryGraphContext]
    ) -> QueryGraphState:
        """LangGraph wrapper for fail-closed invalid plans.

        Args:
            state: Planned or missing plan state.
            runtime: Per-invocation deps context.

        Returns:
            Routing-rejected state with no draft.
        """

        return invalid_scope_node(state, deps_from_runtime(runtime, bound))

    def apply_correction(
        state: QueryGraphState, runtime: Runtime[QueryGraphContext]
    ) -> QueryGraphState:
        """LangGraph wrapper for the single global correction.

        Args:
            state: State after branches.
            runtime: Per-invocation deps context.

        Returns:
            State after the single correction.
        """

        return apply_correction_node(state, deps_from_runtime(runtime, bound))

    def fuse_evidence(
        state: QueryGraphState, runtime: Runtime[QueryGraphContext]
    ) -> QueryGraphState:
        """LangGraph wrapper for Combined fusion.

        Args:
            state: State after correction.
            runtime: Per-invocation deps context.

        Returns:
            State with fused canonical evidence.
        """

        return fuse_evidence_node(state, deps_from_runtime(runtime, bound))

    def compose_tables(
        state: QueryGraphState, runtime: Runtime[QueryGraphContext]
    ) -> QueryGraphState:
        """LangGraph wrapper for deterministic table composition.

        Args:
            state: State after fusion.
            runtime: Per-invocation deps context.

        Returns:
            State with table provenance.
        """

        return compose_tables_node(state, deps_from_runtime(runtime, bound))

    def generate_answer(
        state: QueryGraphState, runtime: Runtime[QueryGraphContext]
    ) -> QueryGraphState:
        """LangGraph wrapper for one canonical answer generation.

        Args:
            state: State after optional tools.
            runtime: Per-invocation deps context.

        Returns:
            State with one answer payload.
        """

        return generate_answer_node(state, deps_from_runtime(runtime, bound))

    def disclose_optional_tools(
        state: QueryGraphState, runtime: Runtime[QueryGraphContext]
    ) -> QueryGraphState:
        """LangGraph wrapper for optional-tool disclosure and execution.

        Args:
            state: State after table composition.
            runtime: Per-invocation deps context.

        Returns:
            State with optional-tool telemetry and maybe one execution.
        """

        return disclose_optional_tools_node(state, deps_from_runtime(runtime, bound))

    def verify_answer(
        state: QueryGraphState, runtime: Runtime[QueryGraphContext]
    ) -> QueryGraphState:
        """LangGraph wrapper for layered verification.

        Args:
            state: State after answer generation.
            runtime: Per-invocation deps context.

        Returns:
            Terminal verified state.
        """

        return verify_answer_node(state, deps_from_runtime(runtime, bound))

    return BoundQueryNodes(
        load_memory=load_memory,
        prepare_query=prepare_query,
        compile_plan=compile_plan,
        company_scope=company_scope,
        general_scope=general_scope,
        mixed_scope=mixed_scope,
        web_scope=web_scope,
        invalid_scope=invalid_scope,
        apply_correction=apply_correction,
        fuse_evidence=fuse_evidence,
        compose_tables=compose_tables,
        disclose_optional_tools=disclose_optional_tools,
        generate_answer=generate_answer,
        verify_answer=verify_answer,
    )
