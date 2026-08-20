"""One-shot Graph-200 rebuild using canonical-passage LightRAG sources.

Preflights current passages, deletes the legacy whole-version vendor source
plus leftover passage IDs through the qualified adapter, requeues one index
job, processes that job once, and exits. Does not start a forever worker and
does not ingest ``plot_summaries.txt``.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

import psycopg

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from langsmith import Client  # noqa: E402
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
EXPECTED_PASSAGE_COUNT = 164
VENDOR_CHUNK_INDEX = "lightrag_chunk_map_vendor_chunk_uq"


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
    """

    with psycopg.connect(operator_url, connect_timeout=15) as connection:
        connection.execute("SET ROLE postgres")
        workspace = connection.execute(
            """
            SELECT state::text
            FROM app.graph_workspaces
            WHERE workspace_key = 'company_default'
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
    """Read version, workspace, and map counts after the one-shot job.

    Args:
        worker_url: ``app_worker`` session DSN. Never logged.
        version_id: Graph-200 canonical version.

    Returns:
        Sanitized readiness snapshot.
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
        workspace = connection.execute(
            """
            SELECT state::text
            FROM app.graph_workspaces
            WHERE workspace_key = 'company_default'
            """
        ).fetchone()
        maps = connection.execute(
            """
            SELECT
              count(*),
              count(DISTINCT lightrag_doc_id),
              count(DISTINCT lightrag_chunk_id)
            FROM app.lightrag_chunk_map
            WHERE version_id = %s::uuid
            """,
            (version_id,),
        ).fetchone()
        job = connection.execute(
            """
            SELECT status::text, last_error
            FROM app.lightrag_index_jobs
            WHERE id = %s::uuid
            """,
            (GRAPH_JOB_ID,),
        ).fetchone()
    return {
        "version_status": None if version is None else str(version[0]),
        "workspace_state": None if workspace is None else str(workspace[0]),
        "chunk_map_count": None if maps is None else int(maps[0]),
        "vendor_doc_count": None if maps is None else int(maps[1]),
        "vendor_chunk_count": None if maps is None else int(maps[2]),
        "job_status": None if job is None else str(job[0]),
        "job_last_error": None if job is None or job[1] is None else str(job[1]),
    }


def main() -> int:
    """Run one bounded Graph-200 canonical-passage rebuild.

    Returns:
        Process exit code. Non-zero stops on the first failed invariant.

    Side Effects:
        Deletes Graph-200 vendor sources, requeues one index job, processes
        that job once, and prints a sanitized snapshot plus LangSmith usage.
        Hybrid-800 and Graph-200 Hybrid indexes are not modified.
    """

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
        with psycopg.connect(worker_url, connect_timeout=15) as connection:
            connection.execute("SET ROLE app_worker")
            deletion_ids = load_version_vendor_deletion_ids(
                connection,
                version_id=version_id,
            )
        for vendor_id in deletion_ids:
            loop.run_until_complete(
                adapter.delete_document(document_id=vendor_id, delete_llm_cache=True)
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
    if not claimed:
        print(
            json.dumps(
                {
                    "ok": False,
                    "failed_invariant": "graph_job_not_claimed",
                    "preflight": preflight,
                },
                sort_keys=True,
            ),
            flush=True,
        )
        return 1
    if readiness["version_status"] != "graph_ready":
        print(
            json.dumps(
                {
                    "ok": False,
                    "failed_invariant": (
                        f"version_status:{readiness['version_status']}"
                    ),
                    "preflight": preflight,
                    "readiness": readiness,
                },
                sort_keys=True,
            ),
            flush=True,
        )
        return 1
    if readiness["workspace_state"] != "active":
        print(
            json.dumps(
                {
                    "ok": False,
                    "failed_invariant": (
                        f"workspace_state:{readiness['workspace_state']}"
                    ),
                    "preflight": preflight,
                    "readiness": readiness,
                },
                sort_keys=True,
            ),
            flush=True,
        )
        return 1
    mapped = readiness["chunk_map_count"]
    if not isinstance(mapped, int) or mapped != EXPECTED_PASSAGE_COUNT:
        print(
            json.dumps(
                {
                    "ok": False,
                    "failed_invariant": (
                        f"chunk_map_count:{readiness['chunk_map_count']}"
                    ),
                    "preflight": preflight,
                    "readiness": readiness,
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
                "preflight": preflight,
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
