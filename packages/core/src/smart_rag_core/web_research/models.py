"""Run-scoped public Web evidence models.

Web excerpts are never company RAG, BM25, LightRAG, or StructuredTable
evidence. API listing omits excerpt and span text.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class WebSourceRecord(BaseModel):
    """Persisted Web source after URL policy and excerpt hashing."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    web_source_id: str = Field(min_length=1, max_length=36)
    source_index: int = Field(ge=0, le=5)
    url: str = Field(min_length=1, max_length=2048)
    title: str = Field(default="", max_length=512)
    excerpt: str = Field(min_length=1, max_length=8000)
    content_hash: str = Field(min_length=64, max_length=64)
    published_date: str | None = Field(default=None, max_length=64)


class WebCitation(BaseModel):
    """Verified citation span bound to a persisted Web source."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    web_source_id: str = Field(min_length=1, max_length=36)
    span: str = Field(min_length=1, max_length=1000)
    atomic_link_id: str | None = Field(default=None, max_length=64)

    @model_validator(mode="after")
    def reject_blank_span(self) -> WebCitation:
        """Reject whitespace-only spans.

        Returns:
            This citation.

        Raises:
            ValueError: If the span is blank after strip.
        """

        if not self.span.strip():
            raise ValueError("web_evidence:invalid_span")
        return self


class WebOperationState(BaseModel):
    """Idempotent research operation row."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    operation_id: str = Field(min_length=1, max_length=36)
    status: Literal["planned", "sent", "succeeded", "failed", "ambiguous"]
    replayed: bool = False
    attempts: int = Field(default=0, ge=0, le=2)
