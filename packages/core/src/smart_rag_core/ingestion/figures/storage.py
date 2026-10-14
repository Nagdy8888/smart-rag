"""Private Storage paths for figure PNGs."""

from __future__ import annotations

import hashlib
from uuid import UUID

from smart_rag_core.gateways.storage import StorageGateway, StorageGatewayError
from smart_rag_core.ingestion.figures.limits import FIGURE_ARTIFACT_BUCKET


def figure_storage_path(*, document_id: UUID, version_id: UUID, figure_id: str) -> str:
    """Build the canonical object key for one figure PNG.

    Args:
        document_id: Canonical document identifier.
        version_id: Immutable version identifier.
        figure_id: Stable figure identifier. Path separators are stripped.

    Returns:
        Object key under ``figure-artifacts``.
    """

    safe = "".join(char for char in figure_id if char.isalnum())[:64] or "figure"
    return f"documents/{document_id}/versions/{version_id}/figures/{safe}.png"


def upload_figure_png(
    gateway: StorageGateway,
    *,
    document_id: UUID,
    version_id: UUID,
    figure_id: str,
    png: bytes,
) -> tuple[str, str]:
    """Upload one PNG and verify its hash.

    Args:
        gateway: Privileged Storage gateway.
        document_id: Canonical document identifier.
        version_id: Immutable version identifier.
        figure_id: Stable figure identifier.
        png: PNG bytes.

    Returns:
        Object path and SHA-256 hex digest.

    Raises:
        StorageGatewayError: When upload and verification both fail.

    Idempotency:
        A prior identical object is treated as success.
    """

    digest = hashlib.sha256(png).hexdigest()
    path = figure_storage_path(
        document_id=document_id, version_id=version_id, figure_id=figure_id
    )
    try:
        gateway.upload_object(
            bucket=FIGURE_ARTIFACT_BUCKET,
            object_path=path,
            data=png,
            content_type="image/png",
        )
    except StorageGatewayError:
        gateway.verify_object(
            bucket=FIGURE_ARTIFACT_BUCKET,
            object_path=path,
            expected_hash=digest,
            expected_bytes=len(png),
        )
        return path, digest
    gateway.verify_object(
        bucket=FIGURE_ARTIFACT_BUCKET,
        object_path=path,
        expected_hash=digest,
        expected_bytes=len(png),
    )
    return path, digest
