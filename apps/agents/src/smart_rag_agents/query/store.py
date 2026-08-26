"""Compatibility facade for the query memory store."""

from smart_rag_agents.query.persistence.store import (
    QueryMemoryStore,
    StoreSchemaError,
    open_query_memory_store,
)

__all__ = [
    "QueryMemoryStore",
    "StoreSchemaError",
    "open_query_memory_store",
]
