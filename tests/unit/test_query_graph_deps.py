"""Run-scoped QueryGraphDeps injection from Runtime, mappings, and contextvars."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from pydantic import SecretStr
from smart_rag_agents.query.deps import (
    QueryGraphContext,
    QueryGraphDeps,
    bind_query_run_deps,
    deps_from_runtime,
    reset_query_run_deps,
)
from smart_rag_agents.query.runtime.deps_factory import refresh_web_search_deps
from smart_rag_core.gateways.exa_search import ExaSearchGateway
from smart_rag_core.settings import SharedSettings


def test_deps_from_runtime_reads_dataclass_context() -> None:
    """QueryGraphContext.deps wins over the compile-time fallback."""

    live = QueryGraphDeps(web_search_enabled=True)
    runtime = SimpleNamespace(context=QueryGraphContext(deps=live))
    assert deps_from_runtime(runtime, QueryGraphDeps()) is live


def test_deps_from_runtime_reads_mapping_context() -> None:
    """LangGraph may coerce context to a mapping; deps must still resolve."""

    live = QueryGraphDeps(web_search_enabled=True)
    runtime = SimpleNamespace(context={"deps": live})
    assert deps_from_runtime(runtime, QueryGraphDeps()) is live


def test_deps_from_runtime_uses_task_binding_when_runtime_empty() -> None:
    """Worker-thread nodes can read the SSE task binding when Runtime is empty."""

    fallback = QueryGraphDeps()
    live = QueryGraphDeps(web_search_enabled=True)
    token = bind_query_run_deps(live)
    try:
        assert deps_from_runtime(SimpleNamespace(), fallback) is live
    finally:
        reset_query_run_deps(token)
    assert deps_from_runtime(SimpleNamespace(), fallback) is fallback


def test_refresh_web_search_deps_overlays_stale_cached_flags(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Per-run deps reread WEB_SEARCH_ENABLED instead of a stale Hybrid cache."""

    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setenv("WEB_SEARCH_ENABLED", "true")
    monkeypatch.setenv("EXA_API_KEY", "exa-refresh-canary")
    monkeypatch.setenv("MOCK_MODEL_MODE", "true")
    settings = SharedSettings()
    deps = QueryGraphDeps(web_search_enabled=False, web_search_configured=False)
    refresh_web_search_deps(deps, settings)
    assert deps.web_search_enabled is True
    assert deps.web_search_configured is True
    assert isinstance(deps.exa_search_gateway, ExaSearchGateway)
    assert "exa-refresh-canary" not in repr(deps)


def test_refresh_web_search_deps_clears_gateway_when_disabled() -> None:
    """Disabled Web must not keep a leftover Exa client on run deps."""

    gateway = ExaSearchGateway(api_key=SecretStr("exa-disabled-canary"))
    deps = QueryGraphDeps(
        web_search_enabled=True,
        web_search_configured=True,
        exa_search_gateway=gateway,
    )
    refresh_web_search_deps(
        deps, SimpleNamespace(web_search_enabled=False, exa_api_key=None)
    )
    assert deps.web_search_enabled is False
    assert deps.web_search_configured is False
    assert deps.exa_search_gateway is None


def test_refresh_web_search_deps_replaces_closed_gateway(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A closed Exa client must not be reused across later Ask runs."""

    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setenv("WEB_SEARCH_ENABLED", "true")
    monkeypatch.setenv("EXA_API_KEY", "exa-closed-canary")
    monkeypatch.setenv("MOCK_MODEL_MODE", "true")
    settings = SharedSettings()
    closed = ExaSearchGateway(api_key=SecretStr("exa-closed-canary"))
    asyncio.run(closed.aclose())
    deps = QueryGraphDeps(
        web_search_enabled=True,
        web_search_configured=True,
        exa_search_gateway=closed,
    )
    refresh_web_search_deps(deps, settings)
    assert isinstance(deps.exa_search_gateway, ExaSearchGateway)
    assert deps.exa_search_gateway is not closed
    assert deps.exa_search_gateway.closed is False


def test_refresh_web_search_deps_replaces_gateway_when_key_changes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Settings-changed credentials recreate the gateway."""

    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setenv("WEB_SEARCH_ENABLED", "true")
    monkeypatch.setenv("EXA_API_KEY", "exa-new-canary")
    monkeypatch.setenv("MOCK_MODEL_MODE", "true")
    settings = SharedSettings()
    stale = ExaSearchGateway(api_key=SecretStr("exa-old-canary"))
    deps = QueryGraphDeps(
        web_search_enabled=True,
        web_search_configured=True,
        exa_search_gateway=stale,
    )
    refresh_web_search_deps(deps, settings)
    assert isinstance(deps.exa_search_gateway, ExaSearchGateway)
    assert deps.exa_search_gateway is not stale
    assert deps.exa_search_gateway.credential_matches(SecretStr("exa-new-canary"))
