"""Reliability metrics expose missing judgments rather than fabricated passes."""

import json
from typing import cast

from smart_rag_core.evaluation.company_ask_regression import CompanyAskQuestion
from smart_rag_core.evaluation.knowledge_metrics import summarize_knowledge_metrics


def test_category_metrics_are_private_and_missing_measurements_stay_unknown() -> None:
    """Arabic coverage and measurement availability remain independently visible."""
    questions = [
        CompanyAskQuestion("en", "What is the policy?", (), kind="policy"),
        CompanyAskQuestion("ar", "ما سياسة الإجازات؟", (), kind="policy"),
    ]
    report = summarize_knowledge_metrics(
        questions,
        [],
        {
            "en": {
                "knowledge_result": {"outcome": "partial"},
                "timing": {"wall_seconds": 2.5},
                "usage": {"cost_usd": 0.01},
                "citation_supported": True,
            }
        },
    )
    encoded = json.dumps(report, ensure_ascii=False)
    assert all(question.prompt not in encoded for question in questions)
    assert report["quality_gate"] == "not_evaluated"
    categories = cast(dict[str, dict[str, object]], report["categories"])
    english = categories["policy:en"]
    arabic = categories["policy:ar"]
    assert english["latency_p95_seconds"] == 2.5
    assert (
        cast(dict[str, dict[str, object]], english["judgments"])["citation_supported"][
            "pass_rate"
        ]
        == 1
    )
    assert arabic["outcome_measured"] == 0
    assert arabic["measured_cost_usd"] is None
    assert (
        cast(dict[str, dict[str, object]], arabic["judgments"])["citation_supported"][
            "pass_rate"
        ]
        is None
    )
