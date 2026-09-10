"""Unit tests for paired bake-off metrics and classification."""

from __future__ import annotations

from uuid import uuid4

from smart_rag_core.evaluation.parser_bakeoff.metrics import (
    bootstrap_mean_ci,
    classify,
    compare_reports,
)
from smart_rag_core.evaluation.parser_bakeoff.models import (
    Classification,
    LaneAgentScore,
    LaneIdentity,
    LaneRetrieveScore,
    PairedMetric,
)


def _identity(lane_id: str, *, locators: bool) -> LaneIdentity:
    """Build one lane identity.

    Args:
        lane_id: Lane token.
        locators: Physical PDF locators available.

    Returns:
        Identity model.
    """

    return LaneIdentity(
        lane_id=lane_id,  # type: ignore[arg-type]
        parser_version="parser_v1"
        if lane_id == "current"
        else "anydoc_pdf_0_2_4_local",
        cleaning_version="cleaning_v1",
        locator_available=locators,
        ingest_document_id=uuid4(),
        ingest_version_id=uuid4(),
    )


def _retrieve(
    hit: bool, *, locator_ok: bool, locator_available: bool
) -> LaneRetrieveScore:
    """Build one retrieval score.

    Args:
        hit: Recall@10 hit.
        locator_ok: Locator correctness.
        locator_available: Provenance available.

    Returns:
        Retrieval score.
    """

    return LaneRetrieveScore(
        case_id="case-0010",
        recall_hit_at_10=hit,
        locator_ok=locator_ok,
        locator_available=locator_available,
        refusal_ok=True,
        first_evidence_ms=20.0,
        ranked_id_count=5,
    )


def _agent(*, faith: float | None, status: str = "complete") -> LaneAgentScore:
    """Build one agent score.

    Args:
        faith: Faithfulness.
        status: Judge status.

    Returns:
        Agent score.
    """

    return LaneAgentScore(
        case_id="case-0010",
        citation_correctness=1.0,
        citation_completeness=1.0,
        fact_completeness=1.0,
        faithfulness=faith,
        judge_status=status,
        refusal_ok=True,
        cost_usd=0.01,
    )


def test_bootstrap_seed_is_deterministic() -> None:
    """The recorded seed must reproduce the same interval."""

    paired = ((0.2, 0.4), (0.3, 0.5), (0.1, 0.2))
    first = bootstrap_mean_ci(paired, seed=20260909, resamples=200)
    second = bootstrap_mean_ci(paired, seed=20260909, resamples=200)
    assert first == second
    assert first[0] is not None and first[1] is not None


def test_missing_locators_and_unscored_are_inconclusive_or_secondary() -> None:
    """Unavailable locators cannot become a primary-parser candidate."""

    current = _identity("current", locators=True)
    anydoc = _identity("anydoc_local", locators=False)
    report = compare_reports(
        run_id="run",
        source_sha256="a" * 64,
        source_basename="book.pdf",
        current_identity=current,
        anydoc_identity=anydoc,
        current_chunk=None,
        anydoc_chunk=None,
        current_retrieve=(_retrieve(True, locator_ok=True, locator_available=True),),
        anydoc_retrieve=(_retrieve(True, locator_ok=False, locator_available=False),),
        current_agent=(_agent(faith=0.9),),
        anydoc_agent=(_agent(faith=0.95),),
        mapping_review_count=0,
        infra_mismatch=False,
    )
    locator = next(
        item for item in report.paired_metrics if item.name == "locator_correctness"
    )
    assert locator.anydoc_local == 0.0
    assert report.anydoc_local.locator_available is False
    unscored = compare_reports(
        run_id="run",
        source_sha256="a" * 64,
        source_basename="book.pdf",
        current_identity=current,
        anydoc_identity=anydoc,
        current_chunk=None,
        anydoc_chunk=None,
        current_retrieve=(_retrieve(True, locator_ok=True, locator_available=True),),
        anydoc_retrieve=(_retrieve(True, locator_ok=False, locator_available=False),),
        current_agent=(_agent(faith=None, status="unscored"),),
        anydoc_agent=(_agent(faith=0.9),),
        mapping_review_count=0,
        infra_mismatch=False,
    )
    assert unscored.classification is Classification.INCONCLUSIVE


def test_classification_branches() -> None:
    """Cover leak, mismatch, review, CI, secondary, primary, and current."""

    recall = PairedMetric(
        name="hybrid_recall_at_10",
        current=0.4,
        anydoc_local=0.8,
        delta=0.4,
        ci_low=0.1,
        ci_high=0.6,
        winner="anydoc_local",
    )
    faith = PairedMetric(
        name="judge_faithfulness",
        current=0.8,
        anydoc_local=0.9,
        delta=0.1,
        ci_low=0.01,
        ci_high=0.2,
        winner="anydoc_local",
    )
    token, _reasons = classify(
        recall=recall,
        faithfulness=faith,
        current_locator_available=True,
        anydoc_locator_available=True,
        acl_leaks=1,
        unscored_count=0,
        mapping_review_unresolved=0,
        infra_mismatch=False,
    )
    assert token is Classification.INCONCLUSIVE
    token, _reasons = classify(
        recall=recall,
        faithfulness=faith,
        current_locator_available=True,
        anydoc_locator_available=True,
        acl_leaks=0,
        unscored_count=0,
        mapping_review_unresolved=0,
        infra_mismatch=True,
    )
    assert token is Classification.INCONCLUSIVE
    token, _reasons = classify(
        recall=recall,
        faithfulness=faith,
        current_locator_available=True,
        anydoc_locator_available=True,
        acl_leaks=0,
        unscored_count=0,
        mapping_review_unresolved=2,
        infra_mismatch=False,
    )
    assert token is Classification.INCONCLUSIVE
    crossing = recall.model_copy(update={"ci_low": -0.1, "ci_high": 0.1, "delta": 0.0})
    token, _reasons = classify(
        recall=crossing,
        faithfulness=faith,
        current_locator_available=True,
        anydoc_locator_available=False,
        acl_leaks=0,
        unscored_count=0,
        mapping_review_unresolved=0,
        infra_mismatch=False,
    )
    assert token is Classification.INCONCLUSIVE
    token, reasons = classify(
        recall=recall,
        faithfulness=faith,
        current_locator_available=True,
        anydoc_locator_available=False,
        acl_leaks=0,
        unscored_count=0,
        mapping_review_unresolved=0,
        infra_mismatch=False,
    )
    assert token is Classification.ANYDOC_SECONDARY_CANDIDATE
    assert "without_pdf_locators" in reasons[0]
    token, _reasons = classify(
        recall=recall,
        faithfulness=faith,
        current_locator_available=True,
        anydoc_locator_available=True,
        acl_leaks=0,
        unscored_count=0,
        mapping_review_unresolved=0,
        infra_mismatch=False,
    )
    assert token is Classification.ANYDOC_PRIMARY_CANDIDATE
    worse = recall.model_copy(
        update={"delta": -0.2, "anydoc_local": 0.2, "winner": "current"}
    )
    token, _reasons = classify(
        recall=worse,
        faithfulness=faith,
        current_locator_available=True,
        anydoc_locator_available=False,
        acl_leaks=0,
        unscored_count=0,
        mapping_review_unresolved=0,
        infra_mismatch=False,
    )
    assert token is Classification.CURRENT_PRIMARY
