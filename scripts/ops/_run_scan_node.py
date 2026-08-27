"""Run scan_and_govern against the demo job payload inside the worker."""

from __future__ import annotations

import os
import traceback
from typing import Any, cast
from uuid import UUID

import psycopg
from langchain_core.runnables import RunnableConfig
from smart_rag_agents.ingestion.scan_graph import (
    IngestionScanState,
    promote_object,
    scan_and_govern,
)

JOB_ID = UUID("681cc466-9216-442a-ac7a-189328660316")


def _optional_str(payload: dict[str, object], key: str) -> str | None:
    """Return a string field when present.

    Args:
        payload: Job payload mapping.
        key: Field name.

    Returns:
        String value or ``None``.
    """

    value = payload.get(key)
    if value is None:
        return None
    return str(value)


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
    payload: object = row[4]
    payload_map = cast(dict[str, object], payload) if isinstance(payload, dict) else {}
    byte_size_raw = payload_map.get("byte_size")
    byte_size = (
        byte_size_raw
        if isinstance(byte_size_raw, int) and not isinstance(byte_size_raw, bool)
        else None
    )
    state: IngestionScanState = {
        "job_id": str(row[0]),
        "lease_token": str(row[1] or ""),
        "document_id": str(row[2]) if row[2] is not None else None,
        "version_id": str(row[3]) if row[3] is not None else None,
        "operation_key": str(payload_map.get("operation_key", "scan_promote")),
        "storage_bucket": _optional_str(payload_map, "storage_bucket"),
        "storage_path": _optional_str(payload_map, "storage_path"),
        "content_hash": _optional_str(payload_map, "content_hash"),
        "byte_size": byte_size,
        "media_type": _optional_str(payload_map, "media_type"),
        "destination_bucket": _optional_str(payload_map, "destination_bucket"),
        "destination_path": _optional_str(payload_map, "destination_path"),
        "reservation_id": _optional_str(payload_map, "reservation_id"),
        "declared_category": _optional_str(payload_map, "declared_category"),
        "attestation_policy_version": _optional_str(
            payload_map, "attestation_policy_version"
        ),
        "uploader_user_id": _optional_str(payload_map, "uploader_user_id"),
        "review_approved": payload_map.get("review_approved") is True,
        "content_class": str(payload_map.get("content_class", "synthetic")),
        "crash_after": None,
        "status": "scanning",
        "scan_result": None,
        "detail": "manual scan node",
    }
    configurable: dict[str, Any] = {
        "postgres_url": postgres_url,
        "lease_owner": "manual-scan-node",
        "job_lease_seconds": 300,
        "storage_url": os.environ["SUPABASE_URL"],
        "storage_admin_secret": os.environ["SUPABASE_STORAGE_ADMIN_SECRET"],
        "clamav_host": os.environ.get("CLAMAV_HOST", "clamav"),
        "clamav_port": int(os.environ.get("CLAMAV_PORT", "3310")),
        "mock_model_mode": True,
    }
    config: RunnableConfig = {"configurable": configurable}
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
