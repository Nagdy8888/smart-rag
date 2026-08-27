"""Studio live socket-free introspection and registration."""

from __future__ import annotations

import asyncio
import json

import pytest
from smart_rag_agents.query.studio_live import (
    make_graph,
)

from tests.support.studio_live import (
    CANARY,
    STUDIO_REPO_ROOT,
    IntrospectionRuntime,
)


def test_introspection_opens_zero_sockets(monkeypatch: pytest.MonkeyPatch) -> None:
    """Schema/graph introspection must not open DB or model sockets."""

    def boom(*_args: object, **_kwargs: object) -> None:
        """Fail if any connect-like helper is used.

        Args:
            *_args: Ignored.
            **_kwargs: Ignored.

        Raises:
            AssertionError: Always.
        """

        raise AssertionError("introspection opened a socket")

    monkeypatch.setattr("psycopg.connect", boom)
    monkeypatch.setattr(
        "smart_rag_core.security.profile_snapshot.psycopg.connect",
        boom,
    )
    monkeypatch.setattr(
        "smart_rag_agents.query.live_runtime.psycopg.connect",
        boom,
    )
    monkeypatch.setattr(
        "smart_rag_agents.query.runtime.adapters.psycopg.connect",
        boom,
    )
    monkeypatch.setattr(
        "smart_rag_agents.query.runtime.deps_factory.psycopg.connect",
        boom,
    )
    monkeypatch.setattr(
        "smart_rag_core.security.jwks.httpx.Client",
        boom,
    )

    async def _run() -> None:
        """Compile the introspection graph and inspect topology."""

        async with make_graph(IntrospectionRuntime()) as graph:  # type: ignore[arg-type]
            nodes = set(graph.get_graph().nodes)
            assert "seed_studio_live_runtime" in nodes
            assert "emit_studio_response" in nodes
            schema = json.dumps(graph.get_input_jsonschema())
            assert CANARY not in schema

    asyncio.run(_run())


def test_live_modules_do_not_import_backend_or_print_token() -> None:
    """Agents live modules stay import-safe and do not mention service_role."""

    paths = [
        STUDIO_REPO_ROOT / "apps/agents/src/smart_rag_agents/query/studio_live.py",
        STUDIO_REPO_ROOT / "apps/agents/src/smart_rag_agents/query/live_runtime.py",
        STUDIO_REPO_ROOT
        / "packages/core/src/smart_rag_core/security/profile_snapshot.py",
    ]
    haystack = "\n".join(path.read_text(encoding="utf-8") for path in paths)
    assert "from smart_rag_api" not in haystack
    assert "import smart_rag_api" not in haystack
    assert "from fastapi" not in haystack
    assert "import fastapi" not in haystack
    assert "service_role" not in haystack
    assert "print(" not in haystack


def test_query_studio_registration_unchanged() -> None:
    """The unbound Studio graph entry must stay on ``studio.py:graph``."""

    payload = json.loads(
        (STUDIO_REPO_ROOT / "apps/agents/langgraph.json").read_text(encoding="utf-8")
    )
    assert (
        payload["graphs"]["query_studio"]
        == "./src/smart_rag_agents/query/studio.py:graph"
    )
    assert (
        payload["graphs"]["query_studio_live"]
        == "./src/smart_rag_agents/query/studio_live.py:make_graph"
    )
