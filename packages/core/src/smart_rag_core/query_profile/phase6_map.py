"""Frozen Phase 4 ``QueryType`` to Phase 6 route-family map.

This module does not implement Phase 6 routing, LangGraph, FastAPI, or Valkey.
It records the allow-listed family each frozen Phase 4 query type selects so
later packets can consume a typed contract without changing the Phase 4 enum.
"""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from smart_rag_core.evaluation.classes import (
    QueryClass,
    RuntimeOwner,
    class_runtime_owner,
)
from smart_rag_core.evaluation.schema import QueryType


class Phase6RouteFamily(StrEnum):
    """Phase 6 answering or limitation family names.

    ``graph_inspection`` and ``no_retrieval`` are Phase-6-only extensions.
    They are valid values on this enum so Phase 6 can reuse the type, but
    :func:`map_query_type_to_phase6_family` never produces them from a
    Phase 4 ``QueryType`` alone.
    """

    HYBRID = "hybrid"
    COMBINED = "combined"
    STRUCTURED_TABLE = "structured_table"
    COMPOSITE = "composite"
    SCOPED_REFUSAL = "scoped_refusal"
    GRAPH_INSPECTION = "graph_inspection"
    NO_RETRIEVAL = "no_retrieval"


class Phase6Limitation(StrEnum):
    """Named limitation attached to a mapped Phase 6 family."""

    TEMPORAL_GRAPH_LIMITATION = "temporal_graph_limitation"


PHASE6_EXTENSION_FAMILIES: frozenset[Phase6RouteFamily] = frozenset(
    {
        Phase6RouteFamily.GRAPH_INSPECTION,
        Phase6RouteFamily.NO_RETRIEVAL,
    }
)


def _complete_base_family() -> dict[QueryType, Phase6RouteFamily]:
    """Return the total QueryType → family table.

    Returns:
        Mapping covering every frozen Phase 4 ``QueryType``.

    Raises:
        RuntimeError: If a QueryType member is missing or unexpected. This
            keeps later lookups free of ``KeyError`` for the frozen enum.
    """

    mapping: dict[QueryType, Phase6RouteFamily] = {
        QueryType.EXACT_IDENTIFIER: Phase6RouteFamily.HYBRID,
        QueryType.FACTUAL: Phase6RouteFamily.HYBRID,
        QueryType.SEMANTIC_CONCEPTUAL: Phase6RouteFamily.HYBRID,
        QueryType.MULTI_PART: Phase6RouteFamily.HYBRID,
        QueryType.RELATIONSHIP_MULTI_HOP: Phase6RouteFamily.COMBINED,
        QueryType.BROAD_SUMMARY: Phase6RouteFamily.HYBRID,
        QueryType.STRUCTURED_TABULAR: Phase6RouteFamily.STRUCTURED_TABLE,
    }
    missing = [member.value for member in QueryType if member not in mapping]
    if missing:
        raise RuntimeError(f"unmapped_query_type:{','.join(missing)}")
    unexpected = [key.value for key in mapping if key not in set(QueryType)]
    if unexpected:
        raise RuntimeError(f"unexpected_query_type:{','.join(unexpected)}")
    return mapping


QUERY_TYPE_BASE_FAMILY: Mapping[QueryType, Phase6RouteFamily] = _complete_base_family()


class Phase6FamilyMapResult(BaseModel):
    """Frozen result of mapping one Phase 4 query type onto a Phase 6 family.

    Attributes:
        query_type: Frozen Phase 4 ``QueryType``. Never a Phase 6 extension.
        query_class: Evaluation class used for owner and relationship kind.
        phase6_family: Selected Phase 6 route family.
        notes: Human-readable mapping rationale, including comparison subset
            and relationship versus multi-hop distinction.
        phase4_may_execute: True only when ``runtime_owner`` is ``phase_4``.
        runtime_owner: Phase that may execute the labeled class at runtime.
        limitation: Optional named limitation such as historical graph.
        comparison_subset: True when comparison was requested under
            ``multi_part``.
    """

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    query_type: QueryType
    query_class: QueryClass
    phase6_family: Phase6RouteFamily
    phase4_may_execute: bool
    runtime_owner: RuntimeOwner
    notes: tuple[str, ...] = ()
    limitation: Phase6Limitation | None = None
    comparison_subset: bool = False


def map_query_type_to_phase6_family(
    query_type: QueryType,
    query_class: QueryClass,
    *,
    historical_relationship: bool = False,
    comparison: bool = False,
    scoped_summary_incomplete: bool = False,
) -> Phase6FamilyMapResult:
    """Map a frozen Phase 4 ``QueryType`` to a Phase 6 route family.

    Exact, factual, and semantic types select Hybrid. ``multi_part`` may
    include comparison as a subset and still selects Hybrid here; Phase 6
    may later compose ``composite`` when mixed route families are required.
    ``relationship_multi_hop`` plus ``QueryClass.relationship`` versus
    ``multi_hop`` selects Combined, or Hybrid with
    ``temporal_graph_limitation`` when ``historical_relationship`` is set.
    ``structured_tabular_aggregation`` selects StructuredTable.
    ``broad_summary`` selects Hybrid, or scoped refusal when whole-document
    coverage is incomplete. ``graph_inspection`` and ``no_retrieval`` are
    not produced.

    Args:
        query_type: Frozen Phase 4 query type. Members must not be added.
        query_class: Labeled class used for runtime owner and the
            relationship versus multi-hop distinction.
        historical_relationship: Past or ``as_of`` relationship signal.
            Applies only to ``relationship_multi_hop``.
        comparison: Whether this multi-part query is a comparison. Must not
            be set unless ``query_type`` is ``multi_part``.
        scoped_summary_incomplete: Whole-document summary without
            ``section_coverage_ratio=1.0``. Applies only to ``broad_summary``.

    Returns:
        Frozen mapping result. ``phase4_may_execute`` is true only when
        :func:`class_runtime_owner` returns ``phase_4``.

    Raises:
        ValueError: If ``comparison`` is true for a type other than
            ``multi_part``.
        KeyError: If ``query_type`` is not in the frozen base map. The
            frozen ``QueryType`` enum is fully keyed, so this is not raised
            for ordinary callers.
    """

    if comparison and query_type is not QueryType.MULTI_PART:
        raise ValueError("comparison_requires_multi_part")

    try:
        family = QUERY_TYPE_BASE_FAMILY[query_type]
    except KeyError as exc:
        raise KeyError(f"unmapped_query_type:{query_type}") from exc

    notes: list[str] = []
    limitation: Phase6Limitation | None = None

    if query_type in {
        QueryType.EXACT_IDENTIFIER,
        QueryType.FACTUAL,
        QueryType.SEMANTIC_CONCEPTUAL,
    }:
        notes.append("exact/factual/semantic map to Hybrid")
    elif query_type is QueryType.MULTI_PART:
        notes.append("multi_part maps to Hybrid; comparison is a subset of multi_part")
        notes.append(
            "Phase 6 may label Composite when mixed route families are required"
        )
        if comparison:
            notes.append(
                "comparison decomposes to Hybrid for explicit documents/attributes"
            )
    elif query_type is QueryType.STRUCTURED_TABULAR:
        notes.append("structured_tabular_aggregation maps to StructuredTable")
    elif query_type is QueryType.BROAD_SUMMARY:
        if scoped_summary_incomplete:
            family = Phase6RouteFamily.SCOPED_REFUSAL
            notes.append(
                "broad_summary with incomplete section coverage is scoped refusal"
            )
        else:
            notes.append("broad_summary ordinary synthesis maps to Hybrid")
    elif query_type is QueryType.RELATIONSHIP_MULTI_HOP:
        if query_class is QueryClass.RELATIONSHIP:
            notes.append("QueryClass.relationship is the current-relationship kind")
        elif query_class is QueryClass.MULTI_HOP:
            notes.append("QueryClass.multi_hop is the current multi-hop kind")
        else:
            notes.append(
                "relationship_multi_hop QueryType maps by historical flag; "
                "graph_inspection is not derived from QueryType"
            )
        if historical_relationship:
            family = Phase6RouteFamily.HYBRID
            limitation = Phase6Limitation.TEMPORAL_GRAPH_LIMITATION
            notes.append(
                "historical/as_of relationship or multi-hop stays Hybrid "
                "with temporal_graph_limitation"
            )
        else:
            notes.append("current relationship or multi-hop maps to Combined")

    owner = class_runtime_owner(query_class)
    return Phase6FamilyMapResult(
        query_type=query_type,
        query_class=query_class,
        phase6_family=family,
        notes=tuple(notes),
        phase4_may_execute=owner is RuntimeOwner.PHASE_4,
        runtime_owner=owner,
        limitation=limitation,
        comparison_subset=comparison and query_type is QueryType.MULTI_PART,
    )
