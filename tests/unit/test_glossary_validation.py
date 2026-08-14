"""Unit tests for glossary validation, identifier rules, and log redaction."""

from __future__ import annotations

import pytest
from smart_rag_core.evaluation.identifier_rules import (
    CollisionRisk,
    assess_collision_risk,
    propose_rules_from_corpus,
)
from smart_rag_core.glossary.models import (
    GlossaryAliasDraft,
    GlossaryBatch,
    GlossaryEntryDraft,
    GlossaryEntryType,
    GlossaryLanguage,
    GlossaryScope,
)
from smart_rag_core.glossary.validation import (
    GlossaryValidationError,
    validate_glossary_batch,
)


def _entry(
    key: str,
    canonical: str,
    alias: str,
    *,
    scope: GlossaryScope = GlossaryScope.SYNTHETIC_EVAL,
    entry_type: GlossaryEntryType = GlossaryEntryType.PRODUCT_CODE,
    pattern: str | None = None,
) -> GlossaryEntryDraft:
    """Build one glossary draft for tests.

    Args:
        key: Entry key.
        canonical: Canonical term.
        alias: Alias text.
        scope: Effective scope.
        entry_type: Entry type.
        pattern: Optional identifier pattern.

    Returns:
        Frozen entry draft.
    """

    return GlossaryEntryDraft(
        entry_key=key,
        canonical_term=canonical,
        language=GlossaryLanguage.EN,
        entry_type=entry_type,
        effective_scope=scope,
        identifier_pattern=pattern,
        aliases=[
            GlossaryAliasDraft(alias=alias, language=GlossaryLanguage.EN),
        ],
    )


def test_valid_batch_is_accepted() -> None:
    """A well-formed synthetic glossary batch passes validation."""

    batch = GlossaryBatch(
        source_name="synthetic-seed",
        source_version="v1",
        idempotency_key="glossary-seed-0001",
        entries=[_entry("inv-1", "INV-SR-8801", "invoice 8801")],
    )
    validate_glossary_batch(batch)


def test_alias_cycle_is_rejected() -> None:
    """Mutual aliases are rejected with a reason code and no term text."""

    batch = GlossaryBatch(
        source_name="cycle",
        source_version="v1",
        idempotency_key="glossary-cycle-0001",
        entries=[
            _entry("a", "alpha-term", "beta-term"),
            _entry("b", "beta-term", "alpha-term"),
        ],
    )
    with pytest.raises(GlossaryValidationError, match="alias_cycle") as caught:
        validate_glossary_batch(batch)
    assert "alpha-term" not in str(caught.value)
    assert caught.value.reason == "alias_cycle"


def test_alias_conflict_and_duplicate_are_rejected() -> None:
    """Conflicting and duplicate aliases fail closed."""

    conflict = GlossaryBatch(
        source_name="conflict",
        source_version="v1",
        idempotency_key="glossary-conflict-0001",
        entries=[
            _entry("a", "INV-SR-8801", "widget"),
            _entry("b", "INV-SR-8802", "widget"),
        ],
    )
    with pytest.raises(GlossaryValidationError, match="alias_conflict"):
        validate_glossary_batch(conflict)
    duplicate = GlossaryBatch(
        source_name="dup",
        source_version="v1",
        idempotency_key="glossary-dup-0001",
        entries=[
            GlossaryEntryDraft(
                entry_key="a",
                canonical_term="INV-SR-8801",
                language=GlossaryLanguage.EN,
                entry_type=GlossaryEntryType.PRODUCT_CODE,
                effective_scope=GlossaryScope.SYNTHETIC_EVAL,
                aliases=[
                    GlossaryAliasDraft(alias="widget", language=GlossaryLanguage.EN),
                    GlossaryAliasDraft(alias="widget", language=GlossaryLanguage.EN),
                ],
            )
        ],
    )
    with pytest.raises(GlossaryValidationError, match="duplicate_alias"):
        validate_glossary_batch(duplicate)


def test_cross_scope_conflict_is_rejected() -> None:
    """The same alias cannot map to different canonicals across scopes."""

    batch = GlossaryBatch(
        source_name="scope",
        source_version="v1",
        idempotency_key="glossary-scope-0001",
        entries=[
            _entry(
                "a",
                "INV-SR-8801",
                "widget",
                scope=GlossaryScope.COMPANY,
            ),
            _entry(
                "b",
                "INV-SR-8802",
                "widget",
                scope=GlossaryScope.SYNTHETIC_EVAL,
            ),
        ],
    )
    with pytest.raises(GlossaryValidationError, match="cross_scope_conflict"):
        validate_glossary_batch(batch)


def test_high_collision_identifier_rule_is_rejected() -> None:
    """Unsafe identifier patterns cannot be imported."""

    batch = GlossaryBatch(
        source_name="rules",
        source_version="v1",
        idempotency_key="glossary-rule-0001",
        entries=[
            _entry(
                "digits",
                "digit-rule",
                "digit-alias",
                entry_type=GlossaryEntryType.IDENTIFIER_RULE,
                pattern=r"\d{1,3}",
            )
        ],
    )
    with pytest.raises(GlossaryValidationError, match="high_collision_rule"):
        validate_glossary_batch(batch)
    risk, reason = assess_collision_risk(r"\d{1,3}")
    assert risk is CollisionRisk.HIGH
    assert reason == "short_digit_class"


def test_identifier_sampler_rejects_high_collision_rule() -> None:
    """Corpus sampling versions approved rules and keeps rejected proposals."""

    rules = propose_rules_from_corpus(["INV-SR-8801 status", "PRJ-ORION handbook"])
    assert any(rule.approved and rule.rule_id == "inv-sr-v1" for rule in rules)
    assert any(
        not rule.approved and rule.collision_risk is CollisionRisk.HIGH
        for rule in rules
    )


def test_import_logs_do_not_contain_private_values(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Validation failures log reason codes, never glossary surface forms."""

    private_term = "PRIVATE-GLOSS-99"
    batch = GlossaryBatch(
        source_name="redaction",
        source_version="v1",
        idempotency_key="glossary-redaction-0001",
        entries=[
            _entry("a", "INV-SR-8801", private_term),
            _entry("b", "INV-SR-8802", private_term),
        ],
    )
    with pytest.raises(GlossaryValidationError) as caught:
        validate_glossary_batch(batch)
    assert caught.value.reason == "alias_conflict"
    assert private_term not in str(caught.value)
    combined = " ".join(record.getMessage() for record in caplog.records)
    assert private_term not in combined
