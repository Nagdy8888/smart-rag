"""Pending-cap and daily ingestion budget admission checks."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import psycopg

from smart_rag_core.jobs.exceptions import JobAdmissionError
from smart_rag_core.jobs.limits import (
    DEFAULT_DAILY_GRAPH_INDEX_BUDGET_USD,
    DEFAULT_DAILY_INGESTION_BUDGET_USD,
    DEFAULT_MONTHLY_GRAPH_MAINTENANCE_BUDGET_USD,
    INGESTION_BUDGET_RESERVATION_TTL_MINUTES,
    MAX_ESTIMATED_JOB_SIZE_BYTES,
    MAX_PENDING_INGESTION_JOBS,
)


class JobAdmissionService:
    """Enforces pending-cap and durable daily ingestion budget reservations."""

    def __init__(self, connection: psycopg.Connection) -> None:
        """Bind one open Postgres connection scoped to ``app_worker`` role.

        Args:
            connection: Active worker-role connection with autocommit disabled
                unless the caller manages transactions explicitly.
        """

        self._connection = connection

    def assert_can_enqueue_ingestion(
        self,
        *,
        estimated_size_bytes: int,
        estimated_cost_usd: Decimal,
    ) -> None:
        """Reject enqueue when backpressure or budget admission would be violated.

        Args:
            estimated_size_bytes: Declared job size used for ordering/admission.
            estimated_cost_usd: Estimated ingestion spend to reserve.

        Raises:
            JobAdmissionError: When pending cap, size cap, or budget blocks
                admission.
        """

        if estimated_size_bytes < 0:
            raise JobAdmissionError("invalid_estimated_size")
        if estimated_size_bytes > MAX_ESTIMATED_JOB_SIZE_BYTES:
            raise JobAdmissionError("estimated_size_exceeds_cap")
        pending = self._count_pending_ingestion_jobs()
        if pending >= MAX_PENDING_INGESTION_JOBS:
            raise JobAdmissionError("pending_cap")
        self._assert_daily_budget_available(estimated_cost_usd)

    def true_up_ingestion_reservation(
        self,
        reservation_id: UUID,
        *,
        actual_cost_usd: Decimal,
    ) -> None:
        """Commit a reserved ingestion budget hold to the measured actual cost.

        Args:
            reservation_id: Previously created ``app.budget_reservations.id``.
            actual_cost_usd: Measured spend to commit; values above the reserved
                amount remain bounded by the reservation row amount.

        Side Effects:
            Updates ``app.budget_reservations`` status to ``committed``.
        """

        with self._connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE app.budget_reservations
                SET
                  status = 'committed'::app.budget_reservation_status,
                  amount_usd = LEAST(amount_usd, %s),
                  committed_at = timezone('utc', now()),
                  updated_at = timezone('utc', now())
                WHERE id = %s
                  AND reservation_kind = 'ingestion_daily'
                  AND status = 'reserved'::app.budget_reservation_status
                """,
                (actual_cost_usd, reservation_id),
            )

    def release_ingestion_reservation(self, reservation_id: UUID) -> None:
        """Release an unused ingestion budget reservation.

        Args:
            reservation_id: Reservation row to release.

        Side Effects:
            Updates ``app.budget_reservations`` status to ``released``.
        """

        with self._connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE app.budget_reservations
                SET
                  status = 'released'::app.budget_reservation_status,
                  released_at = timezone('utc', now()),
                  updated_at = timezone('utc', now())
                WHERE id = %s
                  AND reservation_kind = 'ingestion_daily'
                  AND status = 'reserved'::app.budget_reservation_status
                """,
                (reservation_id,),
            )

    def create_ingestion_budget_reservation(
        self,
        *,
        estimated_cost_usd: Decimal,
    ) -> UUID:
        """Reserve daily ingestion budget and return the reservation identifier.

        Args:
            estimated_cost_usd: Positive estimated spend for one enqueue.

        Returns:
            New ``app.budget_reservations.id``.

        Raises:
            JobAdmissionError: When the daily budget is exhausted.
        """

        return self._reserve_daily_ingestion_budget(estimated_cost_usd)

    def pending_ingestion_count(self) -> int:
        """Return the current pending ingestion queue depth."""

        return self._count_pending_ingestion_jobs()

    def pending_graph_index_handoffs(self) -> int:
        """Return pending LightRAG ``index`` handoff jobs."""

        with self._connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT count(*)
                FROM app.lightrag_index_jobs
                WHERE status = 'pending'::app.job_status
                  AND operation = 'index'::app.lightrag_job_operation
                """
            )
            row = cursor.fetchone()
            if row is None:
                return 0
            return int(row[0])

    def _count_pending_ingestion_jobs(self) -> int:
        """Count ingestion jobs waiting in pending status.

        Returns:
            Number of ``pending`` rows in ``app.ingestion_jobs``.
        """

        with self._connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT count(*)
                FROM app.ingestion_jobs
                WHERE status = 'pending'::app.job_status
                """
            )
            row = cursor.fetchone()
            if row is None:
                return 0
            return int(row[0])

    def _reserve_daily_ingestion_budget(self, estimated_cost_usd: Decimal) -> UUID:
        """Insert one daily ingestion budget reservation after the cap check.

        Args:
            estimated_cost_usd: Positive estimated cost for this admission.

        Returns:
            New reservation identifier.

        Raises:
            JobAdmissionError: When the estimate is not positive or the daily
                cap cannot cover it.
        """

        if estimated_cost_usd <= 0:
            raise JobAdmissionError("invalid_estimated_cost")
        self._assert_daily_budget_available(estimated_cost_usd)
        reservation_id = uuid4()
        expires_at = datetime.now(tz=UTC) + timedelta(
            minutes=INGESTION_BUDGET_RESERVATION_TTL_MINUTES
        )
        with self._connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO app.budget_reservations (
                  id,
                  reservation_kind,
                  amount_usd,
                  expires_at
                )
                VALUES (%s, 'ingestion_daily', %s, %s)
                """,
                (reservation_id, estimated_cost_usd, expires_at),
            )
        return reservation_id

    def _assert_daily_budget_available(self, estimated_cost_usd: Decimal) -> None:
        """Fail closed when the remaining daily ingestion budget is too small.

        Args:
            estimated_cost_usd: Positive estimated cost for this admission.

        Raises:
            JobAdmissionError: When the estimate is invalid or the remaining
                cap is insufficient.
        """

        if estimated_cost_usd <= 0:
            raise JobAdmissionError("invalid_estimated_cost")
        with self._connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT COALESCE(cs.daily_ingestion_budget_usd, %s)
                FROM app.company_settings AS cs
                WHERE cs.id = '00000000-0000-0000-0000-000000000001'::uuid
                """,
                (DEFAULT_DAILY_INGESTION_BUDGET_USD,),
            )
            budget_row = cursor.fetchone()
            daily_budget = (
                Decimal(str(budget_row[0]))
                if budget_row
                else Decimal(str(DEFAULT_DAILY_INGESTION_BUDGET_USD))
            )
            cursor.execute(
                """
                SELECT COALESCE(sum(amount_usd), 0)
                FROM app.budget_reservations
                WHERE reservation_kind = 'ingestion_daily'
                  AND status IN (
                    'reserved'::app.budget_reservation_status,
                    'committed'::app.budget_reservation_status
                  )
                  AND created_at >= date_trunc('day', timezone('utc', now()))
                """
            )
            used_row = cursor.fetchone()
            used_today = Decimal(str(used_row[0])) if used_row else Decimal("0")
            if used_today + estimated_cost_usd > daily_budget:
                raise JobAdmissionError("budget_exhausted")

    def create_graph_budget_reservation(
        self,
        *,
        reservation_kind: str,
        estimated_cost_usd: Decimal,
    ) -> UUID:
        """Reserve graph index or maintenance budget without using ingestion_daily.

        Args:
            reservation_kind: ``graph_index`` or ``graph_maintenance``.
            estimated_cost_usd: Positive estimated spend.

        Returns:
            New ``app.budget_reservations.id``.

        Raises:
            JobAdmissionError: When the kind is invalid or the cap is exhausted.
        """

        if reservation_kind not in {"graph_index", "graph_maintenance"}:
            raise JobAdmissionError("invalid_graph_reservation_kind")
        if estimated_cost_usd <= 0:
            raise JobAdmissionError("invalid_estimated_cost")
        self._assert_graph_budget_available(
            reservation_kind=reservation_kind,
            estimated_cost_usd=estimated_cost_usd,
        )
        reservation_id = uuid4()
        expires_at = datetime.now(tz=UTC) + timedelta(
            minutes=INGESTION_BUDGET_RESERVATION_TTL_MINUTES
        )
        with self._connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO app.budget_reservations (
                  id,
                  reservation_kind,
                  amount_usd,
                  expires_at
                )
                VALUES (%s, %s, %s, %s)
                """,
                (
                    reservation_id,
                    reservation_kind,
                    estimated_cost_usd,
                    expires_at,
                ),
            )
        return reservation_id

    def true_up_graph_reservation(
        self,
        reservation_id: UUID,
        *,
        reservation_kind: str,
        actual_cost_usd: Decimal,
    ) -> None:
        """Commit a graph reservation to the measured actual cost.

        Args:
            reservation_id: Previously created reservation id.
            reservation_kind: Must match the reserved kind.
            actual_cost_usd: Measured spend.

        Side Effects:
            Updates ``app.budget_reservations`` to ``committed``.
        """

        if reservation_kind not in {"graph_index", "graph_maintenance"}:
            raise JobAdmissionError("invalid_graph_reservation_kind")
        with self._connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE app.budget_reservations
                SET
                  status = 'committed'::app.budget_reservation_status,
                  amount_usd = LEAST(amount_usd, %s),
                  committed_at = timezone('utc', now()),
                  updated_at = timezone('utc', now())
                WHERE id = %s
                  AND reservation_kind = %s
                  AND status = 'reserved'::app.budget_reservation_status
                """,
                (actual_cost_usd, reservation_id, reservation_kind),
            )

    def release_graph_reservation(
        self,
        reservation_id: UUID,
        *,
        reservation_kind: str,
    ) -> None:
        """Release an unused graph reservation.

        Args:
            reservation_id: Reservation row to release.
            reservation_kind: Must match the reserved kind.

        Side Effects:
            Updates ``app.budget_reservations`` to ``released``.
        """

        if reservation_kind not in {"graph_index", "graph_maintenance"}:
            raise JobAdmissionError("invalid_graph_reservation_kind")
        with self._connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE app.budget_reservations
                SET
                  status = 'released'::app.budget_reservation_status,
                  released_at = timezone('utc', now()),
                  updated_at = timezone('utc', now())
                WHERE id = %s
                  AND reservation_kind = %s
                  AND status = 'reserved'::app.budget_reservation_status
                """,
                (reservation_id, reservation_kind),
            )

    def _assert_graph_budget_available(
        self,
        *,
        reservation_kind: str,
        estimated_cost_usd: Decimal,
    ) -> None:
        """Fail closed when remaining graph index or maintenance budget is too small.

        Args:
            reservation_kind: ``graph_index`` or ``graph_maintenance``.
            estimated_cost_usd: Positive estimated cost for this reservation.

        Raises:
            JobAdmissionError: When the remaining cap cannot cover the estimate.
        """

        with self._connection.cursor() as cursor:
            if reservation_kind == "graph_index":
                cursor.execute(
                    """
                    SELECT COALESCE(cs.daily_graph_index_budget_usd, %s)
                    FROM app.company_settings AS cs
                    WHERE cs.id = '00000000-0000-0000-0000-000000000001'::uuid
                    """,
                    (DEFAULT_DAILY_GRAPH_INDEX_BUDGET_USD,),
                )
                budget_row = cursor.fetchone()
                cap = (
                    Decimal(str(budget_row[0]))
                    if budget_row
                    else Decimal(str(DEFAULT_DAILY_GRAPH_INDEX_BUDGET_USD))
                )
                cursor.execute(
                    """
                    SELECT COALESCE(sum(amount_usd), 0)
                    FROM app.budget_reservations
                    WHERE reservation_kind = 'graph_index'
                      AND status IN (
                        'reserved'::app.budget_reservation_status,
                        'committed'::app.budget_reservation_status
                      )
                      AND created_at >= date_trunc('day', timezone('utc', now()))
                    """
                )
            else:
                cursor.execute(
                    """
                    SELECT COALESCE(cs.monthly_graph_maintenance_budget_usd, %s)
                    FROM app.company_settings AS cs
                    WHERE cs.id = '00000000-0000-0000-0000-000000000001'::uuid
                    """,
                    (DEFAULT_MONTHLY_GRAPH_MAINTENANCE_BUDGET_USD,),
                )
                budget_row = cursor.fetchone()
                cap = (
                    Decimal(str(budget_row[0]))
                    if budget_row
                    else Decimal(str(DEFAULT_MONTHLY_GRAPH_MAINTENANCE_BUDGET_USD))
                )
                cursor.execute(
                    """
                    SELECT COALESCE(sum(amount_usd), 0)
                    FROM app.budget_reservations
                    WHERE reservation_kind = 'graph_maintenance'
                      AND status IN (
                        'reserved'::app.budget_reservation_status,
                        'committed'::app.budget_reservation_status
                      )
                      AND created_at >= date_trunc('month', timezone('utc', now()))
                    """
                )
            used_row = cursor.fetchone()
            used = Decimal(str(used_row[0])) if used_row else Decimal("0")
            if used + estimated_cost_usd > cap:
                raise JobAdmissionError("graph_budget_exhausted")
