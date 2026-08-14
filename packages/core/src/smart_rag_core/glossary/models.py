"""Glossary import payload models. Private terms stay out of Git fixtures."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class GlossaryLanguage(StrEnum):
    """Allow-listed glossary languages."""

    EN = "en"
    AR = "ar"
    MIXED = "mixed"


class GlossaryEntryType(StrEnum):
    """Allow-listed glossary entry types."""

    PRODUCT_CODE = "product_code"
    PROJECT_NAME = "project_name"
    ACRONYM = "acronym"
    CANONICAL_TERM = "canonical_term"
    IDENTIFIER_RULE = "identifier_rule"


class GlossaryScope(StrEnum):
    """Effective scope. Cross-scope alias collisions are rejected."""

    COMPANY = "company"
    SYNTHETIC_EVAL = "synthetic_eval"


class GlossaryImportStatus(StrEnum):
    """Durable glossary import lifecycle."""

    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    ROLLED_BACK = "rolled_back"
    REJECTED = "rejected"


class GlossaryAliasDraft(BaseModel):
    """One alias attached to a canonical glossary entry.

    Attributes:
        alias: Raw alias text. Never logged by import services.
        language: Alias language.
    """

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    alias: str = Field(min_length=1, max_length=256)
    language: GlossaryLanguage


class GlossaryEntryDraft(BaseModel):
    """One canonical glossary entry in an import batch.

    Attributes:
        entry_key: Stable key unique within the import.
        canonical_term: Canonical surface form.
        language: Entry language.
        entry_type: Allow-listed type.
        effective_scope: Scope used for conflict detection.
        identifier_pattern: Required for identifier_rule entries.
        checksum_algorithm: Optional checksum name.
        aliases: Aliases that must resolve to this canonical term.
    """

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    entry_key: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9._:-]+$")
    canonical_term: str = Field(min_length=1, max_length=256)
    language: GlossaryLanguage
    entry_type: GlossaryEntryType
    effective_scope: GlossaryScope
    identifier_pattern: str | None = Field(default=None, max_length=256)
    checksum_algorithm: str | None = Field(default=None, max_length=32)
    aliases: list[GlossaryAliasDraft] = Field(
        default_factory=list[GlossaryAliasDraft],
        max_length=20,
    )

    @field_validator("aliases")
    @classmethod
    def _cap_aliases(cls, value: list[GlossaryAliasDraft]) -> list[GlossaryAliasDraft]:
        """Reject oversized alias lists.

        Args:
            value: Alias drafts.

        Returns:
            The alias list when within bounds.
        """

        return value


class GlossaryBatch(BaseModel):
    """Owner/admin glossary import payload.

    Attributes:
        source_name: Provenance label for the batch.
        source_version: Version string recorded on the import row.
        idempotency_key: Duplicate imports reuse one row.
        entries: Canonical entries and aliases.
    """

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    source_name: str = Field(min_length=1, max_length=128)
    source_version: str = Field(min_length=1, max_length=64)
    idempotency_key: str = Field(min_length=8, max_length=256)
    entries: list[GlossaryEntryDraft] = Field(min_length=1, max_length=500)
