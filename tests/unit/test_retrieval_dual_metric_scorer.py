"""Unit tests for dual-metric scoring and private-safe Ask regression helpers."""

from __future__ import annotations

from pathlib import Path

import pytest
from smart_rag_core.evaluation.company_ask_regression import (
    AskRegressionConfigError,
    CompanyAskQuestion,
    assert_fresh_conversation_policy,
    load_ask_regression_credentials,
    load_private_gold,
    run_scored_questions,
    score_full_answer_record,
    write_redacted_summary,
)
from smart_rag_core.evaluation.dual_metric import (
    DualOutcome,
    RequiredFact,
    RetrievalStageAttribution,
    score_company_answer,
    summarize_scores,
    synthetic_disjoint_cases,
)
from smart_rag_core.query_answer.assembly import DEADLINE_RESERVE_REFUSAL_TEXT
from smart_rag_core.query_answer.paragraphs import INSUFFICIENT_EVIDENCE_TEXT

_CODE_FACT = RequiredFact(
    fact_id="inv-code",
    canonical_phrases=("INV-1001",),
    approved_aliases=("invoice 1001",),
)


def test_strict_pass_uses_full_unescaped_answer() -> None:
    """HTML-escaped full answers still match canonical phrases."""

    score = score_company_answer(
        answer_text="The listed code is INV-1001 and Acme&#x27;s ledger.",
        facts=(
            _CODE_FACT,
            RequiredFact(fact_id="owner", canonical_phrases=("Acme's",)),
        ),
        stages=RetrievalStageAttribution(fused_count=2, dense_hit=True),
    )
    assert score.outcome is DualOutcome.STRICT_PHRASE
    assert score.strict_pass is True
    assert score.grounded_fact_pass is True


def test_alias_coverage_can_pass_when_strict_fails() -> None:
    """Approved aliases count for fact coverage, not strict phrase match."""

    score = score_company_answer(
        answer_text="The record is invoice 1001 on the ledger.",
        facts=(_CODE_FACT,),
        stages=RetrievalStageAttribution(fused_count=1, term_hit=True),
    )
    assert score.strict_pass is False
    assert score.grounded_fact_pass is True
    assert score.outcome is DualOutcome.FACT_COVERED
    assert score.alias_hits == ("invoice 1001",)


def test_deadline_is_distinct_from_wrong_phrasing() -> None:
    """Product deadline copy is a first-class failure even with fused evidence."""

    score = score_company_answer(
        answer_text=DEADLINE_RESERVE_REFUSAL_TEXT,
        facts=(_CODE_FACT,),
        stages=RetrievalStageAttribution(fused_count=4),
        terminal_reason="answer_deadline_reserve_exhausted",
    )
    assert score.deadline_failure is True
    assert score.outcome is DualOutcome.DEADLINE
    assert score.empty_retrieval is False


def test_verifier_refusal_after_fusion_is_not_empty_retrieval() -> None:
    """Fused survivors plus insufficient-evidence copy are verifier-stage."""

    score = score_company_answer(
        answer_text=INSUFFICIENT_EVIDENCE_TEXT,
        facts=(_CODE_FACT,),
        stages=RetrievalStageAttribution(fused_count=3, dense_hit=True),
        answer_status="insufficient_evidence",
    )
    assert score.verifier_refusal_after_fusion is True
    assert score.empty_retrieval is False
    assert score.outcome is DualOutcome.VERIFIER_REFUSAL_AFTER_FUSION


def test_empty_retrieval_requires_zero_channel_hits() -> None:
    """Empty retrieval is proven only when fusion and channels are empty."""

    score = score_company_answer(
        answer_text=INSUFFICIENT_EVIDENCE_TEXT,
        facts=(_CODE_FACT,),
        stages=RetrievalStageAttribution(
            fused_count=0,
            dense_hit=False,
            bm25_hit=False,
            term_hit=False,
            retrieval_empty=True,
        ),
        answer_status="insufficient_evidence",
    )
    assert score.empty_retrieval is True
    assert score.verifier_refusal_after_fusion is False
    assert score.outcome is DualOutcome.EMPTY_RETRIEVAL


def test_curly_apostrophe_matches_ascii_canonical() -> None:
    """Curly apostrophes in answers still match ASCII gold phrases."""

    score = score_company_answer(
        answer_text="users smoothly adjust an agent\u2019s autonomy setting",
        facts=(
            RequiredFact(
                fact_id="autonomy",
                canonical_phrases=("an agent's autonomy",),
            ),
        ),
        stages=RetrievalStageAttribution(fused_count=2, dense_hit=True),
    )
    assert score.strict_pass is True
    assert score.outcome is DualOutcome.STRICT_PHRASE


def test_strict_phrase_beats_empty_retrieval_flag() -> None:
    """A phrase-complete answer is not scored empty when stages disagree."""

    score = score_company_answer(
        answer_text="Manager Coordination",
        facts=(
            RequiredFact(
                fact_id="heading",
                canonical_phrases=("Manager Coordination",),
            ),
        ),
        stages=RetrievalStageAttribution(
            fused_count=0,
            dense_hit=False,
            bm25_hit=False,
            term_hit=False,
            retrieval_empty=True,
        ),
    )
    assert score.empty_retrieval is True
    assert score.strict_pass is True
    assert score.outcome is DualOutcome.STRICT_PHRASE


def test_runner_requires_env_credentials_and_fresh_conversations(
    tmp_path: Path,
) -> None:
    """Missing secrets fail closed and questions cannot share a conversation."""

    with pytest.raises(AskRegressionConfigError):
        load_ask_regression_credentials({})
    with pytest.raises(AskRegressionConfigError):
        load_ask_regression_credentials(
            {
                "SMART_RAG_EVAL_EMAIL": "eval@example.test",
                "SMART_RAG_EVAL_PASSWORD": "changeme",
                "SMART_RAG_EVAL_BASE_URL": "http://127.0.0.1:8000",
            }
        )
    creds = load_ask_regression_credentials(
        {
            "SMART_RAG_EVAL_EMAIL": "eval@example.test",
            "SMART_RAG_EVAL_PASSWORD": "env-sourced-secret",
            "SMART_RAG_EVAL_BASE_URL": "http://127.0.0.1:8000/",
        }
    )
    assert creds.password == "env-sourced-secret"  # noqa: S105
    assert creds.base_url == "http://127.0.0.1:8000"
    with pytest.raises(AskRegressionConfigError):
        assert_fresh_conversation_policy(reuse_conversation_id="shared-conversation")
    questions = (
        CompanyAskQuestion("syn-a", "What is the code?", (_CODE_FACT,)),
        CompanyAskQuestion("syn-b", "Repeat the code.", (_CODE_FACT,)),
    )
    results = run_scored_questions(
        questions,
        answers={
            "syn-a": "The listed code is INV-1001.",
            "syn-b": "invoice 1001 is recorded.",
        },
        stages={
            "syn-a": RetrievalStageAttribution(fused_count=1, term_hit=True),
            "syn-b": RetrievalStageAttribution(fused_count=1, term_hit=True),
        },
    )
    assert results[0].conversation_id != results[1].conversation_id
    assert results[0].score.strict_pass is True
    assert results[1].score.outcome is DualOutcome.FACT_COVERED
    assert (
        score_full_answer_record(
            answer_text="INV-1001",
            facts=(_CODE_FACT,),
            stages=RetrievalStageAttribution(fused_count=1),
        ).strict_pass
        is True
    )
    summary = write_redacted_summary(results, tmp_path / "summary.json")
    text = (tmp_path / "summary.json").read_text(encoding="utf-8")
    assert "INV-1001" not in text
    assert summary["questions"] == 2
    assert summarize_scores(tuple(item.score for item in results))["strict_pass"] == 1


def test_private_gold_must_stay_under_private_eval(tmp_path: Path) -> None:
    """Committed-looking gold paths are rejected."""

    outside = tmp_path / "gold.json"
    outside.write_text("[]", encoding="utf-8")
    with pytest.raises(AskRegressionConfigError):
        load_private_gold(outside)
    private_dir = tmp_path / ".private-eval"
    private_dir.mkdir()
    gold = private_dir / "gold.json"
    gold.write_text(
        (
            '[{"id":"syn-1","prompt":"code?","facts":['
            '{"id":"f1","canonical":["INV-1001"],"aliases":["invoice 1001"]}]}]'
        ),
        encoding="utf-8",
    )
    loaded = load_private_gold(gold)
    assert loaded[0].facts[0].canonical_phrases == ("INV-1001",)
    required_gold = private_dir / "required.json"
    required_gold.write_text(
        '[{"id":"syn-2","question":"code?","required":["INV-1001"]}]',
        encoding="utf-8",
    )
    required_loaded = load_private_gold(required_gold)
    assert required_loaded[0].facts[0].canonical_phrases == ("INV-1001",)
    classes = {item.query_class for item in synthetic_disjoint_cases()}
    assert "acronym" in classes
    assert "bm25_outage" in classes
    assert all(
        "pdf" not in item.document_fixture.casefold()
        for item in synthetic_disjoint_cases()
    )
