"""Prove routing-plan JSON dumps did not drift after the packet 3 split."""

from __future__ import annotations

import json
from pathlib import Path

from smart_rag_core.query_profile.phase6_map import Phase6RouteFamily
from smart_rag_core.query_routing.matrix import compile_retrieval_plan
from smart_rag_core.query_routing.models import RetrievalPlan
from smart_rag_core.query_routing.preparation import prepare_query

from tests.support.query_runtime import authorized_runtime as _runtime

FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "query_routing"
    / "plan_snapshots.json"
)


def test_representative_plans_match_pre_split_snapshots() -> None:
    """Recompiled plans equal the fixtures captured before the split."""

    snapshots = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert snapshots
    for name, payload in snapshots.items():
        query = str(payload["query"])
        extra: dict[str, object] = {}
        if name == "whole_document_insufficient":
            extra["section_coverage_ratio"] = 0.5
        runtime = (
            _runtime(Phase6RouteFamily.HYBRID)
            if name == "envelope_cannot_enlarge"
            else _runtime()
        )
        prep = prepare_query(query, runtime=runtime)
        plan = compile_retrieval_plan(prep, runtime, **extra)
        expected = RetrievalPlan.model_validate(payload["plan"])
        assert plan == expected, name
        assert plan.model_dump(mode="json") == expected.model_dump(mode="json"), name


def test_routing_model_json_schemas_stay_closed() -> None:
    """Split model modules keep extra=forbid and the same public fields."""

    from smart_rag_core.query_routing.models import (
        BranchResult,
        QueryPreparation,
        RetrievalPlan,
    )

    for model in (QueryPreparation, RetrievalPlan, BranchResult):
        schema = model.model_json_schema()
        assert schema.get("additionalProperties") is False
        assert model.model_config.get("extra") == "forbid"
        assert model.model_config.get("frozen") is True
