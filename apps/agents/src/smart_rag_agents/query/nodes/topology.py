"""Deterministic post-node routers for the query LangGraph."""

from __future__ import annotations

from smart_rag_core.query_profile.phase6_map import Phase6RouteFamily
from smart_rag_core.query_routing.knowledge_scope import NoRetrievalAnswerMode
from smart_rag_core.query_routing.models.plan import BranchKind
from smart_rag_core.query_routing.serde import plan_from_state

from smart_rag_agents.query.state import QueryGraphState


def route_after_studio_seed(state: QueryGraphState) -> str:
    """Continue to admission only when Studio seeding produced a context.

    Args:
        state: State after ``seed_studio_runtime``.

    Returns:
        ``enforce_admission`` or ``end``.
    """

    if state["status"] == "admission_rejected":
        return "end"
    return "enforce_admission"


def route_after_admission(state: QueryGraphState) -> str:
    """Continue past admission only when context was valid.

    Args:
        state: State after ``enforce_admission``.

    Returns:
        ``load_memory`` or ``end``.
    """

    if state["status"] == "admission_rejected":
        return "end"
    return "load_memory"


def route_after_plan(state: QueryGraphState) -> str:
    """Select the explicit scope path from a validated ``RetrievalPlan``.

    Args:
        state: State after ``compile_plan``.

    Returns:
        ``company_scope``, ``general_scope``, ``mixed_scope``,
        ``web_scope``, ``invalid_scope``, or ``end``.
    """

    if state["status"] in {"admission_rejected", "routing_rejected"}:
        return "end"
    raw_plan = state.get("retrieval_plan")
    if raw_plan is None:
        return "invalid_scope"
    try:
        plan = plan_from_state(raw_plan)
    except ValueError:
        return "invalid_scope"
    if plan.effective_route is Phase6RouteFamily.WEB_RESEARCH:
        if not plan.company_claim_forbidden:
            return "invalid_scope"
        if {branch.kind for branch in plan.branches} != {BranchKind.WEB_RESEARCH}:
            return "invalid_scope"
        return "web_scope"
    if plan.effective_route is Phase6RouteFamily.NO_RETRIEVAL:
        if not plan.company_claim_forbidden:
            return "invalid_scope"
        mode = plan.no_retrieval_answer_mode
        if mode is NoRetrievalAnswerMode.CLARIFICATION:
            return "mixed_scope"
        if mode in {
            NoRetrievalAnswerMode.GENERAL_MODEL,
            NoRetrievalAnswerMode.USER_TEXT_MODEL,
            NoRetrievalAnswerMode.DETERMINISTIC_CHAT,
        }:
            return "general_scope"
        return "invalid_scope"
    return "company_scope"


def route_after_prepare(state: QueryGraphState) -> str:
    """Stop on routing rejection after preparation.

    Args:
        state: State after ``prepare_query``.

    Returns:
        ``compile_plan`` or ``end``.
    """

    if state["status"] in {"admission_rejected", "routing_rejected"}:
        return "end"
    return "compile_plan"


def route_after_correction(state: QueryGraphState) -> str:
    """Continue to fusion unless admission, routing, or evidence already failed.

    Args:
        state: State after ``apply_correction``.

    Returns:
        ``fuse_evidence`` or ``end``. Exhausted retrieval
        (``insufficient_evidence``) ends without fusion, answer, or verifier.
    """

    if state["status"] in {
        "admission_rejected",
        "routing_rejected",
        "insufficient_evidence",
    }:
        return "end"
    return "fuse_evidence"


def route_after_web_scope(state: QueryGraphState) -> str:
    """Continue to verification only when Web produced a draft.

    Args:
        state: State after ``web_scope``.

    Returns:
        ``verify_answer`` or ``end``. Drafts go to verification; typed
        fail-closed statuses end.
    """

    if state["status"] in {
        "admission_rejected",
        "routing_rejected",
        "insufficient_evidence",
    }:
        return "end"
    return "verify_answer"
