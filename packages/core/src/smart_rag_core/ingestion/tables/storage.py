"""Private Storage paths for table artifacts."""

from __future__ import annotations

from uuid import UUID

from smart_rag_core.gateways.storage import StorageGateway
from smart_rag_core.ingestion.tables.limits import TABLE_ARTIFACT_BUCKET


def table_artifact_storage_path(
    *,
    document_id: UUID,
    version_id: UUID,
    sheet_name: str,
    filename: str,
) -> str:
    """Build the canonical Storage path for one table artifact.

    Args:
        document_id: Canonical document identifier.
        version_id: Immutable version identifier.
        sheet_name: Sanitized sheet/table segment.
        filename: Safe Parquet filename.

    Returns:
        Object key under ``table-artifacts``.
    """

    return (
        f"documents/{document_id}/versions/{version_id}/tables/"
        f"{sheet_name}/{filename}"
    )


def upload_table_artifact(
    gateway: StorageGateway,
    *,
    document_id: UUID,
    version_id: UUID,
    sheet_name: str,
    filename: str,
    parquet_bytes: bytes,
    expected_hash: str,
) -> str:
    """Upload one Parquet artifact and verify hash linkage.

    Args:
        gateway: Privileged Storage gateway.
        document_id: Canonical document identifier.
        version_id: Immutable version identifier.
        sheet_name: Sanitized sheet/table segment.
        filename: Safe Parquet filename.
        parquet_bytes: Exact Parquet payload.
        expected_hash: Lowercase SHA-256 digest of ``parquet_bytes``.

    Returns:
        Stored object path.

    Raises:
        StorageGatewayError: When upload or verification fails.
    """

    path = table_artifact_storage_path(
        document_id=document_id,
        version_id=version_id,
        sheet_name=sheet_name,
        filename=filename,
    )
    gateway.upload_object(
        bucket=TABLE_ARTIFACT_BUCKET,
        object_path=path,
        data=parquet_bytes,
        content_type="application/vnd.apache.parquet",
    )
    gateway.verify_object(
        bucket=TABLE_ARTIFACT_BUCKET,
        object_path=path,
        expected_hash=expected_hash,
        expected_bytes=len(parquet_bytes),
    )
    return path


def table_artifact_bucket() -> str:
    """Return the private bucket id for table artifacts."""

    return TABLE_ARTIFACT_BUCKET
