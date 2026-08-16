"""Unit tests for the Phase 6 packet 2 deterministic route matrix."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError
from smart_rag_core.evaluation.classes import QueryClass
from smart_rag_core.query_admission.context import AuthorizedRuntimeContext
from smart_rag_core.query_profile.phase6_map import Phase6RouteFamily
from smart_rag_core.query_routing.branches import (
    disclose_acl_blindness,
    empty_keyword_guard,
    execute_branches,
    suppress_unauthorized_blindness,
)
from smart_rag_core.query_routing.constants import (
    BRANCH_CONCURRENCY,
    PROVISIONAL_COVERAGE_THRESHOLD,
    WHOLE_DOCUMENT_SECTION_COVERAGE,
)
from smart_rag_core.query_routing.exceptions import QueryRoutingError
from smart_rag_core.query_routing.matrix import (
    compile_retrieval_plan,
    frozen_coverage_threshold,
)
from smart_rag_core.query_routing.models import (
    REQUIRED_PREPARATION_FIELDS,
    BranchKind,
    QueryPreparation,
    RetrievalPlan,
)
from smart_rag_core.query_routing.preparation import (
    forbid_separate_rewrite_call,
    prepare_query,
)
from smart_rag_core.query_routing.serde import preparation_from_state
from smart_rag_core.retrieval.frozen_profile import (
    COVERAGE_SCORE_BASELINE,
    coverage_threshold_for,
)
from smart_rag_core.security.identity import CallerContext, UserRole


def _runtime(
    family: Phase6RouteFamily = Phase6RouteFamily.COMPOSITE,
) -> AuthorizedRuntimeContext:
    """Return a packet 1 context with a Composite envelope unless overridden.

    Args:
        family: Reserved envelope family.

    Returns:
        Frozen authorized runtime context.
    """

    now = datetime.now(UTC)
    ceilings = {
        Phase6RouteFamily.HYBRID: (25, 7, 4, Decimal("2.80")),
        Phase6RouteFamily.COMBINED: (45, 8, 4, Decimal("3.20")),
        Phase6RouteFamily.STRUCTURED_TABLE: (30, 6, 4, Decimal("2.40")),
        Phase6RouteFamily.COMPOSITE: (50, 9, 5, Decimal("3.60")),
        Phase6RouteFamily.GRAPH_INSPECTION: (10, 3, 4, Decimal("0.75")),
        Phase6RouteFamily.NO_RETRIEVAL: (25, 7, 4, Decimal("2.80")),
        Phase6RouteFamily.SCOPED_REFUSAL: (25, 7, 4, Decimal("2.80")),
    }
    deadline, calls, tools, usd = ceilings[family]
    return AuthorizedRuntimeContext(
        user_id=uuid4(),
        role=UserRole.MEMBER,
        authorization_version=1,
        conversation_id=uuid4(),
        run_id=uuid4(),
        reservation_id=uuid4(),
        reconnect=False,
        route_family=family,
        deadline_at=now + timedelta(seconds=deadline),
        recursion_limit=24,
        correction_ceiling=1,
        subquestion_ceiling=3,
        model_call_ceiling=calls,
        tool_ceiling=tools,
        discovery_ceiling=1,
        manifest_ceiling=3,
        side_effect_ceiling=1,
        reserved_amount_usd=usd,
        remaining_usd=usd,
        remaining_prompt_tokens=calls * 8000,
        remaining_completion_tokens=calls * 2000,
        optimistic_version=1,
        heartbeat_at=now,
        payload_hash="b" * 64,
        status="pending",
    )


def _prep(query: str) -> QueryPreparation:
    """Prepare one query with the deterministic zero-call path.

    Args:
        query: Original user text.

    Returns:
        Typed preparation.
    """

    return prepare_query(query, runtime=_runtime())


def _plan(query: str, **kwargs: object) -> RetrievalPlan:
    """Compile a plan for one query using a Composite reservation.

    Args:
        query: Original user text.
        **kwargs: Extra ``compile_retrieval_plan`` arguments.

    Returns:
        Frozen retrieval plan.
    """

    runtime = kwargs.pop("runtime", None)
    context = runtime if isinstance(runtime, AuthorizedRuntimeContext) else _runtime()
    return compile_retrieval_plan(_prep(query), context, **kwargs)  # pyright: ignore[reportArgumentType]


def _kinds(plan: RetrievalPlan) -> set[BranchKind]:
    """Return the set of branch kinds.

    Args:
        plan: Compiled plan.

    Returns:
        Branch kinds present on the plan.
    """

    return {branch.kind for branch in plan.branches}


_NO_LIMITATIONS: set[str] = set()
"""Shared empty limitation set for matrix cases that expect no flags."""


@pytest.mark.parametrize(
    ("query", "family", "required_kinds", "limitations"),
    [
        (
            "What is the status of INV-SR-1001?",
            Phase6RouteFamily.HYBRID,
            {BranchKind.HYBRID},
            _NO_LIMITATIONS,
        ),
        (
            "Define the Orion widget alias policy date.",
            Phase6RouteFamily.HYBRID,
            {BranchKind.HYBRID},
            _NO_LIMITATIONS,
        ),
        (
            "Which team owns INV-SR-1001 related to procurement?",
            Phase6RouteFamily.COMBINED,
            {BranchKind.HYBRID, BranchKind.GRAPH_LOCAL},
            _NO_LIMITATIONS,
        ),
        (
            "Which team owns the widget after the handoff as of 2020-01-01?",
            Phase6RouteFamily.HYBRID,
            {BranchKind.HYBRID},
            {"temporal_graph_limitation"},
        ),
        (
            "Summarize ordinary safety themes.",
            Phase6RouteFamily.HYBRID,
            {BranchKind.HYBRID},
            _NO_LIMITATIONS,
        ),
        (
            "What is the corpus-wide landscape of safety themes?",
            Phase6RouteFamily.COMBINED,
            {BranchKind.HYBRID, BranchKind.GRAPH_GLOBAL_STEERING},
            {"global_steering_only"},
        ),
        (
            "Summarize document p4-src-0001",
            Phase6RouteFamily.HYBRID,
            {BranchKind.HYBRID},
            {"whole_document_section_coverage"},
        ),
        (
            "What is not allowed for INV-SR-1001?",
            Phase6RouteFamily.HYBRID,
            {BranchKind.HYBRID},
            {"negation_unscoped"},
        ),
        (
            "Describe the unlabeled chart in the figure",
            Phase6RouteFamily.SCOPED_REFUSAL,
            {BranchKind.SCOPED_REFUSAL},
            {"media_limitation"},
        ),
        (
            "Compare PRJ-ALPHA leave days and notice period.",
            Phase6RouteFamily.HYBRID,
            {BranchKind.HYBRID},
            _NO_LIMITATIONS,
        ),
        (
            "Compare INV-SR-1001 policy and sum the Q1 sheet",
            Phase6RouteFamily.COMPOSITE,
            {BranchKind.HYBRID, BranchKind.STRUCTURED_TABLE},
            _NO_LIMITATIONS,
        ),
        (
            "sum the Q1 sheet totals",
            Phase6RouteFamily.STRUCTURED_TABLE,
            {BranchKind.STRUCTURED_TABLE},
            _NO_LIMITATIONS,
        ),
        (
            "Inspect the current graph workspace",
            Phase6RouteFamily.GRAPH_INSPECTION,
            {BranchKind.GRAPH_INSPECTION},
            {"graph_inspection_only"},
        ),
        (
            "Hello",
            Phase6RouteFamily.NO_RETRIEVAL,
            {BranchKind.NO_RETRIEVAL},
            {"no_retrieval"},
        ),
        (
            "Rewrite this paragraph without company files",
            Phase6RouteFamily.NO_RETRIEVAL,
            {BranchKind.NO_RETRIEVAL},
            {"no_retrieval"},
        ),
        (
            "maybe related to INV-SR-1001",
            Phase6RouteFamily.HYBRID,
            {BranchKind.HYBRID},
            {"low_confidence_relationship"},
        ),
    ],
)
def test_matrix_routes(
    query: str,
    family: Phase6RouteFamily,
    required_kinds: set[BranchKind],
    limitations: set[str],
) -> None:
    """Every listed route, limitation, mixed, and Composite case is deterministic."""

    plan = _plan(query)
    assert plan.effective_route is family
    assert required_kinds <= _kinds(plan)
    assert limitations <= set(plan.limitations)
    assert plan.catalog_llm_call_count == 0
    assert plan.prove_complement is False
    assert plan.branch_concurrency == BRANCH_CONCURRENCY
    if BranchKind.GRAPH_LOCAL in _kinds(plan) or BranchKind.GRAPH_HYBRID in _kinds(
        plan
    ):
        assert "temporal_graph_limitation" not in plan.limitations


def test_historical_relationship_never_has_graph_branch() -> None:
    """Historical relationships stay Hybrid with temporal_graph_limitation."""

    plan = _plan("Which team owns the widget after the handoff as of 2020-01-01?")
    assert plan.effective_route is Phase6RouteFamily.HYBRID
    assert plan.temporal_graph_limitation is True
    assert plan.historical_relationship is True
    assert not (
        {
            BranchKind.GRAPH_LOCAL,
            BranchKind.GRAPH_HYBRID,
            BranchKind.GRAPH_GLOBAL_STEERING,
        }
        & _kinds(plan)
    )


def test_whole_document_requires_section_coverage_one() -> None:
    """Whole-document claims require exactly ``section_coverage_ratio=1.0``."""

    plan = _plan("Summarize document p4-src-0001")
    assert plan.whole_document_summary is True
    assert plan.section_coverage_required == WHOLE_DOCUMENT_SECTION_COVERAGE
    refused = compile_retrieval_plan(
        _prep("Summarize document p4-src-0001"),
        _runtime(),
        section_coverage_ratio=0.5,
    )
    assert refused.effective_route is Phase6RouteFamily.SCOPED_REFUSAL
    assert "section_coverage_below_1" in refused.limitations


def test_negation_never_combined_or_complement() -> None:
    """Negation stays Hybrid and cannot prove a complement from top-k."""

    plan = _plan("What is not allowed for INV-SR-1001?")
    assert plan.effective_route is Phase6RouteFamily.HYBRID
    assert plan.prove_complement is False
    assert BranchKind.GRAPH_LOCAL not in _kinds(plan)
    with pytest.raises(ValidationError):
        RetrievalPlan.model_validate({**plan.model_dump(), "prove_complement": True})


def test_media_refusal_cannot_answer() -> None:
    """Unsupported media cannot become an answer family."""

    plan = _plan("Describe the unlabeled chart in the figure")
    assert plan.effective_route is Phase6RouteFamily.SCOPED_REFUSAL
    assert plan.media_answer_forbidden is True


def test_no_retrieval_forbids_company_claim() -> None:
    """NoRetrieval cannot make company-knowledge claims."""

    plan = _plan("Hello")
    assert plan.effective_route is Phase6RouteFamily.NO_RETRIEVAL
    assert plan.company_claim_forbidden is True
    with pytest.raises(ValidationError):
        RetrievalPlan.model_validate(
            {**plan.model_dump(), "company_claim_forbidden": False}
        )


def test_graph_only_is_inspection_not_answer() -> None:
    """Graph-only remains inspection and cannot be an answer fallback."""

    plan = _plan("Inspect the current graph workspace")
    assert plan.effective_route is Phase6RouteFamily.GRAPH_INSPECTION
    assert plan.graph_as_answer_forbidden is True
    with pytest.raises(ValidationError):
        RetrievalPlan.model_validate(
            {**plan.model_dump(), "graph_as_answer_forbidden": False}
        )


def test_caption_media_may_use_hybrid() -> None:
    """Caption/OCR language lets a media query take ordinary Hybrid."""

    plan = _plan("What does the caption say under the unlabeled figure?")
    assert plan.effective_route is Phase6RouteFamily.HYBRID
    assert plan.media_answer_forbidden is False


def test_client_combined_cannot_enlarge_hybrid_reservation() -> None:
    """A Combined matrix result cannot enlarge a Hybrid reservation."""

    plan = compile_retrieval_plan(
        _prep("Which team owns INV-SR-1001 related to procurement?"),
        _runtime(Phase6RouteFamily.HYBRID),
    )
    assert plan.requested_route is Phase6RouteFamily.HYBRID
    assert plan.effective_route is Phase6RouteFamily.HYBRID
    assert plan.fallback_reason == "envelope_cannot_enlarge"
    assert BranchKind.GRAPH_LOCAL not in _kinds(plan)


def test_production_manual_override_rejected() -> None:
    """Production surfaces reject client manual routing."""

    with pytest.raises(QueryRoutingError, match="production_manual_override"):
        compile_retrieval_plan(
            _prep("What is the status of INV-SR-1001?"),
            _runtime(),
            requested_manual_route="combined",
        )


def test_fourth_subquestion_rejected() -> None:
    """A fourth subquestion fails closed instead of silently truncating."""

    prep = _prep("Compare PRJ-ALPHA leave days and notice period.")
    with pytest.raises(ValidationError):
        preparation_from_state(
            {
                **prep.model_dump(mode="json"),
                "decomposition": (
                    "one",
                    "two",
                    "three",
                    "four",
                ),
            }
        )


def test_preparation_contains_every_required_field() -> None:
    """One typed preparation result contains every required field."""

    prep = _prep("What is the status of INV-SR-1001?")
    dumped = prep.model_dump()
    assert REQUIRED_PREPARATION_FIELDS <= set(dumped)
    assert prep.original == prep.original_fallback_variant
    assert prep.model_calls == 0
    assert prep.timezone == "UTC"


def test_profile_schema_omission_fails() -> None:
    """Omitting a required preparation field is a schema failure."""

    with pytest.raises(ValidationError):
        QueryPreparation.model_validate({"original": "hi"})


def test_original_query_loss_fails() -> None:
    """The original query cannot be replaced by the rewrite fallback."""

    prep = _prep("What is the status of INV-SR-1001?")
    with pytest.raises(ValidationError):
        preparation_from_state(
            {**prep.model_dump(mode="json"), "original_fallback_variant": "rewritten"}
        )


def test_separate_rewrite_call_forbidden() -> None:
    """A second standalone rewrite call is forbidden."""

    with pytest.raises(QueryRoutingError, match="separate_rewrite_call"):
        forbid_separate_rewrite_call()


def test_model_assisted_prep_uses_at_most_one_call() -> None:
    """Rewrite plus profile share one structured call and keep fidelity."""

    calls = {"n": 0}

    def _caller(query: str, memory: object) -> object:
        del memory
        calls["n"] += 1
        from smart_rag_core.query_routing.models import PreparationModelPayload

        return PreparationModelPayload(
            rewrite=query + " please",
            confidence=0.8,
            hl_keywords=("status",),
            ll_keywords=("INV-SR-1001",),
        )

    prep = prepare_query(
        "What is the status of INV-SR-1001?",
        runtime=_runtime(),
        model_caller=_caller,  # pyright: ignore[reportArgumentType]
        force_model=True,
    )
    assert calls["n"] == 1
    assert prep.model_calls == 1
    assert prep.original == "What is the status of INV-SR-1001?"
    assert prep.intent_fidelity > 0.0
    assert prep.entity_fidelity == 1.0
    assert prep.rewrite is not None


def test_rewrite_dropping_entity_keeps_original() -> None:
    """A rewrite that drops codes is discarded; original remains the fallback."""

    def _caller(query: str, memory: object) -> object:
        del query, memory
        from smart_rag_core.query_routing.models import PreparationModelPayload

        return PreparationModelPayload(rewrite="status of the invoice", confidence=0.9)

    prep = prepare_query(
        "What is the status of INV-SR-1001?",
        runtime=_runtime(),
        model_caller=_caller,  # pyright: ignore[reportArgumentType]
        force_model=True,
    )
    assert prep.rewrite is None
    assert prep.original_fallback_variant == prep.original
    assert prep.entity_fidelity < 1.0


def test_coverage_threshold_not_retuned() -> None:
    """Phase 6 does not retune the frozen 0.65 coverage threshold."""

    assert COVERAGE_SCORE_BASELINE == 0.65
    assert PROVISIONAL_COVERAGE_THRESHOLD == 0.65
    for query_class in QueryClass:
        assert coverage_threshold_for(query_class) == pytest.approx(0.65)
    prep = _prep("What is the status of INV-SR-1001?")
    assert frozen_coverage_threshold(prep) == pytest.approx(0.65)
    plan = _plan("What is the status of INV-SR-1001?")
    with pytest.raises(ValidationError):
        RetrievalPlan.model_validate({**plan.model_dump(), "coverage_threshold": 0.40})
    with pytest.raises(ValidationError):
        RetrievalPlan.model_validate(
            {**plan.model_dump(), "section_coverage_required": 0.65}
        )


def test_empty_keywords_never_extract() -> None:
    """Empty graph keywords fail closed instead of a hidden extract call."""

    with pytest.raises(QueryRoutingError, match="empty_keywords"):
        empty_keyword_guard((), ("entity",))
    with pytest.raises(QueryRoutingError, match="empty_keywords"):
        empty_keyword_guard(("topic",), ())


def test_unauthorized_blindness_suppressed() -> None:
    """Unauthorized callers receive silence, not a revealing zero."""

    caller = CallerContext(
        user_id=str(uuid4()),
        role=UserRole.VIEWER,
        authorization_version=1,
    )
    assert (
        disclose_acl_blindness(caller=caller, count=7, authorized_visibility=False)
        is None
    )
    assert suppress_unauthorized_blindness(role=UserRole.VIEWER, count=7) is None
    assert (
        disclose_acl_blindness(caller=caller, count=7, authorized_visibility=True) == 7
    )


def test_branch_fan_out_rejected() -> None:
    """Server concurrency cannot be raised above two."""

    plan = _plan("What is the status of INV-SR-1001?")
    prep = _prep("What is the status of INV-SR-1001?")
    with pytest.raises(QueryRoutingError, match="branch_fan_out"):
        execute_branches(plan, prep, _runtime(), branch_concurrency=8)


def test_historical_execute_rejects_graph_path() -> None:
    """Executing a graph branch on a historical plan fails closed."""

    from smart_rag_core.query_routing.models import BranchSpec

    prep = _prep("Which team owns the widget after the handoff as of 2020-01-01?")
    plan = compile_retrieval_plan(prep, _runtime())
    poisoned = plan.model_copy(
        update={
            "branches": (
                BranchSpec(
                    branch_id="bad-graph",
                    kind=BranchKind.GRAPH_LOCAL,
                    family=Phase6RouteFamily.COMBINED,
                    query_text=prep.original,
                    parallel_group=0,
                    hl_keywords=("relationship_multi_hop",),
                    ll_keywords=("widget",),
                ),
            )
        }
    )
    with pytest.raises(QueryRoutingError, match="historical_graph_path"):
        execute_branches(poisoned, prep, _runtime())


def test_unbound_combined_degrades_without_graph_prose() -> None:
    """Missing LightRAG degrades Combined to Hybrid with graph_unavailable."""

    plan = _plan("Which team owns INV-SR-1001 related to procurement?")
    prep = _prep("Which team owns INV-SR-1001 related to procurement?")
    results = execute_branches(plan, prep, _runtime())
    graphish = [
        item
        for item in results
        if item.kind is BranchKind.HYBRID
        and item.fallback_reason == "graph_unavailable"
    ]
    assert graphish
    assert all(item.graph_prose_used is False for item in results)
    assert all(item.bm25_snippets_used is False for item in results)
    assert all(item.keyword_extract_count == 0 for item in results)
    assert all(
        item.run_id == results[0].run_id
        and item.reservation_id == results[0].reservation_id
        for item in results
    )
