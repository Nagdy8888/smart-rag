"""Idempotent hybrid-index enqueue used by scan and crawl completion."""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID

import psycopg

from smart_rag_core.jobs.ingestion_repository import IngestionJobRepository
from smart_rag_core.schema.tables import IngestionJobRecord

HYBRID_INDEX_JOB_KIND = "hybrid_index"
DEFAULT_HYBRID_INDEX_COST_USD = Decimal("0.05")


def hybrid_index_idempotency_key(version_id: UUID) -> str:
    """Return the stable enqueue key for one document version.

    Args:
        version_id: Canonical version that hybrid indexing will parse.

    Returns:
        Idempotency key ``hybrid_index:{version_id}``. Replay returns the same job.
    """

    return f"hybrid_index:{version_id}"


def enqueue_hybrid_index_job(
    connection: psycopg.Connection,
    *,
    document_id: UUID,
    version_id: UUID,
    payload_ref: dict[str, Any],
    estimated_size_bytes: int = 0,
    estimated_cost_usd: Decimal = DEFAULT_HYBRID_INDEX_COST_USD,
    lease_owner: str = "pipeline-chaining",
    lease_seconds: int = 300,
) -> IngestionJobRecord:
    """Enqueue one ``hybrid_index`` job for a version, or return the existing row.

    Args:
        connection: Worker-role Postgres connection.
        document_id: Canonical document identifier.
        version_id: Canonical version identifier.
        payload_ref: Durable Storage refs, hashes, attestation, and optional
            ``crawl_run_id``. Must not contain raw bytes or secrets.
        estimated_size_bytes: Declared byte estimate for admission/ordering.
        estimated_cost_usd: Estimated embedding spend reserved at enqueue.
        lease_owner: Repository lease owner label (unused for insert).
        lease_seconds: Repository lease duration (unused for insert).

    Returns:
        Existing or newly inserted ``hybrid_index`` job.

    Side Effects:
        Inserts at most one ``app.ingestion_jobs`` row per version. Duplicate
        calls return the same row without a second budget reservation after the
        first successful insert (repository short-circuits on idempotency key).
    """

    payload = dict(payload_ref)
    payload.setdefault("operation_key", hybrid_index_idempotency_key(version_id))
    repository = IngestionJobRepository(
        connection,
        lease_owner=lease_owner,
        lease_seconds=lease_seconds,
    )
    return repository.enqueue(
        idempotency_key=hybrid_index_idempotency_key(version_id),
        job_kind=HYBRID_INDEX_JOB_KIND,
        document_id=document_id,
        version_id=version_id,
        payload_ref=payload,
        estimated_size_bytes=estimated_size_bytes,
        estimated_cost_usd=estimated_cost_usd,
    )
