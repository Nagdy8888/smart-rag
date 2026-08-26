"""FastAPI-free query runtime adapters, bindings, and factories."""

from smart_rag_agents.query.runtime.adapters import (
    DsnBm25Retriever,
    ProcessHybridRetriever,
    bind_profile_model_caller,
    bind_table_executor,
    context_loader,
)
from smart_rag_agents.query.runtime.bindings import (
    QueryGraphProcessBindings,
    QueryGraphRuntimeError,
)
from smart_rag_agents.query.runtime.deps_factory import (
    build_query_graph_deps,
    build_query_process_bindings,
    open_run_app_api_connection,
    secret_url,
)

__all__ = [
    "DsnBm25Retriever",
    "ProcessHybridRetriever",
    "QueryGraphProcessBindings",
    "QueryGraphRuntimeError",
    "bind_profile_model_caller",
    "bind_table_executor",
    "build_query_graph_deps",
    "build_query_process_bindings",
    "context_loader",
    "open_run_app_api_connection",
    "secret_url",
]
