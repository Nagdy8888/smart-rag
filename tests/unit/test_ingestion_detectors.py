"""Unit tests for ``detectors-v1`` Luhn/issuer payment-card checks."""

from __future__ import annotations

from smart_rag_core.ingestion.detectors import (
    DETECTOR_FAMILY_PAYMENT_CARD,
    DETECTOR_POLICY_VERSION,
    has_payment_card_issuer_prefix,
    luhn_valid,
    run_detectors_v1,
)
from smart_rag_core.ingestion.governance import (
    ExtractionGovernanceInput,
    evaluate_extraction_governance,
)
from smart_rag_core.ingestion.limits import EXTERNAL_PROCESSING_POLICY_VERSION
from smart_rag_core.security.external_processing import ContentClass, DetectorResult


def test_isbn_like_number_is_not_a_payment_card() -> None:
    """Thirteen-digit ISBN-shaped values without issuer/Luhn stay clean.

    Returns:
        None.
    """

    outcomes = run_detectors_v1(None, ("See identifier 9780262048224 in the index.",))
    payment = next(item for item in outcomes if item.family == DETECTOR_FAMILY_PAYMENT_CARD)
    assert payment.result is DetectorResult.CLEAN
    assert DETECTOR_POLICY_VERSION == "detectors-v1"


def test_luhn_valid_visa_test_number_is_positive() -> None:
    """A Luhn-valid Visa test PAN is a payment-card hit without storing digits.

    Returns:
        None.
    """

    outcomes = run_detectors_v1(None, ("card 4111111111111111",))
    payment = next(item for item in outcomes if item.family == DETECTOR_FAMILY_PAYMENT_CARD)
    assert payment.result is DetectorResult.POSITIVE
    assert payment.bounded_count == 1
    assert "4111" not in payment.locator_fingerprint


def test_luhn_helper_rejects_non_issuer_checksum() -> None:
    """Issuer prefix without a valid checksum is not a card.

    Returns:
        None.
    """

    assert luhn_valid("4111111111111111") is True
    assert has_payment_card_issuer_prefix("4111111111111111") is True
    assert luhn_valid("4111111111111112") is False


def test_reviewed_false_positive_allows_promotion() -> None:
    """Hash-bound review, not payload flags, can clear a detector hold.

    Returns:
        None.
    """

    result = evaluate_extraction_governance(
        ExtractionGovernanceInput(
            declared_category="allowed",
            attestation_present=True,
            attestation_policy_version=EXTERNAL_PROCESSING_POLICY_VERSION,
            review_approved=True,
            content_class=ContentClass.SYNTHETIC,
        ),
        extracted_texts=("card 4111111111111111",),
        scan_evidence_current=True,
    )
    assert result.promotion_allowed is True
    assert result.detector_results[0] is DetectorResult.POSITIVE
