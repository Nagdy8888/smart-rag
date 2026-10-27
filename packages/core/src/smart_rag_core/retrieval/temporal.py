"""UTC-anchored temporal policies for Hybrid candidates."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from enum import StrEnum
from uuid import UUID

from smart_rag_core.retrieval.profiles import RECENT_WINDOW_DAYS
from smart_rag_core.retrieval.types import RetrievalCandidate


class TemporalIntent(StrEnum):
    """Allow-listed temporal intents from the query profile."""

    NONE = "none"
    LATEST = "latest"
    CURRENT = "current"
    RECENT = "recent"
    AS_OF = "as_of"


class TemporalDocument:
    """Authoritative dates for one candidate document version.

    Attributes:
        chunk_id: Canonical chunk.
        effective_at: Version effective timestamp, UTC, or None when unknown.
        published_at: Publication timestamp, UTC, or None.
        expired: True when the version is superseded or expired.
    """

    __slots__ = (
        "authority_status",
        "chunk_id",
        "effective_at",
        "expired",
        "published_at",
        "reliability_enabled",
    )

    def __init__(
        self,
        chunk_id: UUID,
        *,
        effective_at: datetime | None,
        published_at: datetime | None = None,
        expired: bool = False,
        authority_status: str = "unreviewed",
        reliability_enabled: bool = False,
    ) -> None:
        """Store UTC dates. Naive datetimes and Hijri values are rejected.

        Callers must convert source dates through the Gregorian parser before
        constructing this record. Hijri calendar values are not authoritative
        ``effective_at`` values in v1 (QT-TZ-001).

        Args:
            chunk_id: Canonical chunk.
            effective_at: Effective timestamp.
            published_at: Published timestamp.
            expired: Supersession flag.
            authority_status: Human-reviewed authority status.
            reliability_enabled: Whether the company enabled authority-aware selection.

        Raises:
            ValueError: If a provided datetime is not timezone-aware UTC.
        """

        self.chunk_id = chunk_id
        self.effective_at = _require_utc(effective_at)
        self.published_at = _require_utc(published_at)
        self.expired = expired
        self.authority_status = authority_status
        self.reliability_enabled = reliability_enabled


def _require_utc(value: datetime | None) -> datetime | None:
    """Reject naive or non-UTC timestamps.

    Args:
        value: Optional datetime.

    Returns:
        The same value when it is UTC-aware or None.

    Raises:
        ValueError: If tzinfo is missing or not UTC.
    """

    if value is None:
        return None
    if value.tzinfo is None:
        raise ValueError("naive_datetime_forbidden")
    if value.utcoffset() != timedelta(0):
        raise ValueError("timezone_must_be_utc")
    return value


def apply_temporal_policy(
    candidates: tuple[RetrievalCandidate, ...],
    records: dict[UUID, TemporalDocument],
    *,
    intent: TemporalIntent,
    target_date: date | None,
    now: datetime | None = None,
) -> tuple[RetrievalCandidate, ...]:
    """Filter or order candidates under one temporal policy.

    Unknown dates cannot win ``latest``. Hijri values are not accepted here;
    callers must pass Gregorian UTC timestamps.

    Args:
        candidates: Fused authorized candidates.
        records: Per-chunk date records.
        intent: Profile temporal intent.
        target_date: Required for ``as_of``.
        now: Comparison instant. Defaults to ``datetime.now(UTC)``.

    Returns:
        Candidates that satisfy the policy, same relative order otherwise.
        Empty when the policy cannot be satisfied.

    Raises:
        ValueError: If ``as_of`` lacks a target date or the clock is not UTC.
    """

    clock = now if now is not None else datetime.now(UTC)
    aware = _require_utc(clock)
    if aware is None:
        raise ValueError("utc_clock_required")
    # Historical requests retain the existing historical evidence boundary.
    # For ordinary/current requests, authority filtering applies before ranking.
    if intent in {
        TemporalIntent.NONE,
        TemporalIntent.CURRENT,
        TemporalIntent.LATEST,
        TemporalIntent.RECENT,
    }:
        candidates = tuple(
            item
            for item in candidates
            if (record := records.get(item.chunk_id)) is None
            or not record.reliability_enabled
            or (
                record.authority_status not in {"draft", "superseded"}
                and not record.expired
                and (record.effective_at is None or record.effective_at <= aware)
            )
        )
        # A stable partition preserves relevance within each authority tier.
        candidates = tuple(
            sorted(
                candidates,
                key=lambda item: (
                    0
                    if (record := records.get(item.chunk_id)) is not None
                    and record.reliability_enabled
                    and record.authority_status == "approved"
                    else 1
                ),
            )
        )
    if intent is TemporalIntent.NONE:
        return candidates
    if intent is TemporalIntent.CURRENT:
        kept: list[RetrievalCandidate] = []
        for item in candidates:
            record = records.get(item.chunk_id)
            if record is not None and record.expired:
                continue
            kept.append(item)
        return tuple(kept)
    if intent is TemporalIntent.AS_OF:
        if target_date is None:
            raise ValueError("as_of_requires_target_date")
        cutoff = datetime(
            target_date.year,
            target_date.month,
            target_date.day,
            tzinfo=UTC,
        )
        kept = []
        for item in candidates:
            record = records.get(item.chunk_id)
            if record is None or record.effective_at is None:
                continue
            if record.effective_at <= cutoff:
                kept.append(item)
        return tuple(kept)
    if intent is TemporalIntent.RECENT:
        window = aware - timedelta(days=RECENT_WINDOW_DAYS)
        kept = []
        for item in candidates:
            record = records.get(item.chunk_id)
            if record is None or record.effective_at is None:
                continue
            if record.effective_at >= window:
                kept.append(item)
        return tuple(kept)
    dated: list[RetrievalCandidate] = []
    stamps: list[datetime] = []
    for item in candidates:
        record = records.get(item.chunk_id)
        if record is None or record.effective_at is None or record.expired:
            continue
        dated.append(item)
        stamps.append(record.effective_at)
    if not dated:
        return ()
    latest_stamp = max(stamps)
    return tuple(
        item for item in dated if records[item.chunk_id].effective_at == latest_stamp
    )
