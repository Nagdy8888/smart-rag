"""Replay the two existing demo Hybrid jobs without uploading files again.

The normal ingest graph intentionally rejects terminal document-version
statuses. This operator-only demo helper assigns fresh operation keys, moves
the two known versions through ``scanning``, and preserves prior embedding
ledgers. After both Hybrid jobs complete, ``--bm25`` replays their existing
projection jobs so canonical terminal statuses are restored.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

import psycopg

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from scripts.ops.ingest_demo_plot_slices import (  # noqa: E402
    merged_env,
    require_env,
)


@dataclass(frozen=True)
class DemoHybridReplay:
    """Identifiers and expected status for one bounded demo replay.

    Attributes:
        ingestion_job_id: Existing ``hybrid_index`` job id.
        version_id: Existing canonical document-version id.
        expected_terminal_status: Status accepted before the replay.
        bm25_job_id: Existing local ParadeDB projection job id.
    """

    ingestion_job_id: str
    version_id: str
    expected_terminal_status: str
    bm25_job_id: str


REPLAYS = (
    DemoHybridReplay(
        ingestion_job_id="a488e1ab-d7a1-4316-889e-1e4a0b4b53f2",
        version_id="9c245c8d-31e4-4100-bccf-3c3cb15d3a7f",
        expected_terminal_status="graph_ineligible",
        bm25_job_id="c4ac75b9-ef3d-4989-bcf3-3fed27746470",
    ),
    DemoHybridReplay(
        ingestion_job_id="907a1b75-aa48-4b1a-abe8-a87265565a7f",
        version_id="c9b7a989-d575-4346-be92-2537f01fa7c8",
        expected_terminal_status="graph_pending",
        bm25_job_id="340815d9-c613-41b9-90f7-f2a7ced51f53",
    ),
)


def prepare_hybrid_replays(
    operator_url: str,
    *,
    operation_prefix: str,
) -> list[dict[str, object]]:
    """Prepare fresh embedding operations for both bounded demo versions.

    Args:
        operator_url: Operator session DSN. Never logged.
        operation_prefix: Safe unique prefix that forces fresh embedding and
            canonical operation ledgers without deleting prior evidence.

    Returns:
        Sanitized job/version snapshots.

    Raises:
        RuntimeError: If a version is not in its expected terminal status or
            a known Hybrid job is missing.

    Side Effects:
        Deletes only the two jobs' LangGraph checkpoints, assigns fresh
        operation keys, moves versions to ``scanning``, and requeues jobs at
        attempt zero. Prior embedding and job-operation ledgers are retained.
    """

    if re.fullmatch(r"[a-zA-Z0-9_-]{1,96}", operation_prefix) is None:
        raise ValueError("invalid_operation_prefix")
    snapshots: list[dict[str, object]] = []
    with psycopg.connect(operator_url, connect_timeout=15) as connection:
        connection.execute("SET ROLE postgres")
        for replay in REPLAYS:
            for table in (
                "checkpoint_writes",
                "checkpoint_blobs",
                "checkpoints",
            ):
                connection.execute(
                    f"DELETE FROM langgraph.{table} WHERE thread_id = %s",  # noqa: S608
                    (replay.ingestion_job_id,),
                )
            version = connection.execute(
                """
                UPDATE app.document_versions
                SET status = 'scanning'::app.document_status
                WHERE id = %s::uuid
                  AND status::text = %s
                RETURNING id::text, status::text
                """,
                (replay.version_id, replay.expected_terminal_status),
            ).fetchone()
            if version is None:
                raise RuntimeError(
                    f"unexpected_demo_version_status:{replay.version_id}"
                )
            operation_key = f"{operation_prefix}_{replay.version_id}"
            job = connection.execute(
                """
                UPDATE app.ingestion_jobs
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
                    'operation_key', %s::text,
                    'content_class', 'synthetic',
                    'review_approved', true
                  )
                WHERE id = %s::uuid
                  AND job_kind = 'hybrid_index'
                RETURNING id::text, status::text, attempt_count
                """,
                (operation_key, replay.ingestion_job_id),
            ).fetchone()
            if job is None:
                raise RuntimeError(f"missing_demo_hybrid_job:{replay.ingestion_job_id}")
            snapshots.append(
                {
                    "job_id": job[0],
                    "job_status": job[1],
                    "attempt_count": job[2],
                    "version_id": version[0],
                    "version_status": version[1],
                    "operation_key": operation_key,
                }
            )
        connection.commit()
    return snapshots


def requeue_bm25_replays(operator_url: str) -> list[dict[str, object]]:
    """Requeue both existing BM25 jobs after Hybrid embedding succeeds.

    Args:
        operator_url: Operator session DSN. Never logged.

    Returns:
        Sanitized BM25 job snapshots.

    Raises:
        RuntimeError: If a Hybrid replay is not completed or a BM25 job is
            missing.

    Side Effects:
        Resets only the two known BM25 jobs to pending attempt zero. The local
        projection worker re-verifies ParadeDB and finalizes document status.
    """

    snapshots: list[dict[str, object]] = []
    with psycopg.connect(operator_url, connect_timeout=15) as connection:
        connection.execute("SET ROLE postgres")
        for replay in REPLAYS:
            hybrid_status = connection.execute(
                "SELECT status::text FROM app.ingestion_jobs WHERE id = %s::uuid",
                (replay.ingestion_job_id,),
            ).fetchone()
            if hybrid_status is None or str(hybrid_status[0]) != "completed":
                raise RuntimeError(
                    f"hybrid_replay_not_completed:{replay.ingestion_job_id}"
                )
            row = connection.execute(
                """
                UPDATE app.bm25_index_jobs
                SET
                  status = 'pending'::app.job_status,
                  next_attempt_at = timezone('utc', now()),
                  lease_token = NULL,
                  lease_owner = NULL,
                  lease_expires_at = NULL,
                  heartbeat_at = NULL,
                  attempt_count = 0,
                  last_error = NULL,
                  error_category = NULL
                WHERE id = %s::uuid
                RETURNING id::text, status::text, attempt_count
                """,
                (replay.bm25_job_id,),
            ).fetchone()
            if row is None:
                raise RuntimeError(f"missing_demo_bm25_job:{replay.bm25_job_id}")
            snapshots.append(
                {
                    "job_id": row[0],
                    "status": row[1],
                    "attempt_count": row[2],
                }
            )
        connection.commit()
    return snapshots


def main() -> int:
    """Run the requested replay stage.

    Returns:
        Process exit code.
    """

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--bm25",
        action="store_true",
        help="requeue BM25 only after both Hybrid jobs complete",
    )
    parser.add_argument(
        "--operation-prefix",
        default="hybrid_demo_retry_20260819",
        help="unique safe prefix for fresh Hybrid operation ledgers",
    )
    args = parser.parse_args()
    env = merged_env()
    operator_url = require_env(env, "OPERATOR_SUPABASE_DB_URL")
    if args.bm25:
        snapshots = requeue_bm25_replays(operator_url)
    else:
        snapshots = prepare_hybrid_replays(
            operator_url,
            operation_prefix=args.operation_prefix,
        )
    print(json.dumps(snapshots, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
