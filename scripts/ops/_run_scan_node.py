"""Run scan_and_govern against the demo job payload inside the worker."""

from __future__ import annotations

import os
import traceback
from uuid import UUID

import psycopg
from smart_rag_agents.ingestion.scan_graph import promote_object, scan_and_govern

JOB_ID = UUID("681cc466-9216-442a-ac7a-189328660316")


def main() -> None:
    """Load the job row and execute scan plus promote nodes."""

    postgres_url = os.environ["SUPABASE_DB_URL"]
    with psycopg.connect(postgres_url, connect_timeout=10) as connection:
        row = connection.execute(
            """
            SELECT id::text, lease_token, document_id::text, version_id::text,
                   payload_ref
            FROM app.ingestion_jobs
            WHERE id = %s
            """,
            (JOB_ID,),
        ).fetchone()
    if row is None:
        raise SystemExit("job missing")
    payload = row[4]
    state = {
        "job_id": row[0],
        "lease_token": row[1] or "",
        "document_id": row[2],
        "version_id": row[3],
        "operation_key": str(payload.get("operation_key", "scan_promote")),
        "storage_bucket": payload.get("storage_bucket"),
        "storage_path": payload.get("storage_path"),
        "content_hash": payload.get("content_hash"),
        "byte_size": payload.get("byte_size"),
        "media_type": payload.get("media_type"),
        "destination_bucket": payload.get("destination_bucket"),
        "destination_path": payload.get("destination_path"),
        "reservation_id": payload.get("reservation_id"),
        "declared_category": payload.get("declared_category"),
        "attestation_policy_version": payload.get("attestation_policy_version"),
        "uploader_user_id": payload.get("uploader_user_id"),
        "review_approved": bool(payload.get("review_approved", False)),
        "content_class": str(payload.get("content_class", "synthetic")),
        "crash_after": None,
        "status": "scanning",
        "scan_result": None,
        "detail": "manual scan node",
    }
    config = {
        "configurable": {
            "postgres_url": postgres_url,
            "lease_owner": "manual-scan-node",
            "job_lease_seconds": 300,
            "storage_url": os.environ["SUPABASE_URL"],
            "storage_admin_secret": os.environ["SUPABASE_STORAGE_ADMIN_SECRET"],
            "clamav_host": os.environ.get("CLAMAV_HOST", "clamav"),
            "clamav_port": int(os.environ.get("CLAMAV_PORT", "3310")),
            "mock_model_mode": True,
        }
    }
    print("start_scan", flush=True)
    try:
        scanned = scan_and_govern(state, config)
        print(
            "scan_done",
            scanned.get("status"),
            scanned.get("scan_result"),
            scanned.get("detail"),
            flush=True,
        )
        promoted = promote_object(scanned, config)
        print(
            "promote_done",
            promoted.get("status"),
            promoted.get("detail"),
            flush=True,
        )
    except Exception:
        traceback.print_exc()
        raise


if __name__ == "__main__":
    main()
