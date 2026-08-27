"""Studio live execution resource lifecycle and token rejection."""

from __future__ import annotations

import asyncio
import json
from typing import cast

import pytest
from smart_rag_agents.query.graph import build_query_graph
from smart_rag_agents.query.live_runtime import QueryGraphProcessBindings
from smart_rag_agents.query.studio_live import (
    DETAIL_DISABLED,
    DETAIL_TOKEN_INVALID,
    open_studio_live_graph,
)
from smart_rag_core.security.jwks import JwksVerificationError

from tests.support.studio_live import (
    CANARY,
    ExecutionRuntime,
    FakeConnection,
    studio_bindings,
    studio_hooks,
)
from tests.support.typed_graph import untyped


def test_build_query_graph_rejects_both_studio_modes() -> None:
    """Local and live Studio flags are mutually exclusive."""

    with pytest.raises(ValueError, match="mutually exclusive"):
        build_query_graph(studio_local=True, studio_live=True)


def test_disabled_execution_never_synthetic_admits() -> None:
    """Enabled-off execution rejects and does not mint ``studio_local``."""

    hooks = studio_hooks(enabled=False)

    async def _run() -> object:
        """Invoke the disabled live graph.

        Returns:
            Terminal state.
        """

        async with open_studio_live_graph(ExecutionRuntime(), hooks=hooks) as graph:  # type: ignore[arg-type]
            return await untyped(graph).ainvoke({"user_query": "hello"})

    result = untyped(asyncio.run(_run()))
    assert result["status"] == "admission_rejected"
    assert result["authorized_runtime"] is None
    assert DETAIL_DISABLED in str(result["detail"])
    raw_messages = result.get("messages")
    assert isinstance(raw_messages, list)
    messages = cast(list[object], raw_messages)
    assert messages
    assert CANARY not in json.dumps(result, default=str)


def test_invalid_token_execution_does_not_open_connection() -> None:
    """Invalid JWT execution rejects before the per-run connection."""

    opened = {"count": 0}

    def open_connection() -> FakeConnection:
        """Record an unexpected open.

        Returns:
            Never.
        """

        opened["count"] += 1
        raise AssertionError("opened")

    hooks = studio_hooks(
        verify=JwksVerificationError("invalid"),
        open_connection=open_connection,
    )

    async def _run() -> object:
        """Invoke the invalid-token live graph.

        Returns:
            Terminal state.
        """

        async with open_studio_live_graph(ExecutionRuntime(), hooks=hooks) as graph:  # type: ignore[arg-type]
            return await untyped(graph).ainvoke({"user_query": "hello"})

    result = untyped(asyncio.run(_run()))
    assert result["detail"] == DETAIL_TOKEN_INVALID
    assert opened["count"] == 0


def test_connection_closes_on_success_error_and_cancel() -> None:
    """The per-run connection closes after success, error, and cancel."""

    success = FakeConnection()
    hooks = studio_hooks(
        open_connection=lambda: success,
        build_bindings=studio_bindings,
    )

    async def _success() -> None:
        """Open then close the success-path connection."""

        async with open_studio_live_graph(ExecutionRuntime(), hooks=hooks) as graph:  # type: ignore[arg-type]
            assert not success.closed
            nodes = set(graph.get_graph().nodes)
            assert "seed_studio_live_runtime" in nodes

    asyncio.run(_success())
    assert success.closed

    errored = FakeConnection()

    def boom_bindings() -> QueryGraphProcessBindings:
        """Fail after the connection is open.

        Raises:
            OSError: Simulated bind failure.
        """

        raise OSError("bind failed")

    error_hooks = studio_hooks(
        open_connection=lambda: errored, build_bindings=boom_bindings
    )

    async def _error() -> object:
        """Compile the error-path reject graph.

        Returns:
            Terminal state.
        """

        async with open_studio_live_graph(
            ExecutionRuntime(),  # type: ignore[arg-type]
            hooks=error_hooks,
        ) as graph:
            return await untyped(graph).ainvoke({"user_query": "hello"})

    result = untyped(asyncio.run(_error()))
    assert result["status"] == "admission_rejected"
    assert errored.closed

    cancelled = FakeConnection()
    cancel_hooks = studio_hooks(
        open_connection=lambda: cancelled, build_bindings=studio_bindings
    )

    async def _cancel() -> None:
        """Cancel while the live graph is yielded."""

        async with open_studio_live_graph(
            ExecutionRuntime(),  # type: ignore[arg-type]
            hooks=cancel_hooks,
        ) as graph:
            assert graph is not None
            raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(_cancel())
    assert cancelled.closed
