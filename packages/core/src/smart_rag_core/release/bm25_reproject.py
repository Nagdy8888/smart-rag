"""Re-project Packet 2 BM25 rows without changing document or version ids.

Packet 3 overlay recreate emptied ParadeDB. Packet 4 fills the derived index
through existing ``Bm25ProjectionService.process_upsert_job`` (or upsert plus
verify when finalize would destroy ``graph_ready``). Hybrid Ready is never
SQL-stamped.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from uuid import UUID, uuid4

import psycopg
from psycopg.rows import dict_row

from smart_rag_core.ingestion.bm25_projection import Bm25ProjectionService
from smart_rag_core.ingestion.limits import DEFAULT_BM25_UPSERT_BATCH_SIZE
from smart_rag_core.release.hybrid import mark_bm25_job_processing
from smart_rag_core.release.io import as_json_list, as_json_object

REPROJECT_SCHEMA_VERSION = "phase09-candidate-packet4-bm25-v1"
_WORKER_OUTPUT = Path("/tmp/phase09/candidate-packet4-bm25.json")  # noqa: S108

ReprojectDriver = Literal[
    "Bm25ProjectionService.process_upsert_job",
    "Bm25ProjectionService.upsert_verify_without_finalize",
    "skipped",
]

_REPROJECT_STATUSES = frozenset({"hybrid_ready", "graph_ineligible", "graph_pending"})
_SKIP_STATUSES = frozenset(
    {
        "uploading",
        "uploaded",
        "scanning",
        "parsing",
        "failed",
        "deletion_pending",
    }
)


@dataclass(frozen=True, slots=True)
class ReprojectVersionResult:
    """Outcome of one Packet 2 version BM25 re-projection.

    Attributes:
        case_id: Corpus case id when provided.
        document_id: Canonical document id (must match the corpus).
        version_id: Canonical version id (must match the corpus).
        status_before: Public version status before the driver.
        status_after: Public version status after the driver.
        skipped: True when finalize would be unsafe or chunks are absent.
        driver: Existing projection driver, or ``skipped``.
        passed: True when ParadeDB verify succeeded or skip was intentional.
        job_id: Outbox job when ``process_upsert_job`` ran.
        parade_row_count: Projection rows after the driver.
        detail: Bounded reason.
    """

    case_id: str | None
    document_id: UUID
    version_id: UUID
    status_before: str
    status_after: str
    skipped: bool
    driver: ReprojectDriver
    passed: bool
    job_id: UUID | None
    parade_row_count: int
    detail: str


@dataclass(frozen=True, slots=True)
class ReprojectOutcome:
    """Aggregate Packet 2 BM25 re-projection.

    Attributes:
        results: Per-version outcomes.
        identity_drift: True when any document or version id changed.
        passed: True when every required version projected or was skipped safely.
        parade_total_rows: ``bm25_chunks`` count after the run.
        sample_is_eight_doc_subset: Always true for this candidate.
    """

    results: tuple[ReprojectVersionResult, ...]
    identity_drift: bool
    passed: bool
    parade_total_rows: int
    sample_is_eight_doc_subset: bool = True


def _version_row(
    supabase: psycopg.Connection, version_id: UUID
) -> dict[str, object] | None:
    """Load one version row as postgres.

    Args:
        supabase: Open connection.
        version_id: Canonical version.

    Returns:
        Mapping or ``None`` when missing.
    """

    supabase.execute("SET ROLE postgres")
    with supabase.cursor(row_factory=dict_row) as cursor:
        cursor.execute(
            """
            SELECT
              id,
              document_id,
              status,
              chunk_set_hash,
              deleted_at
            FROM app.document_versions
            WHERE id = %s
            """,
            (version_id,),
        )
        row = cursor.fetchone()
    if row is None:
        return None
    return dict(row)


def _complete_job(supabase: psycopg.Connection, job_id: UUID) -> None:
    """Mark a processing BM25 outbox row completed after verify.

    Args:
        supabase: Open connection.
        job_id: Outbox identifier.

    Side Effects:
        Updates ``app.bm25_index_jobs.status``. Caller commits.
    """

    supabase.execute("SET ROLE postgres")
    with supabase.cursor() as cursor:
        cursor.execute(
            """
            UPDATE app.bm25_index_jobs
            SET
              status = 'completed'::app.job_status,
              lease_owner = NULL,
              lease_token = NULL,
              lease_expires_at = NULL,
              updated_at = timezone('utc', now())
            WHERE id = %s
            """,
            (job_id,),
        )


def _enqueue_unique_upsert(
    supabase: psycopg.Connection,
    *,
    version_id: UUID,
    chunk_set_hash: str,
) -> UUID:
    """Enqueue a unique BM25 upsert so the completed seed job is not reused.

    Args:
        supabase: Worker-capable connection.
        version_id: Canonical version.
        chunk_set_hash: Version chunk-set hash.

    Returns:
        New or existing outbox job id.

    Raises:
        RuntimeError: If the enqueue RPC returns no id.

    Side Effects:
        Inserts ``app.bm25_index_jobs``.
    """

    supabase.execute("SET ROLE app_worker")
    operation_key = f"phase09-p4-reproject:{version_id}:{uuid4()}"
    with supabase.cursor() as cursor:
        cursor.execute(
            """
            SELECT app.enqueue_bm25_projection_for_version(%s, %s, %s)
            """,
            (version_id, chunk_set_hash, operation_key),
        )
        row = cursor.fetchone()
    if row is None or row[0] is None:
        raise RuntimeError("enqueue_bm25_projection_for_version returned null")
    return UUID(str(row[0]))


def _upsert_without_finalize(service: Bm25ProjectionService, version_id: UUID) -> bool:
    """Write ParadeDB rows and verify without calling ``finalize_hybrid_ready``.

    Used only when the version is already ``graph_ready`` so Packet 2 mapping
    state is not reset to ``hybrid_ready``.

    Args:
        service: Bound projection service.
        version_id: Canonical version.

    Returns:
        True when ParadeDB verify passed.

    Side Effects:
        Upserts derived BM25 rows and commits ParadeDB.
    """

    service._indexer.ensure_projection_schema()  # pyright: ignore[reportPrivateUsage]
    rows = service._load_projection_rows(  # pyright: ignore[reportPrivateUsage]
        version_id
    )
    for offset in range(0, len(rows), DEFAULT_BM25_UPSERT_BATCH_SIZE):
        batch = tuple(rows[offset : offset + DEFAULT_BM25_UPSERT_BATCH_SIZE])
        service._indexer.upsert_batch(batch)  # pyright: ignore[reportPrivateUsage]
    service._parade.commit()  # pyright: ignore[reportPrivateUsage]
    return bool(
        service._verifier.verify_version(version_id).passed  # pyright: ignore[reportPrivateUsage]
    )


def _parade_count(parade: psycopg.Connection, version_id: UUID | None = None) -> int:
    """Count derived BM25 rows.

    Args:
        parade: ParadeDB connection.
        version_id: Optional version filter.

    Returns:
        Row count.
    """

    with parade.cursor() as cursor:
        if version_id is None:
            cursor.execute("SELECT count(*) FROM bm25_chunks")
        else:
            cursor.execute(
                "SELECT count(*) FROM bm25_chunks WHERE version_id = %s",
                (version_id,),
            )
        row = cursor.fetchone()
    return int(row[0]) if row is not None else 0


def reproject_one_version(
    supabase: psycopg.Connection,
    parade: psycopg.Connection,
    *,
    document_id: UUID,
    version_id: UUID,
    case_id: str | None = None,
) -> ReprojectVersionResult:
    """Re-project one Packet 2 version through the existing BM25 driver.

    Args:
        supabase: Open Supabase connection.
        parade: Open ParadeDB writer connection.
        document_id: Expected corpus document id.
        version_id: Expected corpus version id.
        case_id: Optional corpus case id.

    Returns:
        Per-version outcome. Document and version ids are never rewritten.

    Side Effects:
        May insert an outbox job, upsert ParadeDB rows, and call
        ``finalize_hybrid_ready`` for non-``graph_ready`` versions.
    """

    row = _version_row(supabase, version_id)
    if row is None:
        return ReprojectVersionResult(
            case_id=case_id,
            document_id=document_id,
            version_id=version_id,
            status_before="missing",
            status_after="missing",
            skipped=True,
            driver="skipped",
            passed=False,
            job_id=None,
            parade_row_count=0,
            detail="version_missing",
        )
    actual_document = UUID(str(row["document_id"]))
    status_before = str(row["status"])
    if actual_document != document_id:
        return ReprojectVersionResult(
            case_id=case_id,
            document_id=actual_document,
            version_id=version_id,
            status_before=status_before,
            status_after=status_before,
            skipped=True,
            driver="skipped",
            passed=False,
            job_id=None,
            parade_row_count=0,
            detail="document_id_drift",
        )
    if row["deleted_at"] is not None or status_before in _SKIP_STATUSES:
        return ReprojectVersionResult(
            case_id=case_id,
            document_id=document_id,
            version_id=version_id,
            status_before=status_before,
            status_after=status_before,
            skipped=True,
            driver="skipped",
            passed=True,
            job_id=None,
            parade_row_count=0,
            detail="skip_deleted_or_pre_hybrid_status",
        )
    chunk_set_hash = row["chunk_set_hash"]
    if not isinstance(chunk_set_hash, str) or chunk_set_hash == "":
        return ReprojectVersionResult(
            case_id=case_id,
            document_id=document_id,
            version_id=version_id,
            status_before=status_before,
            status_after=status_before,
            skipped=True,
            driver="skipped",
            passed=False,
            job_id=None,
            parade_row_count=0,
            detail="chunk_set_hash_missing",
        )
    parade.execute("SET ROLE paradedb_writer")
    service = Bm25ProjectionService(supabase, parade)
    job_id: UUID | None = None
    driver: ReprojectDriver
    passed = False
    detail = ""
    if status_before == "graph_ready":
        driver = "Bm25ProjectionService.upsert_verify_without_finalize"
        passed = _upsert_without_finalize(service, version_id)
        detail = "finalize_skipped_to_preserve_graph_ready"
    elif status_before in _REPROJECT_STATUSES:
        driver = "Bm25ProjectionService.process_upsert_job"
        job_id = _enqueue_unique_upsert(
            supabase, version_id=version_id, chunk_set_hash=chunk_set_hash
        )
        supabase.execute("SET ROLE app_worker")
        mark_bm25_job_processing(supabase, job_id)
        supabase.commit()
        passed = service.process_upsert_job(version_id=version_id, job_id=job_id)
        if passed:
            supabase.commit()
            parade.commit()
            _complete_job(supabase, job_id)
            supabase.commit()
        else:
            supabase.rollback()
            parade.rollback()
            detail = "process_upsert_job_verify_failed"
    else:
        driver = "skipped"
        return ReprojectVersionResult(
            case_id=case_id,
            document_id=document_id,
            version_id=version_id,
            status_before=status_before,
            status_after=status_before,
            skipped=True,
            driver="skipped",
            passed=True,
            job_id=None,
            parade_row_count=0,
            detail=f"unhandled_status:{status_before}",
        )
    after = _version_row(supabase, version_id)
    status_after = str(after["status"]) if after is not None else "missing"
    after_document = (
        UUID(str(after["document_id"])) if after is not None else document_id
    )
    identity_ok = after_document == document_id and (
        after is not None and UUID(str(after["id"])) == version_id
    )
    parade_rows = _parade_count(parade, version_id)
    return ReprojectVersionResult(
        case_id=case_id,
        document_id=after_document,
        version_id=version_id,
        status_before=status_before,
        status_after=status_after,
        skipped=False,
        driver=driver,
        passed=passed and identity_ok,
        job_id=job_id,
        parade_row_count=parade_rows,
        detail=detail if identity_ok else "identity_drift",
    )


def reproject_corpus_rows(
    *,
    supabase_url: str,
    parade_url: str,
    rows: tuple[tuple[str | None, UUID, UUID], ...],
) -> ReprojectOutcome:
    """Re-project every Packet 2 corpus version through the existing driver.

    Args:
        supabase_url: Postgres URL reachable from this process.
        parade_url: ParadeDB writer URL reachable from this process.
        rows: ``(case_id, document_id, version_id)`` triples from the Packet 2
            corpus manifest.

    Returns:
        Aggregate outcome. ``sample_is_eight_doc_subset`` stays true.

    Side Effects:
        Writes derived ParadeDB rows. Does not change document or version ids.
    """

    results: list[ReprojectVersionResult] = []
    with (
        psycopg.connect(supabase_url) as supabase,
        psycopg.connect(parade_url, connect_timeout=8) as parade,
    ):
        for case_id, document_id, version_id in rows:
            results.append(
                reproject_one_version(
                    supabase,
                    parade,
                    document_id=document_id,
                    version_id=version_id,
                    case_id=case_id,
                )
            )
        parade_total = _parade_count(parade)
    identity_drift = any(item.detail == "identity_drift" for item in results)
    required_failed = any(
        not item.passed and not item.skipped for item in results
    ) or any(item.detail == "document_id_drift" for item in results)
    return ReprojectOutcome(
        results=tuple(results),
        identity_drift=identity_drift,
        passed=not identity_drift and not required_failed,
        parade_total_rows=parade_total,
        sample_is_eight_doc_subset=True,
    )


def outcome_payload(outcome: ReprojectOutcome) -> dict[str, object]:
    """Serialize a re-projection outcome without secrets.

    Args:
        outcome: Aggregate result.

    Returns:
        JSON object.
    """

    return {
        "schema_version": REPROJECT_SCHEMA_VERSION,
        "identity_drift": outcome.identity_drift,
        "passed": outcome.passed,
        "parade_total_rows": outcome.parade_total_rows,
        "sample_is_eight_doc_subset": outcome.sample_is_eight_doc_subset,
        "sql_stamped_hybrid_or_graph_ready": False,
        "versions": [
            {
                "case_id": item.case_id,
                "document_id": str(item.document_id),
                "version_id": str(item.version_id),
                "status_before": item.status_before,
                "status_after": item.status_after,
                "skipped": item.skipped,
                "driver": item.driver,
                "passed": item.passed,
                "job_id": str(item.job_id) if item.job_id is not None else None,
                "parade_row_count": item.parade_row_count,
                "detail": item.detail,
            }
            for item in outcome.results
        ],
    }


def parse_corpus_rows(raw: str) -> tuple[tuple[str | None, UUID, UUID], ...]:
    """Parse Packet 2 corpus JSON into case/document/version triples.

    Args:
        raw: Corpus manifest or ``{"rows": [...]}`` JSON.

    Returns:
        Ordered triples. Document and version ids are not rewritten.

    Raises:
        ValueError: If the payload is not an object with id rows.
    """

    loaded: object = json.loads(raw)
    payload = as_json_object(loaded, source="reproject-stdin")
    rows = as_json_list(payload.get("rows"), source="reproject-stdin.rows")
    triples: list[tuple[str | None, UUID, UUID]] = []
    for item in rows:
        row = as_json_object(item, source="reproject-stdin.rows[]")
        case_id = row.get("case_id")
        document_id = row.get("document_id")
        version_id = row.get("version_id")
        if not isinstance(document_id, str) or not isinstance(version_id, str):
            raise ValueError("corpus row missing document_id or version_id")
        triples.append(
            (
                case_id if isinstance(case_id, str) else None,
                UUID(document_id),
                UUID(version_id),
            )
        )
    return tuple(triples)


def authorized_current_rows(
    supabase: psycopg.Connection,
) -> tuple[tuple[str | None, UUID, UUID], ...]:
    """Load every authorized current version that may hold BM25 projection rows.

    Args:
        supabase: Open canonical connection.

    Returns:
        ``(None, document_id, version_id)`` triples. ``deletion_pending`` and
        deleted rows are excluded. Document and version ids are not rewritten.
    """

    statuses = tuple(sorted(_REPROJECT_STATUSES | {"graph_ready"}))
    with supabase.cursor() as cursor:
        cursor.execute(
            """
            SELECT document_id::text, id::text
            FROM app.document_versions
            WHERE deleted_at IS NULL
              AND status::text = ANY(%s)
            ORDER BY id
            """,
            (list(statuses),),
        )
        return tuple(
            (None, UUID(str(row[0])), UUID(str(row[1]))) for row in cursor.fetchall()
        )


def run_reproject_cli(
    *,
    supabase_url: str,
    parade_url: str,
    corpus_json: str,
    output: Path,
) -> int:
    """Re-project stdin corpus rows or authorized current versions.

    Args:
        supabase_url: Postgres URL reachable from this process.
        parade_url: ParadeDB writer URL reachable from this process.
        corpus_json: Packet 2 corpus manifest JSON, or
            ``{"rebuild_scope":"authorized_current"}``.
        output: Destination path, typically worker ``/tmp/phase09``.

    Returns:
        ``0`` when identity held and required versions projected.

    Side Effects:
        Writes ``output``. Does not change document or version ids.
    """

    loaded: object = json.loads(corpus_json)
    request = as_json_object(loaded, source="reproject-stdin")
    rebuild_scope = request.get("rebuild_scope")
    if rebuild_scope == "authorized_current":
        with psycopg.connect(supabase_url) as supabase:
            triples = authorized_current_rows(supabase)
    else:
        triples = parse_corpus_rows(corpus_json)
    outcome = reproject_corpus_rows(
        supabase_url=supabase_url,
        parade_url=parade_url,
        rows=triples,
    )
    payload = outcome_payload(outcome)
    if rebuild_scope == "authorized_current":
        payload["rebuild_scope"] = "authorized_current"
        payload["sample_is_eight_doc_subset"] = False
        payload["version_count"] = len(outcome.results)
        payload.pop("versions", None)
    else:
        payload["rebuild_scope"] = "packet2_corpus"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    sys.stdout.write(json.dumps(payload, sort_keys=True) + "\n")
    return 0 if outcome.passed and not outcome.identity_drift else 1


def main() -> int:
    """CLI entry used inside the frozen worker via ``/tmp`` injection.

    Returns:
        Process exit code.

    Raises:
        SystemExit: When required environment variables are missing.
    """

    supabase_url = os.environ.get("SUPABASE_DB_URL")
    parade_url = os.environ.get("PARADEDB_URL")
    if not supabase_url or not parade_url:
        sys.stderr.write("SUPABASE_DB_URL and PARADEDB_URL are required\n")
        return 2
    corpus_json = sys.stdin.read()
    if not corpus_json.strip():
        sys.stderr.write("reproject requires corpus JSON on stdin\n")
        return 2
    return run_reproject_cli(
        supabase_url=supabase_url,
        parade_url=parade_url,
        corpus_json=corpus_json,
        output=_WORKER_OUTPUT,
    )


if __name__ == "__main__":
    raise SystemExit(main())
