"""FastAPI schemas for owner/admin glossary import."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field
from smart_rag_core.glossary.models import (
    GlossaryAliasDraft,
    GlossaryEntryDraft,
    GlossaryEntryType,
    GlossaryLanguage,
    GlossaryScope,
)


class GlossaryAliasRequest(BaseModel):
    """One alias in an import request."""

    alias: str = Field(min_length=1, max_length=256)
    language: GlossaryLanguage = GlossaryLanguage.EN


class GlossaryEntryRequest(BaseModel):
    """One canonical glossary entry in an import request."""

    entry_key: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9._:-]+$")
    canonical_term: str = Field(min_length=1, max_length=256)
    language: GlossaryLanguage = GlossaryLanguage.EN
    entry_type: GlossaryEntryType
    effective_scope: GlossaryScope = GlossaryScope.SYNTHETIC_EVAL
    identifier_pattern: str | None = Field(default=None, max_length=256)
    checksum_algorithm: str | None = Field(default=None, max_length=32)
    aliases: list[GlossaryAliasRequest] = Field(
        default_factory=list[GlossaryAliasRequest],
        max_length=20,
    )


class ImportGlossaryRequest(BaseModel):
    """Owner/admin glossary import body."""

    source_name: str = Field(min_length=1, max_length=128)
    source_version: str = Field(min_length=1, max_length=64)
    idempotency_key: str = Field(min_length=8, max_length=256)
    entries: list[GlossaryEntryRequest] = Field(min_length=1, max_length=500)


class GlossaryImportResponse(BaseModel):
    """Identifiers after import, approval, or rollback."""

    import_id: UUID
    status: str
    entry_count: int
    alias_count: int


def request_to_drafts(body: ImportGlossaryRequest) -> list[GlossaryEntryDraft]:
    """Convert the HTTP body to core glossary drafts.

    Args:
        body: Validated import request.

    Returns:
        Core entry drafts used by the import service.
    """

    return [
        GlossaryEntryDraft(
            entry_key=entry.entry_key,
            canonical_term=entry.canonical_term,
            language=entry.language,
            entry_type=entry.entry_type,
            effective_scope=entry.effective_scope,
            identifier_pattern=entry.identifier_pattern,
            checksum_algorithm=entry.checksum_algorithm,
            aliases=[
                GlossaryAliasDraft(alias=alias.alias, language=alias.language)
                for alias in entry.aliases
            ],
        )
        for entry in body.entries
    ]
