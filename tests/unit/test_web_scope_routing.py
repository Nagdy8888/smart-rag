"""Four-mode Auto/Web admission, routing, envelope, and fail-closed stub."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import cast
from uuid import uuid4

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from smart_rag_agents.query.deps import QueryGraphDeps
from smart_rag_agents.query.graph import build_query_graph
from smart_rag_agents.query.nodes.topology import route_after_plan
from smart_rag_agents.query.state import pending_query_state
from smart_rag_api.schemas.fastapi_security import SubmitMessageRequest
from smart_rag_api.services.http_errors import raise_admission_http
from smart_rag_api.services.query_runs import QueryRunService
from smart_rag_core.query_admission.ceilings import envelope_for_family
from smart_rag_core.query_admission.context import AuthorizedRuntimeContext
from smart_rag_core.query_admission.exceptions import QueryAdmissionError
from smart_rag_core.query_answer.generate import generate_answer
from smart_rag_core.query_fusion import fusion_config_hash
from smart_rag_core.query_fusion.models import FusionAlgorithm, FusionResult
from smart_rag_core.query_profile.phase6_map import Phase6RouteFamily
from smart_rag_core.query_profile.schemas import query_profile_json_schema
from smart_rag_core.query_routing.envelope import clamp_family_to_reservation
from smart_rag_core.query_routing.exceptions import QueryRoutingError
from smart_rag_core.query_routing.knowledge_scope import (
    KnowledgeScope,
    apply_requested_search_scope,
    classify_knowledge_scope,
    has_web_intent,
)
from smart_rag_core.query_routing.matrix import compile_retrieval_plan
from smart_rag_core.query_routing.models import BranchKind
from smart_rag_core.query_routing.preparation import prepare_query
from smart_rag_core.search_scope import RequestedSearchScope
from smart_rag_core.security.identity import CallerContext, UserRole
from smart_rag_core.sse.catalog import AnswerOriginPayload
from smart_rag_core.tools.catalog import default_registry
from smart_rag_core.tools.constants import CORE_FORBIDDEN_TOOL_KEYS

from tests.support.scope_graph import COMPANY_ONLY_NODES, SpyHybrid
from tests.support.typed_graph import compile_state_graph


def _runtime(
    *,
    requested_search_scope: RequestedSearchScope = RequestedSearchScope.AUTO,
    route_family: Phase6RouteFamily = Phase6RouteFamily.COMPOSITE,
) -> AuthorizedRuntimeContext:
    """Return an admission envelope for routing tests.

    Args:
        requested_search_scope: Client source preference.
        route_family: Reserved family.

    Returns:
        Frozen authorized runtime context.
    """

    now = datetime.now(UTC)
    ceiling = envelope_for_family(route_family)
    return AuthorizedRuntimeContext(
        user_id=uuid4(),
        role=UserRole.MEMBER,
        authorization_version=1,
        conversation_id=uuid4(),
        run_id=uuid4(),
        reservation_id=uuid4(),
        reconnect=False,
        route_family=route_family,
        requested_search_scope=requested_search_scope,
        deadline_at=now + timedelta(seconds=ceiling.deadline_seconds),
        recursion_limit=ceiling.recursion_limit,
        correction_ceiling=ceiling.correction_ceiling,
        subquestion_ceiling=ceiling.subquestion_ceiling,
        model_call_ceiling=ceiling.model_call_ceiling,
        tool_ceiling=ceiling.tool_ceiling,
        discovery_ceiling=ceiling.discovery_ceiling,
        manifest_ceiling=ceiling.manifest_ceiling,
        side_effect_ceiling=ceiling.side_effect_ceiling,
        reserved_amount_usd=ceiling.envelope_usd,
        remaining_usd=ceiling.envelope_usd,
        remaining_prompt_tokens=ceiling.envelope_prompt_tokens,
        remaining_completion_tokens=ceiling.envelope_completion_tokens,
        optimistic_version=1,
        heartbeat_at=now,
        payload_hash="b" * 64,
        status="pending",
    )


def _prep(
    query: str,
    *,
    requested_search_scope: RequestedSearchScope = RequestedSearchScope.AUTO,
    route_family: Phase6RouteFamily = Phase6RouteFamily.COMPOSITE,
):
    """Prepare one query on the deterministic path.

    Args:
        query: Original user text.
        requested_search_scope: Client source preference.
        route_family: Reserved family.

    Returns:
        Typed preparation.
    """

    return prepare_query(
        query,
        runtime=_runtime(
            requested_search_scope=requested_search_scope,
            route_family=route_family,
        ),
        requested_search_scope=requested_search_scope,
    )


def _plan(
    query: str,
    *,
    requested_search_scope: RequestedSearchScope = RequestedSearchScope.AUTO,
    route_family: Phase6RouteFamily = Phase6RouteFamily.COMPOSITE,
):
    """Compile a retrieval plan for one query.

    Args:
        query: Original user text.
        requested_search_scope: Client source preference.
        route_family: Reserved family.

    Returns:
        Frozen retrieval plan.
    """

    runtime = _runtime(
        requested_search_scope=requested_search_scope,
        route_family=route_family,
    )
    return compile_retrieval_plan(
        prepare_query(
            query,
            runtime=runtime,
            requested_search_scope=requested_search_scope,
        ),
        runtime,
    )


def _planned_state(
    query: str,
    *,
    requested_search_scope: RequestedSearchScope = RequestedSearchScope.AUTO,
):
    """Compile a retrieval plan onto pending graph state.

    Args:
        query: Original user text.
        requested_search_scope: Client source preference.

    Returns:
        Planned query-graph state mapping.
    """

    plan = _plan(query, requested_search_scope=requested_search_scope)
    state = pending_query_state(user_query=query)
    state["status"] = "planned"
    state["retrieval_plan"] = plan.model_dump(mode="json")
    return state


def _visit_nodes(
    query: str,
    *,
    hybrid: SpyHybrid | None = None,
    requested_search_scope: RequestedSearchScope = RequestedSearchScope.AUTO,
    web_search_enabled: bool = False,
    web_search_configured: bool = False,
) -> list[str]:
    """Compile and stream one admitted run, returning visited node names.

    Args:
        query: Original user text.
        hybrid: Optional Hybrid spy.
        requested_search_scope: Client source preference.
        web_search_enabled: Web feature flag on deps.
        web_search_configured: Exa key presence flag on deps.

    Returns:
        Node names emitted by LangGraph ``updates`` stream mode.
    """

    deps = QueryGraphDeps(
        hybrid_retriever=hybrid,
        web_search_enabled=web_search_enabled,
        web_search_configured=web_search_configured,
    )
    compiled = compile_state_graph(build_query_graph(deps))
    state = pending_query_state(
        _runtime(requested_search_scope=requested_search_scope).model_dump(mode="json"),
        user_query=query,
    )
    visited: list[str] = []
    for chunk in compiled.stream(state, stream_mode="updates"):
        if isinstance(chunk, dict):
            visited.extend(str(name) for name in cast(dict[object, object], chunk))
    return visited


def test_auto_company_general_web_conflict_and_greeting() -> None:
    """Auto settles company, general, web, conflict, and greeting as specified."""

    greeting = classify_knowledge_scope("Hello")
    assert greeting.knowledge_scope is KnowledgeScope.GENERAL_KNOWLEDGE
    company = classify_knowledge_scope("What is our refund period?")
    assert company.knowledge_scope is KnowledgeScope.COMPANY_DOCUMENTS
    general = classify_knowledge_scope("What is the capital of France?")
    assert general.knowledge_scope is KnowledgeScope.GENERAL_KNOWLEDGE
    web = classify_knowledge_scope("search the web for latest news")
    assert web.knowledge_scope is KnowledgeScope.WEB
    assert has_web_intent("look online for the score")
    latest_only = classify_knowledge_scope("What is our latest refund period?")
    assert latest_only.knowledge_scope is KnowledgeScope.COMPANY_DOCUMENTS
    conflict = classify_knowledge_scope("search the web for our refund period")
    assert conflict.knowledge_scope is KnowledgeScope.AMBIGUOUS
    unavailable = classify_knowledge_scope(
        "Why is the sky blue?",
        model_available=False,
    )
    assert unavailable.knowledge_scope is KnowledgeScope.GENERAL_KNOWLEDGE
    assert unavailable.knowledge_scope is not KnowledgeScope.WEB


def test_forced_web_never_searches_company() -> None:
    """Forced Web compiles to one WEB_RESEARCH branch with company forbidden."""

    plan = _plan(
        "search the web for latest news",
        requested_search_scope=RequestedSearchScope.WEB,
        route_family=Phase6RouteFamily.WEB_RESEARCH,
    )
    assert plan.knowledge_scope is KnowledgeScope.WEB
    assert plan.effective_route is Phase6RouteFamily.WEB_RESEARCH
    assert plan.company_claim_forbidden is True
    assert {branch.kind for branch in plan.branches} == {BranchKind.WEB_RESEARCH}
    hybrid = SpyHybrid()
    nodes = _visit_nodes(
        "search the web for latest news",
        hybrid=hybrid,
        requested_search_scope=RequestedSearchScope.WEB,
    )
    assert hybrid.calls == 0
    assert "web_scope" in nodes
    assert "company_scope" not in nodes
    assert COMPANY_ONLY_NODES.isdisjoint(nodes)
    assert "verify_answer" not in nodes


def test_forced_company_never_searches_web() -> None:
    """Forced Company files never emits a Web branch."""

    plan = _plan(
        "search the web for latest news",
        requested_search_scope=RequestedSearchScope.COMPANY_DOCUMENTS,
    )
    assert plan.knowledge_scope is KnowledgeScope.COMPANY_DOCUMENTS
    assert plan.effective_route is not Phase6RouteFamily.WEB_RESEARCH
    assert all(branch.kind is not BranchKind.WEB_RESEARCH for branch in plan.branches)


def test_forced_web_with_company_signals_clarifies() -> None:
    """Explicit Web plus company signals uses mixed clarification, not Exa."""

    automatic = classify_knowledge_scope("What is our refund period?")
    applied = apply_requested_search_scope(
        "What is our refund period?",
        automatic,
        RequestedSearchScope.WEB,
    )
    assert applied.knowledge_scope is KnowledgeScope.AMBIGUOUS
    assert route_after_plan(_planned_state("What is our refund period?")) == (
        "company_scope"
    )
    web_forced = _planned_state(
        "What is our refund period?",
        requested_search_scope=RequestedSearchScope.WEB,
    )
    assert route_after_plan(web_forced) == "mixed_scope"


def test_disabled_web_is_typed_fail_closed() -> None:
    """Disabled and unconfigured Web never become a silent general answer."""

    service = QueryRunService("postgresql://invalid", web_search_enabled=False)
    caller = CallerContext(
        user_id="11111111-1111-4111-8111-111111111111",
        role=UserRole.MEMBER,
        authorization_version=1,
    )
    with pytest.raises(QueryAdmissionError, match="web_search_disabled"):
        service.submit_auto_message(
            caller,
            conversation_id=uuid4(),
            idempotency_key=uuid4(),
            message="search the web for latest news",
            requested_search_scope=RequestedSearchScope.WEB,
        )
    unconfigured = QueryRunService(
        "postgresql://invalid",
        web_search_enabled=True,
        web_search_configured=False,
    )
    with pytest.raises(QueryAdmissionError, match="web_search_unconfigured"):
        unconfigured.submit_auto_message(
            caller,
            conversation_id=uuid4(),
            idempotency_key=uuid4(),
            message="search the web for latest news",
            requested_search_scope=RequestedSearchScope.WEB,
        )
    with pytest.raises(HTTPException) as disabled_http:
        raise_admission_http(QueryAdmissionError("web_search_disabled"))
    assert disabled_http.value.status_code == 503
    assert disabled_http.value.detail == "web_search_disabled"
    with pytest.raises(HTTPException) as unconfigured_http:
        raise_admission_http(QueryAdmissionError("web_search_unconfigured"))
    assert unconfigured_http.value.status_code == 503
    assert unconfigured_http.value.detail == "web_search_unconfigured"
    nodes = _visit_nodes("search the web for latest news")
    assert "web_scope" in nodes
    assert "general_scope" not in nodes
    assert "company_scope" not in nodes


def test_web_envelope_never_hybrid_clamps() -> None:
    """A Web plan that cannot fit the reservation rejects instead of Hybrid."""

    runtime = _runtime(route_family=Phase6RouteFamily.HYBRID)
    prep = prepare_query("search the web for latest news", runtime=runtime)
    with pytest.raises(QueryRoutingError, match="web_envelope_cannot_fit"):
        compile_retrieval_plan(prep, runtime)
    composite = _runtime(route_family=Phase6RouteFamily.COMPOSITE)
    family, reason = clamp_family_to_reservation(
        Phase6RouteFamily.WEB_RESEARCH, composite
    )
    assert family is Phase6RouteFamily.WEB_RESEARCH
    assert reason is None
    reserved = _runtime(route_family=Phase6RouteFamily.WEB_RESEARCH)
    family, reason = clamp_family_to_reservation(
        Phase6RouteFamily.WEB_RESEARCH, reserved
    )
    assert family is Phase6RouteFamily.WEB_RESEARCH
    assert reason is None


def test_openapi_includes_web_scope_and_answer_origin() -> None:
    """Public contracts accept ``web`` search scope and ``answer_origin=web``."""

    schema = SubmitMessageRequest.model_json_schema()
    defs = schema.get("$defs") or schema.get("definitions") or {}
    scope = defs.get("RequestedSearchScope") if isinstance(defs, dict) else None
    if not isinstance(scope, dict):
        scope = schema
    enum_values = scope.get("enum")
    assert isinstance(enum_values, list)
    assert "web" in enum_values
    assert "auto" in enum_values
    origin = AnswerOriginPayload(origin="web")
    assert origin.origin == "web"
    properties = query_profile_json_schema()["properties"]
    assert isinstance(properties, dict)
    knowledge = properties["knowledge_scope"]
    assert isinstance(knowledge, dict)
    any_of = knowledge["anyOf"]
    assert isinstance(any_of, list)
    string_enum = next(
        item for item in any_of if isinstance(item, dict) and "enum" in item
    )
    assert "web" in string_enum["enum"]


def test_optional_catalog_still_has_no_web_search() -> None:
    """Web research is not an optional-tool catalog key."""

    keys = {item.tool_key for item in default_registry()}
    assert "web_search" not in keys
    assert "web_search" in CORE_FORBIDDEN_TOOL_KEYS
    assert keys.isdisjoint(CORE_FORBIDDEN_TOOL_KEYS)


def test_company_insufficient_never_becomes_web() -> None:
    """Company retrieval plans never fall back to Web research."""

    plan = _plan("What is our refund period?")
    assert plan.effective_route is not Phase6RouteFamily.WEB_RESEARCH
    assert all(branch.kind is not BranchKind.WEB_RESEARCH for branch in plan.branches)


def test_generate_answer_refuses_unbound_web() -> None:
    """Direct generate_answer never fabricates a Web success."""

    fusion = FusionResult(
        algorithm=FusionAlgorithm.RESOLVED_PATH_FUSION,
        config_hash=fusion_config_hash(FusionAlgorithm.RESOLVED_PATH_FUSION),
        requested_route="web_research",
        effective_route="web_research",
        evidence=(),
        graph_discovered_only_ratio=0.0,
    )
    payload = generate_answer(
        fusion=fusion,
        tables=(),
        user_query="search the web for latest news",
        caller=None,
        already_generated=0,
        company_claim_forbidden=True,
        graph_as_answer_forbidden=False,
        knowledge_scope=KnowledgeScope.WEB,
    )
    assert payload.status == "refused"
    assert payload.answer_origin is KnowledgeScope.WEB


def test_invalid_requested_scope_still_rejected_by_schema() -> None:
    """Unknown search_scope strings remain 422 at the request model."""

    with pytest.raises(ValidationError):
        SubmitMessageRequest.model_validate(
            {"message": "hello", "search_scope": "world_knowledge"}
        )
