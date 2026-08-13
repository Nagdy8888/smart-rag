"""Deny-by-default external-processing governance decisions.

This module encodes the Phase 3 Packet 1 decision record. It never contacts
providers and never auto-approves from detector hits alone.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class CategoryDisposition(StrEnum):
    """Uploader category disposition from the signed governance packet."""

    ALLOWED = "allowed"
    PROHIBITED = "prohibited"
    MANDATORY_REVIEW = "mandatory_review"
    UNKNOWN = "unknown"


class DetectorResult(StrEnum):
    """Deterministic local detector outcome for one pattern family."""

    CLEAN = "clean"
    POSITIVE = "positive"
    UNKNOWN = "unknown"


class ContentClass(StrEnum):
    """Whether the payload is real company content or synthetic fixtures."""

    REAL_COMPANY = "real_company"
    SYNTHETIC = "synthetic"


class ExternalProcessingDecisionInput(BaseModel):
    """Inputs required to decide ``external_processing_allowed``.

    Attributes:
        attestation_present: Whether uploader category/authority attestation exists.
        attestation_expired: Whether attestation or review approval is expired.
        attestation_contradictory: Whether attestation conflicts with detectors/metadata.
        category: Declared or inferred category disposition.
        review_approved: Active owner/admin approval for mandatory-review categories.
        detector_results: Outcomes for each configured detector family.
        scan_evidence_current: Whether malware/scan evidence is present and fresh.
        provider_settings_verified: Whether required provider matrix rows are verified.
        policy_version_matches: Whether attestation cites the signed policy version.
        content_class: Real company versus synthetic fixture content.
    """

    attestation_present: bool
    attestation_expired: bool = False
    attestation_contradictory: bool = False
    category: CategoryDisposition
    review_approved: bool = False
    detector_results: list[DetectorResult] = Field(default_factory=list[DetectorResult])
    scan_evidence_current: bool = False
    provider_settings_verified: bool = False
    policy_version_matches: bool = False
    content_class: ContentClass = ContentClass.REAL_COMPANY


class ExternalProcessingDecision(BaseModel):
    """Immutable allow/deny result with an auditable reason code.

    Attributes:
        allowed: Whether external processing may proceed.
        reason_code: Stable machine reason for logs and tests.
        detail: Short human-readable explanation without secrets.
    """

    allowed: bool
    reason_code: str
    detail: str


def decide_external_processing(
    decision_input: ExternalProcessingDecisionInput,
) -> ExternalProcessingDecision:
    """Decide ``external_processing_allowed`` with deny-by-default semantics.

    Args:
        decision_input: Attestation, category, detector, scan, and provider evidence.

    Returns:
        Decision that is ``allowed`` only when every gate passes. Missing,
        expired, contradictory, prohibited, review-required, positive/unknown
        detector, stale scan, unverified provider settings for real content, or
        policy mismatch always deny.

    Side Effects:
        None. Pure function; no I/O.
    """

    if not decision_input.attestation_present:
        return ExternalProcessingDecision(
            allowed=False,
            reason_code="missing_attestation",
            detail="Uploader category/authority attestation is missing.",
        )
    if decision_input.attestation_expired:
        return ExternalProcessingDecision(
            allowed=False,
            reason_code="expired_approval",
            detail="Attestation or review approval is expired.",
        )
    if decision_input.attestation_contradictory:
        return ExternalProcessingDecision(
            allowed=False,
            reason_code="contradictory_category",
            detail="Attestation contradicts detectors or metadata.",
        )
    if not decision_input.policy_version_matches:
        return ExternalProcessingDecision(
            allowed=False,
            reason_code="policy_version_mismatch",
            detail="Attestation policy version does not match the signed packet.",
        )
    if decision_input.category is CategoryDisposition.PROHIBITED:
        return ExternalProcessingDecision(
            allowed=False,
            reason_code="prohibited_category",
            detail="Category is prohibited for external processing.",
        )
    if decision_input.category is CategoryDisposition.UNKNOWN:
        return ExternalProcessingDecision(
            allowed=False,
            reason_code="unknown_category",
            detail="Category is unknown; remain quarantined for review.",
        )
    if (
        decision_input.category is CategoryDisposition.MANDATORY_REVIEW
        and not decision_input.review_approved
    ):
        return ExternalProcessingDecision(
            allowed=False,
            reason_code="review_required",
            detail="Mandatory-review category lacks owner/admin approval.",
        )
    if any(result is not DetectorResult.CLEAN for result in decision_input.detector_results):
        return ExternalProcessingDecision(
            allowed=False,
            reason_code="sensitive_detector",
            detail="A detector result is positive or unknown.",
        )
    if not decision_input.scan_evidence_current:
        return ExternalProcessingDecision(
            allowed=False,
            reason_code="stale_or_missing_scan",
            detail="Current malware/scan evidence is missing or stale.",
        )
    if (
        decision_input.content_class is ContentClass.REAL_COMPANY
        and not decision_input.provider_settings_verified
    ):
        return ExternalProcessingDecision(
            allowed=False,
            reason_code="unverified_provider_settings",
            detail="Required provider settings are unverified for real company content.",
        )
    if decision_input.category is not CategoryDisposition.ALLOWED and not (
        decision_input.category is CategoryDisposition.MANDATORY_REVIEW
        and decision_input.review_approved
    ):
        return ExternalProcessingDecision(
            allowed=False,
            reason_code="category_not_allowed",
            detail="Category disposition does not permit external processing.",
        )
    return ExternalProcessingDecision(
        allowed=True,
        reason_code="allowed",
        detail="All governance gates passed.",
    )
