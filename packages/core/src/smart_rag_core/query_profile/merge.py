"""Merge optional model-inferred fields onto deterministic extractions."""

from __future__ import annotations

from smart_rag_core.evaluation.schema import QueryType
from smart_rag_core.query_profile.extract import DeterministicExtract
from smart_rag_core.query_profile.models import (
    ModelInferredProfile,
    ProfileFallbackReason,
)
from smart_rag_core.query_profile.variants import generate_focused_variants
from smart_rag_core.query_profile.versions import (
    LOW_CONFIDENCE_HARD_FILTER,
    MAX_SUBQUESTIONS,
)
from smart_rag_core.retrieval.profiles import ALLOWED_RETRIEVAL_PROFILE_IDS


class ProfileMergeError(ValueError):
    """Raised when inferred output contradicts deterministic extractions."""


def _as_query_type(value: str | None) -> QueryType | None:
    """Parse an inferred query type.

    Args:
        value: Raw string.

    Returns:
        Query type or ``None`` when missing.

    Raises:
        ProfileMergeError: If the value is not allow-listed.
    """

    if value is None:
        return None
    try:
        return QueryType(value)
    except ValueError as error:
        raise ProfileMergeError("unknown_query_type") from error


def merge_inferred(
    query: str,
    extract: DeterministicExtract,
    inferred: ModelInferredProfile | None,
) -> tuple[DeterministicExtract, tuple[str, ...], ProfileFallbackReason]:
    """Validate inferred fields without changing protected extractions.

    Args:
        query: Original query.
        extract: Deterministic extract.
        inferred: Optional structured model payload.

    Returns:
        Possibly extended extract, diagnostics, and fallback reason.

    Raises:
        ProfileMergeError: On unknown hard fields or contradiction.
    """

    diagnostics: list[str] = []
    if inferred is None:
        return extract, (), ProfileFallbackReason.NOT_NEEDED
    inferred_type = _as_query_type(inferred.query_type)
    if (
        inferred_type is not None
        and inferred_type is not extract.query_type
        and inferred.confidence < LOW_CONFIDENCE_HARD_FILTER
    ):
        diagnostics.append("low_confidence_type_ignored")
        inferred_type = None
    query_type = inferred_type or extract.query_type
    subquestions = extract.subquestions
    if inferred.subquestions:
        trimmed = tuple(inferred.subquestions[:MAX_SUBQUESTIONS])
        if extract.subquestions and trimmed != extract.subquestions:
            raise ProfileMergeError("rewrite_changed_decomposition")
        if not extract.subquestions:
            subquestions = trimmed
    variants = generate_focused_variants(
        query,
        extract,
        candidates=tuple(inferred.variants),
    )
    profile_id = inferred.retrieval_profile_id
    if profile_id is not None and profile_id not in ALLOWED_RETRIEVAL_PROFILE_IDS:
        raise ProfileMergeError("unknown_retrieval_profile")
    if inferred.metadata_filters:
        if inferred.confidence < LOW_CONFIDENCE_HARD_FILTER:
            diagnostics.append("low_confidence_filter_soft")
        else:
            raise ProfileMergeError("unknown_hard_field")
    updated = DeterministicExtract(
        language=extract.language,
        locale=extract.locale,
        query_type=query_type,
        codes=extract.codes,
        quoted_phrases=extract.quoted_phrases,
        aliases=extract.aliases,
        dates=extract.dates,
        temporal_intent=extract.temporal_intent,
        target_date=extract.target_date,
        filters=extract.filters,
        negation_scope=extract.negation_scope,
        document_scope=extract.document_scope,
        media_dependence=extract.media_dependence,
        historical_relationship=extract.historical_relationship,
        relationship_intent=extract.relationship_intent,
        table_intent=extract.table_intent,
        table_ops=extract.table_ops,
        subquestions=subquestions,
        variants=variants,
        rewrite_justified=extract.rewrite_justified,
        normalized_query=extract.normalized_query,
    )
    return updated, tuple(diagnostics), ProfileFallbackReason.NONE
