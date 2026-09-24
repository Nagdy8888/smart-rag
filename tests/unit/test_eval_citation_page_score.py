"""Citation-page scoring counts gold, near, and other pages without text."""

from __future__ import annotations

from typing import cast

from scripts.eval_citation_page_score import score_rows


def test_score_rows_counts_fact_and_gold_page() -> None:
    """A strict pass with the gold page cited counts as fact and gold page."""

    result = score_rows(
        gold_pages={"q1": 10, "q2": 20},
        run_ids={"q1": "r1", "q2": "r2"},
        strict={"q1": True, "q2": False},
        citation_pages={"r1": [10, 11], "r2": [20]},
    )
    assert result["totals"] == {
        "questions": 2,
        "cited_gold": 2,
        "fact_and_gold_page": 1,
        "fact_near_page": 0,
        "fact_other_page": 0,
    }


def test_score_rows_near_page_is_not_gold() -> None:
    """One page away counts as near only when the gold page is not cited."""

    result = score_rows(
        gold_pages={"q1": 10, "q2": 30},
        run_ids={"q1": "r1", "q2": "r2"},
        strict={"q1": True, "q2": True},
        citation_pages={"r1": [9], "r2": [28, 33]},
    )
    assert result["totals"] == {
        "questions": 2,
        "cited_gold": 0,
        "fact_and_gold_page": 0,
        "fact_near_page": 1,
        "fact_other_page": 1,
    }
    rows = cast(list[dict[str, object]], result["questions"])
    assert rows[0] == {
        "id": "q1",
        "gold_page": 10,
        "pages": [9],
        "strict": True,
        "cited_gold": False,
        "cited_near": True,
    }


def test_score_rows_run_without_citations_counts_zero() -> None:
    """A question with no run or no citations scores no page."""

    result = score_rows(
        gold_pages={"q1": 5, "q2": 6},
        run_ids={"q1": "r1"},
        strict={"q1": True, "q2": True},
        citation_pages={},
    )
    assert result["totals"] == {
        "questions": 2,
        "cited_gold": 0,
        "fact_and_gold_page": 0,
        "fact_near_page": 0,
        "fact_other_page": 2,
    }
