"""Phase 6 eval registry completeness, holdout isolation, and online bounds."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest
from smart_rag_core.evaluation.holdout import HoldoutAccess
from smart_rag_core.evaluation.online import (
    ONLINE_EVAL_MAX_CASES,
    ONLINE_EVAL_MAX_USD,
    ONLINE_EVAL_MOCK_DEFAULT,
    OnlineEvalError,
    assert_online_eval_permitted,
)
from smart_rag_core.evaluation.phase6_registry import (
    PHASE6_EVAL_REGISTRY,
    REQUIRED_CATEGORY_IDS,
    missing_registry_categories,
    qt_eval_009_status,
)


def test_registry_maps_every_required_category() -> None:
    """CI fails if a packet-7 category has no mapped command."""

    assert missing_registry_categories() == ()
    assert set(REQUIRED_CATEGORY_IDS) <= set(PHASE6_EVAL_REGISTRY)
    for category_id in REQUIRED_CATEGORY_IDS:
        mapping = PHASE6_EVAL_REGISTRY[category_id]
        assert mapping.command.strip()
        assert mapping.evidence_doc
        assert (Path(__file__).resolve().parents[2] / mapping.evidence_doc).is_file()


def test_holdout_stays_sealed_and_qt_eval_009_unverified() -> None:
    """Launch holdout remains denied; Combined +10pp is not claimed proven."""

    assert HoldoutAccess.denied().allowed is False
    assert qt_eval_009_status() == "unverified"
    assert PHASE6_EVAL_REGISTRY["qt_eval_009_combined_plus_10pp"].status == (
        "unverified"
    )


def test_online_eval_refuses_unbounded_openai_and_holdout() -> None:
    """Online eval is mock-default, sample-capped, and holdout-disjoint."""

    assert ONLINE_EVAL_MOCK_DEFAULT is True
    assert_online_eval_permitted(
        mock_mode=True,
        case_count=ONLINE_EVAL_MAX_CASES,
        max_usd=ONLINE_EVAL_MAX_USD,
        holdout_access=HoldoutAccess.denied(),
    )
    with pytest.raises(OnlineEvalError, match="unbounded_openai_forbidden"):
        assert_online_eval_permitted(
            case_count=1,
            max_usd=Decimal("1.00"),
            unlimited_openai=True,
        )
    with pytest.raises(OnlineEvalError, match="sample_exceeds_ceiling"):
        assert_online_eval_permitted(
            case_count=ONLINE_EVAL_MAX_CASES + 1,
            max_usd=Decimal("1.00"),
        )
    with pytest.raises(OnlineEvalError, match="cost_exceeds_ceiling"):
        assert_online_eval_permitted(
            case_count=1,
            max_usd=ONLINE_EVAL_MAX_USD + Decimal("0.01"),
        )
    with pytest.raises(OnlineEvalError, match="holdout_forbidden"):
        assert_online_eval_permitted(
            case_count=1,
            max_usd=Decimal("1.00"),
            holdout_access=HoldoutAccess(
                allowed=True,
                purpose="packet8_immutable_holdout",
                actor="tester",
            ),
        )


def test_check_phase6_eval_registry_script_exists() -> None:
    """The cheap unit-tier script is present next to other CI gates."""

    script = (
        Path(__file__).resolve().parents[2]
        / "scripts"
        / "ci"
        / "check_phase6_eval_registry.py"
    )
    assert script.is_file()
    text = script.read_text(encoding="utf-8")
    assert "missing_registry_categories" in text
    assert "qt_eval_009_status" in text
