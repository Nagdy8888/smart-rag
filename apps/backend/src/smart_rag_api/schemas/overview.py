"""Typed anonymous admin dashboard response."""

from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from smart_rag_core.gateways.cost_reporting import CostReporting
from smart_rag_core.knowledge import MaintenanceKind
from smart_rag_core.observability.checkpoint_usage import CheckpointUsageSummary


class OverviewSummary(BaseModel):
    """Counts and recorded measurements; missing measurements remain null."""

    questions: int = Field(ge=0)
    completed: int = Field(ge=0)
    failed: int = Field(ge=0)
    cancelled: int = Field(ge=0)
    measured: int = Field(ge=0)
    supported: int = Field(ge=0)
    not_measured: int = Field(ge=0)
    median_response_seconds: float | None = Field(ge=0)
    latency_samples: int = Field(ge=0)
    cost_usd: str
    cost_reporting: CostReporting | None = None
    display_cost_usd: Decimal | None = None

    checkpoint_usage: CheckpointUsageSummary | None = None


class OverviewDay(BaseModel):
    """UTC daily bucket including actual zero-count days."""

    date: date
    questions: int = Field(ge=0)
    cost_usd: str
    cost_reporting: CostReporting | None = None
    display_cost_usd: Decimal | None = None


class OverviewAttention(BaseModel):
    """Authorized task metadata, never conversation content."""

    kind: MaintenanceKind
    source_id: UUID
    document_id: UUID | None
    title: str | None


class OverviewResponse(BaseModel):
    """Single-snapshot response for the owner/admin overview."""

    model_config = ConfigDict(extra="forbid")
    generated_at: datetime
    period_start: datetime
    days: Literal[7, 30, 90]
    timezone: Literal["UTC"]
    reliability_enabled: bool
    summary: OverviewSummary
    daily: list[OverviewDay]
    outcomes: dict[
        Literal[
            "supported", "partial", "insufficient_evidence", "conflicting_evidence"
        ],
        int,
    ]
    authority: dict[Literal["approved", "unreviewed", "draft", "superseded"], int]
    authority_unversioned: int
    attention_counts: dict[MaintenanceKind, int]
    attention_items: list[OverviewAttention]
