"""Direct retrieval channel implementations."""

from smart_rag_core.query_routing.branch_channels.citation import run_citation_lookups
from smart_rag_core.query_routing.branch_channels.graph import run_graph
from smart_rag_core.query_routing.branch_channels.hybrid import chunk_loader, run_hybrid
from smart_rag_core.query_routing.branch_channels.table import table_evidence

__all__ = [
    "chunk_loader",
    "run_citation_lookups",
    "run_graph",
    "run_hybrid",
    "table_evidence",
]
