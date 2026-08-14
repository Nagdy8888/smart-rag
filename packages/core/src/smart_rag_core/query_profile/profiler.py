"""Build a typed query profile from deterministic extract plus at most one model call."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from smart_rag_core.evaluation.schema import ExpectedProfile, FieldProvenance, det
from smart_rag_core.query_profile.extract import (
    DeterministicExtract,
    extract_deterministic,
)
from smart_rag_core.query_profile.merge import ProfileMergeError, merge_inferred
from smart_rag_core.query_profile.models import (
    ModelInferredProfile,
    ProfileFallbackReason,
    QueryProfileResult,
)
from smart_rag_core.query_profile.versions import (
    DATE_PARSER_VERSION,
    NORMALIZER_VERSION,
    PROFILE_MODEL_VERSION,
    PROFILE_PROMPT_SHA256,
    PROFILE_PROMPT_VERSION,
)
from smart_rag_core.retrieval.profiles import HYBRID_DEFAULT_PROFILE_ID

ProfileModelCaller = Callable[[str], Awaitable[ModelInferredProfile]]


def _to_expected(query: str, extract: DeterministicExtract) -> ExpectedProfile:
    """Map a deterministic extract onto the evaluation profile schema.

    Args:
        query: Original query, stored unmodified.
        extract: Deterministic extract.

    Returns:
        Frozen ``ExpectedProfile``.
    """

    codes = list(extract.codes)
    aliases = list(extract.aliases)
    entities = aliases or codes
    alias_provenance = (
        FieldProvenance.APPROVED_ALIAS if aliases else FieldProvenance.DETERMINISTIC
    )
    temporal = extract.temporal_intent
    return ExpectedProfile(
        original_query=query,
        normalizer_version=NORMALIZER_VERSION,
        date_parser_version=DATE_PARSER_VERSION,
        prompt_version=PROFILE_PROMPT_VERSION,
        model_version=PROFILE_MODEL_VERSION,
        language=det(extract.language, span=extract.language),
        locale_configuration=det(extract.locale),
        query_type=det(extract.query_type.value),
        exact_terms=det(codes),
        quoted_phrases=det(list(extract.quoted_phrases)),
        codes=det(codes, rule_id="inv-sr-v1" if codes else None),
        numbers=det([]),
        dates=det(list(extract.dates)),
        entities=det(entities),
        approved_aliases=det(
            aliases,
            provenance=alias_provenance,
            alias_id=aliases[0] if aliases else None,
        ),
        requested_sources=det([]),
        metadata_filters=det(list(extract.filters)),
        temporal_intent=det(temporal),
        target_date=det(extract.target_date),
        timezone=det("UTC"),
        authoritative_date_field=det(
            "effective_at" if temporal in {"latest", "current", "as_of"} else "none"
        ),
        negation_scope=det(extract.negation_scope),
        document_scope=det(extract.document_scope),
        media_dependence=det(extract.media_dependence),
        historical_relationship=det(extract.historical_relationship),
        relationship_intent=det(extract.relationship_intent),
        table_intent=det(extract.table_intent),
        table_operation_hints=det(list(extract.table_ops)),
        rewrite_justified=det(extract.rewrite_justified),
        subquestions=det(list(extract.subquestions)),
        variants=det(list(extract.variants)),
        hl_keywords=det([extract.query_type.value]),
        ll_keywords=det(codes or aliases or [query.split()[0]]),
        retrieval_profile_id=det(HYBRID_DEFAULT_PROFILE_ID),
    )


def profile_query_sync(
    query: str,
    *,
    inferred: ModelInferredProfile | None = None,
    model_calls: int = 0,
    fallback: ProfileFallbackReason = ProfileFallbackReason.NOT_NEEDED,
    diagnostics: tuple[str, ...] = (),
) -> QueryProfileResult:
    """Profile one query without performing a second hidden model call.

    Args:
        query: Original query. Must be 1-2000 characters.
        inferred: Optional already-fetched structured payload.
        model_calls: ``0`` or ``1`` accounting for that payload.
        fallback: Fallback when the model was skipped or rejected.
        diagnostics: Soft diagnostics to append.

    Returns:
        Typed profile result.

    Raises:
        ValueError: If the query is empty or over-long, or ``model_calls`` > 1.
    """

    if not query or len(query) > 2000:
        raise ValueError("query exceeds profile bounds")
    if model_calls > 1:
        raise ValueError("second_profile_model_call_forbidden")
    extract = extract_deterministic(query)
    extra = diagnostics
    merge_reason = fallback
    try:
        extract, merged_diag, merged_reason = merge_inferred(query, extract, inferred)
        extra = (*diagnostics, *merged_diag)
        if inferred is not None:
            merge_reason = merged_reason
    except ProfileMergeError as error:
        merge_reason = ProfileFallbackReason.UNKNOWN_FIELD
        extra = (*diagnostics, str(error))
    profile = _to_expected(query, extract)
    return QueryProfileResult(
        profile=profile,
        model_calls=model_calls,
        fallback_reason=merge_reason,
        diagnostics=extra,
        prompt_sha256=PROFILE_PROMPT_SHA256,
    )


async def profile_query(
    query: str,
    *,
    model_caller: ProfileModelCaller | None = None,
    force_model: bool = False,
    budget_remaining_calls: int = 1,
    deadline_seconds: float | None = None,
) -> QueryProfileResult:
    """Profile a query with deterministic extract and at most one model call.

    The model runs only when ``force_model`` is true because Packet 3's
    labeled corpus is covered by deterministic rules. A hidden second keyword
    or profile call is forbidden.

    Args:
        query: Original query.
        model_caller: Optional async structured-output adapter.
        force_model: Test/production hook to spend the one allowed call.
        budget_remaining_calls: Remaining gateway profile calls.
        deadline_seconds: Optional deadline; ``0`` fails closed as timeout.

    Returns:
        Typed profile. ``model_calls`` is 0 or 1.

    Raises:
        ValueError: If query bounds fail.

    Side Effects:
        May await ``model_caller`` once. Never opens retrieval or tools.
    """

    if deadline_seconds is not None and deadline_seconds <= 0:
        result = profile_query_sync(
            query,
            fallback=ProfileFallbackReason.TIMEOUT,
        )
        return result.model_copy(
            update={"fallback_reason": ProfileFallbackReason.TIMEOUT}
        )
    if force_model and budget_remaining_calls < 1:
        result = profile_query_sync(
            query,
            fallback=ProfileFallbackReason.BUDGET_DENIED,
        )
        return result.model_copy(
            update={"fallback_reason": ProfileFallbackReason.BUDGET_DENIED}
        )
    if not force_model or model_caller is None:
        return profile_query_sync(query)
    try:
        inferred = await model_caller(query)
    except TimeoutError:
        return profile_query_sync(query, fallback=ProfileFallbackReason.TIMEOUT)
    except ValueError:
        return profile_query_sync(
            query,
            model_calls=1,
            fallback=ProfileFallbackReason.MALFORMED,
        )
    return profile_query_sync(
        query,
        inferred=inferred,
        model_calls=1,
        fallback=ProfileFallbackReason.NONE,
    )
