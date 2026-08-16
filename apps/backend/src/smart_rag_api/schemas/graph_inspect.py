"""Graph inspection request and response schemas."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class GraphInspectRequest(BaseModel):
    """Bounded inspection request. Native graph prose is not accepted.

    Attributes:
        entity_keys: Application entity keys, at most 12.
        document_id: Optional document seed. Results stay ACL-filtered.
        depth: Hop cap, default 3, maximum 3.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    entity_keys: tuple[str, ...] = Field(default=(), max_length=12)
    document_id: UUID | None = None
    depth: int = Field(default=3, ge=1, le=3)

    @model_validator(mode="after")
    def require_seed(self) -> GraphInspectRequest:
        """Reject an empty inspection seed.

        Returns:
            The request when a seed is present.

        Raises:
            ValueError: If both ``entity_keys`` and ``document_id`` are empty.
        """

        if not self.entity_keys and self.document_id is None:
            raise ValueError("inspect_seed_required")
        for key in self.entity_keys:
            if not key or len(key) > 64:
                raise ValueError("inspect_entity_key_invalid")
        return self


class GraphInspectLocator(BaseModel):
    """Canonical locator coordinates. Never vendor chunk text."""

    model_config = ConfigDict(frozen=True)

    chunk_id: UUID
    document_id: UUID
    version_id: UUID
    page_number: int | None = None
    section_path: tuple[str, ...] = ()
    sheet_name: str | None = None
    range_ref: str | None = None
    source_url: str | None = None


class GraphInspectNodeResponse(BaseModel):
    """One authorized inspection row."""

    model_config = ConfigDict(frozen=True)

    object_type: str
    object_id: str
    chunk_id: UUID
    document_id: UUID
    version_id: UUID
    support: float
    hop: int


class GraphInspectLimitation(BaseModel):
    """Typed inspection limitation without restricted names."""

    model_config = ConfigDict(frozen=True)

    code: str
    count: int | None = None


class GraphInspectResponse(BaseModel):
    """Inspection payload. At most 200 rows."""

    model_config = ConfigDict(frozen=True)

    nodes: tuple[GraphInspectNodeResponse, ...] = ()
    locators: tuple[GraphInspectLocator, ...] = ()
    limitations: tuple[GraphInspectLimitation, ...] = ()
    row_count: int = Field(ge=0, le=200)
    depth: int = Field(ge=1, le=3)
