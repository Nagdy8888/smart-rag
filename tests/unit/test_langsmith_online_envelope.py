"""Online-eval suite identity and envelope validation."""

from __future__ import annotations

import pytest
from smart_rag_core.evaluation.holdout import HoldoutAccess
from smart_rag_core.evaluation.loader import load_qualification_cases
from smart_rag_core.evaluation.online import (
    AGENT_ONLINE_EVAL_SCHEMA_VERSION,
    APPLICATION_LANGSMITH_PROJECT,
    ONLINE_EVAL_MAX_CASES,
    ONLINE_EVAL_MAX_USD,
    ONLINE_EVAL_PROJECT,
    ONLINE_EVAL_SAMPLING_RATE,
    QUERY_AGENT_ONLINE_EVAL_RUN,
)
from smart_rag_core.evaluation.online_agent_runner import (
    plan_online_dry_run,
)
from smart_rag_core.evaluation.online_envelope import (
    OnlineEnvelopeError,
    build_online_envelope,
    sample_online_envelope,
)
from smart_rag_core.evaluation.online_suite import (
    OnlineSuiteError,
    load_online_eval_selection,
    load_online_suite_manifest,
    online_suite_hash,
)
from smart_rag_core.evaluation.schema import DatasetSplit

from tests.support.online_eval import (
    _output,
)


def test_frozen_suite_is_representative_synthetic_development() -> None:
    """The frozen 20-id suite covers routes, classes, languages, and refusals."""

    manifest = load_online_suite_manifest()
    selection = load_online_eval_selection()
    assert len(manifest.case_ids) == ONLINE_EVAL_MAX_CASES
    assert len(selection.cases) == ONLINE_EVAL_MAX_CASES
    assert manifest.project == ONLINE_EVAL_PROJECT
    assert manifest.holdout_opened is False
    classes = {case.query_class.value for case in selection.cases}
    routes = {case.expected_route.value for case in selection.cases}
    languages = {case.language for case in selection.cases}
    assert "acl_negative" in classes
    assert "prompt_injection" in classes
    assert "arabic_mixed" in classes
    assert "hybrid" in routes
    assert "combined" in routes
    assert "structured_table" in routes
    assert "graph_inspection" in routes
    assert "refusal" in routes
    assert "en" in languages
    assert "mixed" in languages
    for case in selection.cases:
        assert case.split is DatasetSplit.DEVELOPMENT
        assert case.redaction_class == "synthetic"


def test_suite_rejects_qualification_holdout_and_empty() -> None:
    """Qualification ids, enabled holdout, and empty subsets fail closed."""

    qualification = load_qualification_cases()
    assert qualification
    with pytest.raises(OnlineSuiteError):
        load_online_eval_selection(case_ids=(qualification[0].case_id,))
    with pytest.raises(OnlineSuiteError):
        load_online_eval_selection(
            holdout_access=HoldoutAccess(
                allowed=True,
                purpose="packet8_immutable_holdout",
                actor="tester",
            )
        )
    with pytest.raises(OnlineSuiteError):
        load_online_eval_selection(limit=0)


def test_online_dry_run_validates_envelope_without_writes() -> None:
    """Dry-run proves suite identity, project, bounds, and zero writes."""

    plan = plan_online_dry_run()
    assert plan.dry_run is True
    assert plan.writes is False
    assert plan.dataset_created is False
    assert plan.experiment_created is False
    assert plan.local_judge is False
    assert plan.holdout_opened is False
    assert plan.project == ONLINE_EVAL_PROJECT
    assert plan.application_project == APPLICATION_LANGSMITH_PROJECT
    assert plan.root_run_name == QUERY_AGENT_ONLINE_EVAL_RUN
    assert plan.selected_case_count == ONLINE_EVAL_MAX_CASES
    assert plan.sampling_rate == ONLINE_EVAL_SAMPLING_RATE
    assert plan.spend_limit_usd == format(ONLINE_EVAL_MAX_USD, "f")
    assert plan.backfill is False
    assert plan.envelope_valid is True
    assert plan.suite_hash == online_suite_hash(load_online_suite_manifest())
    sample = sample_online_envelope(load_online_eval_selection(limit=1).cases[0])
    assert sample.inputs.redaction_class == "synthetic"
    assert sample.inputs.schema_version == AGENT_ONLINE_EVAL_SCHEMA_VERSION


def test_envelope_rejects_secrets() -> None:
    """JWTs and API-key-like strings cannot enter the dedicated envelope."""

    case = load_online_eval_selection(limit=1).cases[0]
    leaked = _output(
        answer_text="bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.aaaaaaaabbbbbbbb"
    )
    with pytest.raises(OnlineEnvelopeError):
        build_online_envelope(case, leaked)
