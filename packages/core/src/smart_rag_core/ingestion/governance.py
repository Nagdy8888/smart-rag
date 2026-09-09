"""Metadata- and extraction-level governance gates before promotion."""

from __future__ import annotations

from dataclasses import dataclass

from smart_rag_core.ingestion.detectors import (
    DETECTOR_POLICY_VERSION,
    DetectorFamilyOutcome,
    detector_results_from_outcomes,
    run_detectors_v1,
)
from smart_rag_core.ingestion.limits import EXTERNAL_PROCESSING_POLICY_VERSION
from smart_rag_core.security.external_processing import (
    CategoryDisposition,
    ContentClass,
    DetectorResult,
    ExternalProcessingDecision,
    ExternalProcessingDecisionInput,
    decide_external_processing,
)


def _provider_settings_verified_for_process() -> bool:
    """Return the local-unsigned live-key waiver, not org-matrix verification.

    Returns:
        True when ``APP_ENV=local`` and ``MOCK_MODEL_MODE=false``.
    """

    from smart_rag_core.settings import SharedSettings

    return SharedSettings().allows_unsigned_local_live_providers()


@dataclass(frozen=True, slots=True)
class MetadataGovernanceInput:
    """Uploader attestation and metadata available before parser extraction.

    ``review_approved`` is the hash-bound repository decision, never a
    ``payload_ref.review_approved`` override.
    """

    declared_category: str | None
    attestation_present: bool
    attestation_policy_version: str | None
    review_approved: bool = False
    filename: str | None = None
    content_class: ContentClass = ContentClass.REAL_COMPANY


@dataclass(frozen=True, slots=True)
class MetadataGovernanceResult:
    """Governance evaluation for metadata-only detectors."""

    category: CategoryDisposition
    detector_results: tuple[DetectorResult, ...]
    detector_outcomes: tuple[DetectorFamilyOutcome, ...]
    detector_policy_version: str
    external_processing: ExternalProcessingDecision
    promotion_allowed: bool
    detail: str


@dataclass(frozen=True, slots=True)
class ExtractionGovernanceInput:
    """Uploader attestation plus optional filename metadata."""

    declared_category: str | None
    attestation_present: bool
    attestation_policy_version: str | None
    review_approved: bool = False
    filename: str | None = None
    content_class: ContentClass = ContentClass.REAL_COMPANY


@dataclass(frozen=True, slots=True)
class ExtractionGovernanceResult:
    """Governance evaluation after local parser extraction."""

    category: CategoryDisposition
    detector_results: tuple[DetectorResult, ...]
    detector_outcomes: tuple[DetectorFamilyOutcome, ...]
    detector_policy_version: str
    external_processing: ExternalProcessingDecision
    promotion_allowed: bool
    detail: str


def evaluate_metadata_governance(
    decision_input: MetadataGovernanceInput,
    *,
    scan_evidence_current: bool,
) -> MetadataGovernanceResult:
    """Run metadata-level detectors and external-processing decision.

    Real company content requires explicit reviewer approval and verified
    provider settings before external processing is allowed.

    Args:
        decision_input: Uploader attestation and filename metadata.
        scan_evidence_current: Whether current scan evidence exists.

    Returns:
        Governance result including promotion allowance for synthetic or
        hash-bound reviewed content only when scan evidence is current.
    """

    category = _resolve_category(decision_input.declared_category)
    outcomes = run_detectors_v1(decision_input.filename, ())
    detectors = detector_results_from_outcomes(outcomes)
    external, promotion_allowed, detail = _decide(
        decision_input=decision_input,
        category=category,
        detectors=detectors,
        scan_evidence_current=scan_evidence_current,
        passed_detail="metadata governance passed",
    )
    return MetadataGovernanceResult(
        category=category,
        detector_results=detectors,
        detector_outcomes=outcomes,
        detector_policy_version=DETECTOR_POLICY_VERSION,
        external_processing=external,
        promotion_allowed=promotion_allowed,
        detail=detail,
    )


def evaluate_extraction_governance(
    decision_input: ExtractionGovernanceInput,
    *,
    extracted_texts: tuple[str, ...],
    scan_evidence_current: bool,
) -> ExtractionGovernanceResult:
    """Run metadata plus extracted-text detectors before promotion/external calls.

    Args:
        decision_input: Uploader attestation and filename metadata. Reviews must
            already be hash-bound; payload flags are not consulted here.
        extracted_texts: Normalized text fragments from typed parser output.
        scan_evidence_current: Whether current scan evidence exists.

    Returns:
        Fail-closed governance result integrated with ``decide_external_processing``.
    """

    category = _resolve_category(decision_input.declared_category)
    outcomes = run_detectors_v1(decision_input.filename, extracted_texts)
    detectors = detector_results_from_outcomes(outcomes)
    external, promotion_allowed, detail = _decide(
        decision_input=decision_input,
        category=category,
        detectors=detectors,
        scan_evidence_current=scan_evidence_current,
        passed_detail="extraction governance passed",
    )
    return ExtractionGovernanceResult(
        category=category,
        detector_results=detectors,
        detector_outcomes=outcomes,
        detector_policy_version=DETECTOR_POLICY_VERSION,
        external_processing=external,
        promotion_allowed=promotion_allowed,
        detail=detail,
    )


def _decide(
    *,
    decision_input: MetadataGovernanceInput | ExtractionGovernanceInput,
    category: CategoryDisposition,
    detectors: tuple[DetectorResult, ...],
    scan_evidence_current: bool,
    passed_detail: str,
) -> tuple[ExternalProcessingDecision, bool, str]:
    """Apply deny-by-default gates with hash-bound false-positive reviews.

    Args:
        decision_input: Attestation and content class.
        category: Resolved category disposition.
        detectors: Raw detector results before review overlay.
        scan_evidence_current: Fresh scan evidence flag.
        passed_detail: Detail when promotion is allowed.

    Returns:
        External decision, promotion flag, and detail.
    """

    reviewed = decision_input.review_approved
    effective = (
        tuple(DetectorResult.CLEAN for _ in detectors) if reviewed else detectors
    )
    external = decide_external_processing(
        ExternalProcessingDecisionInput(
            attestation_present=decision_input.attestation_present,
            category=category,
            review_approved=reviewed,
            detector_results=list(effective),
            scan_evidence_current=scan_evidence_current,
            provider_settings_verified=_provider_settings_verified_for_process(),
            policy_version_matches=(
                decision_input.attestation_policy_version
                == EXTERNAL_PROCESSING_POLICY_VERSION
            ),
            content_class=decision_input.content_class,
        )
    )
    detectors_ok = (
        all(result is DetectorResult.CLEAN for result in detectors) or reviewed
    )
    promotion_allowed = (
        scan_evidence_current
        and category is not CategoryDisposition.PROHIBITED
        and category is not CategoryDisposition.UNKNOWN
        and detectors_ok
    )
    detail = external.detail if not promotion_allowed else passed_detail
    return external, promotion_allowed, detail


def _resolve_category(declared_category: str | None) -> CategoryDisposition:
    """Map declared category text to disposition.

    Args:
        declared_category: Uploader attestation category.

    Returns:
        Disposition used by the signed packet.
    """

    if declared_category is None or not declared_category.strip():
        return CategoryDisposition.UNKNOWN
    normalized = declared_category.strip().lower()
    if normalized in {"allowed", "public", "internal"}:
        return CategoryDisposition.ALLOWED
    if normalized in {"prohibited", "restricted", "secret"}:
        return CategoryDisposition.PROHIBITED
    if normalized in {"review", "mandatory_review", "regulated"}:
        return CategoryDisposition.MANDATORY_REVIEW
    return CategoryDisposition.UNKNOWN
