"""Requeue Graph-200 mapping without deleting or re-extracting vendor data."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import psycopg

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from scripts.ops.ingest_demo_plot_slices import (  # noqa: E402
    merged_env,
    require_env,
)

GRAPH_JOB_ID = "542628df-2c38-4b15-a180-893d7fd74998"
GRAPH_VERSION_ID = "c9b7a989-d575-4346-be92-2537f01fa7c8"


def requeue_demo_graph_mapping(operator_url: str) -> dict[str, object]:
    """Requeue the known Graph-200 job with the approved local mapping flag.

    Args:
        operator_url: Operator session DSN. Never logged.

    Returns:
        Sanitized graph-job snapshot after requeue.

    Raises:
        RuntimeError: If vendor extraction is not already processed, the
            canonical version is not ``graph_pending``, or the known job is
            missing.

    Side Effects:
        Marks only the known LightRAG job pending at attempt zero and appends
        reviewed synthetic local-demo flags. A quarantined/updating workspace
        is reset to ``building`` and the expired writer lease is cleared.
        Vendor tables, document status, graph objects, and prior usage
        evidence are not deleted. The indexer sees the existing vendor
        ``processed`` row and skips ``ainsert``.
    """

    with psycopg.connect(operator_url, connect_timeout=15) as connection:
        connection.execute("SET ROLE postgres")
        vendor = connection.execute(
            """
            SELECT status
            FROM lightrag.lightrag_doc_status
            WHERE id = %s
            """,
            (GRAPH_VERSION_ID,),
        ).fetchone()
        if vendor is None or str(vendor[0]).lower() != "processed":
            raise RuntimeError("demo_graph_vendor_not_processed")
        version = connection.execute(
            """
            SELECT status::text
            FROM app.document_versions
            WHERE id = %s::uuid
            """,
            (GRAPH_VERSION_ID,),
        ).fetchone()
        if version is None or str(version[0]) != "graph_pending":
            raise RuntimeError("demo_graph_version_not_pending")
        workspace = connection.execute(
            """
            UPDATE app.graph_workspaces
            SET
              state = 'building'::app.graph_workspace_state,
              config_snapshot = (
                config_snapshot
                - 'quarantined_at'
                - 'quarantine_reason'
              ) || jsonb_build_object('reconciliation_required', false)
            WHERE workspace_key = 'company_default'
              AND state IN (
                'quarantined'::app.graph_workspace_state,
                'updating'::app.graph_workspace_state
              )
            RETURNING state::text
            """
        ).fetchone()
        if workspace is None:
            raise RuntimeError("demo_graph_workspace_not_recoverable")
        connection.execute(
            """
            UPDATE app.graph_writer_lease
            SET
              owner = NULL,
              token = NULL,
              expires_at = NULL,
              updated_at = timezone('utc', now())
            WHERE id = '00000000-0000-0000-0000-000000000001'::uuid
            """
        )
        row = connection.execute(
            """
            UPDATE app.lightrag_index_jobs
            SET
              status = 'pending'::app.job_status,
              next_attempt_at = timezone('utc', now()),
              lease_token = NULL,
              lease_owner = NULL,
              lease_expires_at = NULL,
              heartbeat_at = NULL,
              attempt_count = 0,
              last_error = NULL,
              error_category = NULL,
              payload_ref = payload_ref || jsonb_build_object(
                'local_demo_mapping_override', true,
                'content_class', 'synthetic',
                'review_approved', true
              )
            WHERE id = %s::uuid
              AND version_id = %s::uuid
              AND operation = 'index'::app.lightrag_job_operation
            RETURNING id::text, status::text, attempt_count
            """,
            (GRAPH_JOB_ID, GRAPH_VERSION_ID),
        ).fetchone()
        if row is None:
            raise RuntimeError("demo_graph_job_missing")
        connection.commit()
    return {
        "job_id": row[0],
        "status": row[1],
        "attempt_count": row[2],
        "vendor_status": str(vendor[0]),
        "version_status": str(version[0]),
        "workspace_state": str(workspace[0]),
    }


def main() -> int:
    """Requeue mapping and print a sanitized snapshot.

    Returns:
        Process exit code.
    """

    env = merged_env()
    snapshot = requeue_demo_graph_mapping(
        require_env(env, "OPERATOR_SUPABASE_DB_URL")
    )
    print(json.dumps(snapshot, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
