"""Offline parse, chunk, and gold-mapping pipeline for one bake-off run."""

from __future__ import annotations

from pathlib import Path
from uuid import UUID, uuid4

from smart_rag_core.evaluation.parser_bakeoff.artifacts import (
    lane_dir,
    load_manifest,
    read_model,
    save_manifest,
    write_json_atomic,
)
from smart_rag_core.evaluation.parser_bakeoff.constants import (
    AGENT_REPORT_NAME,
    ANYDOC_LANE,
    CHUNK_SUMMARY_NAME,
    CURRENT_LANE,
    GOLD_MAP_NAME,
    INGEST_IDS_NAME,
    MAPPING_REVIEW_NAME,
    PARSE_RESULT_NAME,
    RETRIEVAL_REPORT_NAME,
    LaneId,
)
from smart_rag_core.evaluation.parser_bakeoff.indexing import lane_document_title
from smart_rag_core.evaluation.parser_bakeoff.lanes import (
    LaneParseRequest,
    MarkdownConverter,
    parse_lane,
)
from smart_rag_core.evaluation.parser_bakeoff.mapping import (
    apply_review,
    map_facts_to_chunks,
    review_pending_count,
)
from smart_rag_core.evaluation.parser_bakeoff.models import (
    BakeoffError,
    BakeoffManifest,
    ChunkSummary,
    GoldMap,
    LaneIdentity,
    LaneIngestIds,
    MappingStatus,
    NeutralCaseSet,
    RunStage,
)
from smart_rag_core.evaluation.parser_bakeoff.summaries import (
    replay_matches,
    summarize_parse_chunk,
)
from smart_rag_core.ingestion.chunking.service import chunk_parse_result
from smart_rag_core.ingestion.parser.types import (
    ParseDisposition,
    ParseResult,
    PdfLocator,
)


def parse_result_path(repo: Path, run_id: str, lane_id: LaneId) -> Path:
    """Return the parse-result artifact path.

    Args:
        repo: Repository root.
        run_id: Run identifier.
        lane_id: Lane token.

    Returns:
        JSON path.
    """

    return lane_dir(repo, run_id, lane_id) / PARSE_RESULT_NAME


def load_parse_result(repo: Path, run_id: str, lane_id: LaneId) -> ParseResult:
    """Load a stored parse result.

    Args:
        repo: Repository root.
        run_id: Run identifier.
        lane_id: Lane token.

    Returns:
        Closed parse result.
    """

    return read_model(parse_result_path(repo, run_id, lane_id), ParseResult)


def load_ingest_ids(repo: Path, run_id: str, lane_id: LaneId) -> LaneIngestIds:
    """Load stored ingest identifiers.

    Args:
        repo: Repository root.
        run_id: Run identifier.
        lane_id: Lane token.

    Returns:
        Lane ingest ids.
    """

    return read_model(lane_dir(repo, run_id, lane_id) / INGEST_IDS_NAME, LaneIngestIds)


def load_gold_map(repo: Path, run_id: str, lane_id: LaneId) -> GoldMap:
    """Load a stored gold map.

    Args:
        repo: Repository root.
        run_id: Run identifier.
        lane_id: Lane token.

    Returns:
        Gold map.
    """

    return read_model(lane_dir(repo, run_id, lane_id) / GOLD_MAP_NAME, GoldMap)


def load_chunk_summary(repo: Path, run_id: str, lane_id: LaneId) -> ChunkSummary:
    """Load a stored chunk summary.

    Args:
        repo: Repository root.
        run_id: Run identifier.
        lane_id: Lane token.

    Returns:
        Count-only summary.
    """

    return read_model(
        lane_dir(repo, run_id, lane_id) / CHUNK_SUMMARY_NAME, ChunkSummary
    )


def parse_lane_artifacts(
    repo: Path,
    manifest: BakeoffManifest,
    *,
    payload: bytes,
    lane_id: LaneId,
    use_docker: bool,
    converter: MarkdownConverter | None = None,
    resume: bool = False,
) -> tuple[ParseResult, ChunkSummary, LaneIngestIds]:
    """Parse one lane, replay for determinism, and write private artifacts.

    Args:
        repo: Repository root.
        manifest: Immutable run manifest.
        payload: Exact PDF bytes.
        lane_id: Lane token.
        use_docker: Production path uses Docker.
        converter: Optional in-process AnyDoc converter.
        resume: Reuse matching artifacts when hashes agree.

    Returns:
        Parse result, summary, and allocated ingest ids.

    Raises:
        BakeoffError: On hash mismatch or nondeterministic replay.
    """

    existing = parse_result_path(repo, manifest.run_id, lane_id)
    if resume and existing.is_file():
        result = load_parse_result(repo, manifest.run_id, lane_id)
        if result.content_hash != manifest.source_sha256:
            raise BakeoffError(
                "hash_mismatch", "resume parse hash does not match the manifest"
            )
        return (
            result,
            load_chunk_summary(repo, manifest.run_id, lane_id),
            load_ingest_ids(repo, manifest.run_id, lane_id),
        )
    request = LaneParseRequest(
        payload=payload,
        content_hash=manifest.source_sha256,
        filename=manifest.source_basename,
        media_type="application/pdf",
        lane_id=lane_id,
        run_id=manifest.run_id,
        use_docker=use_docker,
    )
    first = parse_lane(request, converter=converter)
    if first.content_hash != manifest.source_sha256:
        raise BakeoffError("hash_mismatch", "lane parse hash does not match the source")
    if first.disposition is not ParseDisposition.FAILED:
        second = parse_lane(request, converter=converter)
        if not replay_matches(first, second):
            raise BakeoffError("nondeterministic", "replay parse did not match")
        replay_ok = True
    else:
        replay_ok = True
    document_id = uuid4()
    version_id = uuid4()
    summary = summarize_parse_chunk(
        first,
        lane_id=lane_id,
        document_id=document_id,
        version_id=version_id,
        replay_matched=replay_ok,
    )
    if lane_id == ANYDOC_LANE and any(
        isinstance(element.locator, PdfLocator) for element in first.elements
    ):
        raise BakeoffError("fabricated_locator", "AnyDoc lane must not emit PdfLocator")
    ingest = LaneIngestIds(
        lane_id=lane_id,
        document_id=document_id,
        version_id=version_id,
        title=lane_document_title(manifest.run_id, lane_id),
        status="parsing",
        chunk_count=summary.chunk_count,
    )
    write_json_atomic(existing, first)
    write_json_atomic(
        lane_dir(repo, manifest.run_id, lane_id) / CHUNK_SUMMARY_NAME, summary
    )
    write_json_atomic(
        lane_dir(repo, manifest.run_id, lane_id) / INGEST_IDS_NAME, ingest
    )
    return first, summary, ingest


def update_manifest_lanes(
    repo: Path,
    manifest: BakeoffManifest,
    ingest_by_lane: dict[LaneId, LaneIngestIds],
    summaries: dict[LaneId, ChunkSummary],
    *,
    stage: RunStage,
) -> BakeoffManifest:
    """Stamp document/version ids and parser hashes onto the manifest.

    Args:
        repo: Repository root.
        manifest: Current manifest.
        ingest_by_lane: Allocated ids.
        summaries: Lane summaries.
        stage: New stage token.

    Returns:
        Rewritten manifest.
    """

    updated: list[LaneIdentity] = []
    for identity in manifest.lanes:
        ingest = ingest_by_lane.get(identity.lane_id)
        summary = summaries.get(identity.lane_id)
        updates: dict[str, object] = {}
        if ingest is not None:
            updates["ingest_document_id"] = ingest.document_id
            updates["ingest_version_id"] = ingest.version_id
            updates["bm25_job_id"] = ingest.bm25_job_id
        if summary is not None:
            updates["parser_version"] = summary.parser_version
            updates["cleaning_version"] = summary.cleaning_version
            updates["config_hash"] = summary.config_hash
            updates["locator_available"] = summary.locator_available
        updated.append(identity.model_copy(update=updates) if updates else identity)
    return save_manifest(
        repo,
        manifest.model_copy(update={"lanes": tuple(updated), "stage": stage}),
    )


def map_lane_gold(
    repo: Path,
    manifest: BakeoffManifest,
    cases: NeutralCaseSet,
    lane_id: LaneId,
) -> GoldMap:
    """Map neutral facts onto one lane's chunks and write review artifacts.

    Args:
        repo: Repository root.
        manifest: Run manifest.
        cases: Neutral case set.
        lane_id: Lane token.

    Returns:
        Unapproved gold map.

    Raises:
        BakeoffError: When parse or ingest artifacts are missing.
    """

    parse_result = load_parse_result(repo, manifest.run_id, lane_id)
    ingest = load_ingest_ids(repo, manifest.run_id, lane_id)
    chunking = chunk_parse_result(
        parse_result, document_id=ingest.document_id, version_id=ingest.version_id
    )
    mapping = map_facts_to_chunks(
        cases.cases,
        chunking.chunks,
        lane_id=lane_id,
        source_sha256=manifest.source_sha256,
        version_id=ingest.version_id,
    )
    write_json_atomic(lane_dir(repo, manifest.run_id, lane_id) / GOLD_MAP_NAME, mapping)
    pending = tuple(
        item for item in mapping.items if item.status is MappingStatus.REVIEW_REQUIRED
    )
    write_json_atomic(
        lane_dir(repo, manifest.run_id, lane_id) / MAPPING_REVIEW_NAME,
        {
            "lane_id": lane_id,
            "pending_count": review_pending_count(mapping),
            "items": [item.model_dump(mode="json") for item in pending],
        },
    )
    return mapping


def validate_lane_gold(
    repo: Path,
    run_id: str,
    lane_id: LaneId,
    *,
    reviewer: str,
    decisions: dict[tuple[str, int], tuple[UUID, ...]] | None = None,
    rejected: set[tuple[str, int]] | None = None,
) -> GoldMap:
    """Approve a gold map after human review of pending items.

    Args:
        repo: Repository root.
        run_id: Run identifier.
        lane_id: Lane token.
        reviewer: Named reviewer.
        decisions: Selected chunk ids for pending facts.
        rejected: Facts marked as extraction failures.

    Returns:
        Approved gold map.

    Raises:
        BakeoffError: When review remains incomplete.
    """

    mapping = load_gold_map(repo, run_id, lane_id)
    approved = apply_review(
        mapping,
        decisions=decisions or {},
        reviewer=reviewer,
        rejected=rejected,
    )
    write_json_atomic(lane_dir(repo, run_id, lane_id) / GOLD_MAP_NAME, approved)
    write_json_atomic(
        lane_dir(repo, run_id, lane_id) / MAPPING_REVIEW_NAME,
        {"lane_id": lane_id, "pending_count": 0, "items": []},
    )
    return approved


def identity_for(manifest: BakeoffManifest, lane_id: LaneId) -> LaneIdentity:
    """Return the lane identity from the manifest.

    Args:
        manifest: Run manifest.
        lane_id: Lane token.

    Returns:
        Lane identity.

    Raises:
        BakeoffError: When the lane is missing.
    """

    for identity in manifest.lanes:
        if identity.lane_id == lane_id:
            return identity
    raise BakeoffError("unknown_lane", "lane missing from manifest")


def require_stage(manifest: BakeoffManifest, minimum: RunStage) -> None:
    """Require that a prior stage has completed.

    Args:
        manifest: Run manifest.
        minimum: Required stage.

    Raises:
        BakeoffError: When the run has not reached the stage.
    """

    order = (
        RunStage.PREPARED,
        RunStage.PARSED,
        RunStage.INDEXED,
        RunStage.MAPPED,
        RunStage.GOLD_VALIDATED,
        RunStage.EVALUATED,
        RunStage.REPORTED,
    )
    if order.index(manifest.stage) < order.index(minimum):
        raise BakeoffError("stage_incomplete", f"run has not reached {minimum.value}")


def lane_report_paths(repo: Path, run_id: str, lane_id: LaneId) -> tuple[Path, Path]:
    """Return retrieval and agent report paths.

    Args:
        repo: Repository root.
        run_id: Run identifier.
        lane_id: Lane token.

    Returns:
        ``(retrieval_path, agent_path)``.
    """

    folder = lane_dir(repo, run_id, lane_id)
    return folder / RETRIEVAL_REPORT_NAME, folder / AGENT_REPORT_NAME


def reload_manifest(repo: Path, run_id: str) -> BakeoffManifest:
    """Reload the run manifest.

    Args:
        repo: Repository root.
        run_id: Run identifier.

    Returns:
        Manifest model.
    """

    return load_manifest(repo, run_id)


CURRENT_AND_ANYDOC: tuple[LaneId, ...] = (CURRENT_LANE, ANYDOC_LANE)
