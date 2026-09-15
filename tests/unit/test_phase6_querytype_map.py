"""Unit tests for the frozen Phase 4 QueryType to Phase 6 family map."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError
from smart_rag_core.evaluation.classes import (
    QueryClass,
    RuntimeOwner,
    class_runtime_owner,
)
from smart_rag_core.evaluation.schema import QueryType
from smart_rag_core.query_profile import (
    PHASE6_EXTENSION_FAMILIES,
    QUERY_TYPE_BASE_FAMILY,
    Phase6Limitation,
    Phase6RouteFamily,
    map_query_type_to_phase6_family,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
METRICS_SOURCE = (
    REPO_ROOT
    / "packages"
    / "core"
    / "src"
    / "smart_rag_core"
    / "query_profile"
    / "metrics.py"
)

_REPRESENTATIVE_CLASS: dict[QueryType, QueryClass] = {
    QueryType.EXACT_IDENTIFIER: QueryClass.EXACT_CODE,
    QueryType.FACTUAL: QueryClass.SEMANTIC_FACTUAL,
    QueryType.SEMANTIC_CONCEPTUAL: QueryClass.SEMANTIC_FACTUAL,
    QueryType.MULTI_PART: QueryClass.MULTI_PART,
    QueryType.RELATIONSHIP_MULTI_HOP: QueryClass.RELATIONSHIP,
    QueryType.BROAD_SUMMARY: QueryClass.BROAD_SYNTHESIS,
    QueryType.STRUCTURED_TABULAR: QueryClass.TABULAR_AGGREGATION,
}


def test_every_query_type_maps_without_keyerror() -> None:
    """Every frozen Phase 4 QueryType maps; the base table is total."""

    assert set(QUERY_TYPE_BASE_FAMILY) == set(QueryType)
    assert set(_REPRESENTATIVE_CLASS) == set(QueryType)
    families: list[Phase6RouteFamily] = []
    for query_type in QueryType:
        result = map_query_type_to_phase6_family(
            query_type, _REPRESENTATIVE_CLASS[query_type]
        )
        families.append(result.phase6_family)
        assert result.query_type is query_type
        assert result.query_class is _REPRESENTATIVE_CLASS[query_type]
        assert result.phase6_family is QUERY_TYPE_BASE_FAMILY[query_type]
    assert len(families) == len(QueryType)


def test_exact_factual_semantic_map_to_hybrid() -> None:
    """Exact, factual, and semantic query types select Hybrid."""

    for query_type in (
        QueryType.EXACT_IDENTIFIER,
        QueryType.FACTUAL,
        QueryType.SEMANTIC_CONCEPTUAL,
    ):
        result = map_query_type_to_phase6_family(
            query_type, _REPRESENTATIVE_CLASS[query_type]
        )
        assert result.phase6_family is Phase6RouteFamily.HYBRID
        assert result.limitation is None
        assert result.phase4_may_execute is True


def test_comparison_is_subset_of_multi_part() -> None:
    """Comparison is not a QueryType; it is only valid under multi_part."""

    assert "comparison" not in {member.value for member in QueryType}
    result = map_query_type_to_phase6_family(
        QueryType.MULTI_PART,
        QueryClass.MULTI_PART,
        comparison=True,
    )
    assert result.phase6_family is Phase6RouteFamily.HYBRID
    assert result.comparison_subset is True
    assert result.phase4_may_execute is True
    assert any("comparison is a subset of multi_part" in note for note in result.notes)
    with pytest.raises(ValueError, match="comparison_requires_multi_part"):
        map_query_type_to_phase6_family(
            QueryType.FACTUAL,
            QueryClass.SEMANTIC_FACTUAL,
            comparison=True,
        )


def test_relationship_versus_multi_hop_and_historical_flag() -> None:
    """Relationship and multi-hop share Combined unless historical."""

    relationship = map_query_type_to_phase6_family(
        QueryType.RELATIONSHIP_MULTI_HOP,
        QueryClass.RELATIONSHIP,
    )
    multi_hop = map_query_type_to_phase6_family(
        QueryType.RELATIONSHIP_MULTI_HOP,
        QueryClass.MULTI_HOP,
    )
    assert relationship.phase6_family is Phase6RouteFamily.COMBINED
    assert multi_hop.phase6_family is Phase6RouteFamily.COMBINED
    assert relationship.limitation is None
    assert multi_hop.limitation is None
    assert relationship.phase4_may_execute is False
    assert multi_hop.phase4_may_execute is False
    assert relationship.runtime_owner is RuntimeOwner.PHASE_5_AND_6
    assert multi_hop.runtime_owner is RuntimeOwner.PHASE_5_AND_6
    assert any("relationship" in note for note in relationship.notes)
    assert any("multi-hop" in note for note in multi_hop.notes)

    historical_relationship = map_query_type_to_phase6_family(
        QueryType.RELATIONSHIP_MULTI_HOP,
        QueryClass.RELATIONSHIP,
        historical_relationship=True,
    )
    historical_multi_hop = map_query_type_to_phase6_family(
        QueryType.RELATIONSHIP_MULTI_HOP,
        QueryClass.MULTI_HOP,
        historical_relationship=True,
    )
    assert historical_relationship.phase6_family is Phase6RouteFamily.HYBRID
    assert historical_multi_hop.phase6_family is Phase6RouteFamily.HYBRID
    assert (
        historical_relationship.limitation is Phase6Limitation.TEMPORAL_GRAPH_LIMITATION
    )
    assert historical_multi_hop.limitation is Phase6Limitation.TEMPORAL_GRAPH_LIMITATION
    assert any(
        "temporal_graph_limitation" in note for note in historical_relationship.notes
    )


def test_graph_inspection_and_no_retrieval_cannot_come_from_query_type() -> None:
    """Phase 6 extensions exist on the family type but not on QueryType."""

    assert "graph_inspection" not in {member.value for member in QueryType}
    assert "no_retrieval" not in {member.value for member in QueryType}
    assert Phase6RouteFamily.GRAPH_INSPECTION.value == "graph_inspection"
    assert Phase6RouteFamily.NO_RETRIEVAL.value == "no_retrieval"
    assert Phase6RouteFamily.WEB_RESEARCH.value == "web_research"
    assert "web_research" not in {member.value for member in QueryType}
    assert PHASE6_EXTENSION_FAMILIES == frozenset(
        {
            Phase6RouteFamily.GRAPH_INSPECTION,
            Phase6RouteFamily.NO_RETRIEVAL,
            Phase6RouteFamily.WEB_RESEARCH,
        }
    )

    produced = {
        map_query_type_to_phase6_family(
            query_type, _REPRESENTATIVE_CLASS[query_type]
        ).phase6_family
        for query_type in QueryType
    }
    produced.add(
        map_query_type_to_phase6_family(
            QueryType.RELATIONSHIP_MULTI_HOP,
            QueryClass.GRAPH_MAPPING,
        ).phase6_family
    )
    produced.add(
        map_query_type_to_phase6_family(
            QueryType.BROAD_SUMMARY,
            QueryClass.DOCUMENT_SUMMARY,
            scoped_summary_incomplete=True,
        ).phase6_family
    )
    produced.add(
        map_query_type_to_phase6_family(
            QueryType.RELATIONSHIP_MULTI_HOP,
            QueryClass.MULTI_HOP,
            historical_relationship=True,
        ).phase6_family
    )
    assert PHASE6_EXTENSION_FAMILIES.isdisjoint(produced)
    mapping_case = map_query_type_to_phase6_family(
        QueryType.RELATIONSHIP_MULTI_HOP,
        QueryClass.GRAPH_MAPPING,
    )
    assert mapping_case.phase6_family is Phase6RouteFamily.COMBINED
    assert mapping_case.phase4_may_execute is False


def test_structured_table_and_broad_summary_routes() -> None:
    """Tabular aggregation selects StructuredTable; summary may refuse."""

    table = map_query_type_to_phase6_family(
        QueryType.STRUCTURED_TABULAR,
        QueryClass.TABULAR_AGGREGATION,
    )
    assert table.phase6_family is Phase6RouteFamily.STRUCTURED_TABLE
    assert table.phase4_may_execute is True

    synthesis = map_query_type_to_phase6_family(
        QueryType.BROAD_SUMMARY,
        QueryClass.BROAD_SYNTHESIS,
    )
    assert synthesis.phase6_family is Phase6RouteFamily.HYBRID
    assert synthesis.phase4_may_execute is True

    scoped = map_query_type_to_phase6_family(
        QueryType.BROAD_SUMMARY,
        QueryClass.DOCUMENT_SUMMARY,
        scoped_summary_incomplete=True,
    )
    assert scoped.phase6_family is Phase6RouteFamily.SCOPED_REFUSAL
    assert scoped.phase4_may_execute is True


def test_phase4_may_execute_follows_runtime_owner() -> None:
    """Phase 4 may execute only when class_runtime_owner is phase_4."""

    for query_class in QueryClass:
        result = map_query_type_to_phase6_family(QueryType.FACTUAL, query_class)
        assert result.runtime_owner is class_runtime_owner(query_class)
        assert result.phase4_may_execute is (
            class_runtime_owner(query_class) is RuntimeOwner.PHASE_4
        )


def test_map_result_is_frozen() -> None:
    """The mapping result cannot be mutated after construction."""

    result = map_query_type_to_phase6_family(
        QueryType.FACTUAL, QueryClass.SEMANTIC_FACTUAL
    )
    with pytest.raises(ValidationError):
        result.phase6_family = Phase6RouteFamily.COMBINED  # type: ignore[misc]


def test_query_type_enum_members_remain_frozen() -> None:
    """Wave 1C must not add Phase 4 QueryType members."""

    assert {member.value for member in QueryType} == {
        "exact_identifier",
        "factual",
        "semantic_conceptual",
        "multi_part",
        "relationship_multi_hop",
        "broad_summary",
        "structured_tabular_aggregation",
    }


def test_metrics_pass_rule_still_requires_zero_model_calls() -> None:
    """QT-QP still requires model_calls == 0; this packet must not weaken it."""

    source = METRICS_SOURCE.read_text(encoding="utf-8")
    gate_assignment = next(
        line.strip()
        for line in source.splitlines()
        if line.strip().startswith("passed =")
    )
    assert (
        gate_assignment
        == "passed = all(item.passed for item in scores) and model_calls == 0"
    )
    assert "model_calls == 0" in source
