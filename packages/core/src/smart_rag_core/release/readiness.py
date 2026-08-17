"""Public document-status export and fake/duplicate readiness rejection."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from smart_rag_core.release.constants import (
    READINESS_SCHEMA_VERSION,
    REQUIRED_DOCUMENT_STATES,
)
from smart_rag_core.release.errors import FakeReadinessError
from smart_rag_core.schema.enums import DocumentStatus


class ReadinessEvent(BaseModel):
    """One observed public document-status transition.

    Attributes:
        state: Public ``app.document_status`` value.
        document_id: Canonical document UUID string when known.
        version_id: Canonical version UUID string when known.
        job_id: Durable job UUID string when the transition used a job.
        observed_at: UTC timestamp in ISO-8601 form.
        driver: Real driver or RPC that produced the state.
        bm25_verified: True when Hybrid Ready included BM25 verify.
        maps_verified: True when Graph Ready included mapping gates.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    state: str = Field(min_length=1, max_length=64)
    document_id: str | None = None
    version_id: str | None = None
    job_id: str | None = None
    observed_at: str = Field(min_length=1, max_length=64)
    driver: str = Field(min_length=1, max_length=128)
    bm25_verified: bool = False
    maps_verified: bool = False


class ReadinessExport(BaseModel):
    """Machine-readable Packet 1 readiness proof.

    Attributes:
        schema_version: Frozen export schema.
        events: Observed transitions.
        missing_states: Required states not observed.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["phase09-candidate-readiness-v1"] = READINESS_SCHEMA_VERSION
    events: tuple[ReadinessEvent, ...]
    missing_states: tuple[str, ...]


def reject_fake_readiness(event: ReadinessEvent) -> None:
    """Reject Hybrid Ready or Graph Ready claimed without real verification.

    Args:
        event: Proposed readiness event.

    Raises:
        FakeReadinessError: If Hybrid Ready lacks BM25 verify, Graph Ready
            lacks mapping verify, or the driver is a SQL stamp.
    """

    driver = event.driver.lower()
    if "sql-stamp" in driver or "fake" in driver or driver == "update_status":
        raise FakeReadinessError(f"fake readiness driver {event.driver}")
    if event.state == DocumentStatus.HYBRID_READY.value and not event.bm25_verified:
        raise FakeReadinessError("hybrid_ready requires BM25 verification")
    if event.state == DocumentStatus.GRAPH_READY.value and not event.maps_verified:
        raise FakeReadinessError("graph_ready requires mapping verification")


def reject_duplicate_readiness(
    existing: Sequence[ReadinessEvent],
    incoming: ReadinessEvent,
) -> None:
    """Reject a second identical version/state pair as duplicate readiness.

    Args:
        existing: Already recorded events.
        incoming: Candidate event.

    Raises:
        FakeReadinessError: If the same version already recorded the state.
    """

    if incoming.version_id is None:
        return
    for event in existing:
        if event.version_id == incoming.version_id and event.state == incoming.state:
            raise FakeReadinessError(
                f"duplicate readiness {incoming.state} for {incoming.version_id}"
            )


def utc_now_iso(moment: datetime) -> str:
    """Format a timezone-aware UTC datetime as ISO-8601.

    Args:
        moment: Timestamp. Naive values are treated as UTC.

    Returns:
        ISO-8601 string with a ``Z`` suffix.
    """

    if moment.tzinfo is None:
        stamped = moment.replace(tzinfo=UTC)
    else:
        stamped = moment.astimezone(UTC)
    return stamped.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def missing_required_states(events: Sequence[ReadinessEvent]) -> tuple[str, ...]:
    """Return required public states that were not observed.

    Args:
        events: Observed transitions.

    Returns:
        Sorted missing state names.
    """

    observed = {event.state for event in events}
    return tuple(state for state in REQUIRED_DOCUMENT_STATES if state not in observed)


def as_uuid_text(value: UUID | str | None) -> str | None:
    """Return a UUID string or none.

    Args:
        value: UUID, string, or none.

    Returns:
        Canonical UUID text.
    """

    if value is None:
        return None
    return str(value)
