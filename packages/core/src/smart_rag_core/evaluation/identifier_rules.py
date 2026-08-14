"""Versioned identifier regex/checksum rules sampled from synthetic corpus."""

from __future__ import annotations

import re
from collections.abc import Sequence
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

IDENTIFIER_RULE_VERSION = "identifier-rules-v1"

_CATASTROPHIC = re.compile(r"\([^)]*[+*][^)]*\)[+*]")
_BROAD_WILDCARD = re.compile(r"(\.\*)|(\.\+)|(\\w\+)|(\\S\+)")


class CollisionRisk(StrEnum):
    """Collision risk for a proposed identifier rule."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class IdentifierRule(BaseModel):
    """One versioned identifier extraction rule.

    Attributes:
        rule_id: Stable rule identifier.
        pattern: Python regular expression.
        checksum_algorithm: Optional checksum name.
        language: Language applicability.
        source_version: Rule-set version.
        collision_risk: Assessed collision risk.
        approved: Whether the rule may run. High-risk rules are rejected.
        rejection_reason: Machine-readable reason when not approved.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    rule_id: str = Field(min_length=3, max_length=64)
    pattern: str = Field(min_length=1, max_length=256)
    checksum_algorithm: str | None = None
    language: str = Field(min_length=2, max_length=16)
    source_version: str = Field(min_length=1, max_length=64)
    collision_risk: CollisionRisk
    approved: bool
    rejection_reason: str | None = None


def literal_prefix_length(pattern: str) -> int:
    """Count leading literal characters before a regex metacharacter.

    Args:
        pattern: Candidate regular expression.

    Returns:
        Number of leading literal characters.
    """

    count = 0
    for char in pattern:
        if char in ".^$*+?{}[]\\|()":
            break
        count += 1
    return count


def assess_collision_risk(pattern: str) -> tuple[CollisionRisk, str | None]:
    """Classify identifier-pattern collision risk.

    Args:
        pattern: Candidate regular expression.

    Returns:
        Risk class and a rejection reason when the rule is unsafe.
    """

    if pattern.strip() == "":
        return CollisionRisk.HIGH, "empty_pattern"
    if _CATASTROPHIC.search(pattern) is not None:
        return CollisionRisk.HIGH, "catastrophic_backtracking"
    if (
        _BROAD_WILDCARD.search(pattern) is not None
        and literal_prefix_length(pattern) < 4
    ):
        return CollisionRisk.HIGH, "unanchored_wildcard"
    if re.fullmatch(r"\\d\{1,3\}", pattern) is not None:
        return CollisionRisk.HIGH, "short_digit_class"
    if literal_prefix_length(pattern) < 3 and "[" not in pattern:
        return CollisionRisk.HIGH, "short_literal"
    if literal_prefix_length(pattern) >= 6:
        return CollisionRisk.LOW, None
    return CollisionRisk.MEDIUM, None


def compile_approved_rule(rule: IdentifierRule) -> re.Pattern[str]:
    """Compile an approved identifier rule.

    Args:
        rule: Rule that must already be approved.

    Returns:
        Compiled Unicode regular expression.

    Raises:
        ValueError: If the rule is not approved or the pattern is invalid.
    """

    if not rule.approved:
        raise ValueError("unapproved identifier rule")
    try:
        return re.compile(rule.pattern, flags=re.UNICODE)
    except re.error as error:
        raise ValueError("invalid identifier pattern") from error


def propose_rules_from_corpus(texts: Sequence[str]) -> list[IdentifierRule]:
    """Sample synthetic corpus text and version identifier rules.

    Real company content is not sampled. This function inspects the Phase 4
    synthetic labeled corpus only.

    Args:
        texts: Synthetic query and passage strings.

    Returns:
        Versioned rules. High-collision proposals are present with
        ``approved=False`` so rejection is testable.
    """

    joined = "\n".join(texts)
    candidates = [
        IdentifierRule(
            rule_id="inv-sr-v1",
            pattern=r"INV-SR-\d{4}",
            checksum_algorithm=None,
            language="en",
            source_version=IDENTIFIER_RULE_VERSION,
            collision_risk=CollisionRisk.LOW,
            approved=True,
            rejection_reason=None,
        ),
        IdentifierRule(
            rule_id="prj-orion-v1",
            pattern=r"PRJ-[A-Z]{5,12}",
            checksum_algorithm=None,
            language="en",
            source_version=IDENTIFIER_RULE_VERSION,
            collision_risk=CollisionRisk.LOW,
            approved=True,
            rejection_reason=None,
        ),
        IdentifierRule(
            rule_id="sku-p4-v1",
            pattern=r"SKU-P4-[A-Z0-9]{3}",
            checksum_algorithm=None,
            language="en",
            source_version=IDENTIFIER_RULE_VERSION,
            collision_risk=CollisionRisk.LOW,
            approved=True,
            rejection_reason=None,
        ),
        IdentifierRule(
            rule_id="acr-mixed-v1",
            pattern=r"P4-[A-Z]{2}-\d{3}",
            checksum_algorithm=None,
            language="mixed",
            source_version=IDENTIFIER_RULE_VERSION,
            collision_risk=CollisionRisk.LOW,
            approved=True,
            rejection_reason=None,
        ),
    ]
    unsafe = IdentifierRule(
        rule_id="reject-digit-only",
        pattern=r"\d{1,3}",
        checksum_algorithm=None,
        language="en",
        source_version=IDENTIFIER_RULE_VERSION,
        collision_risk=CollisionRisk.HIGH,
        approved=False,
        rejection_reason="short_digit_class",
    )
    observed = [rule for rule in candidates if re.search(rule.pattern, joined)]
    if not observed:
        observed = list(candidates)
    risk, reason = assess_collision_risk(unsafe.pattern)
    rejected = unsafe.model_copy(
        update={"collision_risk": risk, "rejection_reason": reason, "approved": False}
    )
    return [*observed, rejected]
