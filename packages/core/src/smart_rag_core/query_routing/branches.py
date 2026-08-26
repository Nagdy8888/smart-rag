"""Public branch-execution facade. Implementations live in focused modules."""

from smart_rag_core.query_routing.acl_blindness import (
    disclose_acl_blindness,
    suppress_unauthorized_blindness,
)
from smart_rag_core.query_routing.branch_results import empty_keyword_guard, inherit_ids
from smart_rag_core.query_routing.branch_scheduler import execute_branches
from smart_rag_core.query_routing.protocols import (
    GraphRetrieveLike,
    HybridRetrieveLike,
    TableExecuteLike,
)

__all__ = [
    "GraphRetrieveLike",
    "HybridRetrieveLike",
    "TableExecuteLike",
    "disclose_acl_blindness",
    "empty_keyword_guard",
    "execute_branches",
    "inherit_ids",
    "suppress_unauthorized_blindness",
]
