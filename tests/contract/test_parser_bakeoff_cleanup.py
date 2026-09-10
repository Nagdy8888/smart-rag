"""Contract tests for manifest-guarded bake-off cleanup."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from smart_rag_core.evaluation.parser_bakeoff.cleanup import (
    assert_manifest_hash,
    collect_listed_ids,
    refuse_unlisted_targets,
)
from smart_rag_core.evaluation.parser_bakeoff.models import (
    BakeoffError,
    BakeoffManifest,
    BakeoffScanEvidence,
    LaneIdentity,
    LaneIngestIds,
    RunStage,
)


def _manifest(digest: str) -> BakeoffManifest:
    """Build a minimal manifest.

    Args:
        digest: Manifest hash to stamp.

    Returns:
        Manifest model.
    """

    return BakeoffManifest(
        run_id="20260909T010000Z-abcdef123456",
        source_basename="book.pdf",
        source_sha256="ab" * 32,
        source_bytes=12,
        source_pages=2,
        scan=BakeoffScanEvidence(
            disposition="clean",
            engine_version="1",
            signature_version="1",
            bytes_examined=12,
        ),
        lanes=(
            LaneIdentity(
                lane_id="current",
                parser_version="parser_v1",
                cleaning_version="cleaning_v1",
                locator_available=True,
            ),
            LaneIdentity(
                lane_id="anydoc_local",
                parser_version="anydoc_pdf_0_2_4_local",
                cleaning_version="anydoc_markdown_0_2_4",
                locator_available=False,
            ),
        ),
        stage=RunStage.REPORTED,
        command_version="parser_bakeoff_cli_v1",
        created_at=datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ"),
        manifest_sha256=digest,
    )


def test_cleanup_refuses_hash_mismatch_and_unlisted_ids() -> None:
    """Cleanup cannot delete data outside the confirmed manifest list."""

    digest = "c" * 64
    manifest = _manifest(digest)
    with pytest.raises(BakeoffError) as err:
        assert_manifest_hash(manifest, "d" * 64)
    assert err.value.code == "manifest_hash_mismatch"
    assert_manifest_hash(manifest, digest)
    current = LaneIngestIds(
        lane_id="current",
        document_id=uuid4(),
        version_id=uuid4(),
        title="parser-bakeoff:20260909T010000Z-abcdef123456:current",
    )
    anydoc = LaneIngestIds(
        lane_id="anydoc_local",
        document_id=uuid4(),
        version_id=uuid4(),
        title="parser-bakeoff:20260909T010000Z-abcdef123456:anydoc_local",
    )
    listed_docs, listed_versions = collect_listed_ids((current, anydoc))
    refuse_unlisted_targets(
        requested_document_ids=listed_docs,
        requested_version_ids=listed_versions,
        listed_document_ids=listed_docs,
        listed_version_ids=listed_versions,
    )
    with pytest.raises(BakeoffError) as extra_docs:
        refuse_unlisted_targets(
            requested_document_ids=listed_docs | {uuid4()},
            requested_version_ids=listed_versions,
            listed_document_ids=listed_docs,
            listed_version_ids=listed_versions,
        )
    assert extra_docs.value.code == "cleanup_unlisted_id"
    with pytest.raises(BakeoffError) as extra_versions:
        refuse_unlisted_targets(
            requested_document_ids=listed_docs,
            requested_version_ids=listed_versions | {uuid4()},
            listed_document_ids=listed_docs,
            listed_version_ids=listed_versions,
        )
    assert extra_versions.value.code == "cleanup_unlisted_id"
