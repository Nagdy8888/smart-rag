"""Unit tests for post-extraction governance integration."""

from __future__ import annotations

from smart_rag_core.ingestion.governance import (
    ExtractionGovernanceInput,
    evaluate_extraction_governance,
)
from smart_rag_core.ingestion.limits import EXTERNAL_PROCESSING_POLICY_VERSION
from smart_rag_core.security.external_processing import ContentClass


def test_extraction_positive_detector_blocks_promotion() -> None:
    """Positive extracted-text detector fails closed before promotion."""

    result = evaluate_extraction_governance(
        ExtractionGovernanceInput(
            declared_category="allowed",
            attestation_present=True,
            attestation_policy_version=EXTERNAL_PROCESSING_POLICY_VERSION,
            review_approved=True,
            content_class=ContentClass.SYNTHETIC,
        ),
        extracted_texts=("contact api_key=secret-value",),
        scan_evidence_current=True,
    )
    assert result.promotion_allowed is False
    assert result.external_processing.allowed is False
    assert result.external_processing.reason_code == "sensitive_detector"


def test_extraction_clean_synthetic_allows_with_gates() -> None:
    """Clean synthetic extraction passes governance when attestation matches."""

    result = evaluate_extraction_governance(
        ExtractionGovernanceInput(
            declared_category="allowed",
            attestation_present=True,
            attestation_policy_version=EXTERNAL_PROCESSING_POLICY_VERSION,
            review_approved=False,
            content_class=ContentClass.SYNTHETIC,
        ),
        extracted_texts=("harmless fixture text",),
        scan_evidence_current=True,
    )
    assert result.promotion_allowed is True
    assert result.external_processing.allowed is True
