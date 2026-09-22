"""Verbose Ask runner lines stay free of answer text and gold phrases."""

from scripts.run_company_ask import (
    classify_ask_drop,
    format_diagnosis_line,
    format_live_ask_line,
)


def test_live_line_names_reason_and_coverage() -> None:
    """A live line shows the terminal reason and coverage, not the answer."""

    line = format_live_ask_line(
        done=3,
        total=50,
        question_id="k03",
        terminal="partial",
        reason="citation_persist_failed",
        origin="company_documents",
        coverage=0.9,
        correction="none",
        citations=1,
        path="fuse_evidence:fused>verify_answer:verified",
    )

    assert line == (
        "3/50 id=k03 terminal=partial reason=citation_persist_failed "
        "origin=company_documents coverage=0.90 correction=none "
        "citations=1 path=fuse_evidence:fused>verify_answer:verified"
    )
    assert "The book says" not in line


def test_diagnosis_line_names_citation_drop_without_phrases() -> None:
    """Citation failures become a drop bucket and codes, not prose."""

    line = format_diagnosis_line(
        question_id="k12",
        outcome="verifier_refusal_after_fusion",
        strict_pass=False,
        grounded=False,
        missed_fact_ids=("k12-f1",),
        terminal="insufficient_evidence",
        reason="citation_persist_failed",
        origin="company_documents",
        coverage=1.0,
        rerank_call_count=1,
        rerank_fallback="none",
        profile="hybrid_default_v1",
        resolution="unscoped",
        gold_page=85,
        gold_page_in_fusion=True,
        citation_failures=("paragraph_unmapped",),
    )

    assert "drop=citation" in line
    assert "failures=paragraph_unmapped" in line
    assert "missed=k12-f1" in line
    assert "in_fusion=yes" in line
    assert "gold phrase" not in line


def test_missing_gold_page_is_a_retrieval_miss() -> None:
    """A fused set that omits the gold page is a retrieval miss."""

    assert (
        classify_ask_drop(
            outcome="wrong_phrasing",
            grounded=False,
            gold_page_in_fusion=False,
            citation_failures=(),
        )
        == "retrieval_miss"
    )


def test_cap_drop_is_named_rerank_pool_drop() -> None:
    """A gold page inside fused ids but outside the pool is a pool drop."""

    assert (
        classify_ask_drop(
            outcome="wrong_phrasing",
            grounded=False,
            gold_page_in_fusion=False,
            citation_failures=(),
            gold_page_in_fused=True,
            gold_page_in_rerank_pool=False,
        )
        == "rerank_pool_drop"
    )
    assert (
        classify_ask_drop(
            outcome="wrong_phrasing",
            grounded=False,
            gold_page_in_fusion=False,
            citation_failures=(),
            gold_page_in_fused=True,
            gold_page_in_rerank_pool=True,
        )
        == "selection_drop"
    )
    assert (
        classify_ask_drop(
            outcome="wrong_phrasing",
            grounded=False,
            gold_page_in_fusion=False,
            citation_failures=(),
            gold_page_in_fused=False,
            gold_page_in_rerank_pool=None,
        )
        == "retrieval_miss"
    )
