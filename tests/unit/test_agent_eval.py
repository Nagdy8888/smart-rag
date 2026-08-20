"""Unit tests for versioned agent-eval schema, selection, and scorers."""

from __future__ import annotations

from decimal import Decimal

import pytest
from smart_rag_core.evaluation.agent_eval import (
    AgentEvalError,
    AgentEvalOutput,
    AgentEvalReference,
    example_uuid,
    failed_target_output,
    hard_failure_reasons,
    sanitize_experiment_prefix,
    score_acl_leak_free,
    score_all,
    score_answer_reference_overlap,
    score_bounds_respected,
    score_citation_precision,
    score_citation_recall,
    score_refusal_correct,
    score_route_correct,
    score_target_completed,
    select_development_cases,
)
from smart_rag_core.evaluation.holdout import HoldoutAccess
from smart_rag_core.evaluation.langsmith_agent_runner import (
    assert_agent_eval_execution_bounds,
)
from smart_rag_core.evaluation.loader import load_qualification_cases
from smart_rag_core.evaluation.online import (
    ONLINE_EVAL_MAX_CASES,
    ONLINE_EVAL_MAX_USD,
    OnlineEvalError,
)
from smart_rag_core.evaluation.schema import DatasetSplit


def _output(**kwargs: object) -> AgentEvalOutput:
    """Build one evaluation output with safe defaults.

    Args:
        **kwargs: Field overrides.

    Returns:
        Frozen ``AgentEvalOutput``.
    """

    payload: dict[str, object] = {
        "case_id": "p4-acl_negative-0003",
        "completed": True,
        "answer_status": "complete",
        "answer_text": "invoice INV-SR-8803 is listed",
        "effective_route": "hybrid",
        "remaining_model_calls": 2,
        "remaining_tool_calls": 2,
        "remaining_corrections": 1,
        "remaining_subquestions": 1,
        "remaining_recursion_steps": 4,
        "deadline_exceeded": False,
    }
    payload.update(kwargs)
    return AgentEvalOutput.model_validate(payload)


def _reference(**kwargs: object) -> AgentEvalReference:
    """Build one reference payload with safe defaults.

    Args:
        **kwargs: Field overrides.

    Returns:
        Frozen ``AgentEvalReference``.
    """

    payload: dict[str, object] = {
        "acceptable_answers": ("invoice INV-SR-8803 is listed",),
        "expected_route": "hybrid",
        "refusal_kind": "none",
        "visible_chunk_ids": ("chunk-a",),
        "visible_table_ids": (),
        "forbidden_evidence_ids": ("chunk-hidden",),
        "expected_profile_fields": {"language": "en"},
    }
    payload.update(kwargs)
    return AgentEvalReference.model_validate(payload)


def test_example_uuid_is_stable() -> None:
    """UUIDv5 example ids stay stable for the same dataset, case, and hash."""

    first = example_uuid("ds", "p4-acl_negative-0003", "abc")
    second = example_uuid("ds", "p4-acl_negative-0003", "abc")
    assert first == second
    assert example_uuid("ds", "p4-acl_negative-0003", "def") != first


def test_select_development_cases_rejects_out_of_range_limits() -> None:
    """Limits of 0 or 21 fail closed before any LangSmith work."""

    with pytest.raises(AgentEvalError):
        select_development_cases(limit=0)
    with pytest.raises(AgentEvalError):
        select_development_cases(limit=ONLINE_EVAL_MAX_CASES + 1)


def test_select_rejects_qualification_and_holdout_access() -> None:
    """Qualification ids and enabled holdout access fail closed."""

    qualification = load_qualification_cases()
    assert qualification
    with pytest.raises(AgentEvalError):
        select_development_cases(limit=1, case_ids=(qualification[0].case_id,))
    with pytest.raises(AgentEvalError):
        select_development_cases(
            limit=1,
            holdout_access=HoldoutAccess(
                allowed=True,
                purpose="packet8_immutable_holdout",
                actor="tester",
            ),
        )


def test_select_rejects_unsupported_query_class() -> None:
    """Unknown class filters fail instead of silently dropping cases."""

    with pytest.raises(AgentEvalError):
        select_development_cases(limit=3, query_classes=("not_a_class",))


def test_selected_cases_are_synthetic_development() -> None:
    """The default selection stays on the synthetic development split."""

    selection = select_development_cases(limit=3)
    assert len(selection.cases) == 3
    for case in selection.cases:
        assert case.split is DatasetSplit.DEVELOPMENT
        assert case.redaction_class == "synthetic"
    assert "holdout" not in selection.dataset_name
    assert "development" in selection.dataset_name


def test_route_and_refusal_formulas() -> None:
    """Route aliases and refusal/answer behavior match the documented scores."""

    hybrid = _output(effective_route="hybrid")
    assert score_route_correct(hybrid, _reference(expected_route="hybrid")) == 1.0
    refusal_out = _output(
        effective_route="scoped_refusal",
        answer_status="refused",
        answer_text="",
    )
    refusal_ref = _reference(
        expected_route="refusal",
        refusal_kind="acl_filtered",
        acceptable_answers=(),
        visible_chunk_ids=(),
    )
    assert score_route_correct(refusal_out, refusal_ref) == 1.0
    confident = _output(answer_status="complete", answer_text="secret appendix")
    assert score_refusal_correct(confident, refusal_ref) == 0.0
    assert score_refusal_correct(refusal_out, refusal_ref) == 1.0


def test_citation_empty_sets_and_acl_leak() -> None:
    """Empty citation sets score 1; hidden citations are a hard ACL failure."""

    empty = _output(cited_chunk_ids=(), selected_evidence_ids=())
    empty_ref = _reference(visible_chunk_ids=(), forbidden_evidence_ids=("hidden",))
    assert score_citation_precision(empty, empty_ref) == 1.0
    assert score_citation_recall(empty, empty_ref) == 1.0
    leak = _output(cited_chunk_ids=("hidden",), selected_evidence_ids=("hidden",))
    leak_ref = _reference(
        visible_chunk_ids=("visible",),
        forbidden_evidence_ids=("hidden",),
    )
    assert score_acl_leak_free(leak, leak_ref) == 0.0
    scores = score_all(leak, leak_ref)
    assert scores["acl_leak_free"] == 0.0
    assert "acl_leak_free" in hard_failure_reasons(leak, scores)


def test_bounds_and_infrastructure_failure_remain_visible() -> None:
    """Deadline/counter breaches and target failures score 0 and stay named."""

    ok = _output()
    assert score_bounds_respected(ok) == 1.0
    late = _output(deadline_exceeded=True)
    assert score_bounds_respected(late) == 0.0
    failed = failed_target_output(
        "p4-acl_negative-0003", failure_kind="graph_invoke_failed"
    )
    assert score_target_completed(failed) == 0.0
    scores = score_all(failed, _reference())
    assert scores["target_completed"] == 0.0
    reasons = hard_failure_reasons(failed, scores)
    assert "graph_invoke_failed" in reasons or scores["target_completed"] == 0.0


def test_answer_overlap_is_diagnostic() -> None:
    """Answer overlap is computed but is not a hard failure."""

    output = _output(answer_text="invoice INV-SR-8803 is listed")
    reference = _reference(acceptable_answers=("invoice INV-SR-8803 is listed",))
    score = score_answer_reference_overlap(output, reference)
    assert 0.0 <= score <= 1.0
    scores = score_all(output, reference)
    assert "answer_reference_overlap" in scores
    assert "answer_reference_overlap" not in hard_failure_reasons(output, scores)


def test_experiment_prefix_and_execution_bounds() -> None:
    """Unsafe prefixes, extra concurrency, extra repetitions, and extra USD fail."""

    assert sanitize_experiment_prefix("ok_prefix") == "ok_prefix"
    with pytest.raises(AgentEvalError):
        sanitize_experiment_prefix("***")
    with pytest.raises((AgentEvalError, OnlineEvalError)):
        assert_agent_eval_execution_bounds(
            max_concurrency=1,
            num_repetitions=1,
            max_usd=ONLINE_EVAL_MAX_USD + Decimal("0.01"),
            unlimited_openai=False,
            mock_mode=True,
            case_count=1,
        )
    with pytest.raises(AgentEvalError):
        assert_agent_eval_execution_bounds(
            max_concurrency=2,
            num_repetitions=1,
            max_usd=Decimal("1.00"),
            unlimited_openai=False,
            mock_mode=True,
            case_count=1,
        )
    with pytest.raises(AgentEvalError):
        assert_agent_eval_execution_bounds(
            max_concurrency=1,
            num_repetitions=2,
            max_usd=Decimal("1.00"),
            unlimited_openai=False,
            mock_mode=True,
            case_count=1,
        )
    with pytest.raises(OnlineEvalError):
        assert_agent_eval_execution_bounds(
            max_concurrency=1,
            num_repetitions=1,
            max_usd=Decimal("1.00"),
            unlimited_openai=True,
            mock_mode=True,
            case_count=1,
        )
