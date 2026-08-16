"""Query-run admission, route ceilings, and run-local budget consumption."""

from smart_rag_core.query_admission.ceilings import (
    DEFAULT_MONTHLY_LLM_BUDGET_USD,
    MAX_CONCURRENT_QUERY_RUNS,
    RouteCeiling,
    assert_call_available,
    assert_deadline_open,
    assert_discovery_available,
    assert_manifest_available,
    assert_recursion_available,
    assert_side_effect_available,
    assert_tool_available,
    envelope_for_family,
)
from smart_rag_core.query_admission.context import AuthorizedRuntimeContext
from smart_rag_core.query_admission.exceptions import (
    QueryAdmissionError,
    QueryBudgetError,
    QueryCeilingError,
    TimeoutAfterSendError,
)
from smart_rag_core.query_admission.payload import hash_query_admission_payload
from smart_rag_core.query_admission.service import (
    QueryAdmissionResult,
    QueryRunRecord,
    RunCitationRecord,
    admit_query_run,
    cancel_query_run,
    consume_query_reservation,
    get_query_run,
    heartbeat_query_run,
    list_run_citations,
    reconcile_expired_query_runs,
    record_query_llm_usage,
    record_run_restricted_evidence,
    true_up_query_reservation,
)
from smart_rag_core.query_admission.usage import execute_counted_model_call

__all__ = [
    "DEFAULT_MONTHLY_LLM_BUDGET_USD",
    "MAX_CONCURRENT_QUERY_RUNS",
    "AuthorizedRuntimeContext",
    "QueryAdmissionError",
    "QueryAdmissionResult",
    "QueryBudgetError",
    "QueryCeilingError",
    "QueryRunRecord",
    "RouteCeiling",
    "RunCitationRecord",
    "TimeoutAfterSendError",
    "admit_query_run",
    "assert_call_available",
    "assert_deadline_open",
    "assert_discovery_available",
    "assert_manifest_available",
    "assert_recursion_available",
    "assert_side_effect_available",
    "assert_tool_available",
    "cancel_query_run",
    "consume_query_reservation",
    "envelope_for_family",
    "execute_counted_model_call",
    "get_query_run",
    "hash_query_admission_payload",
    "heartbeat_query_run",
    "list_run_citations",
    "reconcile_expired_query_runs",
    "record_query_llm_usage",
    "record_run_restricted_evidence",
    "true_up_query_reservation",
]
