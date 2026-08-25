"""One typed query preparation. Rewrite and profile share at most one call."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from uuid import UUID, uuid4

import psycopg

from smart_rag_core.evaluation.schema import FieldProvenance, ProfileField
from smart_rag_core.query_admission.context import AuthorizedRuntimeContext
from smart_rag_core.query_admission.usage import execute_counted_model_call
from smart_rag_core.query_profile.extract import extract_deterministic
from smart_rag_core.query_profile.models import (
    ModelInferredProfile,
    ProfileFallbackReason,
)
from smart_rag_core.query_profile.profiler import profile_query_sync
from smart_rag_core.query_routing.constants import USAGE_KIND_PROFILE
from smart_rag_core.query_routing.exceptions import QueryRoutingError
from smart_rag_core.query_routing.fidelity import score_rewrite_fidelity
from smart_rag_core.query_routing.knowledge_scope import (
    KnowledgeScope,
    classify_knowledge_scope,
    company_intent_signal,
    scope_requires_model,
)
from smart_rag_core.query_routing.models import (
    REQUIRED_PREPARATION_FIELDS,
    MemoryRecord,
    Phase6Extension,
    PreparationModelPayload,
    QueryPreparation,
    RoutingSurface,
)
from smart_rag_core.query_routing.profile_fields import (
    keyword_tuple,
    profile_bool,
    profile_str,
    profile_strings,
)
from smart_rag_core.query_routing.safety import sanitize_user_text
from smart_rag_core.query_routing.signals import (
    is_corpus_wide_theme,
    is_graph_inspection,
    is_greeting,
    is_historical_relationship,
    is_low_confidence_relationship,
    is_product_help,
    is_whole_document_summary,
)
from smart_rag_core.security.identity import CallerContext

PrepModelCaller = Callable[[str, tuple[MemoryRecord, ...]], PreparationModelPayload]


def assert_preparation_schema(preparation: QueryPreparation) -> None:
    """Fail if any required preparation field is missing.

    Args:
        preparation: Candidate preparation.

    Raises:
        QueryRoutingError: ``profile_schema_omission`` when a field is absent.
    """

    dumped = preparation.model_dump()
    missing = REQUIRED_PREPARATION_FIELDS.difference(dumped)
    if missing:
        raise QueryRoutingError("profile_schema_omission")


def forbid_separate_rewrite_call() -> None:
    """Refuse a second standalone rewrite model call.

    Raises:
        QueryRoutingError: Always ``separate_rewrite_call``.
    """

    raise QueryRoutingError("separate_rewrite_call")


def _needs_model(
    query: str,
    *,
    memory: Sequence[MemoryRecord],
    force_model: bool,
) -> bool:
    """Return whether rewrite plus profile needs the one structured call.

    Args:
        query: Original query.
        memory: Loaded untrusted messages.
        force_model: Test/diagnostic hook.

    Returns:
        True when a model is required. Simple deterministic profiles are False.
    """

    if force_model:
        return True
    extract = extract_deterministic(query)
    if is_greeting(query):
        return False
    if is_product_help(query) and not company_intent_signal(query, extract):
        return False
    if extract.rewrite_justified:
        return True
    if memory and extract.query_type.value == "factual" and len(query.split()) <= 4:
        return True
    if scope_requires_model(query, memory=memory):
        return True
    return False


def _extension_for_scope(scope: KnowledgeScope, query: str) -> Phase6Extension:
    """Return the Phase 6 family extension implied by classified scope.

    Args:
        scope: Strict-split knowledge scope.
        query: Original query.

    Returns:
        Graph inspection or none for company documents; otherwise no-retrieval.
    """

    if scope is KnowledgeScope.COMPANY_DOCUMENTS:
        if is_graph_inspection(query):
            return Phase6Extension.GRAPH_INSPECTION
        return Phase6Extension.NONE
    return Phase6Extension.NO_RETRIEVAL


def _to_inferred(payload: PreparationModelPayload) -> ModelInferredProfile:
    """Map the combined prep payload onto the frozen inferred profile.

    Args:
        payload: One structured rewrite-plus-profile payload.

    Returns:
        ``ModelInferredProfile`` without a second model call.
    """

    return ModelInferredProfile(
        query_type=payload.query_type,
        subquestions=list(payload.subquestions),
        variants=list(payload.variants),
        retrieval_profile_id=payload.retrieval_profile_id,
        metadata_filters=list(payload.metadata_filters),
        confidence=payload.confidence,
    )


def prepare_query(
    query: str,
    *,
    runtime: AuthorizedRuntimeContext,
    memory: Sequence[MemoryRecord] = (),
    routing_surface: RoutingSurface = RoutingSurface.PRODUCTION,
    requested_manual_route: str | None = None,
    model_caller: PrepModelCaller | None = None,
    force_model: bool = False,
    connection: psycopg.Connection | None = None,
    caller: CallerContext | None = None,
    model_id: str = "query-profile-mock-v1",
) -> QueryPreparation:
    """Build one ``QueryPreparation`` with at most one counted model call.

    Simple deterministic profiles use ``profile_query_sync`` with zero model
    calls. When rewrite and profile both need a model, they share one
    ``execute_counted_model_call`` with ``usage_kind=profile``.

    Args:
        query: Original user text. Untrusted.
        runtime: Packet 1 authorized context. Used for consume accounting.
        memory: Bounded untrusted messages. Never source documents.
        routing_surface: Production or diagnostic.
        requested_manual_route: Recorded only on diagnostic surfaces.
        model_caller: Optional structured prep adapter.
        force_model: Spend the one call even when deterministic extract exists.
        connection: Required to consume the reservation when a model runs.
        caller: Server-derived caller for consume. Derived from runtime
            when omitted.
        model_id: Provider model identifier recorded on usage.

    Returns:
        Typed preparation. ``model_calls`` is 0 or 1. Original is preserved.

    Raises:
        QueryRoutingError: Empty query, fourth subquestion, original loss,
            or consume failure mapped from admission errors.
        ValueError: Profile bounds from ``profile_query_sync``.

    Side Effects:
        At most one gateway consume plus ``llm_usage`` row when a model runs.
        Never opens retrieval, catalog search, or LightRAG keyword extract.
    """

    original = sanitize_user_text(query)
    extract = extract_deterministic(original)
    needs_model = _needs_model(original, memory=tuple(memory), force_model=force_model)
    payload: PreparationModelPayload | None = None
    model_calls: int = 0
    fallback = "not_needed"
    if needs_model:
        if model_caller is None:
            fallback = "profile_budget_denied"
        else:

            def _send() -> PreparationModelPayload:
                """Invoke the one structured preparation adapter.

                Returns:
                    Combined rewrite-plus-profile payload.
                """

                return model_caller(original, tuple(memory))

            if connection is None:
                try:
                    payload = _send()
                except ValueError as exc:
                    raise QueryRoutingError(_prep_value_error(exc)) from exc
                model_calls = 1
                fallback = "none"
            else:
                resolved_caller = caller or CallerContext(
                    user_id=str(runtime.user_id),
                    role=runtime.role,
                    authorization_version=runtime.authorization_version,
                    session_id=runtime.session_id,
                )
                payload, _consumed, _usage_id = execute_counted_model_call(
                    connection,
                    caller=resolved_caller,
                    run_id=runtime.run_id,
                    reservation_id=runtime.reservation_id,
                    expected_version=runtime.optimistic_version,
                    usage_kind=USAGE_KIND_PROFILE,
                    model_id=model_id,
                    provider_attempt_id=str(uuid4()),
                    send=_send,
                )
                model_calls = 1
                fallback = "none"
    if model_calls > 1:
        raise QueryRoutingError("separate_rewrite_call")
    inferred = _to_inferred(payload) if payload is not None else None
    result = profile_query_sync(
        original,
        inferred=inferred,
        model_calls=model_calls,
        fallback=_result_fallback(fallback),
    )
    rewrite_candidate = payload.rewrite if payload is not None else None
    intent, entity, accepted = score_rewrite_fidelity(
        original, rewrite_candidate, extract
    )
    profile = result.profile
    if accepted is not None:
        profile = profile.model_copy(
            update={
                "variants": ProfileField(
                    value=[accepted],
                    confidence=intent,
                    provenance=FieldProvenance.MODEL_INFERRED,
                )
            }
        )
    decomposition = profile_strings(profile.subquestions)
    if len(decomposition) > 3:
        raise QueryRoutingError("fourth_subquestion")
    comparison = original.lower().startswith("compare ")
    scope = classify_knowledge_scope(
        original,
        memory=memory,
        model_scope=None if payload is None else payload.knowledge_scope,
        model_confidence=(
            None if payload is None else payload.knowledge_scope_confidence
        ),
        model_available=payload is not None,
    )
    try:
        preparation = QueryPreparation(
            original=original,
            rewrite=accepted,
            profile=profile,
            language=profile_str(profile.language, "en"),
            temporal_intent=profile_str(profile.temporal_intent, "none"),
            timezone=profile_str(profile.timezone, "UTC"),
            hl_keywords=keyword_tuple(profile, "hl_keywords"),
            ll_keywords=keyword_tuple(profile, "ll_keywords"),
            entities=profile_strings(profile.entities),
            approved_aliases=profile_strings(profile.approved_aliases),
            exact_terms=profile_strings(profile.exact_terms),
            dates=profile_strings(profile.dates),
            numbers=profile_strings(profile.numbers),
            metadata_filters=profile_strings(profile.metadata_filters),
            negation_scope=profile_str(profile.negation_scope, "none"),
            negation_confidence=profile.negation_scope.confidence,
            document_scope=profile_str(profile.document_scope, "none"),
            section_scope="none",
            page_scope="none",
            media_intent=profile_bool(profile.media_dependence),
            historical_relationship=is_historical_relationship(original, extract),
            low_confidence_relationship=is_low_confidence_relationship(
                original, extract
            ),
            relationship_intent=profile_bool(profile.relationship_intent)
            or is_low_confidence_relationship(original, extract),
            decomposition=decomposition,
            confidence=max(profile.query_type.confidence, 0.0),
            model_calls=0 if model_calls == 0 else 1,
            fallback_reason=result.fallback_reason.value,
            intent_fidelity=intent,
            entity_fidelity=entity,
            original_fallback_variant=original,
            query_type=profile_str(profile.query_type, extract.query_type.value),
            phase6_extension=_extension_for_scope(scope.knowledge_scope, original),
            comparison=comparison,
            table_intent=profile_bool(profile.table_intent),
            corpus_wide_theme=is_corpus_wide_theme(original),
            whole_document_summary=is_whole_document_summary(original, extract),
            routing_surface=routing_surface,
            manual_mode=bool(requested_manual_route)
            and routing_surface is RoutingSurface.DIAGNOSTIC,
            knowledge_scope=scope.knowledge_scope,
            knowledge_scope_confidence=scope.confidence,
        )
    except ValueError as exc:
        raise QueryRoutingError(_prep_value_error(exc)) from exc
    if preparation.original != original:
        raise QueryRoutingError("original_query_loss")
    assert_preparation_schema(preparation)
    return preparation


def _result_fallback(reason: str) -> ProfileFallbackReason:
    """Map a local fallback string onto ``ProfileFallbackReason``.

    Args:
        reason: Local reason code.

    Returns:
        The matching ``ProfileFallbackReason`` member.
    """

    mapping = {
        "not_needed": ProfileFallbackReason.NOT_NEEDED,
        "none": ProfileFallbackReason.NONE,
        "profile_budget_denied": ProfileFallbackReason.BUDGET_DENIED,
        "profile_timeout": ProfileFallbackReason.TIMEOUT,
        "profile_malformed": ProfileFallbackReason.MALFORMED,
    }
    return mapping.get(reason, ProfileFallbackReason.NOT_NEEDED)


def _prep_value_error(exc: ValueError) -> str:
    """Map a Pydantic/value error onto a stable routing reason.

    Args:
        exc: Validation error.

    Returns:
        Packet 2 reason code.
    """

    text = str(exc)
    if "fourth_subquestion" in text:
        return "fourth_subquestion"
    if "original_query_loss" in text:
        return "original_query_loss"
    return "profile_schema_omission"


def caller_from_runtime(runtime: AuthorizedRuntimeContext) -> CallerContext:
    """Build a ``CallerContext`` from packet 1 authorized runtime.

    Args:
        runtime: Admitted context.

    Returns:
        Caller snapshot for RPCs and retrievers.
    """

    return CallerContext(
        user_id=str(runtime.user_id),
        role=runtime.role,
        authorization_version=runtime.authorization_version,
        session_id=runtime.session_id,
    )


def run_ids(runtime: AuthorizedRuntimeContext) -> tuple[UUID, UUID]:
    """Return admitted run and reservation ids.

    Args:
        runtime: Packet 1 context.

    Returns:
        ``(run_id, reservation_id)``.
    """

    return runtime.run_id, runtime.reservation_id
