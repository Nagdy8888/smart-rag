"""Typed wrappers for untyped LangGraph compile/invoke in tests."""

from __future__ import annotations

from typing import Any, cast


def compile_state_graph(graph: object) -> Any:
    """Compile a LangGraph ``StateGraph`` without leaking Unknown members.

    Args:
        graph: State graph builder with a ``compile`` method.

    Returns:
        Compiled graph handle. Invoke/stream/get_graph stay ``Any`` because
        LangGraph's compiled type is incomplete under strict Pyright.
    """

    return cast(Any, graph).compile()


def untyped(value: object) -> Any:
    """Widen an untyped library handle to ``Any``.

    Args:
        value: LangGraph compiled graph, stream chunk, or similar.

    Returns:
        The same object with ``Any`` typing so unknown members are not reported.
    """

    return cast(Any, value)
