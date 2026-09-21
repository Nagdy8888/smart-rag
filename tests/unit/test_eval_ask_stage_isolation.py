"""Unit tests for P06-70 first-fail assignment. No sample gold."""

from __future__ import annotations

import pytest

from scripts.eval_ask_stage_isolation import (
    STAGES,
    assign_stage,
    bind_first_fail_stage,
    name_gate,
    strip_title_clause,
)


def _ask(**overrides: object) -> dict[str, object]:
    """Build one Arm A outcome row.

    Args:
        **overrides: Field replacements.

    Returns:
        Ask outcome mapping.
    """

    row: dict[str, object] = {
        "deadline_failure": False,
        "empty_retrieval": True,
        "grounded_fact_pass": False,
        "fallback_reason": "retrieval_empty",
        "source_resolution": "exact_one",
        "effective_route": "hybrid",
        "citation_count": 0,
    }
    row.update(overrides)
    return row


def _exam(**overrides: object) -> dict[str, object]:
    """Build one exam-retrieve outcome.

    Args:
        **overrides: Field replacements.

    Returns:
        Exam mapping.
    """

    row: dict[str, object] = {
        "any_channel_gold": False,
        "gold_in_fused": False,
        "gold_in_selected": False,
        "fallback_reason": "retrieval_empty",
        "refused": False,
    }
    row.update(overrides)
    return row


def _arm_b(**overrides: object) -> dict[str, object]:
    """Build one oracle-arm outcome.

    Args:
        **overrides: Field replacements.

    Returns:
        Arm B mapping.
    """

    row: dict[str, object] = {
        "grounded_fact_pass": True,
        "authorized_gold": 2,
        "answer_status": "answered",
    }
    row.update(overrides)
    return row


def test_assign_stage_returns_exactly_one_allowlisted_name() -> None:
    """Each fixture maps to one catalog stage."""

    assigned = assign_stage(
        gold_count=2,
        ask=_ask(),
        exam_a=_exam(),
        exam_ap=_exam(),
        arm_b=_arm_b(),
        ask_ap=_ask(),
    )
    assert assigned in STAGES
    assert assigned == "index"


def test_bind_first_fail_stage_rejects_two_stages() -> None:
    """Two first-failing stages for one case is a hard failure."""

    with pytest.raises(RuntimeError, match="multiple_first_fail_stages"):
        bind_first_fail_stage(["answer", "index"])
    with pytest.raises(RuntimeError, match="multiple_first_fail_stages"):
        bind_first_fail_stage([])
    assert bind_first_fail_stage(["fusion/rerank"]) == "fusion/rerank"


def test_arm_b_failure_owns_answer_or_verifier() -> None:
    """Oracle miss forbids retrieval-stage claims."""

    assert (
        assign_stage(
            gold_count=2,
            ask=_ask(),
            exam_a=_exam(),
            exam_ap=_exam(),
            arm_b=_arm_b(grounded_fact_pass=False, authorized_gold=2),
            ask_ap=None,
        )
        == "answer"
    )
    assert (
        assign_stage(
            gold_count=2,
            ask=_ask(),
            exam_a=_exam(),
            exam_ap=_exam(),
            arm_b=_arm_b(
                grounded_fact_pass=False,
                authorized_gold=2,
                answer_status="refused",
            ),
            ask_ap=None,
        )
        == "verifier/release"
    )


def test_aprime_gold_with_a_miss_owns_scope_selector() -> None:
    """Title-stripped gold hit with titled miss is selector corruption."""

    assert (
        assign_stage(
            gold_count=2,
            ask=_ask(),
            exam_a=_exam(any_channel_gold=False),
            exam_ap=_exam(any_channel_gold=True),
            arm_b=_arm_b(),
            ask_ap=_ask(empty_retrieval=False, grounded_fact_pass=True),
        )
        == "scope/selector"
    )


def test_channel_drop_owns_fusion_rerank() -> None:
    """Gold in a channel that fusion or selection drops is fusion/rerank."""

    assert (
        assign_stage(
            gold_count=2,
            ask=_ask(empty_retrieval=True),
            exam_a=_exam(any_channel_gold=True, gold_in_fused=False),
            exam_ap=_exam(any_channel_gold=True),
            arm_b=_arm_b(),
            ask_ap=None,
        )
        == "fusion/rerank"
    )
    assert (
        assign_stage(
            gold_count=2,
            ask=_ask(empty_retrieval=True),
            exam_a=_exam(
                any_channel_gold=True,
                gold_in_fused=True,
                gold_in_selected=False,
            ),
            exam_ap=_exam(any_channel_gold=True),
            arm_b=_arm_b(),
            ask_ap=None,
        )
        == "fusion/rerank"
    )


def test_name_gate_majority_and_earliest_fallback() -> None:
    """Named branches require a majority of six; otherwise earliest stage wins."""

    assert name_gate({"metric_only": 12}) == "metric_aliases"
    assert name_gate({"index": 8, "channel_candidate": 4}) == "candidate_index"
    assert name_gate({"answer": 4, "verifier/release": 5, "index": 3}) == (
        "answer_verifier_release"
    )
    assert name_gate({"scope/selector": 7, "index": 5}) == "scope_selector"
    assert name_gate({"deadline": 12}) == "deadline_budget"
    assert name_gate({"context_fit": 5, "coverage/correction": 4, "label": 3}) == (
        "earliest_majority_context_fit"
    )
    assert name_gate({"deadline": 11, "context_fit": 1}) == "deadline_budget"


def test_ask_deadline_owns_first_fail_before_later_stages() -> None:
    """Ask deadline is first-fail even when later arms retrieve gold."""

    assert (
        assign_stage(
            gold_count=2,
            ask=_ask(deadline_failure=True, empty_retrieval=False),
            exam_a=_exam(any_channel_gold=True, gold_in_fused=True),
            exam_ap=_exam(any_channel_gold=True),
            arm_b=_arm_b(),
            ask_ap=None,
        )
        == "deadline"
    )


def test_strip_title_clause_collapses_whitespace() -> None:
    """Title stripping is mechanical and does not invent synonyms."""

    prompt = "In Building Applications with AI Agents, what is X?"
    stripped = strip_title_clause(prompt, "Building Applications with AI Agents")
    assert "Building Applications" not in stripped
    assert stripped.startswith("In")
    assert "  " not in stripped
