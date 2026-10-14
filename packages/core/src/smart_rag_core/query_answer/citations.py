"""Citation provenance payloads for existing ``app.citations.provenance`` jsonb."""

from __future__ import annotations

from smart_rag_core.query_answer.citations_leaf import (
    CitationPersistResult,
    SkippedCitation,
    citation_provenance_payload,
    drop_skipped_citations,
    leading_sentence,
    repair_leaf_citations,
    shorten_contained_skipped_spans,
)
from smart_rag_core.query_answer.citations_persist import (
    maybe_persist_verified_citations,
    persist_answer_citations,
    persist_web_answer_citations,
)

__all__ = [
    "CitationPersistResult",
    "SkippedCitation",
    "citation_provenance_payload",
    "drop_skipped_citations",
    "leading_sentence",
    "maybe_persist_verified_citations",
    "persist_answer_citations",
    "persist_web_answer_citations",
    "repair_leaf_citations",
    "shorten_contained_skipped_spans",
]
