"""Versioned ``detectors-v1`` families with Luhn/issuer payment-card checks.

Detectors never auto-approve. Hits are count-bounded and fingerprint-only;
raw matched strings are not returned for logs or traces.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from smart_rag_core.security.external_processing import DetectorResult

DETECTOR_POLICY_VERSION = "detectors-v1"
DETECTOR_FAMILY_PAYMENT_CARD = "payment_card"
DETECTOR_FAMILY_CREDENTIALS = "credentials"
DETECTOR_FAMILY_NATIONAL_ID = "national_id"
DETECTOR_FAMILY_HEALTH = "health"
DETECTOR_FAMILIES: tuple[str, ...] = (
    DETECTOR_FAMILY_PAYMENT_CARD,
    DETECTOR_FAMILY_CREDENTIALS,
    DETECTOR_FAMILY_NATIONAL_ID,
    DETECTOR_FAMILY_HEALTH,
)

_CARD_CANDIDATE = re.compile(r"\b(?:\d[ -]*?){13,19}\b")
_SECRET_PATTERN = re.compile(
    r"(?i)("
    r"\bapi[_-]?key\b|"
    r"\bsecret[_-]?key\b|"
    r"\b(password|secret|token|credential)\s*="
    r")"
)
_NATIONAL_ID_PATTERN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
_HEALTH_MARKER_PATTERN = re.compile(r"(?i)\b(hipaa|phi|medical record)\b")
_MAX_HIT_COUNT = 100


@dataclass(frozen=True, slots=True)
class DetectorFamilyOutcome:
    """One detector-family result without raw matched secrets.

    Attributes:
        family: Stable family identifier from ``DETECTOR_FAMILIES``.
        result: Clean or positive. Unknown is reserved for policy drift.
        bounded_count: Positive hit count, capped at 100.
        locator_fingerprint: SHA-256 prefix over match lengths and offsets.
    """

    family: str
    result: DetectorResult
    bounded_count: int
    locator_fingerprint: str


def luhn_valid(digits: str) -> bool:
    """Return whether ``digits`` pass the Luhn checksum.

    Args:
        digits: Decimal digits only.

    Returns:
        True when the Luhn checksum is valid.
    """

    if not digits.isdigit() or not 13 <= len(digits) <= 19:
        return False
    total = 0
    for index, char in enumerate(reversed(digits)):
        value = int(char)
        if index % 2 == 1:
            value *= 2
            if value > 9:
                value -= 9
        total += value
    return total % 10 == 0


def has_payment_card_issuer_prefix(digits: str) -> bool:
    """Return whether ``digits`` match a common card issuer prefix.

    Args:
        digits: Decimal digits only.

    Returns:
        True for Visa, Mastercard, Amex, Discover, or JCB prefixes.
    """

    if len(digits) < 4:
        return False
    if digits.startswith("4"):
        return True
    two = int(digits[:2])
    four = int(digits[:4])
    if 51 <= two <= 55:
        return True
    if 2221 <= four <= 2720:
        return True
    if two in {34, 37}:
        return True
    if digits.startswith(("6011", "65")):
        return True
    return 3528 <= four <= 3589


def run_detectors_v1(
    filename: str | None,
    extracted_texts: tuple[str, ...],
) -> tuple[DetectorFamilyOutcome, ...]:
    """Run the four ``detectors-v1`` families on filename plus extracted text.

    Args:
        filename: Optional object filename. Never logged from this function.
        extracted_texts: Parser fragments. May be empty for metadata-only.

    Returns:
        One outcome per ``DETECTOR_FAMILIES`` entry, in that order.
    """

    haystack = "\n".join([filename or "", *extracted_texts])
    return (
        _payment_card_outcome(haystack),
        _pattern_outcome(
            DETECTOR_FAMILY_CREDENTIALS,
            _SECRET_PATTERN,
            haystack,
        ),
        _pattern_outcome(
            DETECTOR_FAMILY_NATIONAL_ID,
            _NATIONAL_ID_PATTERN,
            haystack,
        ),
        _pattern_outcome(
            DETECTOR_FAMILY_HEALTH,
            _HEALTH_MARKER_PATTERN,
            haystack,
        ),
    )


def detector_results_from_outcomes(
    outcomes: tuple[DetectorFamilyOutcome, ...],
) -> tuple[DetectorResult, ...]:
    """Return the compact result tuple used by ``decide_external_processing``.

    Args:
        outcomes: Family outcomes in policy order.

    Returns:
        Detector results aligned with ``DETECTOR_FAMILIES``.
    """

    return tuple(item.result for item in outcomes)


def _payment_card_outcome(haystack: str) -> DetectorFamilyOutcome:
    """Score payment-card candidates with Luhn and issuer prefixes.

    Args:
        haystack: Filename plus extracted text.

    Returns:
        Family outcome. ISBN-like long numbers without Luhn/issuer stay clean.
    """

    offsets: list[str] = []
    count = 0
    for match in _CARD_CANDIDATE.finditer(haystack):
        digits = re.sub(r"[^0-9]", "", match.group(0))
        if not luhn_valid(digits) or not has_payment_card_issuer_prefix(digits):
            continue
        count += 1
        offsets.append(f"{match.start()}:{len(digits)}")
        if count >= _MAX_HIT_COUNT:
            break
    return _outcome(DETECTOR_FAMILY_PAYMENT_CARD, count, offsets)


def _pattern_outcome(
    family: str,
    pattern: re.Pattern[str],
    haystack: str,
) -> DetectorFamilyOutcome:
    """Count regex hits without capturing matched text.

    Args:
        family: Detector family id.
        pattern: Compiled pattern.
        haystack: Combined text.

    Returns:
        Family outcome with length/offset fingerprints only.
    """

    offsets: list[str] = []
    count = 0
    for match in pattern.finditer(haystack):
        count += 1
        offsets.append(f"{match.start()}:{match.end() - match.start()}")
        if count >= _MAX_HIT_COUNT:
            break
    return _outcome(family, count, offsets)


def _outcome(family: str, count: int, offsets: list[str]) -> DetectorFamilyOutcome:
    """Build a fingerprint-only family outcome.

    Args:
        family: Detector family id.
        count: Positive hit count.
        offsets: Offset/length tokens, never matched values.

    Returns:
        Outcome with a bounded count and fingerprint.
    """

    bounded = min(count, _MAX_HIT_COUNT)
    digest = hashlib.sha256(
        f"{family}|{DETECTOR_POLICY_VERSION}|{'|'.join(offsets)}".encode()
    ).hexdigest()[:32]
    return DetectorFamilyOutcome(
        family=family,
        result=DetectorResult.POSITIVE if bounded else DetectorResult.CLEAN,
        bounded_count=bounded,
        locator_fingerprint=digest,
    )
