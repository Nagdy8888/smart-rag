"""Query graph package: admission through Combined fusion, answer, and verifier.

The compiled default graph constructs no sockets or OpenAI clients. SSE and
the public chat UI remain later packets.
"""

from __future__ import annotations

from smart_rag_agents.query.graph import build_query_graph, graph
from smart_rag_agents.query.state import pending_query_state

__all__ = ["build_query_graph", "graph", "pending_query_state"]
