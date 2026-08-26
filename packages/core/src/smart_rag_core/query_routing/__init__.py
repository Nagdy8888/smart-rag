"""Phase 6 packet 2 query preparation, routing matrix, and one correction."""

from smart_rag_core.query_routing.branches import (
    disclose_acl_blindness,
    empty_keyword_guard,
    execute_branches,
    suppress_unauthorized_blindness,
)
from smart_rag_core.query_routing.constants import (
    BRANCH_CONCURRENCY,
    MEMORY_MESSAGE_LIMIT,
    PROVISIONAL_COVERAGE_THRESHOLD,
    WHOLE_DOCUMENT_SECTION_COVERAGE,
)
from smart_rag_core.query_routing.correction import (
    apply_correction_to_plan,
    decide_correction,
    refuse_second_correction,
)
from smart_rag_core.query_routing.exceptions import QueryRoutingError
from smart_rag_core.query_routing.knowledge_scope import (
    KnowledgeScope,
    KnowledgeScopeDecision,
    NoRetrievalAnswerMode,
    ScopeDegradationReason,
    classify_knowledge_scope,
)
from smart_rag_core.query_routing.matrix import compile_retrieval_plan
from smart_rag_core.query_routing.memory import load_authorized_memory
from smart_rag_core.query_routing.models import (
    REQUIRED_PREPARATION_FIELDS,
    BranchKind,
    BranchResult,
    BranchSpec,
    CorrectionDecision,
    CorrectionKind,
    MemoryRecord,
    PreparationModelPayload,
    QueryPreparation,
    RetrievalPlan,
    RoutingSurface,
    TableEvidenceRecord,
)
from smart_rag_core.query_routing.preparation import (
    assert_preparation_schema,
    forbid_separate_rewrite_call,
    prepare_query,
)
from smart_rag_core.query_routing.serde import (
    branch_results_from_state,
    memory_from_state,
    plan_from_state,
    preparation_from_state,
)

__all__ = [
    "BRANCH_CONCURRENCY",
    "MEMORY_MESSAGE_LIMIT",
    "PROVISIONAL_COVERAGE_THRESHOLD",
    "REQUIRED_PREPARATION_FIELDS",
    "WHOLE_DOCUMENT_SECTION_COVERAGE",
    "BranchKind",
    "BranchResult",
    "BranchSpec",
    "CorrectionDecision",
    "CorrectionKind",
    "KnowledgeScope",
    "KnowledgeScopeDecision",
    "MemoryRecord",
    "NoRetrievalAnswerMode",
    "PreparationModelPayload",
    "QueryPreparation",
    "QueryRoutingError",
    "RetrievalPlan",
    "RoutingSurface",
    "ScopeDegradationReason",
    "TableEvidenceRecord",
    "apply_correction_to_plan",
    "assert_preparation_schema",
    "branch_results_from_state",
    "classify_knowledge_scope",
    "compile_retrieval_plan",
    "decide_correction",
    "disclose_acl_blindness",
    "empty_keyword_guard",
    "execute_branches",
    "forbid_separate_rewrite_call",
    "load_authorized_memory",
    "memory_from_state",
    "plan_from_state",
    "preparation_from_state",
    "prepare_query",
    "refuse_second_correction",
    "suppress_unauthorized_blindness",
]
