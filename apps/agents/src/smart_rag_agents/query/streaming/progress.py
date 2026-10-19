"""Truthful node-start custom events for production query stages."""

from __future__ import annotations

from collections.abc import Callable
from functools import wraps
from typing import TYPE_CHECKING, Literal, TypeVar, cast

from langgraph.config import get_stream_writer
from typing_extensions import TypedDict

from smart_rag_agents.query.nodes.shared import skip_closed_nodes
from smart_rag_agents.query.state import QueryGraphState, QueryStateGraph

if TYPE_CHECKING:
    from smart_rag_agents.query.runtime.bound_nodes import BoundQueryNodes

NodeFn = TypeVar("NodeFn", bound=Callable[..., QueryGraphState])

PRODUCTION_PROGRESS_STAGES: tuple[str, ...] = (
    "enforce_admission",
    "load_memory",
    "prepare_query",
    "compile_plan",
    "company_scope",
    "general_scope",
    "mixed_scope",
    "invalid_scope",
    "web_scope",
    "apply_correction",
    "fuse_evidence",
    "compose_tables",
    "disclose_optional_tools",
    "generate_answer",
    "verify_answer",
    "organize_answer",
)


class NodeStartCustom(TypedDict):
    """Safe custom payload emitted immediately before substantive node work.

    Attributes:
        kind: Constant ``node_start`` discriminator.
        stage: Exact production ``add_node`` key.
    """

    kind: Literal["node_start"]
    stage: str


def wrap_progress_node(stage: str, node: NodeFn) -> NodeFn:
    """Emit ``node_start`` immediately before a substantive production node.

    Closed-state no-ops invoke the original callable and emit nothing.
    Exceptions from the original callable are not caught or translated.

    Args:
        stage: Exact production stage key registered in ``build_query_graph``.
        node: Existing bound or unbound node callable.

    Returns:
        Signature-preserving wrapper.

    Raises:
        ValueError: When ``stage`` is not a production progress stage.

    Notes:
        State inputs/outputs: same ``QueryGraphState`` as ``node``.
        Persistence writes: none. Custom events are stream-only.
        External/model calls: none besides ``get_stream_writer``.
        Budget/deadline behavior: unchanged.
        Failure/fallback route: original node exceptions propagate.
    """

    if stage not in PRODUCTION_PROGRESS_STAGES:
        raise ValueError(f"progress_stage_unknown:{stage}")

    @wraps(node)
    def wrapped(
        state: QueryGraphState, *args: object, **kwargs: object
    ) -> QueryGraphState:
        """Invoke ``node`` after an optional start event.

        Args:
            state: Current graph state.
            *args: Remaining positional node arguments.
            **kwargs: Remaining keyword node arguments.

        Returns:
            The original node return value.
        """

        if not skip_closed_nodes(state):
            writer = get_stream_writer()
            payload: NodeStartCustom = {"kind": "node_start", "stage": stage}
            writer(payload)
        return node(state, *args, **kwargs)

    return cast(NodeFn, wrapped)


def register_production_progress_nodes(
    builder: QueryStateGraph,
    *,
    enforce_admission: Callable[..., QueryGraphState],
    nodes: BoundQueryNodes,
) -> None:
    """Register wrapped production stages on an uncompiled graph.

    Studio seed and emit nodes are not registered here.

    Args:
        builder: Topology builder that already has a state schema.
        enforce_admission: Unbound admission node.
        nodes: Bound production callables from ``bind_query_nodes``.

    Returns:
        None. Mutates ``builder`` with ``add_node`` only.
    """

    staged: tuple[tuple[str, Callable[..., QueryGraphState]], ...] = (
        ("enforce_admission", enforce_admission),
        ("load_memory", nodes.load_memory),
        ("prepare_query", nodes.prepare_query),
        ("compile_plan", nodes.compile_plan),
        ("company_scope", nodes.company_scope),
        ("general_scope", nodes.general_scope),
        ("mixed_scope", nodes.mixed_scope),
        ("invalid_scope", nodes.invalid_scope),
        ("web_scope", nodes.web_scope),
        ("apply_correction", nodes.apply_correction),
        ("fuse_evidence", nodes.fuse_evidence),
        ("compose_tables", nodes.compose_tables),
        ("disclose_optional_tools", nodes.disclose_optional_tools),
        ("generate_answer", nodes.generate_answer),
        ("verify_answer", nodes.verify_answer),
        ("organize_answer", nodes.organize_answer),
    )
    for stage, node in staged:
        builder.add_node(  # pyright: ignore[reportUnknownMemberType]
            stage,
            wrap_progress_node(stage, cast(Callable[..., QueryGraphState], node)),
        )
