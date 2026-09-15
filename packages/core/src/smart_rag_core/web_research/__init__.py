"""Run-scoped public Web evidence and bounded research execution."""

from smart_rag_core.web_research.bound_store import BoundWebStore
from smart_rag_core.web_research.exceptions import WebResearchError
from smart_rag_core.web_research.models import (
    WebCitation,
    WebOperationState,
    WebSourceRecord,
)
from smart_rag_core.web_research.policy import (
    assert_span_contained,
    excerpt_sha256,
    normalize_web_url,
)
from smart_rag_core.web_research.store import (
    begin_web_research_operation,
    complete_web_research_operation,
    insert_web_citation,
    insert_web_source,
    mark_web_research_operation_sent,
)

__all__ = [
    "BoundWebStore",
    "WebCitation",
    "WebOperationState",
    "WebResearchError",
    "WebSourceRecord",
    "assert_span_contained",
    "begin_web_research_operation",
    "complete_web_research_operation",
    "excerpt_sha256",
    "insert_web_citation",
    "insert_web_source",
    "mark_web_research_operation_sent",
    "normalize_web_url",
]
