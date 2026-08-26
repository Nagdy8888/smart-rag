"""Hosted online-eval scoring and standalone evaluator contracts."""

from __future__ import annotations

import ast

import pytest
from smart_rag_core.evaluation.agent_eval import (
    failed_target_output,
    score_all,
)
from smart_rag_core.evaluation.online import (
    ONLINE_EVAL_ROOT_FILTER,
    ONLINE_JUDGE_PROMPT_HANDLE,
)
from smart_rag_core.evaluation.online_provision import (
    OnlineProvisionError,
    assert_llm_create_contract,
    assert_rule_contract,
    llm_evaluator_create_body,
    required_evaluator_fields,
    run_rule_body,
)

from tests.support.online_eval import (
    EVALUATOR_PATH,
    FORBIDDEN_IMPORT_PREFIXES,
    _eval_run,
    _load_perform_eval,
    _output,
    _reference,
)


def test_perform_eval_matches_score_all_fixtures() -> None:
    """Standalone hosted scores equal ``score_all`` on the same fixtures."""

    perform_eval = _load_perform_eval()
    cases = (
        (
            _output(),
            _reference(),
        ),
        (
            _output(cited_chunk_ids=(), selected_evidence_ids=()),
            _reference(visible_chunk_ids=(), forbidden_evidence_ids=("hidden",)),
        ),
        (
            _output(
                cited_chunk_ids=("hidden",),
                selected_evidence_ids=("hidden",),
            ),
            _reference(
                visible_chunk_ids=("visible",),
                forbidden_evidence_ids=("hidden",),
            ),
        ),
        (
            _output(
                effective_route="scoped_refusal",
                answer_status="refused",
                answer_text="",
                remaining_model_calls=0,
            ),
            _reference(
                expected_route="refusal",
                refusal_kind="acl_filtered",
                acceptable_answers=(),
                visible_chunk_ids=(),
            ),
        ),
        (
            failed_target_output(
                "p4-acl_negative-0003",
                failure_kind="graph_invoke_failed",
            ),
            _reference(),
        ),
        (
            _output(deadline_exceeded=True),
            _reference(),
        ),
    )
    for output, reference in cases:
        expected = score_all(output, reference)
        got = perform_eval(_eval_run(output, reference))
        assert got == expected


def test_perform_eval_fail_closed_on_malformed_and_child_spans() -> None:
    """Wrong name, schema, redaction class, or missing counters score zero."""

    perform_eval = _load_perform_eval()
    ok = _eval_run(_output(), _reference())
    child = dict(ok)
    child["name"] = "query.agent.eval"
    assert perform_eval(child)["target_completed"] == 0.0
    wrong_schema = _eval_run(
        _output(),
        _reference(),
        schema_version="agent-eval-v1",
    )
    assert perform_eval(wrong_schema)["route_correct"] == 0.0
    not_synthetic = _eval_run(
        _output(),
        _reference(),
        redaction_class="real_company",
    )
    assert perform_eval(not_synthetic)["acl_leak_free"] == 0.0
    assert perform_eval("not-a-run")["bounds_respected"] == 0.0
    missing = _eval_run(
        _output(remaining_model_calls=None),
        _reference(),
    )
    assert perform_eval(missing)["bounds_respected"] == 0.0


def test_standalone_evaluator_is_stdlib_only() -> None:
    """Uploaded evaluator source cannot import project or network packages."""

    tree = ast.parse(EVALUATOR_PATH.read_text(encoding="utf-8"))
    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.append(node.module.split(".")[0])
    assert "re" in imported
    for name in imported:
        assert name not in FORBIDDEN_IMPORT_PREFIXES
        assert not any(name.startswith(prefix) for prefix in FORBIDDEN_IMPORT_PREFIXES)


def test_llm_and_rule_request_fields_match_documented_contract() -> None:
    """Relied-on evaluator and run-rule fields stay aligned with LangSmith docs."""

    required = required_evaluator_fields()
    body = llm_evaluator_create_body(
        prompt_commit="abc123def456",
        model_configuration_id="11111111-1111-1111-1111-111111111111",
    )
    assert_llm_create_contract(body)
    assert "type" in required
    evaluator = body["llm_evaluator"]
    assert isinstance(evaluator, dict)
    assert evaluator["prompt_repo_handle"] == ONLINE_JUDGE_PROMPT_HANDLE
    rule = run_rule_body(
        display_name="rule",
        project_id="22222222-2222-2222-2222-222222222222",
        evaluator_id="33333333-3333-3333-3333-333333333333",
        include_spend_limit=True,
    )
    assert_rule_contract(
        rule,
        project_id="22222222-2222-2222-2222-222222222222",
        require_spend_limit=True,
    )
    assert rule["filter"] == ONLINE_EVAL_ROOT_FILTER
    assert "backfill_from" not in rule
    with pytest.raises(OnlineProvisionError):
        assert_llm_create_contract(
            llm_evaluator_create_body(
                prompt_commit="latest",
                model_configuration_id="11111111-1111-1111-1111-111111111111",
            )
        )
