"""Unit tests for deny-by-default external-processing governance decisions."""

from __future__ import annotations

from smart_rag_core.security.external_processing import (
    CategoryDisposition,
    ContentClass,
    DetectorResult,
    ExternalProcessingDecisionInput,
    decide_external_processing,
)


def _base_allowed_input() -> ExternalProcessingDecisionInput:
    """Build a fully valid synthetic allow fixture.

    Returns:
        Decision input that should allow external processing for synthetic content.
    """

    return ExternalProcessingDecisionInput(
        attestation_present=True,
        category=CategoryDisposition.ALLOWED,
        detector_results=[DetectorResult.CLEAN, DetectorResult.CLEAN],
        scan_evidence_current=True,
        provider_settings_verified=True,
        policy_version_matches=True,
        content_class=ContentClass.SYNTHETIC,
    )


def test_synthetic_clean_input_allows() -> None:
    """Synthetic fixtures with clean gates may proceed for tests."""

    decision = decide_external_processing(_base_allowed_input())
    assert decision.allowed is True
    assert decision.reason_code == "allowed"


def test_missing_attestation_denies() -> None:
    """Missing attestation cannot produce an allowed decision."""

    payload = _base_allowed_input().model_copy(update={"attestation_present": False})
    decision = decide_external_processing(payload)
    assert decision.allowed is False
    assert decision.reason_code == "missing_attestation"


def test_expired_approval_denies() -> None:
    """Expired approval cannot produce an allowed decision."""

    payload = _base_allowed_input().model_copy(update={"attestation_expired": True})
    decision = decide_external_processing(payload)
    assert decision.allowed is False
    assert decision.reason_code == "expired_approval"


def test_contradictory_category_denies() -> None:
    """Contradictory category evidence denies external processing."""

    payload = _base_allowed_input().model_copy(
        update={"attestation_contradictory": True}
    )
    decision = decide_external_processing(payload)
    assert decision.allowed is False
    assert decision.reason_code == "contradictory_category"


def test_positive_detector_denies() -> None:
    """Positive sensitive detectors deny and never auto-approve."""

    payload = _base_allowed_input().model_copy(
        update={"detector_results": [DetectorResult.CLEAN, DetectorResult.POSITIVE]}
    )
    decision = decide_external_processing(payload)
    assert decision.allowed is False
    assert decision.reason_code == "sensitive_detector"


def test_unverified_provider_settings_deny_real_content() -> None:
    """Unavailable provider settings cannot allow real company content."""

    payload = _base_allowed_input().model_copy(
        update={
            "content_class": ContentClass.REAL_COMPANY,
            "provider_settings_verified": False,
        }
    )
    decision = decide_external_processing(payload)
    assert decision.allowed is False
    assert decision.reason_code == "unverified_provider_settings"
