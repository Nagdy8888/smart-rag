"""Graph queue backlog, ETA, and cost metrics from durable rows.

Mapping-verified completions are zero until Packet 4. ETA must then be
``insufficient-sample``, never a fake documents-per-hour figure.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal

import psycopg
from pydantic import BaseModel, ConfigDict, Field

EtaConfidence = Literal["insufficient-sample", "measured"]


class GraphQueueMetrics(BaseModel):
    """Durable graph backlog, ETA, and cost snapshot.

    Attributes:
        pending_index_count: Pending ``index`` jobs.
        pending_maintenance_count: Pending remove/ACL/rebuild jobs.
        oldest_pending_age_seconds: Age of the oldest pending job, if any.
        mapping_verified_count: Versions that reached mapping-verified
            completion. Zero until Packet 4.
        documents_per_hour: Throughput from mapping-verified completions.
        eta_seconds: Estimated seconds to drain the index backlog.
        eta_confidence: ``insufficient-sample`` when throughput cannot be
            measured.
        attempted_cost_usd: Reserved plus committed graph spend.
        settled_cost_usd: Committed graph spend only.
        bulk_window_active: True only when an owner-approved window is set
            and currently open. Packet 3 never invents a window.
        bulk_window_starts_at: Optional approved window start.
        bulk_window_ends_at: Optional approved window end.
    """

    model_config = ConfigDict(frozen=True)

    pending_index_count: int = Field(ge=0)
    pending_maintenance_count: int = Field(ge=0)
    oldest_pending_age_seconds: float | None = Field(default=None, ge=0)
    mapping_verified_count: int = Field(ge=0)
    documents_per_hour: float | None = Field(default=None, ge=0)
    eta_seconds: float | None = Field(default=None, ge=0)
    eta_confidence: EtaConfidence
    attempted_cost_usd: Decimal
    settled_cost_usd: Decimal
    bulk_window_active: bool
    bulk_window_starts_at: datetime | None = None
    bulk_window_ends_at: datetime | None = None


class GraphMetricsService:
    """Read backlog/ETA/cost exclusively from durable Postgres rows."""

    def __init__(self, connection: psycopg.Connection) -> None:
        """Bind one ``app_worker`` or ``app_api`` connection.

        Args:
            connection: Open Postgres connection.
        """

        self._connection = connection

    def collect(self) -> GraphQueueMetrics:
        """Compute the current graph queue metrics snapshot.

        Returns:
            Frozen metrics. ``eta_confidence`` is ``insufficient-sample``
            until Packet 4 records mapping-verified completions.
        """

        pending_index, pending_maint, oldest_age = self._backlog()
        mapping_verified = self._mapping_verified_count()
        documents_per_hour = None
        eta_seconds = None
        eta_confidence: EtaConfidence = "insufficient-sample"
        if mapping_verified > 0:
            documents_per_hour = self._documents_per_hour()
            if documents_per_hour and documents_per_hour > 0:
                eta_confidence = "measured"
                eta_seconds = (
                    float(pending_index) / documents_per_hour * 3600.0
                    if pending_index
                    else 0.0
                )
        attempted, settled = self._graph_costs()
        bulk_active, bulk_start, bulk_end = self._bulk_window()
        return GraphQueueMetrics(
            pending_index_count=pending_index,
            pending_maintenance_count=pending_maint,
            oldest_pending_age_seconds=oldest_age,
            mapping_verified_count=mapping_verified,
            documents_per_hour=documents_per_hour,
            eta_seconds=eta_seconds,
            eta_confidence=eta_confidence,
            attempted_cost_usd=attempted,
            settled_cost_usd=settled,
            bulk_window_active=bulk_active,
            bulk_window_starts_at=bulk_start,
            bulk_window_ends_at=bulk_end,
        )

    def _backlog(self) -> tuple[int, int, float | None]:
        with self._connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                  count(*) FILTER (
                    WHERE operation = 'index'::app.lightrag_job_operation
                  ),
                  count(*) FILTER (
                    WHERE operation <> 'index'::app.lightrag_job_operation
                  ),
                  extract(
                    epoch FROM (timezone('utc', now()) - min(created_at))
                  )
                FROM app.lightrag_index_jobs
                WHERE status = 'pending'::app.job_status
                """
            )
            row = cursor.fetchone()
        if row is None:
            return 0, 0, None
        oldest = float(row[2]) if row[2] is not None else None
        return int(row[0] or 0), int(row[1] or 0), oldest

    def _mapping_verified_count(self) -> int:
        """Count mapping-verified completions.

        Packet 3 never writes that public status, so the count stays zero
        until Packet 4.
        """

        with self._connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT count(*)
                FROM app.document_versions
                WHERE status = 'graph_ready'::app.document_status
                  AND deleted_at IS NULL
                """
            )
            row = cursor.fetchone()
        return int(row[0]) if row else 0

    def _documents_per_hour(self) -> float | None:
        with self._connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT count(*)
                FROM app.document_versions
                WHERE status = 'graph_ready'::app.document_status
                  AND deleted_at IS NULL
                  AND updated_at >= timezone('utc', now()) - interval '1 hour'
                """
            )
            row = cursor.fetchone()
        if row is None:
            return None
        count = int(row[0])
        return float(count) if count else None

    def _graph_costs(self) -> tuple[Decimal, Decimal]:
        with self._connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                  COALESCE(sum(amount_usd) FILTER (
                    WHERE status IN (
                      'reserved'::app.budget_reservation_status,
                      'committed'::app.budget_reservation_status
                    )
                  ), 0),
                  COALESCE(sum(amount_usd) FILTER (
                    WHERE status = 'committed'::app.budget_reservation_status
                  ), 0)
                FROM app.budget_reservations
                WHERE reservation_kind IN ('graph_index', 'graph_maintenance')
                """
            )
            row = cursor.fetchone()
        if row is None:
            return Decimal("0"), Decimal("0")
        return Decimal(str(row[0])), Decimal(str(row[1]))

    def _bulk_window(self) -> tuple[bool, datetime | None, datetime | None]:
        with self._connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                  graph_bulk_window_starts_at,
                  graph_bulk_window_ends_at,
                  graph_bulk_approved_at
                FROM app.company_settings
                WHERE id = '00000000-0000-0000-0000-000000000001'::uuid
                """
            )
            row = cursor.fetchone()
        if row is None:
            return False, None, None
        starts_at, ends_at, approved_at = row
        if approved_at is None or starts_at is None or ends_at is None:
            return False, starts_at, ends_at
        with self._connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT timezone('utc', now()) >= %s
                   AND timezone('utc', now()) < %s
                """,
                (starts_at, ends_at),
            )
            active_row = cursor.fetchone()
        active = bool(active_row and active_row[0])
        return active, starts_at, ends_at
