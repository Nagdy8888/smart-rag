"""Unit tests for typed knowledge-scope classification and route mapping."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

from smart_rag_core.query_admission.context import AuthorizedRuntimeContext
from smart_rag_core.query_profile.phase6_map import Phase6RouteFamily
from smart_rag_core.query_routing.knowledge_scope import (
    KnowledgeScope,
    NoRetrievalAnswerMode,
    ScopeDegradationReason,
    classify_knowledge_scope,
    scope_requires_model,
)
from smart_rag_core.query_routing.knowledge_scope_preference import (
    apply_requested_search_scope,
)
from smart_rag_core.query_routing.matrix import compile_retrieval_plan
from smart_rag_core.query_routing.models import (
    BranchKind,
    MemoryRecord,
    PreparationModelPayload,
    QueryPreparation,
    RetrievalPlan,
)
from smart_rag_core.query_routing.preparation import prepare_query
from smart_rag_core.query_routing.signals import (
    is_greeting,
    is_product_help,
    is_small_talk,
)
from smart_rag_core.search_scope import RequestedSearchScope
from smart_rag_core.security.identity import UserRole


def _runtime() -> AuthorizedRuntimeContext:
    """Return a Composite admission envelope for deterministic prep tests.

    Returns:
        Frozen authorized runtime context.
    """

    now = datetime.now(UTC)
    return AuthorizedRuntimeContext(
        user_id=uuid4(),
        role=UserRole.MEMBER,
        authorization_version=1,
        conversation_id=uuid4(),
        run_id=uuid4(),
        reservation_id=uuid4(),
        reconnect=False,
        route_family=Phase6RouteFamily.COMPOSITE,
        deadline_at=now + timedelta(seconds=50),
        recursion_limit=24,
        correction_ceiling=1,
        subquestion_ceiling=3,
        model_call_ceiling=9,
        tool_ceiling=5,
        discovery_ceiling=1,
        manifest_ceiling=3,
        side_effect_ceiling=1,
        reserved_amount_usd=Decimal("3.60"),
        remaining_usd=Decimal("3.60"),
        remaining_prompt_tokens=72000,
        remaining_completion_tokens=18000,
        optimistic_version=1,
        heartbeat_at=now,
        payload_hash="b" * 64,
        status="pending",
    )


def _prep(
    query: str,
    *,
    requested_search_scope: RequestedSearchScope = RequestedSearchScope.AUTO,
) -> QueryPreparation:
    """Prepare one query on the deterministic zero-call path.

    Args:
        query: Original user text.
        requested_search_scope: Client source preference.

    Returns:
        Typed preparation.
    """

    return prepare_query(
        query,
        runtime=_runtime(),
        requested_search_scope=requested_search_scope,
    )


def _plan(
    query: str,
    *,
    requested_search_scope: RequestedSearchScope = RequestedSearchScope.AUTO,
) -> RetrievalPlan:
    """Compile a retrieval plan for one query.

    Args:
        query: Original user text.
        requested_search_scope: Client source preference.

    Returns:
        Frozen retrieval plan.
    """

    return compile_retrieval_plan(
        _prep(query, requested_search_scope=requested_search_scope),
        _runtime(),
    )


def test_full_greeting_is_general_knowledge() -> None:
    """A complete greeting uses the general-chat model, not a canned line."""

    assert is_greeting("Hi") is True
    assert scope_requires_model("Hi") is True
    decision = classify_knowledge_scope("Hi")
    assert decision.knowledge_scope is KnowledgeScope.GENERAL_KNOWLEDGE
    assert (
        decision.scope_degradation_reason is ScopeDegradationReason.PROFILE_UNAVAILABLE
    )
    prep = _prep("Hello")
    plan = _plan("Hello")
    assert prep.knowledge_scope is KnowledgeScope.GENERAL_KNOWLEDGE
    assert prep.scope_degradation_reason is ScopeDegradationReason.PROFILE_UNAVAILABLE
    assert prep.model_calls == 0
    assert plan.effective_route is Phase6RouteFamily.NO_RETRIEVAL
    assert plan.no_retrieval_answer_mode is NoRetrievalAnswerMode.GENERAL_MODEL
    assert plan.company_claim_forbidden is True
    assert {branch.kind for branch in plan.branches} == {BranchKind.NO_RETRIEVAL}


def test_product_help_is_general_knowledge() -> None:
    """Product-help and identity prompts are general-model, not clarification."""

    for query in (
        "What can you do?",
        "How can you help me?",
        "who are you",
        "Who are you?",
        "What are you?",
    ):
        assert is_product_help(query) is True, query
        decision = classify_knowledge_scope(query)
        assert decision.knowledge_scope is KnowledgeScope.GENERAL_KNOWLEDGE, query
        plan = _plan(query)
        assert plan.knowledge_scope is KnowledgeScope.GENERAL_KNOWLEDGE, query
        assert plan.no_retrieval_answer_mode is NoRetrievalAnswerMode.GENERAL_MODEL
        assert plan.effective_route is Phase6RouteFamily.NO_RETRIEVAL
        assert not any(
            branch.kind
            in {BranchKind.HYBRID, BranchKind.GRAPH_LOCAL, BranchKind.STRUCTURED_TABLE}
            for branch in plan.branches
        )


def test_general_fixtures_are_general_knowledge() -> None:
    """Mock-mode world-knowledge fixtures do not open retrieval."""

    for query in ("What is the capital of France?", "Explain photosynthesis"):
        decision = classify_knowledge_scope(query)
        assert decision.knowledge_scope is KnowledgeScope.GENERAL_KNOWLEDGE
        plan = _plan(query)
        assert plan.knowledge_scope is KnowledgeScope.GENERAL_KNOWLEDGE
        assert plan.no_retrieval_answer_mode is NoRetrievalAnswerMode.GENERAL_MODEL
        assert plan.effective_route is Phase6RouteFamily.NO_RETRIEVAL


def test_rewrite_with_supplied_text_is_user_text() -> None:
    """A rewrite of caller-supplied text is user-supplied text, not RAG."""

    query = "Rewrite this paragraph: The sky is blue and wide."
    decision = classify_knowledge_scope(query)
    assert decision.knowledge_scope is KnowledgeScope.USER_SUPPLIED_TEXT
    plan = _plan(query)
    assert plan.no_retrieval_answer_mode is NoRetrievalAnswerMode.USER_TEXT_MODEL
    assert plan.effective_route is Phase6RouteFamily.NO_RETRIEVAL


def test_company_signals_select_documents() -> None:
    """Invoice, our, document, table, relationship, summary, and graph stay RAG."""

    cases = (
        "What is the status of INV-SR-1001?",
        "What is our refund period?",
        "Summarize document p4-src-0001",
        "sum the Q1 sheet totals",
        "Which team owns INV-SR-1001 related to procurement?",
        "Summarize ordinary safety themes.",
        "Inspect the current graph workspace",
    )
    for query in cases:
        decision = classify_knowledge_scope(query)
        assert decision.knowledge_scope is KnowledgeScope.COMPANY_DOCUMENTS, query
        assert decision.company_signal is True
        prep = _prep(query)
        assert prep.knowledge_scope is KnowledgeScope.COMPANY_DOCUMENTS
        if "inspect" in query.lower():
            continue
        plan = _plan(query)
        assert plan.no_retrieval_answer_mode is None
        assert plan.knowledge_scope is KnowledgeScope.COMPANY_DOCUMENTS


def test_greeting_prefix_plus_company_stays_documents() -> None:
    """A polite prefix does not hide a company-document question."""

    query = "Hi, what is our refund period?"
    assert is_greeting(query) is False
    decision = classify_knowledge_scope(query)
    assert decision.knowledge_scope is KnowledgeScope.COMPANY_DOCUMENTS
    plan = _plan(query)
    assert plan.effective_route is Phase6RouteFamily.HYBRID
    assert plan.no_retrieval_answer_mode is None


def test_mixed_general_and_company_is_ambiguous() -> None:
    """Mixed general plus company questions ask for clarification."""

    query = "What is the capital of France and what is our refund period?"
    decision = classify_knowledge_scope(query)
    assert decision.knowledge_scope is KnowledgeScope.AMBIGUOUS
    plan = _plan(query)
    assert plan.effective_route is Phase6RouteFamily.NO_RETRIEVAL
    assert plan.no_retrieval_answer_mode is NoRetrievalAnswerMode.CLARIFICATION
    assert plan.company_claim_forbidden is True
    assert not any(branch.kind is BranchKind.HYBRID for branch in plan.branches)


def test_isolated_policy_is_not_a_company_signal() -> None:
    """The word policy alone does not force company-document scope."""

    decision = classify_knowledge_scope("Explain monetary policy")
    assert decision.company_signal is False
    assert decision.knowledge_scope is KnowledgeScope.GENERAL_KNOWLEDGE
    assert (
        decision.scope_degradation_reason is ScopeDegradationReason.PROFILE_UNAVAILABLE
    )


def test_low_confidence_and_invalid_scope_degrade_general() -> None:
    """Unavailable, invalid, or low-confidence model output is not mixed."""

    unavailable = classify_knowledge_scope(
        "Why is the sky blue?",
        model_available=False,
    )
    assert unavailable.knowledge_scope is KnowledgeScope.GENERAL_KNOWLEDGE
    assert (
        unavailable.scope_degradation_reason
        is ScopeDegradationReason.PROFILE_UNAVAILABLE
    )
    invalid = classify_knowledge_scope(
        "Why is the sky blue?",
        model_scope="not_a_scope",
        model_confidence=0.99,
        model_available=True,
    )
    assert invalid.knowledge_scope is KnowledgeScope.GENERAL_KNOWLEDGE
    assert invalid.scope_degradation_reason is ScopeDegradationReason.PROFILE_MALFORMED
    low = classify_knowledge_scope(
        "Why is the sky blue?",
        model_scope=KnowledgeScope.GENERAL_KNOWLEDGE.value,
        model_confidence=0.79,
        model_available=True,
    )
    assert low.knowledge_scope is KnowledgeScope.GENERAL_KNOWLEDGE
    assert low.scope_degradation_reason is ScopeDegradationReason.PROFILE_LOW_CONFIDENCE
    assert low.confidence == 0.79


def test_company_guard_overrides_malicious_general_model() -> None:
    """A company signal overrides a model result of general knowledge."""

    calls = {"n": 0}

    def _caller(query: str, memory: object) -> PreparationModelPayload:
        """Return a malicious general-knowledge scope.

        Args:
            query: Unused original query.
            memory: Unused memory snapshot.

        Returns:
            One structured payload claiming general knowledge.
        """

        del query, memory
        calls["n"] += 1
        return PreparationModelPayload(
            knowledge_scope=KnowledgeScope.GENERAL_KNOWLEDGE.value,
            knowledge_scope_confidence=0.99,
            confidence=0.99,
        )

    prep = prepare_query(
        "What is our refund period?",
        runtime=_runtime(),
        model_caller=_caller,
        force_model=True,
    )
    assert calls["n"] == 1
    assert prep.knowledge_scope is KnowledgeScope.COMPANY_DOCUMENTS
    assert prep.model_calls == 1


def test_unresolved_scope_uses_one_preparation_call() -> None:
    """Unresolved natural language spends the one existing preparation call."""

    calls = {"n": 0}

    def _caller(query: str, memory: object) -> PreparationModelPayload:
        """Classify remaining scope as general knowledge.

        Args:
            query: Unused original query.
            memory: Unused memory snapshot.

        Returns:
            One structured payload.
        """

        del query, memory
        calls["n"] += 1
        return PreparationModelPayload(
            knowledge_scope=KnowledgeScope.GENERAL_KNOWLEDGE.value,
            knowledge_scope_confidence=0.91,
            confidence=0.91,
        )

    prep = prepare_query(
        "Why is the sky blue?",
        runtime=_runtime(),
        model_caller=_caller,
    )
    assert calls["n"] == 1
    assert prep.model_calls == 1
    assert prep.knowledge_scope is KnowledgeScope.GENERAL_KNOWLEDGE

    calls["n"] = 0
    company = prepare_query(
        "What is the status of INV-SR-1001?",
        runtime=_runtime(),
        model_caller=_caller,
    )
    assert calls["n"] == 0
    assert company.model_calls == 0
    assert company.knowledge_scope is KnowledgeScope.COMPANY_DOCUMENTS


def test_company_followup_memory_keeps_document_scope() -> None:
    """An unresolved follow-up after a cited answer remains company scope."""

    memory = (
        MemoryRecord(
            message_id="11111111-1111-1111-1111-111111111111",
            role="assistant",
            content="INV-SR-1001 is open. See chunk_id abc.",
            created_at="2026-08-25T00:00:00Z",
            delimited="<memory id=1>INV-SR-1001 is open. See chunk_id abc.</memory>",
        ),
    )
    decision = classify_knowledge_scope("What about the deadline?", memory=memory)
    assert decision.knowledge_scope is KnowledgeScope.COMPANY_DOCUMENTS
    assert decision.company_signal is True


def test_identity_question_switches_off_company_followup_memory() -> None:
    """Who-are-you after a cited answer is a clear switch to general help."""

    memory = (
        MemoryRecord(
            message_id="11111111-1111-1111-1111-111111111111",
            role="assistant",
            content="INV-SR-1001 is open. See chunk_id abc.",
            created_at="2026-08-25T00:00:00Z",
            delimited="<memory id=1>INV-SR-1001 is open. See chunk_id abc.</memory>",
        ),
    )
    decision = classify_knowledge_scope("who are you", memory=memory)
    assert decision.knowledge_scope is KnowledgeScope.GENERAL_KNOWLEDGE
    assert decision.company_signal is False
    prep = prepare_query("who are you", runtime=_runtime(), memory=memory)
    assert prep.knowledge_scope is KnowledgeScope.GENERAL_KNOWLEDGE
    assert prep.model_calls == 0


def test_identity_plus_company_in_one_prompt_stays_ambiguous() -> None:
    """Identity help mixed with a company phrase still asks for clarification."""

    query = "Who are you and what is our refund period?"
    assert is_product_help(query) is True
    decision = classify_knowledge_scope(query)
    assert decision.knowledge_scope is KnowledgeScope.AMBIGUOUS
    plan = _plan(query)
    assert plan.no_retrieval_answer_mode is NoRetrievalAnswerMode.CLARIFICATION
    assert decision.scope_degradation_reason is None
    assert plan.scope_degradation_reason is None


def test_root_cause_probes_are_usable_not_mixed() -> None:
    """Former false-ambiguity probes classify to a usable typed result."""

    probes = (
        "hi friend",
        "hi my friend",
        "hey there",
        "good day",
        "how are you?",
        "thanks a lot",
        "What is the capital of Japan?",
        "What is the refund period?",
    )
    for query in probes:
        decision = classify_knowledge_scope(query)
        assert decision.knowledge_scope is not KnowledgeScope.AMBIGUOUS, query
        plan = _plan(query)
        assert plan.no_retrieval_answer_mode is NoRetrievalAnswerMode.GENERAL_MODEL
        assert plan.company_claim_forbidden is True


def test_english_arabic_and_emoji_greetings_match() -> None:
    """Greeting detection covers addresses, Arabic forms, and trailing emoji."""

    for query in (
        "hi friend",
        "hi my friend",
        "hey there!",
        "good day",
        "salam",
        "مرحبا",
        "السلام عليكم",
        "اهلا",
        "أهلا",
        "hi 👋",
        "oh hello team",
    ):
        assert is_greeting(query) is True, query
        assert scope_requires_model(query) is True


def test_small_talk_requires_profile_and_is_not_company_followup() -> None:
    """Small talk uses the profile call and ignores cited company memory."""

    assert is_small_talk("how are you?") is True
    assert is_small_talk("what's up") is True
    assert is_small_talk("nice to meet you") is True
    assert is_small_talk("good to see you") is True
    memory = (
        MemoryRecord(
            message_id="11111111-1111-1111-1111-111111111111",
            role="assistant",
            content="INV-SR-1001 is open. See chunk_id abc.",
            created_at="2026-08-25T00:00:00Z",
            delimited="<memory id=1>INV-SR-1001 is open. See chunk_id abc.</memory>",
        ),
    )
    decision = classify_knowledge_scope("hi", memory=memory)
    assert decision.knowledge_scope is KnowledgeScope.GENERAL_KNOWLEDGE
    assert decision.company_signal is False
    assert scope_requires_model("hi", memory=memory) is True


def test_greeting_spends_one_profile_call() -> None:
    """A bound caller spends exactly one profile call for a pure greeting."""

    calls = {"n": 0}

    def _caller(query: str, memory: object) -> PreparationModelPayload:
        """Classify a greeting as general knowledge.

        Args:
            query: Unused original query.
            memory: Unused memory snapshot.

        Returns:
            One structured payload.
        """

        del query, memory
        calls["n"] += 1
        return PreparationModelPayload(
            knowledge_scope=KnowledgeScope.GENERAL_KNOWLEDGE.value,
            knowledge_scope_confidence=0.95,
            confidence=0.95,
        )

    prep = prepare_query("hi friend", runtime=_runtime(), model_caller=_caller)
    assert calls["n"] == 1
    assert prep.model_calls == 1
    assert prep.knowledge_scope is KnowledgeScope.GENERAL_KNOWLEDGE
    assert prep.scope_degradation_reason is None


def test_greeting_ignores_model_ambiguous_and_company_memory() -> None:
    """A standalone greeting stays general when the profile invents mixed."""

    memory = (
        MemoryRecord(
            message_id="11111111-1111-1111-1111-111111111111",
            role="assistant",
            content="INV-SR-1001 is open. See chunk_id abc.",
            created_at="2026-08-25T00:00:00Z",
            delimited="<memory id=1>INV-SR-1001 is open. See chunk_id abc.</memory>",
        ),
    )
    decision = classify_knowledge_scope(
        "hi friend",
        memory=memory,
        model_scope=KnowledgeScope.AMBIGUOUS.value,
        model_confidence=0.99,
        model_available=True,
    )
    assert decision.knowledge_scope is KnowledgeScope.GENERAL_KNOWLEDGE
    assert decision.company_signal is False
    assert decision.scope_degradation_reason is None
    assert is_greeting("hi friend") is True

    def _caller(query: str, snapshot: object) -> PreparationModelPayload:
        """Return a high-confidence mixed scope for a greeting.

        Args:
            query: Unused original query.
            snapshot: Unused memory snapshot.

        Returns:
            One structured payload claiming mixed scope.
        """

        del query, snapshot
        return PreparationModelPayload(
            knowledge_scope=KnowledgeScope.AMBIGUOUS.value,
            knowledge_scope_confidence=0.99,
            confidence=0.99,
        )

    prep = prepare_query(
        "hi friend",
        runtime=_runtime(),
        memory=memory,
        model_caller=_caller,
    )
    assert prep.knowledge_scope is KnowledgeScope.GENERAL_KNOWLEDGE
    assert prep.scope_degradation_reason is None
    plan = compile_retrieval_plan(prep, _runtime())
    assert plan.effective_route is Phase6RouteFamily.NO_RETRIEVAL
    assert plan.no_retrieval_answer_mode is NoRetrievalAnswerMode.GENERAL_MODEL
    assert plan.company_claim_forbidden is True


def test_model_ambiguous_without_conflict_is_not_mixed() -> None:
    """Model-invented mixed on remaining natural language is degraded general."""

    decision = classify_knowledge_scope(
        "Why is the sky blue?",
        model_scope=KnowledgeScope.AMBIGUOUS.value,
        model_confidence=0.99,
        model_available=True,
    )
    assert decision.knowledge_scope is KnowledgeScope.GENERAL_KNOWLEDGE
    assert decision.scope_degradation_reason is ScopeDegradationReason.PROFILE_MALFORMED
    assert decision.company_signal is False


def test_malformed_profile_payload_degrades() -> None:
    """A ValueError from the profile caller records typed malformed degradation."""

    def _caller(query: str, memory: object) -> PreparationModelPayload:
        """Raise instead of fabricating a profile.

        Args:
            query: Unused original query.
            memory: Unused memory snapshot.

        Returns:
            Never.

        Raises:
            ValueError: Always ``profile_malformed``.
        """

        del query, memory
        raise ValueError("profile_malformed")

    prep = prepare_query(
        "Why is the sky blue?", runtime=_runtime(), model_caller=_caller
    )
    assert prep.knowledge_scope is KnowledgeScope.GENERAL_KNOWLEDGE
    assert prep.scope_degradation_reason is ScopeDegradationReason.PROFILE_MALFORMED
    assert prep.fallback_reason == "profile_malformed"
    assert prep.model_calls == 1


def test_requested_company_forces_heading_to_company_hybrid() -> None:
    """A bare PDF heading plus Company files uses company Hybrid retrieval."""

    query = "Parallel Tool Execution"
    automatic = classify_knowledge_scope(query)
    assert automatic.knowledge_scope is KnowledgeScope.GENERAL_KNOWLEDGE
    forced = apply_requested_search_scope(
        query, automatic, RequestedSearchScope.COMPANY_DOCUMENTS
    )
    assert forced.knowledge_scope is KnowledgeScope.COMPANY_DOCUMENTS
    assert forced.confidence == 1.0
    assert forced.scope_degradation_reason is None
    assert forced.company_signal is automatic.company_signal
    prep = _prep(query, requested_search_scope=RequestedSearchScope.COMPANY_DOCUMENTS)
    assert prep.requested_search_scope is RequestedSearchScope.COMPANY_DOCUMENTS
    assert prep.knowledge_scope is KnowledgeScope.COMPANY_DOCUMENTS
    assert prep.model_calls == 0
    plan = _plan(query, requested_search_scope=RequestedSearchScope.COMPANY_DOCUMENTS)
    assert plan.knowledge_scope is KnowledgeScope.COMPANY_DOCUMENTS
    assert plan.requested_search_scope is RequestedSearchScope.COMPANY_DOCUMENTS
    assert plan.effective_route is Phase6RouteFamily.HYBRID
    assert plan.company_claim_forbidden is False
    assert plan.no_retrieval_answer_mode is None
    assert any(branch.kind is BranchKind.HYBRID for branch in plan.branches)


def test_requested_general_forbids_company_retrieval() -> None:
    """Requested General compiles to NoRetrieval with company claims forbidden."""

    query = "Parallel Tool Execution"
    prep = _prep(query, requested_search_scope=RequestedSearchScope.GENERAL_KNOWLEDGE)
    assert prep.knowledge_scope is KnowledgeScope.GENERAL_KNOWLEDGE
    assert prep.scope_degradation_reason is None
    plan = _plan(query, requested_search_scope=RequestedSearchScope.GENERAL_KNOWLEDGE)
    assert plan.effective_route is Phase6RouteFamily.NO_RETRIEVAL
    assert plan.company_claim_forbidden is True
    assert plan.no_retrieval_answer_mode is NoRetrievalAnswerMode.GENERAL_MODEL
    assert {branch.kind for branch in plan.branches} == {BranchKind.NO_RETRIEVAL}


def test_requested_auto_keeps_classifier_degradation() -> None:
    """Auto returns the automatic decision, including degradation provenance."""

    query = "Parallel Tool Execution"
    automatic = classify_knowledge_scope(query)
    applied = apply_requested_search_scope(query, automatic, RequestedSearchScope.AUTO)
    assert applied is automatic
    prep = _prep(query, requested_search_scope=RequestedSearchScope.AUTO)
    assert prep.knowledge_scope is KnowledgeScope.GENERAL_KNOWLEDGE
    assert prep.scope_degradation_reason is ScopeDegradationReason.PROFILE_UNAVAILABLE


def test_requested_company_keeps_greeting_and_user_text() -> None:
    """Greetings and user-text transforms ignore explicit Company files."""

    hello = apply_requested_search_scope(
        "Hello",
        classify_knowledge_scope("Hello"),
        RequestedSearchScope.COMPANY_DOCUMENTS,
    )
    assert hello.knowledge_scope is KnowledgeScope.GENERAL_KNOWLEDGE
    assert hello.confidence == 1.0
    assert hello.scope_degradation_reason is None
    hello_plan = _plan(
        "Hello", requested_search_scope=RequestedSearchScope.COMPANY_DOCUMENTS
    )
    assert hello_plan.effective_route is Phase6RouteFamily.NO_RETRIEVAL
    assert hello_plan.company_claim_forbidden is True

    help_plan = _plan(
        "How can you help me?",
        requested_search_scope=RequestedSearchScope.COMPANY_DOCUMENTS,
    )
    assert help_plan.knowledge_scope is KnowledgeScope.GENERAL_KNOWLEDGE
    assert help_plan.company_claim_forbidden is True

    rewrite = "Rewrite this paragraph: The sky is blue and wide."
    user_text = apply_requested_search_scope(
        rewrite,
        classify_knowledge_scope(rewrite),
        RequestedSearchScope.COMPANY_DOCUMENTS,
    )
    assert user_text.knowledge_scope is KnowledgeScope.USER_SUPPLIED_TEXT
    assert user_text.confidence == 1.0
    user_plan = _plan(
        rewrite, requested_search_scope=RequestedSearchScope.COMPANY_DOCUMENTS
    )
    assert user_plan.no_retrieval_answer_mode is NoRetrievalAnswerMode.USER_TEXT_MODEL


def test_requested_company_does_not_invent_company_signal() -> None:
    """Requested Company never manufactures ``company_signal=True``."""

    query = "What is the capital of France?"
    automatic = classify_knowledge_scope(query)
    assert automatic.company_signal is False
    forced = apply_requested_search_scope(
        query, automatic, RequestedSearchScope.COMPANY_DOCUMENTS
    )
    assert forced.knowledge_scope is KnowledgeScope.COMPANY_DOCUMENTS
    assert forced.company_signal is False
    assert forced.scope_degradation_reason is None
    plan = _plan(query, requested_search_scope=RequestedSearchScope.COMPANY_DOCUMENTS)
    assert plan.knowledge_scope is KnowledgeScope.COMPANY_DOCUMENTS
    assert plan.company_claim_forbidden is False
