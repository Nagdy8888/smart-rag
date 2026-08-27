"""Shared query-memory reaper clock and completion helpers."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import psycopg

QUERY_MEMORY_NOW = datetime(2026, 8, 16, 12, 0, tzinfo=UTC)


def complete_query_run(
    cursor: psycopg.Cursor,
    run_id: UUID,
    *,
    completed_at: datetime,
) -> None:
    """Mark one run completed at an injected clock.

    Args:
        cursor: Open cursor.
        run_id: Run to complete.
        completed_at: Completion timestamp used by the reaper.
    """

    cursor.execute(
        """
        UPDATE app.runs
        SET
          status = 'completed'::app.run_status,
          completed_at = %s,
          updated_at = %s
        WHERE id = %s
        """,
        (completed_at, completed_at, run_id),
    )
