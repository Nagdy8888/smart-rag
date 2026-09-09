"""Manifest-guarded cleanup for bake-off documents and optional private reports."""

from __future__ import annotations

from pathlib import Path
from uuid import UUID

import psycopg

from smart_rag_core.evaluation.parser_bakeoff.artifacts import run_dir
from smart_rag_core.evaluation.parser_bakeoff.constants import LANE_IDS, LaneId
from smart_rag_core.evaluation.parser_bakeoff.indexing import (
    assert_title_owned,
    lane_document_title,
)
from smart_rag_core.evaluation.parser_bakeoff.models import (
    BakeoffError,
    BakeoffManifest,
    CleanupReceipt,
    LaneIngestIds,
)
from smart_rag_core.ingestion.bm25_projection import Bm25ProjectionService
from smart_rag_core.retrieval.bm25_indexer import Bm25Indexer


def assert_manifest_hash(manifest: BakeoffManifest, expected: str) -> None:
    """Require an exact manifest hash confirmation.

    Args:
        manifest: Loaded run manifest.
        expected: Operator-supplied SHA-256.

    Raises:
        BakeoffError: When the hash is missing or mismatched.
    """

    recorded = manifest.manifest_sha256.strip().lower()
    provided = expected.strip().lower()
    if not recorded or not provided or recorded != provided:
        raise BakeoffError(
            "manifest_hash_mismatch", "cleanup requires the recorded manifest hash"
        )


def collect_listed_ids(
    lanes: tuple[LaneIngestIds, ...],
) -> tuple[frozenset[UUID], frozenset[UUID]]:
    """Collect manifest-listed document and version identifiers.

    Args:
        lanes: Per-lane ingest records.

    Returns:
        ``(document_ids, version_ids)``.
    """

    documents = frozenset(item.document_id for item in lanes)
    versions = frozenset(item.version_id for item in lanes)
    return documents, versions


def refuse_unlisted_targets(
    *,
    requested_document_ids: frozenset[UUID],
    requested_version_ids: frozenset[UUID],
    listed_document_ids: frozenset[UUID],
    listed_version_ids: frozenset[UUID],
) -> None:
    """Refuse any cleanup target that is not listed on the manifest.

    Args:
        requested_document_ids: IDs the operator asked to delete.
        requested_version_ids: Version IDs the operator asked to delete.
        listed_document_ids: IDs recorded for this run.
        listed_version_ids: Version IDs recorded for this run.

    Raises:
        BakeoffError: When a requested ID is outside the manifest list.
    """

    extra_docs = requested_document_ids - listed_document_ids
    extra_versions = requested_version_ids - listed_version_ids
    if extra_docs or extra_versions:
        raise BakeoffError(
            "cleanup_unlisted_id", "refusing to delete IDs outside the manifest"
        )


def cleanup_run(
    supabase: psycopg.Connection,
    parade: psycopg.Connection | None,
    *,
    repo: Path,
    manifest: BakeoffManifest,
    lanes: tuple[LaneIngestIds, ...],
    manifest_sha256: str,
    delete_private_reports: bool = False,
) -> CleanupReceipt:
    """Delete only manifest-listed bake-off documents and BM25 rows.

    Args:
        supabase: Privileged Supabase connection.
        parade: Optional ParadeDB writer used to drop BM25 projections.
        repo: Repository root.
        manifest: Run manifest.
        lanes: Ingest records for this run.
        manifest_sha256: Operator confirmation hash.
        delete_private_reports: When true, remove the private run directory.

    Returns:
        Count-only receipt.

    Raises:
        BakeoffError: On hash, title, or unlisted-ID failures.

    Side Effects:
        Deletes listed documents (cascade) and listed ParadeDB version rows.
        Optionally removes ``.private-eval/parser-bakeoff/<run-id>/``.
    """

    assert_manifest_hash(manifest, manifest_sha256)
    listed_docs, listed_versions = collect_listed_ids(lanes)
    refuse_unlisted_targets(
        requested_document_ids=listed_docs,
        requested_version_ids=listed_versions,
        listed_document_ids=listed_docs,
        listed_version_ids=listed_versions,
    )
    documents_deleted = 0
    versions_deleted = 0
    supabase.execute("SET ROLE postgres")
    for lane in lanes:
        expected_lane: LaneId = lane.lane_id
        if expected_lane not in LANE_IDS:
            raise BakeoffError("unknown_lane", "cleanup lane is not allow-listed")
        with supabase.cursor() as cursor:
            cursor.execute(
                "SELECT title FROM app.documents WHERE id = %s",
                (lane.document_id,),
            )
            row = cursor.fetchone()
        if row is None:
            continue
        assert_title_owned(
            title=str(row[0]), run_id=manifest.run_id, lane_id=expected_lane
        )
        if str(row[0]) != lane_document_title(manifest.run_id, expected_lane):
            raise BakeoffError("cleanup_title_mismatch", "title prefix mismatch")
        if parade is not None:
            parade.execute("SET ROLE paradedb_writer")
            Bm25ProjectionService(supabase, parade).process_delete_job(
                version_id=lane.version_id
            )
            parade.commit()
        with supabase.cursor() as cursor:
            cursor.execute(
                "DELETE FROM app.document_versions WHERE id = %s",
                (lane.version_id,),
            )
            versions_deleted += cursor.rowcount or 0
            cursor.execute(
                "DELETE FROM app.documents WHERE id = %s",
                (lane.document_id,),
            )
            documents_deleted += cursor.rowcount or 0
    supabase.commit()
    chunks_remaining = 0
    bm25_remaining = 0
    with supabase.cursor() as cursor:
        for lane in lanes:
            cursor.execute(
                "SELECT count(*) FROM app.document_chunks WHERE version_id = %s",
                (lane.version_id,),
            )
            count_row = cursor.fetchone()
            chunks_remaining += int(count_row[0]) if count_row is not None else 0
    if parade is not None:
        indexer = Bm25Indexer(parade)
        for lane in lanes:
            bm25_remaining += int(indexer.count_rows_for_version(lane.version_id))
    reports_deleted = False
    if delete_private_reports:
        destination = run_dir(repo, manifest.run_id)
        if destination.is_dir():
            _remove_tree(destination)
            reports_deleted = True
    if chunks_remaining or bm25_remaining:
        raise BakeoffError("cleanup_incomplete", "listed chunks or BM25 rows remain")
    return CleanupReceipt(
        run_id=manifest.run_id,
        manifest_sha256=manifest.manifest_sha256,
        documents_deleted=documents_deleted,
        versions_deleted=versions_deleted,
        chunks_remaining=chunks_remaining,
        bm25_rows_remaining=bm25_remaining,
        reports_deleted=reports_deleted,
        idempotent=True,
    )


def _remove_tree(path: Path) -> None:
    """Remove one private run directory.

    Args:
        path: Run directory under ``.private-eval``.

    Raises:
        BakeoffError: When the path is not a bake-off run directory.
    """

    if "parser-bakeoff" not in path.parts:
        raise BakeoffError("cleanup_path", "refusing to delete a non-bakeoff path")
    for child in sorted(path.rglob("*"), reverse=True):
        if child.is_file() or child.is_symlink():
            child.unlink()
        elif child.is_dir():
            child.rmdir()
    path.rmdir()
