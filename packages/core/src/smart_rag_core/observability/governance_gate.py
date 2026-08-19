"""Fail-closed gates for LangSmith, OpenAI, and Vercel private payloads."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import cast

from smart_rag_core.security.external_processing import (
    CategoryDisposition,
    ContentClass,
    ExternalProcessingDecisionInput,
    decide_external_processing,
)


class ExternalFlowBlockedError(PermissionError):
    """Raised when an unsigned or prohibited external flow would leak private data."""


def assert_langsmith_export_permitted(
    *,
    tracing_enabled: bool,
    content_class: ContentClass,
    provider_settings_verified: bool,
    local_unsigned_waiver: bool = False,
) -> None:
    """Block LangSmith export of real company payloads until the matrix is verified.

    Args:
        tracing_enabled: Process ``LANGSMITH_TRACING`` flag.
        content_class: Real company versus synthetic fixtures.
        provider_settings_verified: Signed org matrix row for LangSmith hide I/O.
        local_unsigned_waiver: True when ``APP_ENV=local`` and mock mode is
            off. Allows redacted tracing with operator keys without claiming
            org-matrix verification.

    Raises:
        ExternalFlowBlockedError: When tracing is on for real company content
            without a verified hide-I/O matrix or local waiver, or when the
            content class is unknown.

    Side Effects:
        None. Staging and production must keep ``LANGSMITH_TRACING=false`` for
        real content until verification.
    """

    if content_class is ContentClass.SYNTHETIC:
        return
    if content_class is not ContentClass.REAL_COMPANY:
        raise ExternalFlowBlockedError("unknown_content_class")
    if local_unsigned_waiver:
        return
    if tracing_enabled and not provider_settings_verified:
        raise ExternalFlowBlockedError("langsmith_real_content_unverified")


def assert_openai_flow_permitted(
    decision_input: ExternalProcessingDecisionInput,
) -> None:
    """Require the signed OpenAI governance decision before private payloads.

    Args:
        decision_input: Attestation, detectors, and provider matrix inputs.

    Raises:
        ExternalFlowBlockedError: When ``decide_external_processing`` denies.

    Side Effects:
        None.
    """

    decision = decide_external_processing(decision_input)
    if not decision.allowed:
        raise ExternalFlowBlockedError(decision.reason_code)


def assert_vercel_metadata_has_no_private_payload(payload: object) -> None:
    """Reject Vercel-visible metadata that includes source or secret keys.

    Args:
        payload: JSON-like metadata that would be visible in frontend hosting.

    Raises:
        ExternalFlowBlockedError: When private keys are present.

    Side Effects:
        None.
    """

    forbidden = {
        "passage",
        "snippet",
        "html",
        "source",
        "api_key",
        "prompt",
        "query",
        "jwt",
        "email",
    }
    if _contains_forbidden_key(payload, forbidden):
        raise ExternalFlowBlockedError("vercel_private_payload")


def unknown_or_prohibited_category_blocks(
    category: CategoryDisposition,
) -> bool:
    """Return whether a category cannot send private payloads externally.

    Args:
        category: Signed disposition.

    Returns:
        True for prohibited and unknown categories.
    """

    return category in {
        CategoryDisposition.PROHIBITED,
        CategoryDisposition.UNKNOWN,
    }


def _contains_forbidden_key(value: object, forbidden: set[str]) -> bool:
    """Walk a JSON-like value for forbidden key names.

    Args:
        value: Nested mapping, sequence, or scalar.
        forbidden: Lowercased key names.

    Returns:
        True when any mapping key matches.
    """

    if isinstance(value, Mapping):
        mapping = cast(Mapping[object, object], value)
        for key, child in mapping.items():
            if str(key).lower() in forbidden:
                return True
            if _contains_forbidden_key(child, forbidden):
                return True
        return False
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        sequence = cast(Sequence[object], value)
        return any(_contains_forbidden_key(item, forbidden) for item in sequence)
    return False
