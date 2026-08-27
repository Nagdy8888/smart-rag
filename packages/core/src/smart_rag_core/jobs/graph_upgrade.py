"""Isolated LightRAG upgrade qualification and disable-review triggers.

A second workspace in runtime schema ``lightrag`` is never upgrade proof.
Snapshot/restore is the vendor schema rollback boundary.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

import psycopg

from smart_rag_core.ingestion.embeddings.policy import (
    EMBEDDING_DIMENSIONS,
    EMBEDDING_MODEL,
)
from smart_rag_core.jobs.exceptions import GraphLifecycleError
from smart_rag_core.jobs.graph_lifecycle import (
    assert_homogeneous_embedding,
    assert_isolated_upgrade_environment,
    disable_review_required,
)
from smart_rag_core.jobs.graph_pointer_switch import disable_workspace
from smart_rag_core.jobs.limits import (
    GRAPH_SURVIVAL_ALERT_PERSIST_DAYS,
    RUNTIME_LIGHTRAG_SCHEMA,
)
from smart_rag_core.retrieval.graph import (
    DEFAULT_GRAPH_WORKSPACE,
    GRAPH_SURVIVAL_ROLLING_ALERT_THRESHOLD,
)


@dataclass(frozen=True, slots=True)
class UpgradeQualificationResult:
    """Recorded isolated upgrade attempt.

    Attributes:
        qualification_id: Durable row id.
        status: ``recorded``, ``passed``, ``failed``, or ``disable_review``.
        consecutive_failures: Failure streak after this row.
    """

    qualification_id: UUID
    status: str
    consecutive_failures: int


def record_upgrade_qualification(
    connection: psycopg.Connection,
    *,
    candidate_database: str,
    candidate_schema: str,
    runtime_database: str,
    runtime_schema: str = RUNTIME_LIGHTRAG_SCHEMA,
    status: str = "recorded",
    notes: str = "",
    embedding_model: str = EMBEDDING_MODEL,
    embedding_dimensions: int = EMBEDDING_DIMENSIONS,
) -> UpgradeQualificationResult:
    """Persist isolated upgrade proof or refuse same-schema attempts.

    Args:
        connection: ``app_worker`` connection. Caller commits.
        candidate_database: Restored copy database.
        candidate_schema: Restored copy schema.
        runtime_database: Live database name.
        runtime_schema: Live vendor schema.
        status: ``recorded``, ``passed``, or ``failed``.
        notes: Bounded operator notes without secrets.
        embedding_model: Homogeneous embedding model.
        embedding_dimensions: Homogeneous dimensions.

    Returns:
        Recorded qualification.

    Raises:
        GraphLifecycleError: Same-schema proof or mixed embeddings.

    Side Effects:
        Inserts ``app.graph_upgrade_qualifications``. May open disable review.
    """

    assert_homogeneous_embedding(
        model=embedding_model,
        dimensions=embedding_dimensions,
    )
    assert_isolated_upgrade_environment(
        candidate_database=candidate_database,
        candidate_schema=candidate_schema,
        runtime_database=runtime_database,
        runtime_schema=runtime_schema,
    )
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT app.record_graph_upgrade_qualification(
                  %s, %s, %s, %s, %s, %s
                )
                """,
                (
                    candidate_database,
                    candidate_schema,
                    runtime_database,
                    runtime_schema,
                    status,
                    notes[:512],
                ),
            )
            row = cursor.fetchone()
            cursor.execute(
                """
                SELECT status, consecutive_failures
                FROM app.graph_upgrade_qualifications
                WHERE id = %s
                """,
                (row[0] if row else None,),
            )
            detail = cursor.fetchone()
    except psycopg.errors.RaiseException as exc:
        if "upgrade_same_schema_insufficient" in str(exc):
            raise GraphLifecycleError("upgrade_same_schema_insufficient") from exc
        raise GraphLifecycleError("upgrade_qualification_failed") from exc
    if row is None or row[0] is None or detail is None:
        raise GraphLifecycleError("upgrade_qualification_missing")
    recorded_status = str(detail[0])
    failures = int(detail[1] or 0)
    if recorded_status == "refused_same_schema":
        raise GraphLifecycleError("upgrade_same_schema_insufficient")
    if recorded_status == "disable_review" or disable_review_required(
        consecutive_failures=failures
    ):
        disable_workspace(
            connection,
            workspace_key=DEFAULT_GRAPH_WORKSPACE,
            reason="upgrade_qualification_failed",
        )
    return UpgradeQualificationResult(
        qualification_id=UUID(str(row[0])),
        status=recorded_status,
        consecutive_failures=failures,
    )


def survival_alerts_persist_seven_days(
    connection: psycopg.Connection,
    *,
    now: datetime | None = None,
) -> bool:
    """Return True when rolling survival stays below 0.80 for seven days.

    Args:
        connection: ``app_worker`` or ``app_api`` connection.
        now: Clock override.

    Returns:
        True when disable review should open from survival alerts.
    """

    stamp = now or datetime.now(tz=UTC)
    window_start = stamp - timedelta(days=GRAPH_SURVIVAL_ALERT_PERSIST_DAYS)
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT
              count(*) > 0 AS has_rows,
              COALESCE(bool_and(survival_ratio < %s), false) AS all_below
            FROM app.graph_survival_samples
            WHERE recorded_at >= %s
            """,
            (GRAPH_SURVIVAL_ROLLING_ALERT_THRESHOLD, window_start),
        )
        row = cursor.fetchone()
    if row is None:
        return False
    return bool(row[0]) and bool(row[1])


def maybe_open_survival_disable_review(
    connection: psycopg.Connection,
    *,
    workspace_key: str = DEFAULT_GRAPH_WORKSPACE,
) -> UUID | None:
    """Disable the workspace when survival alerts persist seven days.

    Args:
        connection: ``app_worker`` connection. Caller commits.
        workspace_key: Workspace to disable.

    Returns:
        Workspace id when disabled, otherwise ``None``.
    """

    if not survival_alerts_persist_seven_days(connection):
        return None
    return disable_workspace(
        connection,
        workspace_key=workspace_key,
        reason="survival_alert_seven_days",
    )
