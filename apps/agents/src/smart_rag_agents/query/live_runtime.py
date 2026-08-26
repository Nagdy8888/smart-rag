"""Compatibility facade for FastAPI-independent query-graph bindings."""

import psycopg
from smart_rag_core.retrieval.context_loader import fetch_authorized_chunk_context

from smart_rag_agents.query.runtime.adapters import (
    DsnBm25Retriever,
    ProcessHybridRetriever,
    bind_profile_model_caller,
    bind_table_executor,
)
from smart_rag_agents.query.runtime.adapters import (
    context_loader as _context_loader,
)
from smart_rag_agents.query.runtime.bindings import (
    QueryGraphProcessBindings,
    QueryGraphRuntimeError,
)
from smart_rag_agents.query.runtime.deps_factory import (
    build_query_graph_deps,
    build_query_process_bindings,
    open_run_app_api_connection,
)
from smart_rag_agents.query.runtime.deps_factory import (
    secret_url as _secret_url,
)

__all__ = [
    "DsnBm25Retriever",
    "ProcessHybridRetriever",
    "QueryGraphProcessBindings",
    "QueryGraphRuntimeError",
    "_context_loader",
    "_secret_url",
    "bind_profile_model_caller",
    "bind_table_executor",
    "build_query_graph_deps",
    "build_query_process_bindings",
    "fetch_authorized_chunk_context",
    "open_run_app_api_connection",
    "psycopg",
]
