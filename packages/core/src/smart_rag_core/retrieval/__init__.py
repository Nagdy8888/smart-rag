"""Hybrid retrieval adapters: dense, BM25, term, and authoritative recheck."""

from smart_rag_core.retrieval.bm25 import Bm25Retriever
from smart_rag_core.retrieval.bm25_indexer import Bm25Indexer, Bm25ProjectionRow
from smart_rag_core.retrieval.bm25_query import (
    Bm25QueryError,
    Bm25StructuredQuery,
    build_bm25_query,
)
from smart_rag_core.retrieval.cache_store import (
    CachedRetrieval,
    CacheEvent,
    RetrievalCacheMode,
    RetrievalCacheStore,
)
from smart_rag_core.retrieval.dense import DenseRetriever
from smart_rag_core.retrieval.fusion import fuse_channels
from smart_rag_core.retrieval.graph import (
    GraphIndexer,
    GraphLeadSet,
    GraphLimitationCode,
    GraphQueryBounds,
    GraphRetriever,
    apply_query_bounds,
    bind_graph_source_text,
    clamp_graph_leads,
    graph_survival_ratio,
    opaque_graph_source_basename,
    strip_graph_source_envelope,
)
from smart_rag_core.retrieval.graph_results import (
    GraphInspectResult,
    GraphRetrievalResult,
)
from smart_rag_core.retrieval.hybrid import HybridRetrievalResult, assemble_hybrid
from smart_rag_core.retrieval.hybrid_run import (
    EvidenceLocator,
    EvidenceUnit,
    HybridRetriever,
    HybridRunResult,
)
from smart_rag_core.retrieval.profiles import (
    BM25_AUTHORIZED_SURVIVOR_CAP,
    DENSE_CANDIDATE_CAP,
    PREFUSION_UNION_CAP,
    RETRIEVAL_SLICE_SECONDS,
    RRF_K,
    TERM_CANDIDATE_CAP,
    Bm25Field,
    Bm25Operator,
    DenseMode,
    HnswProfileId,
    RetrievalFallbackReason,
)
from smart_rag_core.retrieval.recheck import (
    RecheckRejectedError,
    recheck_retrieval_candidates,
)
from smart_rag_core.retrieval.session import (
    RetrievalSessionError,
    retrieval_transaction,
)
from smart_rag_core.retrieval.terms import TermRetriever
from smart_rag_core.retrieval.types import (
    Bm25RetrievalResult,
    DenseRetrievalResult,
    RetrievalCandidate,
    TermRetrievalResult,
)

__all__ = [
    "BM25_AUTHORIZED_SURVIVOR_CAP",
    "DENSE_CANDIDATE_CAP",
    "PREFUSION_UNION_CAP",
    "RETRIEVAL_SLICE_SECONDS",
    "RRF_K",
    "TERM_CANDIDATE_CAP",
    "Bm25Field",
    "Bm25Indexer",
    "Bm25Operator",
    "Bm25ProjectionRow",
    "Bm25QueryError",
    "Bm25RetrievalResult",
    "Bm25Retriever",
    "Bm25StructuredQuery",
    "CacheEvent",
    "CachedRetrieval",
    "DenseMode",
    "DenseRetrievalResult",
    "DenseRetriever",
    "EvidenceLocator",
    "EvidenceUnit",
    "GraphIndexer",
    "GraphInspectResult",
    "GraphLeadSet",
    "GraphLimitationCode",
    "GraphQueryBounds",
    "GraphRetrievalResult",
    "GraphRetriever",
    "HnswProfileId",
    "HybridRetrievalResult",
    "HybridRetriever",
    "HybridRunResult",
    "RecheckRejectedError",
    "RetrievalCacheMode",
    "RetrievalCacheStore",
    "RetrievalCandidate",
    "RetrievalFallbackReason",
    "RetrievalSessionError",
    "TermRetrievalResult",
    "TermRetriever",
    "apply_query_bounds",
    "assemble_hybrid",
    "bind_graph_source_text",
    "build_bm25_query",
    "clamp_graph_leads",
    "fuse_channels",
    "graph_survival_ratio",
    "opaque_graph_source_basename",
    "recheck_retrieval_candidates",
    "retrieval_transaction",
    "strip_graph_source_envelope",
]
