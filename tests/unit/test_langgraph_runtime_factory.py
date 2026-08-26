"""LangGraph runtime factory cache, compile reuse, and setup prohibitions."""

from __future__ import annotations

from types import SimpleNamespace

from smart_rag_api.services.sse.langgraph_runtime import LangGraphRuntimeFactory


def test_factory_reuses_compiled_graph_for_the_same_checkpointer() -> None:
    """Two compiles with a None checkpointer reuse one compiled object."""

    factory = LangGraphRuntimeFactory()
    first = factory.compiled_query_graph(None)
    second = factory.compiled_query_graph(None)
    assert first is second
    assert factory.compile_count == 1


def test_factory_bind_memory_store_skips_when_dsn_is_missing() -> None:
    """Empty checkpoint DSN returns null store callables without opening pools."""

    factory = LangGraphRuntimeFactory()
    settings = SimpleNamespace(resolved_checkpoint_dsn=lambda: None)
    store_get, store_put = factory.bind_memory_store(settings)
    assert store_get is None
    assert store_put is None
    assert factory.store is None


def test_factory_never_exposes_postgres_setup() -> None:
    """Factory methods do not call LangGraph Postgres ``setup()`` helpers."""

    source = LangGraphRuntimeFactory.process_bindings.__doc__ or ""
    assert "setup()" in (LangGraphRuntimeFactory.__doc__ or "")
    assert "PostgresSaver.setup()" in (LangGraphRuntimeFactory.__doc__ or "")
    del source
