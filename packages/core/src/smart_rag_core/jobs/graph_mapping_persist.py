"""Persistence helpers for canonical graph maps and Graph Ready."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from uuid import UUID

import psycopg

from smart_rag_core.ingestion.chunking.normalize import content_hash
from smart_rag_core.jobs.exceptions import GraphMappingError
from smart_rag_core.jobs.limits import GRAPH_PIPELINE_VERSION, GRAPH_POINTER_ID
from smart_rag_core.retrieval.graph import opaque_graph_source_basename
from smart_rag_core.retrieval.graph_mapping import (
    CanonicalPassage,
    ChunkMatch,
    CoverageSlice,
    EntityRuleView,
    ObjectMapping,
)
from smart_rag_core.schema.enums import DocumentStatus


def delete_version_maps(
    connection: psycopg.Connection,
    *,
    version_id: UUID,
    workspace_key: str,
) -> None:
    """Remove prior chunk and evidence rows for one version/workspace.

    Args:
        connection: ``app_worker`` connection inside the mapping txn.
        version_id: Canonical version being remapped.
        workspace_key: Application workspace.

    Side Effects:
        Deletes ``lightrag_chunk_map`` and ``graph_evidence_map`` rows.
    """

    with connection.cursor() as cursor:
        cursor.execute(
            """
            DELETE FROM app.lightrag_chunk_map
            WHERE version_id = %s AND workspace_key = %s
            """,
            (version_id, workspace_key),
        )
        cursor.execute(
            """
            DELETE FROM app.graph_evidence_map
            WHERE version_id = %s AND workspace_key = %s
            """,
            (version_id, workspace_key),
        )


def upsert_source_map(
    connection: psycopg.Connection,
    *,
    document_id: UUID,
    version_id: UUID,
    workspace_key: str,
    language: str,
    config_generation: str,
    source_identity: str,
    retrieval_eligible: bool = True,
) -> None:
    """Upsert the document-level source map row.

    Pending-switch maps are written ineligible and must not overwrite a live
    eligible row for a different current version.

    Args:
        connection: ``app_worker`` connection inside the mapping txn.
        document_id: Canonical document.
        version_id: Canonical version used as vendor id.
        workspace_key: Application workspace.
        language: Version language.
        config_generation: Mapping config digest.
        source_identity: Application source identity hash.
        retrieval_eligible: False until Packet 7 switch commits.
    """

    with connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO app.lightrag_source_map (
              document_id, lightrag_workspace, lightrag_doc_id, version_id,
              workspace_key, pipeline_version, config_generation,
              source_content_hash, language, method, score, support,
              source_hash, target_hash, provenance, retrieval_eligible
            )
            VALUES (
              %s, %s, %s, %s, %s, %s, %s, %s, %s, 'hash', 1.0, 1.0, %s, %s,
              %s::jsonb, %s
            )
            ON CONFLICT (document_id) DO UPDATE SET
              lightrag_workspace = EXCLUDED.lightrag_workspace,
              lightrag_doc_id = EXCLUDED.lightrag_doc_id,
              version_id = EXCLUDED.version_id,
              workspace_key = EXCLUDED.workspace_key,
              pipeline_version = EXCLUDED.pipeline_version,
              config_generation = EXCLUDED.config_generation,
              source_content_hash = EXCLUDED.source_content_hash,
              language = EXCLUDED.language,
              method = EXCLUDED.method,
              score = EXCLUDED.score,
              support = EXCLUDED.support,
              source_hash = EXCLUDED.source_hash,
              target_hash = EXCLUDED.target_hash,
              provenance = EXCLUDED.provenance,
              retrieval_eligible = EXCLUDED.retrieval_eligible,
              mapped_at = timezone('utc', now())
            WHERE app.lightrag_source_map.version_id
                    IS NOT DISTINCT FROM EXCLUDED.version_id
               OR app.lightrag_source_map.retrieval_eligible IS FALSE
            """,
            (
                document_id,
                workspace_key,
                str(version_id),
                version_id,
                workspace_key,
                GRAPH_PIPELINE_VERSION,
                config_generation,
                source_identity,
                language,
                source_identity,
                source_identity,
                json.dumps(
                    {
                        "basename": opaque_graph_source_basename(str(version_id)),
                        "config_generation": config_generation,
                    }
                ),
                retrieval_eligible,
            ),
        )


def insert_chunk_map(
    connection: psycopg.Connection,
    *,
    version_id: UUID,
    workspace_key: str,
    language: str,
    config_generation: str,
    vendor_chunk_id: str,
    internal_key: str,
    match: ChunkMatch,
    retrieval_eligible: bool = True,
) -> None:
    """Insert or replace one canonical chunk map row.

    Args:
        connection: ``app_worker`` connection.
        version_id: Canonical version.
        workspace_key: Application workspace.
        language: Version language.
        config_generation: Mapping config digest.
        vendor_chunk_id: Internal LightRAG chunk token.
        internal_key: Workspace-qualified chunk key.
        match: ``ChunkMatch`` with canonical passage and scores.
        retrieval_eligible: False until Packet 7 switch commits.
    """

    if not isinstance(match, ChunkMatch):
        raise TypeError("chunk_match_required")
    canonical = match.canonical
    with connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO app.lightrag_chunk_map (
              chunk_id, lightrag_doc_id, lightrag_chunk_id, version_id,
              workspace_key, pipeline_version, config_generation, language,
              method, score, support, source_hash, target_hash,
              source_span, target_span, provenance, retrieval_eligible
            )
            VALUES (
              %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
              %s::jsonb, %s::jsonb, %s::jsonb, %s
            )
            ON CONFLICT (chunk_id) DO UPDATE SET
              lightrag_doc_id = EXCLUDED.lightrag_doc_id,
              lightrag_chunk_id = EXCLUDED.lightrag_chunk_id,
              version_id = EXCLUDED.version_id,
              workspace_key = EXCLUDED.workspace_key,
              pipeline_version = EXCLUDED.pipeline_version,
              config_generation = EXCLUDED.config_generation,
              language = EXCLUDED.language,
              method = EXCLUDED.method,
              score = EXCLUDED.score,
              support = EXCLUDED.support,
              source_hash = EXCLUDED.source_hash,
              target_hash = EXCLUDED.target_hash,
              source_span = EXCLUDED.source_span,
              target_span = EXCLUDED.target_span,
              provenance = EXCLUDED.provenance,
              retrieval_eligible = EXCLUDED.retrieval_eligible,
              mapped_at = timezone('utc', now())
            """,
            (
                canonical.chunk_id,
                str(version_id),
                vendor_chunk_id,
                version_id,
                workspace_key,
                GRAPH_PIPELINE_VERSION,
                config_generation,
                language,
                match.method,
                match.score,
                match.score,
                match.source_hash,
                match.target_hash,
                json.dumps(match.source_span),
                json.dumps(match.target_span),
                json.dumps({"internal_chunk_key": internal_key}),
                retrieval_eligible,
            ),
        )


def insert_evidence_row(
    connection: psycopg.Connection,
    *,
    version_id: UUID,
    workspace_key: str,
    language: str,
    config_generation: str,
    item: ObjectMapping,
    retrieval_eligible: bool = True,
) -> None:
    """Insert one accepted evidence map row.

    Args:
        connection: ``app_worker`` connection.
        version_id: Canonical version.
        workspace_key: Application workspace.
        language: Version language.
        config_generation: Mapping config digest.
        item: Accepted object mapping with a chunk match.
        retrieval_eligible: False until Packet 7 switch commits.
    """

    if not item.available or item.chunk_id is None or item.match is None:
        return
    match = item.match
    with connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO app.graph_evidence_map (
              graph_object_type, graph_object_id, chunk_id, confidence,
              version_id, workspace_key, pipeline_version, config_generation,
              language, method, score, support, source_hash, target_hash,
              source_span, target_span, provenance, retrieval_eligible
            )
            VALUES (
              %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
              %s::jsonb, %s::jsonb, %s::jsonb, %s
            )
            ON CONFLICT (graph_object_type, graph_object_id, chunk_id) DO UPDATE SET
              confidence = EXCLUDED.confidence,
              version_id = EXCLUDED.version_id,
              workspace_key = EXCLUDED.workspace_key,
              pipeline_version = EXCLUDED.pipeline_version,
              config_generation = EXCLUDED.config_generation,
              language = EXCLUDED.language,
              method = EXCLUDED.method,
              score = EXCLUDED.score,
              support = EXCLUDED.support,
              source_hash = EXCLUDED.source_hash,
              target_hash = EXCLUDED.target_hash,
              source_span = EXCLUDED.source_span,
              target_span = EXCLUDED.target_span,
              provenance = EXCLUDED.provenance,
              retrieval_eligible = EXCLUDED.retrieval_eligible,
              mapped_at = timezone('utc', now())
            """,
            (
                item.object_type,
                item.object_id,
                item.chunk_id,
                match.score,
                version_id,
                workspace_key,
                GRAPH_PIPELINE_VERSION,
                config_generation,
                language,
                match.method,
                match.score,
                match.score,
                match.source_hash,
                match.target_hash,
                json.dumps(match.source_span),
                json.dumps(match.target_span),
                json.dumps(item.provenance),
                retrieval_eligible,
            ),
        )


def insert_telemetry(
    connection: psycopg.Connection,
    *,
    document_id: UUID,
    version_id: UUID,
    workspace_key: str,
    config_generation: str,
    coverage: Sequence[CoverageSlice],
) -> None:
    """Persist per-language mapping numerators and exclusions.

    Args:
        connection: ``app_worker`` connection.
        document_id: Canonical document.
        version_id: Canonical version.
        workspace_key: Application workspace.
        config_generation: Mapping config digest.
        coverage: Coverage slices for this mapping run.
    """

    with connection.cursor() as cursor:
        for slice_row in coverage:
            cursor.execute(
                """
                INSERT INTO app.graph_mapping_telemetry (
                  document_id, version_id, workspace_key, language, object_type,
                  method, truncation_count, failure_reason, numerator,
                  denominator, exclusion_count, pipeline_version, config_generation
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    document_id,
                    version_id,
                    workspace_key,
                    slice_row.language,
                    slice_row.object_type,
                    slice_row.method,
                    slice_row.truncation_count,
                    slice_row.failure_reason or None,
                    slice_row.numerator,
                    slice_row.denominator,
                    slice_row.exclusion_count,
                    GRAPH_PIPELINE_VERSION,
                    config_generation,
                ),
            )


def insert_repairs(
    connection: psycopg.Connection,
    *,
    document_id: UUID,
    version_id: UUID,
    workspace_key: str,
    config_generation: str,
    repairs: Sequence[Mapping[str, str]],
) -> None:
    """Upsert bounded repair jobs keyed by workspace/object/config.

    Args:
        connection: ``app_worker`` connection.
        document_id: Canonical document.
        version_id: Canonical version.
        workspace_key: Application workspace.
        config_generation: Mapping config digest.
        repairs: Unavailable-object diagnostics.
    """

    with connection.cursor() as cursor:
        for item in repairs:
            cursor.execute(
                """
                INSERT INTO app.graph_map_repair_jobs (
                  workspace_key, document_id, version_id, graph_object_type,
                  graph_object_id, map_kind, config_generation, reason
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (
                  workspace_key, graph_object_type, graph_object_id,
                  map_kind, config_generation
                ) DO UPDATE SET
                  reason = EXCLUDED.reason,
                  status = 'pending'::app.job_status,
                  updated_at = timezone('utc', now())
                """,
                (
                    workspace_key,
                    document_id,
                    version_id,
                    item["object_type"],
                    item["object_id"],
                    item["map_kind"],
                    config_generation,
                    item["reason"][:512],
                ),
            )


def mark_version_graph_ready(
    connection: psycopg.Connection,
    *,
    version_id: UUID,
) -> None:
    """Set ``document_versions.status`` to Graph Ready in the mapping txn.

    Args:
        connection: ``app_worker`` connection.
        version_id: Version that passed every mapping gate.

    Raises:
        GraphMappingError: If the row is no longer ``graph_pending``.
    """

    with connection.cursor() as cursor:
        cursor.execute(
            """
            UPDATE app.document_versions
            SET
              status = 'graph_ready'::app.document_status,
              updated_at = timezone('utc', now())
            WHERE id = %s
              AND status = 'graph_pending'::app.document_status
            """,
            (version_id,),
        )
        if cursor.rowcount != 1:
            raise GraphMappingError("version_status_drift")


def load_eligibility_reason(
    connection: psycopg.Connection,
    *,
    document_id: UUID,
    version_id: UUID,
) -> str | None:
    """Recheck current/eligibility/config before Graph Ready.

    Args:
        connection: ``app_worker`` connection.
        document_id: Canonical document.
        version_id: Canonical version.

    Returns:
        Failure reason, or ``None`` when eligible.
    """

    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT
              dv.status,
              dv.hybrid_verified_at,
              dv.graph_eligible,
              dv.deleted_at,
              d.graph_eligible,
              d.deleted_at,
              d.current_version_id
            FROM app.document_versions AS dv
            JOIN app.documents AS d ON d.id = dv.document_id
            WHERE dv.id = %s AND d.id = %s
            """,
            (version_id, document_id),
        )
        row = cursor.fetchone()
    if row is None:
        return "version_missing"
    status, hybrid_at, version_elig, version_deleted, doc_elig, doc_deleted, current = (
        row
    )
    if str(status) != DocumentStatus.GRAPH_PENDING.value:
        return "version_status_drift"
    if hybrid_at is None:
        return "hybrid_not_ready"
    if version_deleted is not None or doc_deleted is not None:
        return "deleted"
    if not version_elig or not doc_elig:
        return "not_graph_eligible"
    if current is None or UUID(str(current)) != version_id:
        return "pending_switch"
    return None


def load_canonical_passages(
    connection: psycopg.Connection,
    *,
    version_id: UUID,
) -> tuple[CanonicalPassage, ...]:
    """Load canonical chunks for one version using the ingest content hash.

    Args:
        connection: ``app_worker`` connection.
        version_id: Canonical version.

    Returns:
        Passages for hash/span/overlap and Hybrid support.
    """

    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT
              dc.id,
              dc.version_id,
              dc.document_id,
              dc.chunk_index,
              dc.raw_text,
              dc.content_hash,
              dv.language
            FROM app.document_chunks AS dc
            JOIN app.document_versions AS dv ON dv.id = dc.version_id
            WHERE dc.version_id = %s
              AND dc.deleted_at IS NULL
            ORDER BY dc.chunk_index
            """,
            (version_id,),
        )
        rows = cursor.fetchall()
    passages: list[CanonicalPassage] = []
    for row in rows:
        raw_text = str(row[4])
        stored_hash = str(row[5]) if row[5] is not None else ""
        digest = stored_hash or content_hash(raw_text)
        passages.append(
            CanonicalPassage(
                chunk_id=UUID(str(row[0])),
                version_id=UUID(str(row[1])),
                document_id=UUID(str(row[2])),
                chunk_index=int(row[3]),
                raw_text=raw_text,
                content_hash=digest,
                language=str(row[6] or ""),
            )
        )
    return tuple(passages)


def load_entity_rules(connection: psycopg.Connection) -> tuple[EntityRuleView, ...]:
    """Load approved, currently effective entity rules.

    Suggested and revoked rows are ignored. Unresolved names stay separate.
    Hybrid aliases are never copied from LightRAG.

    Args:
        connection: ``app_worker`` connection.

    Returns:
        Active approved rule views.
    """

    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT
              entity_type,
              canonical_name,
              aliases,
              do_not_merge,
              languages,
              relation_label_policy::text,
              status::text,
              rule
            FROM app.graph_entity_rules
            WHERE status = 'approved'::app.graph_entity_rule_status
              AND active IS TRUE
              AND (
                effective_from IS NULL
                OR effective_from <= timezone('utc', now())
              )
              AND (
                effective_until IS NULL
                OR effective_until > timezone('utc', now())
              )
            """
        )
        rows = cursor.fetchall()
    views: list[EntityRuleView] = []
    for row in rows:
        (
            entity_type,
            canonical_name,
            aliases_raw,
            blocked_raw,
            languages_raw,
            relation_policy,
            status,
            raw_rule,
        ) = row
        rule = raw_rule if isinstance(raw_rule, dict) else {}
        aliases = tuple(
            str(item) for item in (aliases_raw or rule.get("aliases", []) or []) if item
        )
        blocked = tuple(
            str(item)
            for item in (blocked_raw or rule.get("do_not_merge", []) or [])
            if item
        )
        languages = tuple(str(item) for item in (languages_raw or []) if item)
        canonical = canonical_name or rule.get("canonical_name")
        views.append(
            EntityRuleView(
                entity_type=str(entity_type),
                canonical_name=str(canonical) if canonical else None,
                aliases=aliases,
                do_not_merge=blocked,
                languages=languages,
                relation_label_policy=str(relation_policy or "directed"),
                status=str(status or "approved"),
            )
        )
    return tuple(views)


def load_pointer_workspace_id(connection: psycopg.Connection) -> UUID | None:
    """Return the singleton active pointer workspace, or ``None``.

    Args:
        connection: ``app_worker`` connection.

    Returns:
        Attached workspace UUID, or ``None`` when the pointer is empty.
    """

    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT workspace_id
            FROM app.graph_active_workspace_pointer
            WHERE id = %s::uuid
            """,
            (GRAPH_POINTER_ID,),
        )
        row = cursor.fetchone()
    if row is None or row[0] is None:
        return None
    return UUID(str(row[0]))


def load_workspace_uuid(
    connection: psycopg.Connection,
    *,
    workspace_key: str,
) -> UUID:
    """Return the workspace row id for a key.

    Args:
        connection: ``app_worker`` connection.
        workspace_key: Application workspace key.

    Returns:
        Workspace UUID.

    Raises:
        GraphMappingError: If the workspace row is missing.
    """

    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT id
            FROM app.graph_workspaces
            WHERE workspace_key = %s
            """,
            (workspace_key,),
        )
        row = cursor.fetchone()
    if row is None:
        raise GraphMappingError("workspace_missing")
    return UUID(str(row[0]))
