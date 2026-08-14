"""Hybrid retrieval adapters: dense, BM25, term, and authoritative recheck."""

from smart_rag_core.retrieval.bm25 import Bm25Retriever
from smart_rag_core.retrieval.bm25_indexer import Bm25Indexer, Bm25ProjectionRow
from smart_rag_core.retrieval.bm25_query import (
    Bm25QueryError,
    Bm25StructuredQuery,
    build_bm25_query,
)
from smart_rag_core.retrieval.dense import DenseRetriever
from smart_rag_core.retrieval.profiles import (
    BM25_AUTHORIZED_SURVIVOR_CAP,
    DENSE_CANDIDATE_CAP,
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
    "TERM_CANDIDATE_CAP",
    "Bm25Field",
    "Bm25Indexer",
    "Bm25Operator",
    "Bm25ProjectionRow",
    "Bm25QueryError",
    "Bm25RetrievalResult",
    "Bm25Retriever",
    "Bm25StructuredQuery",
    "DenseMode",
    "DenseRetrievalResult",
    "DenseRetriever",
    "HnswProfileId",
    "RecheckRejectedError",
    "RetrievalCandidate",
    "RetrievalFallbackReason",
    "RetrievalSessionError",
    "TermRetrievalResult",
    "TermRetriever",
    "build_bm25_query",
    "recheck_retrieval_candidates",
    "retrieval_transaction",
]
