"""Owner/admin detector-finding review request and response bodies."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field


class DetectorFindingReviewRequest(BaseModel):
    """Hash-bound false-positive or uphold decision. No detector outcomes."""

    finding_id: UUID
    decision: str = Field(pattern=r"^(false_positive|upheld|rejected)$")
    reason: str = Field(min_length=1, max_length=500)
    idempotency_key: str = Field(min_length=8, max_length=128)


class DetectorFindingReviewResponse(BaseModel):
    """Identifiers after an authorized review write or replay."""

    review_id: UUID
    finding_id: UUID
    decision: str
    replayed: bool = False
