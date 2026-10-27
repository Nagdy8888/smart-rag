"""Recover one content-free usage snapshot per run into the local reporting table.

Dry-run is the default. No budgets, ledger rows, or checkpoints are modified.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import cast
from urllib.parse import quote

import ormsgpack
import psycopg
from psycopg.rows import dict_row
from smart_rag_core.observability.checkpoint_usage import (
    CheckpointUsageRun,
    deduplicate_checkpoint_usage,
    recover_usage_candidate,
)


def extract_usage(connection: psycopg.Connection) -> tuple[CheckpointUsageRun, ...]:
    """Read only counters and runtime identities, never source or answer payloads."""
    candidates: list[CheckpointUsageRun] = []
    with connection.cursor(
        name="checkpoint_usage_recovery", row_factory=dict_row
    ) as cursor:
        cursor.itersize = 1000
        cursor.execute(
            """
            SELECT c.checkpoint_id,(c.checkpoint->>'ts')::timestamptz AS recorded_at,
              jsonb_build_object('prompt_tokens',c.checkpoint->'channel_values'->'prompt_tokens',
                'completion_tokens',c.checkpoint->'channel_values'->'completion_tokens',
                'cost_usd',c.checkpoint->'channel_values'->'cost_usd') AS counters,
              b.blob
            FROM langgraph.checkpoints c JOIN langgraph.checkpoint_blobs b
              ON b.thread_id=c.thread_id AND b.checkpoint_ns=c.checkpoint_ns
              AND b.channel='authorized_runtime'
              AND b.version=c.checkpoint->'channel_versions'->>'authorized_runtime'
            WHERE b.type='msgpack' AND c.checkpoint_ns=''
              AND c.checkpoint->'channel_values' ? 'prompt_tokens'
            ORDER BY c.thread_id,c.checkpoint_ns,c.checkpoint_id
            """
        )
        for row in cursor:
            try:
                runtime: object = ormsgpack.unpackb(bytes(row["blob"]))
            except (ValueError, TypeError):
                continue
            if not isinstance(runtime, dict):
                continue
            candidate = recover_usage_candidate(
                cast(Mapping[str, object], runtime),
                row["counters"],
                checkpoint_id=str(row["checkpoint_id"]),
                recorded_at=row["recorded_at"],
            )
            if candidate is not None:
                candidates.append(candidate)
    return deduplicate_checkpoint_usage(candidates)


def write_usage(
    connection: psycopg.Connection, rows: tuple[CheckpointUsageRun, ...]
) -> None:
    """Refresh only the operator-owned reporting projection, idempotently per run."""
    with connection.cursor() as cursor:
        cursor.executemany(
            """
            INSERT INTO app.checkpoint_usage_runs(run_id,source_user_id,checkpoint_id,
              recorded_at,prompt_tokens,completion_tokens,stored_cost_usd,estimated_cost_usd,cost_state)
            VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT(run_id) DO UPDATE SET
              source_user_id=EXCLUDED.source_user_id,checkpoint_id=EXCLUDED.checkpoint_id,
              recorded_at=EXCLUDED.recorded_at,prompt_tokens=EXCLUDED.prompt_tokens,
              completion_tokens=EXCLUDED.completion_tokens,stored_cost_usd=EXCLUDED.stored_cost_usd,
              estimated_cost_usd=EXCLUDED.estimated_cost_usd,cost_state=EXCLUDED.cost_state
            WHERE EXCLUDED.recorded_at>=app.checkpoint_usage_runs.recorded_at
            """,
            [
                (
                    r.run_id,
                    r.source_user_id,
                    r.checkpoint_id,
                    r.recorded_at,
                    r.prompt_tokens,
                    r.completion_tokens,
                    r.stored_cost_usd,
                    r.estimated_cost_usd,
                    r.cost_state,
                )
                for r in rows
            ],
        )


def main() -> int:
    """Use only the explicitly selected local Docker database; never print a DSN."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--database", default="postgres")
    parser.add_argument("--evidence", type=Path)
    args = parser.parse_args()
    if args.database != "postgres" and not args.database.startswith(
        "knowledge_reliability_"
    ):
        raise ValueError("local_application_or_isolated_fixture_required")
    docker = shutil.which("docker")
    if not docker:
        raise RuntimeError("docker_required")
    password = subprocess.run(  # noqa: S603 - fixed local container, no shell
        [
            docker,
            "exec",
            "supabase_db_smart-rag-local-dev",
            "printenv",
            "POSTGRES_PASSWORD",
        ],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    dsn = f"postgresql://postgres:{quote(password, safe='')}@127.0.0.1:15422/{args.database}"
    with psycopg.connect(dsn, connect_timeout=8) as connection:
        connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
        if not args.write:
            connection.execute("SET TRANSACTION READ ONLY")
        connection.execute("SET LOCAL statement_timeout='60s'")
        rows = extract_usage(connection)
        if args.write:
            write_usage(connection, rows)
        result = {
            "recorded_at": datetime.now(UTC).isoformat(),
            "written": args.write,
            "runs": len(rows),
            "prompt_tokens": sum(r.prompt_tokens for r in rows),
            "completion_tokens": sum(r.completion_tokens for r in rows),
            "unpriced_runs": sum(r.estimated_cost_usd is None for r in rows),
            "stored_estimate_usd": str(sum((r.estimated_cost_usd or 0) for r in rows)),
        }
    if args.evidence:
        args.evidence.parent.mkdir(parents=True, exist_ok=True)
        args.evidence.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
