"""One-shot Graph-200 rebuild using canonical-passage LightRAG sources.

Default path preflights current passages, deletes leftover vendor IDs
through the qualified adapter, requeues one index job, processes that job
once, and exits. ``--map-only`` skips deletes and re-extract when the
isolated rebuild workspace already has 164 processed sources. Does not
start a forever worker and does not ingest ``plot_summaries.txt``.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

import psycopg

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from langsmith import Client  # noqa: E402
from smart_rag_core.jobs.graph_source_batches import (  # noqa: E402
    parse_processed_source_ids,
)
from smart_rag_core.jobs.graph_source_text import (  # noqa: E402
    load_version_passage_manifest,
    load_version_vendor_deletion_ids,
)
from smart_rag_core.observability.langsmith_tracing import (  # noqa: E402
    configure_langsmith,
)
from smart_rag_core.retrieval.lightrag_adapter import (  # noqa: E402
    bind_process_runtime_adapter,
)
from smart_rag_core.retrieval.lightrag_qualification import (  # noqa: E402
    inspect_ainsert_list_contract,
)
from smart_rag_core.settings import load_worker_settings  # noqa: E402
from smart_rag_worker.graph_runner import GraphWorkerLoop  # noqa: E402

from scripts.ops.ingest_demo_plot_slices import (  # noqa: E402
    merged_env,
    require_env,
)
from scripts.ops.report_demo_langsmith_usage import recent_usage  # noqa: E402
from scripts.ops.run_laptop_ingest_worker import (  # noqa: E402
    apply_laptop_ingest_environ,
)

GRAPH_JOB_ID = "542628df-2c38-4b15-a180-893d7fd74998"
GRAPH_VERSION_ID = "c9b7a989-d575-4346-be92-2537f01fa7c8"
GRAPH_POINTER_ID = "00000000-0000-0000-0000-000000000001"
LIVE_WORKSPACE_KEY = "company_default"
REBUILD_WORKSPACE_KEY = "company_default__rebuild"
EXPECTED_PASSAGE_COUNT = 164
VENDOR_CHUNK_INDEX = "lightrag_chunk_map_vendor_chunk_uq"


def parse_rebuild_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse one-shot rebuild flags.

    Args:
        argv: Optional argument vector without the program name.

    Returns:
        Parsed flags. ``map_only`` skips vendor deletes and re-extract.
    """

    parser = argparse.ArgumentParser(
        description="One-shot Graph-200 canonical-passage rebuild."
    )
    parser.add_argument(
        "--map-only",
        action="store_true",
        help=(
            "Map the existing isolated extract; do not delete vendor sources "
            "or re-insert LightRAG documents."
        ),
    )
    return parser.parse_args(argv)


def graph_ready_failed_invariant(
    readiness: Mapping[str, object],
    *,
    expected_maps: int = EXPECTED_PASSAGE_COUNT,
) -> str | None:
    """Return the first Graph Ready invariant miss, or ``None`` on success.

    Counts maps on the active pointer workspace only so leftover rows on a
    retired live workspace cannot satisfy or fail the 164-source bijection.

    Args:
        readiness: Snapshot from ``verify_graph_ready``.
        expected_maps: Required chunk-map rows on the pointer workspace.

    Returns:
        Machine-readable failed invariant, or ``None`` when Graph Ready.
    """

    version_status = readiness.get("version_status")
    if version_status != "graph_ready":
        return f"version_status:{version_status}"
    pointer_state = readiness.get("pointer_workspace_state")
    if pointer_state != "active":
        return f"pointer_workspace_state:{pointer_state}"
    pointer_key = readiness.get("pointer_workspace_key")
    if not isinstance(pointer_key, str) or not pointer_key.strip():
        return "pointer_workspace_key:missing"
    mapped = readiness.get("chunk_map_count")
    if mapped != expected_maps:
        return f"chunk_map_count:{mapped}"
    job_status = readiness.get("job_status")
    if job_status != "completed":
        return f"job_status:{job_status}"
    return None


def _require_local_live_env() -> None:
    """Fail closed unless the operator requested a live local graph rebuild.

    Raises:
        RuntimeError: If mock-model mode, tracing, or APP_ENV is wrong.
    """

    app_env = os.environ.get("APP_ENV", "").strip().lower()
    mock_mode = os.environ.get("MOCK_MODEL_MODE", "").strip().lower()
    tracing = os.environ.get("LANGSMITH_TRACING", "").strip().lower()
    if app_env != "local":
        raise RuntimeError("rebuild_requires_app_env_local")
    if mock_mode in {"1", "true", "yes"}:
        raise RuntimeError("rebuild_requires_mock_model_mode_false")
    if tracing not in {"1", "true", "yes"}:
        raise RuntimeError("rebuild_requires_langsmith_tracing")


def preflight_graph_200(
    worker_url: str,
    *,
    version_id: UUID,
) -> dict[str, object]:
    """Load the frozen passage manifest and require the Graph-200 count.

    Args:
        worker_url: ``app_worker`` session DSN. Never logged.
        version_id: Graph-200 canonical version.

    Returns:
        Sanitized preflight snapshot.

    Raises:
        RuntimeError: If the version is missing, not graph-pending, or the
            current passage count is not 164.
    """

    with psycopg.connect(worker_url, connect_timeout=15) as connection:
        connection.execute("SET ROLE app_worker")
        status = connection.execute(
            """
            SELECT status::text, graph_eligible
            FROM app.document_versions
            WHERE id = %s::uuid
            """,
            (version_id,),
        ).fetchone()
        if status is None:
            raise RuntimeError("demo_graph_version_missing")
        if str(status[0]) != "graph_pending":
            raise RuntimeError(f"demo_graph_version_not_pending:{status[0]}")
        if status[1] is not True:
            raise RuntimeError("demo_graph_version_not_eligible")
        manifest = load_version_passage_manifest(connection, version_id=version_id)
        deletion_ids = load_version_vendor_deletion_ids(
            connection,
            version_id=version_id,
        )
    if len(manifest.sources) != EXPECTED_PASSAGE_COUNT:
        raise RuntimeError(f"demo_graph_passage_count:{len(manifest.sources)}")
    return {
        "version_id": str(version_id),
        "passage_count": len(manifest.sources),
        "snapshot_digest": manifest.snapshot_digest,
        "deletion_id_count": len(deletion_ids),
        "version_status": str(status[0]),
        "source_ids": list(manifest.source_ids),
    }


def count_rebuild_processed_sources(
    operator_url: str,
    *,
    version_id: UUID,
) -> int:
    """Count processed isolated vendor sources for this Graph-200 version.

    Args:
        operator_url: Operator session DSN. Never logged.
        version_id: Graph-200 canonical version.

    Returns:
        Processed ``lightrag_doc_status`` rows in ``company_default__rebuild``
        whose IDs start with ``{version_id}:``.
    """

    prefix = f"{version_id}:"
    with psycopg.connect(operator_url, connect_timeout=15) as connection:
        connection.execute("SET ROLE postgres")
        row = connection.execute(
            """
            SELECT count(*)
            FROM lightrag.lightrag_doc_status
            WHERE workspace = %s
              AND id LIKE %s
              AND lower(status) = 'processed'
            """,
            (REBUILD_WORKSPACE_KEY, f"{prefix}%"),
        ).fetchone()
    return 0 if row is None else int(row[0])


def require_map_only_extract(
    operator_url: str,
    *,
    version_id: UUID,
    expected_source_ids: Sequence[str],
) -> dict[str, object]:
    """Require the isolated extract and checkpoint before mapping-only.

    Args:
        operator_url: Operator session DSN. Never logged.
        version_id: Graph-200 canonical version.
        expected_source_ids: Manifest source IDs that must already be
            processed and checkpointed.

    Returns:
        Sanitized extract snapshot.

    Raises:
        RuntimeError: If rebuild sources, checkpoint, isolate flags, or
            competing jobs are not already in the mapping-only shape.

    Side Effects:
        Read-only. Does not un-quarantine live ``company_default`` and does
        not delete vendor rows.
    """

    expected = tuple(expected_source_ids)
    if len(expected) != EXPECTED_PASSAGE_COUNT:
        raise RuntimeError(f"demo_graph_passage_count:{len(expected)}")
    processed = count_rebuild_processed_sources(
        operator_url,
        version_id=version_id,
    )
    if processed != EXPECTED_PASSAGE_COUNT:
        raise RuntimeError(f"rebuild_vendor_processed:{processed}")
    with psycopg.connect(operator_url, connect_timeout=15) as connection:
        connection.execute("SET ROLE postgres")
        rebuild = connection.execute(
            """
            SELECT state::text
            FROM app.graph_workspaces
            WHERE workspace_key = %s
            """,
            (REBUILD_WORKSPACE_KEY,),
        ).fetchone()
        if rebuild is None:
            raise RuntimeError("rebuild_workspace_missing")
        if str(rebuild[0]) != "building":
            raise RuntimeError(f"rebuild_workspace_state:{rebuild[0]}")
        live = connection.execute(
            """
            SELECT state::text
            FROM app.graph_workspaces
            WHERE workspace_key = %s
            """,
            (LIVE_WORKSPACE_KEY,),
        ).fetchone()
        competing = connection.execute(
            """
            SELECT id::text, status::text
            FROM app.lightrag_index_jobs
            WHERE status IN (
              'pending'::app.job_status,
              'processing'::app.job_status
            )
              AND id IS DISTINCT FROM %s::uuid
            """,
            (GRAPH_JOB_ID,),
        ).fetchall()
        if competing:
            raise RuntimeError(
                "other_graph_jobs_active:" + ",".join(str(row[0]) for row in competing)
            )
        own_status = connection.execute(
            """
            SELECT status::text
            FROM app.lightrag_index_jobs
            WHERE id = %s::uuid
            """,
            (GRAPH_JOB_ID,),
        ).fetchone()
        if own_status is not None and str(own_status[0]) == "processing":
            raise RuntimeError("graph_job_already_processing")
        job = connection.execute(
            """
            SELECT payload_ref
            FROM app.lightrag_index_jobs
            WHERE id = %s::uuid
              AND version_id = %s::uuid
            """,
            (GRAPH_JOB_ID, GRAPH_VERSION_ID),
        ).fetchone()
        if job is None:
            raise RuntimeError("demo_graph_job_missing")
        raw_payload = job[0]
        if isinstance(raw_payload, str):
            try:
                raw_payload = json.loads(raw_payload)
            except json.JSONDecodeError as exc:
                raise RuntimeError("map_only_payload_invalid") from exc
        if not isinstance(raw_payload, Mapping):
            raise RuntimeError("map_only_payload_invalid")
        payload = dict(raw_payload)
        checkpoint_ids = set(parse_processed_source_ids(payload))
        if checkpoint_ids != set(expected):
            raise RuntimeError(
                f"map_only_checkpoint_mismatch:{len(checkpoint_ids)}/{len(expected)}"
            )
        if payload.get("isolate_candidate") is not True:
            raise RuntimeError("map_only_isolate_candidate_required")
        if payload.get("local_demo_mapping_override") is not True:
            raise RuntimeError("map_only_local_demo_override_required")
        if payload.get("content_class") != "synthetic":
            raise RuntimeError("map_only_content_class_required")
        if payload.get("review_approved") is not True:
            raise RuntimeError("map_only_review_approved_required")
    return {
        "processed_rebuild_sources": processed,
        "checkpoint_source_count": len(checkpoint_ids),
        "rebuild_workspace_state": str(rebuild[0]),
        "live_workspace_state": None if live is None else str(live[0]),
    }


def ensure_vendor_chunk_unique_index(operator_url: str) -> None:
    """Apply the expand-only vendor-chunk unique index when missing.

    Args:
        operator_url: Operator session DSN. Never logged.

    Side Effects:
        ``CREATE UNIQUE INDEX IF NOT EXISTS`` under ``SET ROLE postgres``.
    """

    with psycopg.connect(operator_url, connect_timeout=15) as connection:
        connection.execute("SET ROLE postgres")
        connection.execute(
            f"""
            CREATE UNIQUE INDEX IF NOT EXISTS {VENDOR_CHUNK_INDEX}
              ON app.lightrag_chunk_map
                (workspace_key, version_id, lightrag_chunk_id)
              WHERE version_id IS NOT NULL
                AND workspace_key IS NOT NULL
                AND lightrag_chunk_id IS NOT NULL
            """
        )
        connection.commit()


def requeue_graph_200_job(operator_url: str) -> dict[str, object]:
    """Reset workspace lease state and requeue the known Graph-200 index job.

    Args:
        operator_url: Operator session DSN. Never logged.

    Returns:
        Sanitized job snapshot.

    Raises:
        RuntimeError: If the workspace or job cannot be recovered.

    Side Effects:
        Clears the writer lease and marks the known job pending. Does not
        change live ``company_default`` state and does not rewrite the
        source-batch checkpoint.
    """

    with psycopg.connect(operator_url, connect_timeout=15) as connection:
        connection.execute("SET ROLE postgres")
        workspace = connection.execute(
            """
            SELECT state::text
            FROM app.graph_workspaces
            WHERE workspace_key = %s
            """,
            (LIVE_WORKSPACE_KEY,),
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
                'review_approved', true,
                'isolate_candidate', true
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
        "workspace_state": str(workspace[0]),
    }


def verify_graph_ready(worker_url: str, *, version_id: UUID) -> dict[str, object]:
    """Read version, pointer workspace, and map counts after the one-shot job.

    Args:
        worker_url: ``app_worker`` session DSN. Never logged.
        version_id: Graph-200 canonical version.

    Returns:
        Sanitized readiness snapshot. ``chunk_map_count`` is the pointer
        workspace only.
    """

    with psycopg.connect(worker_url, connect_timeout=15) as connection:
        connection.execute("SET ROLE app_worker")
        version = connection.execute(
            """
            SELECT status::text
            FROM app.document_versions
            WHERE id = %s::uuid
            """,
            (version_id,),
        ).fetchone()
        pointer = connection.execute(
            """
            SELECT w.workspace_key, w.state::text
            FROM app.graph_active_workspace_pointer p
            LEFT JOIN app.graph_workspaces w ON w.id = p.workspace_id
            WHERE p.id = %s::uuid
            """,
            (GRAPH_POINTER_ID,),
        ).fetchone()
        pointer_key = None if pointer is None else pointer[0]
        maps = (0, 0, 0)
        if isinstance(pointer_key, str) and pointer_key.strip():
            mapped = connection.execute(
                """
                SELECT
                  count(*),
                  count(DISTINCT lightrag_doc_id),
                  count(DISTINCT lightrag_chunk_id)
                FROM app.lightrag_chunk_map
                WHERE version_id = %s::uuid
                  AND workspace_key = %s
                """,
                (version_id, pointer_key),
            ).fetchone()
            if mapped is not None:
                maps = mapped
        leftover = connection.execute(
            """
            SELECT count(*)
            FROM app.lightrag_chunk_map
            WHERE version_id = %s::uuid
              AND workspace_key = %s
            """,
            (version_id, LIVE_WORKSPACE_KEY),
        ).fetchone()
        live = connection.execute(
            """
            SELECT state::text
            FROM app.graph_workspaces
            WHERE workspace_key = %s
            """,
            (LIVE_WORKSPACE_KEY,),
        ).fetchone()
        rebuild = connection.execute(
            """
            SELECT state::text
            FROM app.graph_workspaces
            WHERE workspace_key = %s
            """,
            (REBUILD_WORKSPACE_KEY,),
        ).fetchone()
        job = connection.execute(
            """
            SELECT status::text, last_error
            FROM app.lightrag_index_jobs
            WHERE id = %s::uuid
            """,
            (GRAPH_JOB_ID,),
        ).fetchone()
    pointer_state = None if pointer is None else pointer[1]
    return {
        "version_status": None if version is None else str(version[0]),
        "pointer_workspace_key": pointer_key,
        "pointer_workspace_state": (
            None if pointer_state is None else str(pointer_state)
        ),
        "workspace_state": None if pointer_state is None else str(pointer_state),
        "live_workspace_state": None if live is None else str(live[0]),
        "rebuild_workspace_state": None if rebuild is None else str(rebuild[0]),
        "chunk_map_count": int(maps[0]),
        "vendor_doc_count": int(maps[1]),
        "vendor_chunk_count": int(maps[2]),
        "leftover_live_map_count": 0 if leftover is None else int(leftover[0]),
        "job_status": None if job is None else str(job[0]),
        "job_last_error": None if job is None or job[1] is None else str(job[1]),
    }


def main(argv: Sequence[str] | None = None) -> int:
    """Run one bounded Graph-200 canonical-passage rebuild or mapping-only job.

    Args:
        argv: Optional argument vector without the program name.

    Returns:
        Process exit code. Non-zero stops on the first failed invariant.

    Side Effects:
        Without ``--map-only``, deletes Graph-200 vendor sources then
        requeues and processes one index job. With ``--map-only``, keeps the
        isolated extract, requeues mapping, and processes once. Hybrid-800
        and Graph-200 Hybrid indexes are not modified. Live
        ``company_default`` is not un-quarantined before a verified isolate
        pointer switch.
    """

    args = parse_rebuild_args(argv)
    apply_laptop_ingest_environ()
    os.environ["APP_ENV"] = "local"
    os.environ["MOCK_MODEL_MODE"] = "false"
    os.environ["LANGSMITH_TRACING"] = "true"
    os.environ["JOB_LEASE_SECONDS"] = "3600"
    os.environ["JOB_HEARTBEAT_INTERVAL_SECONDS"] = "30"
    _require_local_live_env()
    flags = inspect_ainsert_list_contract()
    if not all(flags.values()):
        raise RuntimeError("ainsert_list_contract_missing")
    env = merged_env()
    operator_url = require_env(env, "OPERATOR_SUPABASE_DB_URL")
    worker_url = os.environ.get("SUPABASE_DB_URL", "").strip()
    if not worker_url:
        raise RuntimeError("supabase_db_url_unconfigured")
    version_id = UUID(GRAPH_VERSION_ID)
    preflight = preflight_graph_200(worker_url, version_id=version_id)
    source_ids = tuple(str(item) for item in preflight["source_ids"])
    processed_rebuild = count_rebuild_processed_sources(
        operator_url,
        version_id=version_id,
    )
    map_only_snapshot: dict[str, object] | None = None
    if args.map_only:
        map_only_snapshot = require_map_only_extract(
            operator_url,
            version_id=version_id,
            expected_source_ids=source_ids,
        )
    elif processed_rebuild == EXPECTED_PASSAGE_COUNT:
        raise RuntimeError("rebuild_would_delete_processed_extract_use_map_only")
    ensure_vendor_chunk_unique_index(operator_url)
    settings = load_worker_settings()
    configure_langsmith(settings)
    if settings.lightrag_db_url is None:
        raise RuntimeError("lightrag_db_url_unconfigured")
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    adapter = loop.run_until_complete(
        bind_process_runtime_adapter(
            dsn=settings.lightrag_db_url,
            settings=settings,
        )
    )
    if adapter is None:
        raise RuntimeError("lightrag_adapter_unconfigured")
    claimed = False
    try:
        if not args.map_only:
            with psycopg.connect(worker_url, connect_timeout=15) as connection:
                connection.execute("SET ROLE app_worker")
                deletion_ids = load_version_vendor_deletion_ids(
                    connection,
                    version_id=version_id,
                )
            for vendor_id in deletion_ids:
                loop.run_until_complete(
                    adapter.delete_document(
                        document_id=vendor_id, delete_llm_cache=True
                    )
                )
        requeue = requeue_graph_200_job(operator_url)
        graph_loop = GraphWorkerLoop(
            settings,
            adapter=adapter,
            async_loop=loop,
        )
        claimed = graph_loop.process_once()
        readiness = verify_graph_ready(worker_url, version_id=version_id)
    finally:
        loop.run_until_complete(adapter.finalize())
        loop.close()
        asyncio.set_event_loop(None)
    failure_context = {
        "map_only": args.map_only,
        "preflight": {
            key: value for key, value in preflight.items() if key != "source_ids"
        },
        "map_only_extract": map_only_snapshot,
    }
    if not claimed:
        print(
            json.dumps(
                {
                    "ok": False,
                    "failed_invariant": "graph_job_not_claimed",
                    **failure_context,
                },
                sort_keys=True,
            ),
            flush=True,
        )
        return 1
    failed = graph_ready_failed_invariant(readiness)
    if failed is not None:
        print(
            json.dumps(
                {
                    "ok": False,
                    "failed_invariant": failed,
                    "requeue": requeue,
                    "readiness": readiness,
                    **failure_context,
                },
                sort_keys=True,
            ),
            flush=True,
        )
        return 1
    project_name = env.get("LANGSMITH_PROJECT", "smart-rag").strip() or "smart-rag"
    endpoint = env.get("LANGSMITH_ENDPOINT", "").strip() or None
    client = Client(
        api_url=endpoint,
        api_key=require_env(env, "LANGSMITH_API_KEY"),
        hide_inputs=True,
        hide_outputs=True,
    )
    usage = asyncio.run(
        recent_usage(
            client=client,
            project_name=project_name,
            since=datetime.now(UTC) - timedelta(hours=12),
        )
    )
    print(
        json.dumps(
            {
                "ok": True,
                "map_only": args.map_only,
                "preflight": {
                    key: value
                    for key, value in preflight.items()
                    if key != "source_ids"
                },
                "map_only_extract": map_only_snapshot,
                "requeue": requeue,
                "readiness": readiness,
                "langsmith": usage,
            },
            sort_keys=True,
        ),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
