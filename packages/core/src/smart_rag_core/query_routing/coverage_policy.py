"""Frozen evaluation-class and coverage-threshold readers."""

from __future__ import annotations

from smart_rag_core.evaluation.classes import QueryClass
from smart_rag_core.evaluation.schema import QueryType
from smart_rag_core.query_routing.constants import PROVISIONAL_COVERAGE_THRESHOLD
from smart_rag_core.query_routing.exceptions import QueryRoutingError
from smart_rag_core.query_routing.models import QueryPreparation
from smart_rag_core.retrieval.frozen_profile import coverage_threshold_for


def evaluation_class_for(prep: QueryPreparation) -> QueryClass:
    """Map a preparation onto a frozen evaluation class for coverage lookup.

    Args:
        prep: Typed preparation.

    Returns:
        Frozen ``QueryClass``. Unknown types use ``semantic_factual``.
    """

    if prep.media_intent:
        return QueryClass.MEDIA_LIMITATION
    if prep.negation_scope != "none":
        return QueryClass.NEGATION
    if prep.whole_document_summary:
        return QueryClass.DOCUMENT_SUMMARY
    if prep.table_intent:
        return QueryClass.TABULAR_AGGREGATION
    if prep.historical_relationship or prep.relationship_intent:
        return QueryClass.RELATIONSHIP
    try:
        query_type = QueryType(prep.query_type)
    except ValueError:
        return QueryClass.SEMANTIC_FACTUAL
    mapping = {
        QueryType.EXACT_IDENTIFIER: QueryClass.EXACT_CODE,
        QueryType.FACTUAL: QueryClass.SEMANTIC_FACTUAL,
        QueryType.SEMANTIC_CONCEPTUAL: QueryClass.SEMANTIC_FACTUAL,
        QueryType.MULTI_PART: QueryClass.MULTI_PART,
        QueryType.RELATIONSHIP_MULTI_HOP: QueryClass.RELATIONSHIP,
        QueryType.BROAD_SUMMARY: QueryClass.BROAD_SYNTHESIS,
        QueryType.STRUCTURED_TABULAR: QueryClass.TABULAR_AGGREGATION,
    }
    return mapping.get(query_type, QueryClass.SEMANTIC_FACTUAL)


def frozen_coverage_threshold(prep: QueryPreparation) -> float:
    """Return the frozen per-class coverage threshold. Never retuned here.

    Args:
        prep: Typed preparation.

    Returns:
        Frozen threshold. Provisionally ``0.65`` for every class.

    Raises:
        QueryRoutingError: If a caller attempts to use a different value.
    """

    threshold = coverage_threshold_for(evaluation_class_for(prep))
    if abs(threshold - PROVISIONAL_COVERAGE_THRESHOLD) > 1e-12:
        raise QueryRoutingError("holdout_driven_threshold_change")
    return threshold


def query_type_for(prep: QueryPreparation) -> QueryType:
    """Parse the frozen query type, defaulting to factual.

    Args:
        prep: Typed preparation.

    Returns:
        Phase 4 ``QueryType``.
    """

    try:
        return QueryType(prep.query_type)
    except ValueError:
        return QueryType.FACTUAL
