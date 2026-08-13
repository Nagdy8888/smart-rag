"""Metadata-level governance gates before promotion or external processing."""

from __future__ import annotations

import re
from dataclasses import dataclass

from smart_rag_core.ingestion.limits import EXTERNAL_PROCESSING_POLICY_VERSION
from smart_rag_core.security.external_processing import (
    CategoryDisposition,
    ContentClass,
    DetectorResult,
    ExternalProcessingDecision,
    ExternalProcessingDecisionInput,
    decide_external_processing,
)

_CARD_PATTERN = re.compile(r"\b(?:\d[ -]*?){13,19}\b")
_SECRET_PATTERN = re.compile(r"(?i)\b(api[_-]?key|secret|password|token|credential)\b")


@dataclass(frozen=True, slots=True)
class MetadataGovernanceInput:
    """Uploader attestation and metadata available before parser extraction."""

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
    external_processing: ExternalProcessingDecision
    promotion_allowed: bool
    detail: str


def evaluate_metadata_governance(
    decision_input: MetadataGovernanceInput,
    *,
    scan_evidence_current: bool,
) -> MetadataGovernanceResult:
    """Run metadata-level detectors and external-processing decision.

    Until Packet 5 extracted-text detectors exist, real company content requires
    an explicit reviewer approval and cannot enable external processing.

    Args:
        decision_input: Uploader attestation and filename metadata.
        scan_evidence_current: Whether current scan evidence exists.

    Returns:
        Governance result including promotion allowance for synthetic/reviewer
        approved content only when scan evidence is current.
    """

    category = _resolve_category(decision_input.declared_category)
    detectors = _run_metadata_detectors(decision_input.filename)
    external = decide_external_processing(
        ExternalProcessingDecisionInput(
            attestation_present=decision_input.attestation_present,
            category=category,
            review_approved=decision_input.review_approved,
            detector_results=list(detectors),
            scan_evidence_current=scan_evidence_current,
            provider_settings_verified=False,
            policy_version_matches=(
                decision_input.attestation_policy_version
                == EXTERNAL_PROCESSING_POLICY_VERSION
            ),
            content_class=decision_input.content_class,
        )
    )
    promotion_allowed = (
        scan_evidence_current
        and category is not CategoryDisposition.PROHIBITED
        and category is not CategoryDisposition.UNKNOWN
        and all(result is DetectorResult.CLEAN for result in detectors)
        and (
            decision_input.content_class is ContentClass.SYNTHETIC
            or decision_input.review_approved
        )
    )
    detail = external.detail if not promotion_allowed else "metadata governance passed"
    return MetadataGovernanceResult(
        category=category,
        detector_results=detectors,
        external_processing=external,
        promotion_allowed=promotion_allowed,
        detail=detail,
    )


def _resolve_category(declared_category: str | None) -> CategoryDisposition:
    """Map declared category text to disposition."""

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


def _run_metadata_detectors(filename: str | None) -> tuple[DetectorResult, ...]:
    """Run deterministic filename/metadata pattern detectors."""

    haystack = filename or ""
    results: list[DetectorResult] = []
    if _CARD_PATTERN.search(haystack):
        results.append(DetectorResult.POSITIVE)
    else:
        results.append(DetectorResult.CLEAN)
    if _SECRET_PATTERN.search(haystack):
        results.append(DetectorResult.POSITIVE)
    else:
        results.append(DetectorResult.CLEAN)
    return tuple(results)
