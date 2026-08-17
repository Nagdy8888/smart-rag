"""Seed the approved open-split corpus and drive required public states."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

import psycopg

from smart_rag_core.evaluation.classes import QueryClass
from smart_rag_core.evaluation.holdout import HoldoutAccess
from smart_rag_core.evaluation.materialize import build_compact_source
from smart_rag_core.release.corpus import (
    CorpusManifest,
    CorpusSeedRow,
    approved_open_split_cases,
    seed_visibility,
)
from smart_rag_core.release.errors import RestrictedGraphIndexError
from smart_rag_core.release.hybrid import drive_hybrid_ready, parse_local_bytes
from smart_rag_core.release.io import sha256_text
from smart_rag_core.release.lifecycle import (
    drive_deletion_pending,
    drive_failed,
    drive_parsing,
    drive_scanning,
    drive_uploaded,
    drive_uploading,
    read_version_status,
)
from smart_rag_core.release.mapping import (
    assert_graph_index_rejected,
    drive_graph_ready,
    reject_restricted_lightrag_input,
)
from smart_rag_core.release.readiness import (
    ReadinessEvent,
    ReadinessExport,
    as_uuid_text,
    missing_required_states,
    reject_duplicate_readiness,
    reject_fake_readiness,
    utc_now_iso,
)
from smart_rag_core.settings import SharedSettings

_GRAPH_READY_CLASSES = frozenset({QueryClass.GRAPH_MAPPING, QueryClass.EXACT_CODE})


@dataclass(frozen=True, slots=True)
class SeedOutcome:
    """Seeded corpus, readiness export, and local counts for sizing.

    Attributes:
        corpus: Immutable corpus manifest.
        readiness: Public-state export.
        seeded_document_versions: Distinct version ids in the corpus rows.
        seeded_chunks: Canonical chunks persisted for labeled sources.
        seeded_graph_eligible_versions: Graph-eligible labeled versions.
        blockers: Honest failures that must not be recorded as fake success.
    """

    corpus: CorpusManifest
    readiness: ReadinessExport
    seeded_document_versions: int
    seeded_chunks: int
    seeded_graph_eligible_versions: int
    blockers: tuple[str, ...]


def _event(
    *,
    state: str,
    document_id: UUID | None,
    version_id: UUID | None,
    job_id: UUID | None = None,
    driver: str,
    bm25_verified: bool = False,
    maps_verified: bool = False,
) -> ReadinessEvent:
    """Build one readiness event at now-UTC."""

    event = ReadinessEvent(
        state=state,
        document_id=as_uuid_text(document_id),
        version_id=as_uuid_text(version_id),
        job_id=as_uuid_text(job_id),
        observed_at=utc_now_iso(datetime.now(tz=UTC)),
        driver=driver,
        bm25_verified=bm25_verified,
        maps_verified=maps_verified,
    )
    reject_fake_readiness(event)
    return event


def seed_candidate_corpus(
    *,
    supabase_url: str,
    parade_url: str,
    settings: SharedSettings | None = None,
) -> SeedOutcome:
    """Seed approved open-split sources and prove required public states.

    Args:
        supabase_url: Local Supabase Postgres URL.
        parade_url: ParadeDB writer URL reachable from this process.
        settings: Optional embedding settings. Defaults to mock-model mode.

    Returns:
        Seed outcome with manifests and local counts.

    Raises:
        UnapprovedCorpusError: If holdout or unapproved data is selected.
        RestrictedGraphIndexError: If restricted LightRAG indexing is attempted.
        FakeReadinessError: If a fake or duplicate readiness event is recorded.
        RuntimeError: If a required real driver fails.
    """

    resolved = (
        settings if settings is not None else SharedSettings(mock_model_mode=True)
    )
    cases = approved_open_split_cases(holdout_access=HoldoutAccess.denied())
    events: list[ReadinessEvent] = []
    rows: list[CorpusSeedRow] = []
    chunk_total = 0
    graph_eligible_count = 0
    deletion_version: UUID | None = None

    with psycopg.connect(supabase_url) as connection:
        _user_id, uploading_document, uploading_version = drive_uploading(connection)
        events.append(
            _event(
                state="uploading",
                document_id=uploading_document,
                version_id=uploading_version,
                driver="app.reserve_upload_quota",
            )
        )
        _user_id, uploaded_document, uploaded_version = drive_uploaded(connection)
        events.append(
            _event(
                state="uploaded",
                document_id=uploaded_document,
                version_id=uploaded_version,
                driver="app.finalize_quarantine_upload",
            )
        )
        scanning_document, scanning_version = drive_scanning(connection)
        events.append(
            _event(
                state="scanning",
                document_id=scanning_document,
                version_id=scanning_version,
                driver="app.transition_document_version_status",
            )
        )
        parsing_document, parsing_version = drive_parsing(connection)
        events.append(
            _event(
                state="parsing",
                document_id=parsing_document,
                version_id=parsing_version,
                driver="app.transition_document_version_status",
            )
        )
        failed_document, failed_version = drive_failed(connection)
        events.append(
            _event(
                state="failed",
                document_id=failed_document,
                version_id=failed_version,
                driver="app.transition_document_version_status",
            )
        )

    graph_ready_done = False
    restricted_rejected = False
    blockers: list[str] = []
    for case in cases:
        visibility = seed_visibility(case)
        graph_eligible = (
            visibility == "company_visible" and case.query_class in _GRAPH_READY_CLASSES
        )
        source = build_compact_source(case)
        parsed = parse_local_bytes(
            source.markdown_text.encode("utf-8"),
            filename=source.markdown_filename,
            format_key="markdown",
        )
        result = drive_hybrid_ready(
            supabase_url=supabase_url,
            parade_url=parade_url,
            parse_result=parsed,
            title=f"p09-{case.case_id}",
            filename=source.markdown_filename,
            settings=resolved,
            visibility=visibility,
            graph_eligible=graph_eligible,
        )
        if not result.hybrid_ready:
            raise RuntimeError(
                f"hybrid_ready failed for {case.case_id}: {result.status}"
            )
        chunk_total += result.chunk_count
        if graph_eligible:
            graph_eligible_count += 1
        hybrid = _event(
            state="hybrid_ready",
            document_id=result.document_id,
            version_id=result.version_id,
            job_id=result.bm25_job_id,
            driver="Bm25ProjectionService.process_upsert_job",
            bm25_verified=True,
        )
        reject_duplicate_readiness(events, hybrid)
        events.append(hybrid)
        if result.status == "graph_pending":
            pending = _event(
                state="graph_pending",
                document_id=result.document_id,
                version_id=result.version_id,
                job_id=result.bm25_job_id,
                driver="app.finalize_hybrid_ready/enqueue_graph_pending_handoff",
                bm25_verified=True,
            )
            reject_duplicate_readiness(events, pending)
            events.append(pending)
        elif result.status == "graph_ineligible":
            ineligible = _event(
                state="graph_ineligible",
                document_id=result.document_id,
                version_id=result.version_id,
                job_id=result.bm25_job_id,
                driver="app.finalize_hybrid_ready",
                bm25_verified=True,
            )
            reject_duplicate_readiness(events, ineligible)
            events.append(ineligible)

        if visibility == "restricted" and not restricted_rejected:
            try:
                reject_restricted_lightrag_input(
                    visibility=visibility,
                    graph_eligible=False,
                )
            except RestrictedGraphIndexError:
                pass
            else:
                raise RuntimeError("restricted LightRAG input was not rejected")
            with psycopg.connect(supabase_url) as connection:
                reason = assert_graph_index_rejected(
                    connection,
                    document_id=result.document_id,
                    version_id=result.version_id,
                )
                connection.rollback()
            if "restricted" not in reason.lower() and "graph" not in reason.lower():
                raise RuntimeError(f"unexpected graph-index rejection: {reason}")
            restricted_rejected = True

        if graph_eligible and result.status == "graph_pending" and not graph_ready_done:
            try:
                with psycopg.connect(supabase_url) as connection:
                    drive_graph_ready(
                        connection,
                        document_id=result.document_id,
                        version_id=result.version_id,
                        visibility=visibility,
                        graph_eligible=True,
                    )
                    connection.commit()
            except (RestrictedGraphIndexError, RuntimeError) as exc:
                blockers.append(f"graph_ready:{exc}")
            else:
                ready = _event(
                    state="graph_ready",
                    document_id=result.document_id,
                    version_id=result.version_id,
                    driver="GraphMappingService.map_after_vendor_success",
                    bm25_verified=True,
                    maps_verified=True,
                )
                reject_duplicate_readiness(events, ready)
                events.append(ready)
                graph_ready_done = True
                deletion_version = result.version_id

        if deletion_version is None and result.status in {
            "hybrid_ready",
            "graph_ineligible",
            "graph_pending",
        }:
            deletion_version = result.version_id

        rows.append(
            CorpusSeedRow(
                case_id=case.case_id,
                source_family_id=case.source_family_id,
                split=case.split.value,
                query_class=case.query_class.value,
                visibility=visibility,
                content_sha256=sha256_text(source.markdown_text),
                document_id=str(result.document_id),
                version_id=str(result.version_id),
                status=result.status,
            )
        )

    if not restricted_rejected:
        blockers.append("restricted_lightrag_rejection_not_observed")

    if deletion_version is not None:
        with psycopg.connect(supabase_url) as connection:
            drive_deletion_pending(connection, version_id=deletion_version)
            deletion_status = read_version_status(connection, deletion_version)
        events.append(
            _event(
                state=deletion_status,
                document_id=None,
                version_id=deletion_version,
                driver="app.exclude_version_from_retrieval",
            )
        )

    export = ReadinessExport(
        events=tuple(events),
        missing_states=missing_required_states(events),
    )
    if export.missing_states:
        blockers.append("missing_states:" + ",".join(export.missing_states))
    manifest = CorpusManifest(rows=tuple(rows))
    return SeedOutcome(
        corpus=manifest,
        readiness=export,
        seeded_document_versions=len(
            {row.version_id for row in rows if row.version_id}
        ),
        seeded_chunks=chunk_total,
        seeded_graph_eligible_versions=graph_eligible_count,
        blockers=tuple(blockers),
    )
